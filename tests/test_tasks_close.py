"""`ccp tasks close` reconciles in a worktree of its own (SPEC §10.5): the checkout it runs from, the
product's main checkout included, keeps its branch, HEAD and index."""
from __future__ import annotations

import json
import unittest

from tests.test_toolkit import ToolkitFixture, git


class CloseKeepsTheCaller(ToolkitFixture, unittest.TestCase):

    def _state(self, checkout):
        return (git(checkout, "rev-parse", "HEAD"), git(checkout, "symbolic-ref", "-q", "--short", "HEAD")
                if checkout == self.main else None, git(checkout, "status", "--porcelain"))

    def test_close_from_the_main_checkout_leaves_it_on_its_branch_at_its_head(self):
        self._to_approved_pr()
        before = self._state(self.main)
        self.assertEqual(before[1:], ("main", ""))
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._state(self.main), before)
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(git(self.main, "rev-parse", "origin/main"), body["reconcile_sha"])
        self.assertTrue(git(self.main, "log", "-1", "--format=%s", "origin/main").startswith("Reconcile 0002"))
        self.assertIn("status: done", git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md"))
        self.assertFalse((self.main / ".rt" / "merge-0002").exists())

    def test_close_from_the_runner_worktree_ends_it_at_the_reconcile_and_leaves_the_main_checkout(self):
        self._to_approved_pr()
        main_before = self._state(self.main)
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._state(self.runner), (body["reconcile_sha"], None, ""))
        self.assertEqual(self._state(self.main), main_before)
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(git(self.main, "rev-parse", "origin/main"), body["reconcile_sha"])
        self.assertNotIn("merge-0002", git(self.main, "worktree", "list"))

    def test_a_failed_reconcile_is_discarded_by_the_rerun_in_the_merge_worktree(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = ["touch hook-ran && exit 3"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a failing hook")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        git(self.main, "pull", "-q", "origin", "main")
        self._to_approved_pr()
        before = self._state(self.main)
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self._state(self.main), before)
        merge_wt = self.main / ".rt" / "merge-0002"
        self.assertTrue((merge_wt / "hook-ran").exists())  # the half-done reconcile is in close's own worktree
        cfg["reconcile"]["hooks"] = []
        (self.main / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.main, "commit", "-qam", "the hook fixed")
        git(self.main, "pull", "-q", "--rebase", "origin", "main")
        git(self.main, "push", "-q", "origin", "main")
        before = self._state(self.main)
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["merged_now"])
        self.assertTrue(body["reconciled_now"])
        self.assertEqual(self._state(self.main), before)
        self.assertEqual(body["committed"].count("hook-ran"), 0)
        self.assertFalse(merge_wt.exists())

    def test_a_detached_main_checkout_keeps_its_head_too(self):
        self._to_approved_pr()
        git(self.main, "checkout", "-q", "--detach")
        before = (git(self.main, "rev-parse", "HEAD"), git(self.main, "status", "--porcelain"))
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((git(self.main, "rev-parse", "HEAD"), git(self.main, "status", "--porcelain")), before)
        self.assertNotEqual(before[0], body["reconcile_sha"])

    def test_a_merge_worktree_path_taken_by_something_else_stops_the_reconcile_and_touches_nothing(self):
        self._to_approved_pr()
        (self.main / ".rt" / "merge-0002").mkdir(parents=True)
        (self.main / ".rt" / "merge-0002" / "keep.txt").write_text("not ours\n")
        before = self._state(self.main)
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 1, out + err)
        self.assertIn("merge-0002", err)
        self.assertEqual(self._state(self.main), before)
        self.assertEqual((self.main / ".rt" / "merge-0002" / "keep.txt").read_text(), "not ours\n")
        self.assertFalse(git(self.main, "log", "-1", "--format=%s", "origin/main").startswith("Reconcile"))

    def test_without_a_worktrees_dir_the_reconcile_is_made_in_the_checkout_close_runs_from(self):
        cwd = self.main.parent / "hook-cwd"
        self._to_approved_pr()
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["adapter"].pop("worktree_dir")
        cfg["reconcile"]["hooks"] = [f"pwd -P > {cwd}"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "no worktrees dir")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(cwd.read_text().strip(), str(self.runner.resolve()))
        self.assertEqual(git(self.runner, "rev-parse", "HEAD"), body["reconcile_sha"])

    def test_the_reconcile_hooks_run_in_the_merge_worktree(self):
        cwd = self.main.parent / "hook-cwd"
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = [f"pwd -P > {cwd}"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a hook that notes its directory")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        self._to_approved_pr()
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(cwd.read_text().strip(), str((self.main / ".rt" / "merge-0002").resolve()))


if __name__ == "__main__":
    unittest.main()
