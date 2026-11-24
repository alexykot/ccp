"""`ccp wt remove` (SPEC §12.1) on a recorded worktree git no longer lists: a directory left holding only the
language pack's caches is deleted with no warning; one holding any other file stays, with git's failure as the
warning."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from ccp import config, doclang, wt
from tests.git_helpers import git
from tests.wt_fixture import WtFixture


class Leftover(WtFixture, unittest.TestCase):
    def made(self) -> tuple[str, Path]:
        """A recorded worktree, in a product whose language pack names a cache directory."""
        self.plane(language="python")
        code, made, body, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 0, body + err)
        return made["name"], wt.base_dir(config.load(self.main)) / made["name"]

    def only_a_cache(self, path: Path) -> None:
        """Everything in `path` gone but `pkg/<cache>/m.pyc`."""
        for p in sorted(path.iterdir()):
            shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
        cache = doclang.get(config.language_name(config.load(self.main))).file_skip_dirs[0]
        (path / "pkg" / cache).mkdir(parents=True)
        (path / "pkg" / cache / "m.pyc").write_bytes(b"\0")

    def leftover(self) -> tuple[str, Path]:
        """A recorded worktree that git no longer lists, its directory holding only `pkg/<cache>/m.pyc`."""
        name, path = self.made()
        git(self.main, "worktree", "remove", "--force", str(path))
        self.assertNotIn(str(path.resolve()), git(self.main, "worktree", "list", "--porcelain"))
        path.mkdir()
        self.only_a_cache(path)
        return name, path

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

    def test_a_symlinked_directory_beside_a_cache_stays_and_its_target_is_untouched(self):
        name, path = self.leftover()
        cache = doclang.get(config.language_name(config.load(self.main))).file_skip_dirs[0]
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name)
        (target / cache).mkdir()
        (target / cache / "m.pyc").write_bytes(b"\0")  # only a cache: a followed link would leave the leftover only caches
        (path / ".venv").symlink_to(target, target_is_directory=True)
        code, out, body, err = self.wt("remove", name)
        self.assertEqual(code, 0, body + err)
        self.assertEqual(len(out["warnings"]), 1, out["warnings"])
        self.assertTrue(path.is_dir())
        self.assertTrue((path / ".venv").is_symlink())
        self.assertTrue((target / cache / "m.pyc").is_file())

    def test_a_worktree_whose_git_file_is_gone_is_pruned_then_cleared(self):
        name, path = self.made()
        self.only_a_cache(path)  # its `.git` file goes too: git's removal fails, and only its prune unlists it
        self.assertIn(str(path.resolve()), git(self.main, "worktree", "list", "--porcelain"))
        code, out, body, err = self.wt("remove", name)
        self.assertEqual(code, 0, body + err)
        self.assertEqual(out["warnings"], [])
        self.assertFalse(path.exists())

    def test_a_directory_git_still_lists_is_never_deleted(self):
        name, path = self.made()
        git(self.main, "worktree", "lock", str(path))  # git refuses to remove it and its prune keeps it listed
        self.only_a_cache(path)
        code, out, body, err = self.wt("remove", name)
        self.assertEqual(code, 0, body + err)
        self.assertEqual(len(out["warnings"]), 1, out["warnings"])
        self.assertTrue(path.is_dir())


class OnlyCaches(unittest.TestCase):
    def test_every_file_inside_a_cache_directory_or_none_at_all_is_only_caches(self):
        self.assertTrue(wt._only_caches([], ("c",)))
        self.assertTrue(wt._only_caches([Path("c/m"), Path("a/b/c/d/m")], ("c",)))

    def test_one_file_outside_them_or_named_like_one_is_not(self):
        self.assertFalse(wt._only_caches([Path("c/m"), Path("a/n")], ("c",)))
        self.assertFalse(wt._only_caches([Path("a/c")], ("c",)))
        self.assertFalse(wt._only_caches([Path("c/m")], ()))


class FilesUnder(unittest.TestCase):
    def test_a_symlinked_directory_counts_as_one_file_and_is_not_followed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tree, elsewhere = Path(tmp.name) / "tree", Path(tmp.name) / "elsewhere"
        (tree / "a").mkdir(parents=True)
        (tree / "a" / "f").write_text("x")
        (elsewhere / "sub").mkdir(parents=True)
        (elsewhere / "g").write_text("x")
        (elsewhere / "sub" / "h").write_text("x")
        (tree / "l").symlink_to(elsewhere, target_is_directory=True)
        self.assertEqual(sorted(wt._files_under(tree)), [Path("a/f"), Path("l")])


if __name__ == "__main__":
    unittest.main()
