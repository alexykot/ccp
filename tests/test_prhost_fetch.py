"""A PR's head fetched through the PR-host module (ADR-0040 D1, E19): `prhost.fetch_commit` tries the adapter's own
refs for the PR, then the task branch, on a fenced bare origin. Only the GitHub adapter has refs of its own. The
three steps that need a head (`behind_tip`, the resolution gate, the fix judgement) fetch it through it, with the
PR and the task's branch."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccp import lifecycle, prhost, prompt, verify
from ccp.queue import QueueError
from tests.helpers import Product
from tests.test_toolkit import GIT_ENV, git

TID = "0001-a"
BRANCH = f"task/{TID}"
PR = "7"


class Origin:
    """A fenced bare origin with a main, a clone elsewhere that pushes to it, and checkouts of its main."""

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

    def pushed(self, ref: str, name: str, on: str = "main") -> str:
        """A new commit on `on`, pushed to `ref` on origin only, never to main: its sha."""
        git(self.elsewhere, "checkout", "-q", "--detach", on)
        git(self.elsewhere, "commit", "-q", "--allow-empty", "-m", name)
        sha = git(self.elsewhere, "rev-parse", "HEAD")
        git(self.elsewhere, "push", "-q", "origin", f"HEAD:{ref}")
        return sha

    def has(self, p: Product, sha: str) -> bool:
        """Whether `sha` is a commit in `p`'s checkout."""
        r = subprocess.run(["git", "-C", str(p.root), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True,
                           env={**os.environ, **GIT_ENV})
        return r.returncode == 0


class FetchCommit(Origin, unittest.TestCase):
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


class EachStepFetchesItsHead(Origin, unittest.TestCase):
    """Each step that needs a head not in its checkout fetches it from the PR's own ref, or from the task's branch
    when the PR has no such ref: under the GitHub adapter, a head only on either is in the checkout after the step."""

    REFS = (f"refs/pull/{PR}/head", f"refs/heads/{BRANCH}")  # a message per ref: one origin, and git's dates are fixed

    def test_behind_tip_fetches_the_head(self):
        for ref in self.REFS:
            with self.subTest(ref=ref):
                p = self.product("github")
                head = self.pushed(ref, f"head on {ref}")
                self.assertEqual(lifecycle.behind_tip(p.cfg, PR, TID, head, "main"), [])
                self.assertTrue(self.has(p, head))

    def test_the_resolution_gate_fetches_the_head(self):
        for ref in self.REFS:
            with self.subTest(ref=ref):
                p = self.product("github")
                head = self.pushed(ref, f"head on {ref}")
                q = p.root / "queue"
                review = {"run_id": f"{TID}/review", "phase": "review", "opened_at": "2026-11-22T10:00:00Z",
                          "reported_at": "2026-11-22T10:30:00Z", "outcome": "done"}
                p.write(f"queue/runs/{TID}/review.json", json.dumps(review))
                a = SimpleNamespace(mode="resolution", head=head, pr=PR)
                with self.assertRaises(QueueError):  # fetched, then refused: the head is not a merge commit
                    prompt.resolution_gate(p.cfg, q, TID, "review", a)
                self.assertTrue(self.has(p, head))

    def test_the_fix_judgement_fetches_the_reviewed_head_and_the_head(self):
        for ref in self.REFS:
            with self.subTest(ref=ref):
                p = self.product("github")
                reviewed = self.pushed(ref, f"reviewed on {ref}")
                head = self.pushed(ref, f"head on {ref}", on=reviewed)
                tip = git(p.root, "rev-parse", "origin/main")
                verify._judge_fix(p.cfg, p.root / "queue", TID, reviewed, head, PR, f"{TID}/fix", None, [], "main",
                                  tip)
                self.assertEqual((self.has(p, reviewed), self.has(p, head)), (True, True))


if __name__ == "__main__":
    unittest.main()
