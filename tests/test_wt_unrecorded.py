"""The plane's unrecorded worktrees (SPEC §12.1): made with `wt.add_unrecorded`, removed with
`wt.remove_unrecorded` (close's own `merge-<nnnn>` too, by close or gc, with a warning when that fails), and an
architect pass's `arch-<review id>` listed by `ccp wt list`."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from ccp import architect, config, wt
from ccp.queue import QueueError
from tests.toolkit_fixture import ToolkitFixture, git


class ArchName(unittest.TestCase):
    def test_both_review_id_kinds_name_an_arch_worktree(self):
        for mode in ("pass", "shape"):
            with self.subTest(mode=mode):
                self.assertRegex(f"{wt.ARCH_PREFIX}-{architect._new_rid(mode)}", wt.ARCH_RE)

    def test_a_name_without_a_review_id_is_not_one(self):
        for name in (wt.ARCH_PREFIX, f"{wt.ARCH_PREFIX}-x", f"{wt.ARCH_PREFIX}-0002", f"{wt.MERGE_PREFIX}-0002",
                     f"{wt.ARCH_PREFIX}-sm-20261121T000000Z-abcd"):  # a spec question's id, not a pass's
            with self.subTest(name=name):
                self.assertNotRegex(name, wt.ARCH_RE)


class Unrecorded(ToolkitFixture, unittest.TestCase):
    RID = "ar-20261121T000000Z-abcd"

    def setUp(self):
        super().setUp()
        self.cfg = config.load(self.main)
        self.path = wt.base_dir(self.cfg) / f"{wt.ARCH_PREFIX}-{self.RID}"
        self.head = git(self.main, "rev-parse", "origin/main")

    def listed(self, *args: str) -> list[dict]:
        code, _, body, err = self.ccp("wt", "list", *args, root=self.main)
        self.assertEqual(code, 0, body + err)
        return json.loads(body)

    def registered(self) -> str:
        return git(self.main, "worktree", "list", "--porcelain")

    def test_it_is_detached_at_the_rev_with_the_links_linked_in(self):
        wt.add_unrecorded(self.cfg, self.main, self.path, self.head)
        self.assertEqual(git(self.path, "rev-parse", "HEAD"), self.head)
        self.assertEqual(git(self.path, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")
        for one in self.cfg.worktrees["links"]:
            self.assertTrue((self.path / one).is_symlink(), one)
            self.assertEqual((self.path / one).resolve(), (self.main / one).resolve())
        self.assertEqual(wt.records(self.q), [])  # not recorded

    def test_the_worktree_directory_is_excluded_when_the_gitignore_lacks_it(self):
        self.write(".gitignore", ".venv/\nclosed-*\n")
        git(self.main, "commit", "-qam", "drop the runtime ignore line")
        wt.add_unrecorded(self.cfg, self.main, self.path, self.head)
        self.assertEqual(git(self.main, "status", "--porcelain"), "")

    def test_a_git_error_raises_naming_the_path(self):
        with self.assertRaises(QueueError) as cm:
            wt.add_unrecorded(self.cfg, self.main, self.path, "no-such-rev")
        self.assertIn(str(self.path), str(cm.exception))
        self.assertFalse(self.path.exists())

    def test_a_left_arch_worktree_is_listed_unrecorded_with_no_task(self):
        wt.add_unrecorded(self.cfg, self.main, self.path, self.head)
        rows = [r for r in self.listed() if r["name"] == self.path.name]
        self.assertEqual(rows, [{"name": self.path.name, "kind": wt.ARCH_PREFIX, "path": str(self.path),
                                 "exists": True, "recorded": False}])
        self.assertNotIn(self.path.name, [r["name"] for r in self.listed("--task", "0002")])

    def test_remove_unrecorded_removes_and_prunes_and_a_second_call_is_quiet(self):
        wt.add_unrecorded(self.cfg, self.main, self.path, self.head)
        wt.remove_unrecorded(self.main, self.path)
        self.assertFalse(self.path.exists())
        self.assertNotIn(self.path.name, self.registered())
        self.assertNotIn(self.path.name, [r["name"] for r in self.listed()])
        wt.remove_unrecorded(self.main, self.path)  # gone already: nothing raises

    def test_remove_unrecorded_returns_none_when_it_removes_and_git_s_text_when_git_cannot(self):
        wt.add_unrecorded(self.cfg, self.main, self.path, self.head)
        self.assertIsNone(wt.remove_unrecorded(self.main, self.path))
        err = wt.remove_unrecorded(self.main, self.path)  # gone: git has no such worktree
        self.assertIsNotNone(err)
        self.assertIn(str(self.path), err)

    def test_close_warns_when_removing_its_merge_worktree_fails(self):
        self._to_approved_pr()
        with mock.patch.object(wt, "remove_unrecorded", return_value="it is locked"):
            code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR, "--summary", "it is built.")
        self.assertEqual(code, 0, out + err)
        own = wt.merge_path(self.cfg, "0002-second")
        self.assertIn(f"merge worktree {own}: it is locked", body["warnings"])

    def test_gc_warns_when_removing_a_leftover_merge_worktree_fails(self):
        own = self.path.with_name(f"{wt.MERGE_PREFIX}-0002")
        wt.add_unrecorded(self.cfg, self.main, own, self.head)
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps({"task_id": "0002-second", "status": "done"}))
        with mock.patch.object(wt, "remove_unrecorded", return_value="it is locked"):
            code, body, out, err = self.ccp("wt", "gc", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["warnings"], [f"worktree {own}: it is locked"])

    def test_removing_one_prunes_another_removed_by_hand(self):
        other = self.path.with_name(f"{wt.ARCH_PREFIX}-ar-20261121T000000Z-ef01")
        wt.add_unrecorded(self.cfg, self.main, self.path, self.head)
        wt.add_unrecorded(self.cfg, self.main, other, self.head)
        shutil.rmtree(other)
        self.assertIn(other.name, self.registered())
        wt.remove_unrecorded(self.main, self.path)
        self.assertNotIn(other.name, self.registered())


if __name__ == "__main__":
    unittest.main()
