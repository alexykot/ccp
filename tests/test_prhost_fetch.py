"""A PR's head fetched through the PR-host module (ADR-0040 D1, E19): `prhost.fetch_commit` tries the adapter's own
refs for the PR, then the task branch, on a fenced bare origin. Only the GitHub adapter has refs of its own."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import prhost
from tests.helpers import Product
from tests.test_toolkit import GIT_ENV, git

BRANCH = "task/0001-a"
PR = "7"


class FetchCommit(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        t = Path(tmp.name)
        self.origin = t / "origin.git"
        git(t, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.elsewhere = t / "elsewhere"
        git(t, "clone", "-q", str(self.origin), str(self.elsewhere))
        git(self.elsewhere, "checkout", "-q", "-b", "main")
        git(self.elsewhere, "commit", "-q", "--allow-empty", "-m", "init")
        git(self.elsewhere, "push", "-q", "origin", "main")

    def product(self, adapter: str) -> Product:
        """A checkout of origin's main whose plane.json names `adapter`."""
        p = Product({"pr_host": {"adapter": adapter}})
        self.addCleanup(p.cleanup)
        git(p.root, "init", "-q", "-b", "main")
        git(p.root, "remote", "add", "origin", str(self.origin))
        git(p.root, "fetch", "-q", "origin", "main")
        return p

    def pushed(self, ref: str, name: str) -> str:
        """A new commit pushed to `ref` on origin only, never to main: its sha."""
        git(self.elsewhere, "checkout", "-q", "--detach", "main")
        git(self.elsewhere, "commit", "-q", "--allow-empty", "-m", name)
        sha = git(self.elsewhere, "rev-parse", "HEAD")
        git(self.elsewhere, "push", "-q", "origin", f"HEAD:{ref}")
        return sha

    def fetches(self, p: Product, sha: str, pr: str | None) -> tuple[bool, list[str]]:
        """fetch_commit's answer, and each ref it fetched."""
        with mock.patch.object(prhost, "_run", wraps=prhost._run) as run:
            got = prhost.fetch_commit(p.cfg, p.root, sha, pr, BRANCH)
        refs = [c.args[1][-1] for c in run.call_args_list if "fetch" in c.args[1]]
        return got, refs

    def test_under_github_a_commit_only_on_the_prs_own_ref_is_fetched(self):
        p = self.product("github")
        sha = self.pushed(f"refs/pull/{PR}/head", "pr head")
        got, refs = self.fetches(p, sha, PR)
        self.assertTrue(got)
        self.assertEqual(refs, [f"refs/pull/{PR}/head"])
        self.assertEqual(git(p.root, "cat-file", "-t", sha), "commit")

    def test_under_local_a_commit_only_on_the_task_branch_is_fetched_and_no_pr_ref_is_tried(self):
        p = self.product("local")
        sha = self.pushed(f"refs/heads/{BRANCH}", "branch head")
        got, refs = self.fetches(p, sha, PR)
        self.assertTrue(got)
        self.assertEqual(refs, [BRANCH])

    def test_under_local_a_commit_only_on_a_pull_ref_is_not_found(self):
        p = self.product("local")
        sha = self.pushed(f"refs/pull/{PR}/head", "pr head")
        self.assertEqual(self.fetches(p, sha, PR), (False, [BRANCH]))

    def test_without_a_pr_only_the_branch_is_tried(self):
        sha = self.pushed(f"refs/heads/{BRANCH}", "branch head")
        for pr in (None, ""):
            with self.subTest(pr=pr):
                self.assertEqual(self.fetches(self.product("github"), sha, pr), (True, [BRANCH]))

    def test_a_commit_already_here_fetches_nothing(self):
        p = self.product("github")
        sha = git(p.root, "rev-parse", "origin/main")
        self.assertEqual(self.fetches(p, sha, PR), (True, []))

    def test_a_commit_on_neither_ref_is_false(self):
        p = self.product("github")
        self.pushed(f"refs/pull/{PR}/head", "pr head")
        self.pushed(f"refs/heads/{BRANCH}", "branch head")
        git(self.elsewhere, "commit", "-q", "--allow-empty", "-m", "never pushed")
        sha = git(self.elsewhere, "rev-parse", "HEAD")
        self.assertEqual(self.fetches(p, sha, PR), (False, [f"refs/pull/{PR}/head", BRANCH]))


if __name__ == "__main__":
    unittest.main()
