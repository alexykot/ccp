"""`ccp wt remove` (SPEC §12.1) on a recorded worktree git no longer lists: a directory left holding only the
language pack's caches is deleted with no warning; one holding any other file stays, with git's failure as the
warning."""
from __future__ import annotations

import unittest

from ccp import config, doclang, wt
from tests.toolkit_fixture import git
from tests.wt_fixture import WtFixture


class Leftover(WtFixture, unittest.TestCase):
    def leftover(self) -> tuple[str, object]:
        """A recorded worktree that git no longer lists, its directory holding only `pkg/<cache>/m.pyc`, in a product
        whose language pack names a cache directory."""
        self.plane(language="python")
        code, made, body, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 0, body + err)
        path = wt.base_dir(config.load(self.main)) / made["name"]
        git(self.main, "worktree", "remove", "--force", str(path))
        self.assertNotIn(str(path.resolve()), git(self.main, "worktree", "list", "--porcelain"))
        cache = doclang.get(config.language_name(config.load(self.main))).file_skip_dirs[0]
        (path / "pkg" / cache).mkdir(parents=True)
        (path / "pkg" / cache / "m.pyc").write_bytes(b"\0")
        return made["name"], path

    def test_a_directory_holding_only_a_cache_is_gone_with_no_warning(self):
        name, path = self.leftover()
        code, out, body, err = self.wt("remove", name)
        self.assertEqual(code, 0, body + err)
        self.assertEqual(out["warnings"], [])
        self.assertFalse(path.exists())
        self.assertIsNone(wt.load(self.q, name))

    def test_a_directory_holding_another_file_beside_it_stays_with_the_warning(self):
        name, path = self.leftover()
        (path / "notes.txt").write_text("kept\n")
        code, out, body, err = self.wt("remove", name)
        self.assertEqual(code, 0, body + err)
        self.assertEqual(len(out["warnings"]), 1, out["warnings"])
        self.assertTrue(out["warnings"][0].startswith(f"worktree {path}:"), out["warnings"])
        self.assertTrue((path / "notes.txt").is_file())


if __name__ == "__main__":
    unittest.main()
