"""ccp tasks orphans (SPEC §10.7): integration-branch commits since a ref that no task covers."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, health
from tests.helpers import TASK, Product


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                          capture_output=True, text=True).stdout.strip()


def covering(tid: str, shas: list[str], status: str = "pending") -> str:
    """A task file whose frontmatter names merged commits in `covers:`."""
    text = TASK.format(tid=tid, title="After the fact", status=status, deps="", ver="*Append-only.*")
    return text.replace("spec_refs:", "covers: [" + ", ".join(f'"{s}"' for s in shas) + "]\nspec_refs:", 1)


class Orphans(unittest.TestCase):
    def setUp(self):
        self.p = Product({"reconcile": {"log": {"path": "docs/log.md", "entry": "- {task_id}"}}})
        self.p.task("0001-t1")
        self.p.task("0002-t2")
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", "init")
        self.base = git(self.p.root, "rev-parse", "HEAD")

    def tearDown(self):
        self.p.cleanup()

    def change(self, msg: str, *files: str) -> str:
        for f in files:
            p = self.p.root / f
            self.p.write(f, (p.read_text() if p.exists() else "") + "x\n")
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", msg)
        return git(self.p.root, "rev-parse", "HEAD")

    def task_merges(self) -> None:
        """Task 0001 by squash and its reconcile; task 0002 by a merge commit of its branch and its reconcile."""
        sq = self.change("Task 0001: the first thing (#1)", "app/a.py")
        self.change(f"Reconcile 0001: done (PR #1, squash {sq[:7]})", "docs/delivery/tasks/0001-t1.md",
                    "docs/delivery/INDEX.yaml", "docs/log.md", "app/hook-output.txt")
        git(self.p.root, "checkout", "-q", "-b", "task/0002-t2")
        self.change("work on it", "app/b.py")
        git(self.p.root, "checkout", "-q", "main")
        git(self.p.root, "-c", "user.email=t@t", "-c", "user.name=t", "merge", "-q", "--no-ff",
            "-m", "Merge pull request #2 from me/task/0002-t2", "task/0002-t2")
        merge = git(self.p.root, "rev-parse", "HEAD")
        self.change(f"Reconcile 0002: done (PR #2, squash {merge[:7]})", "docs/delivery/tasks/0002-t2.md")

    def orphans(self, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "tasks", "orphans", "--since", self.base, *extra])
        return code, out.getvalue(), err.getvalue()

    def listed(self) -> list[str]:
        code, out, _ = self.orphans("--json")
        shas = [c["sha"] for c in json.loads(out)["uncovered"]]
        self.assertEqual(code, 1 if shas else 0)
        return shas

    def test_an_outside_commit_is_listed_until_a_task_covers_it(self):
        self.task_merges()
        outside = self.change("quick fix from elsewhere", "app/a.py")
        code, out, _ = self.orphans()
        self.assertEqual(code, 1)
        self.assertIn(outside[:7], out.split())
        self.p.write("docs/delivery/tasks/0003-after.md", covering("0003-after", [outside[:7]]))
        self.change("Add task 0003", "docs/delivery/tasks/0003-after.md")
        self.assertEqual(self.listed(), [])

    def test_task_merges_and_their_reconciles_are_not_listed(self):
        self.task_merges()
        code, out, err = self.orphans("--json")
        self.assertEqual((code, json.loads(out)["uncovered"], err), (0, [], ""))

    def test_a_non_task_pull_request_is_listed(self):
        sha = self.change("Lead's config change (#7)", "config/settings.txt")
        self.assertEqual(self.listed(), [sha])

    def test_a_commit_naming_an_unknown_task_or_a_lookalike_reconcile_is_listed(self):
        a = self.change("Task 0009: not in the log (#3)", "app/a.py")
        b = self.change("Reconcile 0009: done (PR #3, squash abcdef1)", "app/a.py")
        c = self.change("Reconcile 0001 done", "app/a.py")
        d = self.change("0001 notes on the plan (#4)", "app/a.py")
        e = self.change("task 0002 and more (#5)", "app/a.py")
        self.assertEqual(self.listed(), [a, b, c, d, e])

    def test_a_task_log_only_commit_is_not_listed_and_one_beyond_it_is(self):
        self.change("Add a task", "docs/delivery/tasks/0001-t1.md", "docs/delivery/INDEX.yaml", "docs/log.md")
        beyond = self.change("Add a task and a doc", "docs/delivery/tasks/0002-t2.md", "docs/guide.md")
        self.assertEqual(self.listed(), [beyond])

    def test_covers_takes_a_full_sha_and_a_dropped_task_covers_nothing(self):
        a = self.change("outside one", "app/a.py")
        b = self.change("outside two", "app/b.py")
        self.p.write("docs/delivery/tasks/0003-after.md", covering("0003-after", [a]))
        self.p.write("docs/delivery/tasks/0004-gone.md", covering("0004-gone", [b[:10]], status="dropped"))
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", "Add tasks 0003 and 0004")
        self.assertEqual(self.listed(), [b])

    def test_a_covers_entry_that_is_not_a_sha_warns(self):
        a = self.change("outside", "app/a.py")
        self.p.write("docs/delivery/tasks/0003-after.md", covering("0003-after", ["123", "the fix"]))
        code, out, err = self.orphans()
        self.assertEqual(code, 1)
        self.assertIn(a[:7], out.split())
        self.assertEqual(err.count("warning: 0003-after: covers"), 2)

    def test_a_merged_branch_of_outside_work_is_one_commit(self):
        git(self.p.root, "checkout", "-q", "-b", "side")
        inner = self.change("side work", "app/c.py")
        git(self.p.root, "checkout", "-q", "main")
        git(self.p.root, "-c", "user.email=t@t", "-c", "user.name=t", "merge", "-q", "--no-ff", "-m", "Merge side", "side")
        merge = git(self.p.root, "rev-parse", "HEAD")
        shas = self.listed()
        self.assertEqual(shas, [merge])
        self.assertNotIn(inner, shas)

    def test_a_ref_that_does_not_resolve_is_a_usage_error(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "tasks", "orphans", "--since", "no-such-ref"])
        self.assertEqual(code, 2)
        self.assertIn("no-such-ref", err.getvalue())

    def test_the_tip_is_origin_when_present_else_the_binding_branch(self):
        seen = self.change("on main, not yet on origin", "app/a.py")
        git(self.p.root, "update-ref", "refs/remotes/origin/main", self.base)
        self.assertEqual(self.listed(), [])
        git(self.p.root, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(self.listed(), [seen])
        git(self.p.root, "checkout", "-q", "-b", "trunk")
        other = self.change("only on trunk", "app/b.py")
        git(self.p.root, "checkout", "-q", "main")
        with tempfile.TemporaryDirectory() as qd:
            (Path(qd) / "project.yaml").write_text("project_id: demo\nintegration_branch: trunk\n")
            with mock.patch.dict(os.environ, {"QUEUE_ROOT": qd}):
                self.assertEqual(health.integration_tip(self.p.cfg, Path(qd)), "trunk")
                self.assertEqual(self.listed(), [seen, other])


if __name__ == "__main__":
    unittest.main()
