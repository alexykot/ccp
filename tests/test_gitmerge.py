"""ccp/gitmerge.py, the plane's one reading of git's merge analysis: the merge probe with a conflicted file's
stages, a head's own patch id, and the remerge diff of a merge commit, on a temporary repository."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import gitmerge, queue
from tests.test_toolkit import git


class Repo(unittest.TestCase):
    """A repository whose `main` has `a.txt`, with a branch cut from it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        self.commit("a.txt", "one\ntwo\nthree\n")

    def commit(self, rel: str, text: str) -> str:
        (self.root / rel).write_text(text)
        git(self.root, "add", rel)
        git(self.root, "commit", "-q", "-m", f"change {rel}")
        return git(self.root, "rev-parse", "HEAD")

    def branch(self, name: str, at: str = "main") -> None:
        git(self.root, "checkout", "-q", "-b", name, at)

    def diverged(self, ours: tuple[str, str], theirs: tuple[str, str]) -> tuple[str, str]:
        """The heads of two branches off `main`, each changing one file."""
        self.branch("ours")
        o = self.commit(*ours)
        self.branch("theirs", "main")
        t = self.commit(*theirs)
        return o, t


class Probe(Repo):
    def test_a_clean_merge_gives_a_tree_and_no_conflicted_files(self):
        o, t = self.diverged(("b.txt", "b\n"), ("c.txt", "c\n"))
        p = gitmerge.probe(self.root, o, t)
        self.assertEqual((p.returncode, p.failed, p.conflicts), (0, False, {}))
        self.assertEqual(git(self.root, "ls-tree", "--name-only", p.tree).split(), ["a.txt", "b.txt", "c.txt"])

    def test_a_conflicting_merge_names_the_file_with_its_three_stages(self):
        o, t = self.diverged(("a.txt", "one\nTWO\nthree\n"), ("a.txt", "one\n2\nthree\n"))
        p = gitmerge.probe(self.root, o, t)
        self.assertEqual((p.returncode, p.failed), (1, False))
        self.assertEqual(list(p.conflicts), ["a.txt"])
        stages = p.conflicts["a.txt"]
        self.assertEqual(sorted(stages), [1, 2, 3])
        self.assertEqual({k: v[0] for k, v in stages.items()}, {1: "100644", 2: "100644", 3: "100644"})
        for k, text in {1: "one\ntwo\nthree\n", 2: "one\nTWO\nthree\n", 3: "one\n2\nthree\n"}.items():
            self.assertEqual(git(self.root, "cat-file", "blob", stages[k][1]) + "\n", text)

    def test_a_git_that_exits_129_is_reported_as_unable_to_merge(self):
        o, t = self.diverged(("b.txt", "b\n"), ("c.txt", "c\n"))
        real = queue.git

        def old_git(cwd, *args, **kw):
            if args[:2] == ("merge-tree", "--write-tree"):
                return subprocess.CompletedProcess(["git", *args], 129, "", "usage: git merge-tree")
            return real(cwd, *args, **kw)
        with mock.patch("ccp.queue.git", side_effect=old_git):
            p = gitmerge.probe(self.root, o, t)
        self.assertEqual((p.returncode, p.failed, p.conflicts), (129, True, {}))
        self.assertEqual(p.detail, "usage: git merge-tree")
        self.assertEqual(gitmerge.old_git_text(p),
                         "`git merge-tree --write-tree` failed (exit 129); it needs git 2.38 or later")
        self.assertIn("could not merge", gitmerge.cannot_merge_text(p, o, "main"))


class OwnPatchId(Repo):
    def test_one_change_on_two_bases_has_one_patch_id_and_nothing_is_fetched(self):
        self.branch("first")
        f = self.commit("feature.txt", "built\n")
        self.branch("moved", "main")
        self.commit("other.txt", "an unrelated change\n")
        git(self.root, "branch", "-f", "tip", "moved")
        self.branch("second", "moved")
        s = self.commit("feature.txt", "built\n")
        self.assertNotEqual(f, s)
        calls: list[tuple[str, ...]] = []

        def run(cwd, *args, data=None):
            calls.append(args)
            return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, input=data)
        a = gitmerge.own_patch_id(self.root, f, "tip", run)
        self.assertTrue(a)
        self.assertEqual(a, gitmerge.own_patch_id(self.root, s, "tip", run))
        self.assertNotIn("fetch", [c[0] for c in calls])
        self.commit("feature.txt", "built differently\n")
        self.assertNotEqual(a, gitmerge.own_patch_id(self.root, "HEAD", "tip", run))

    def test_a_head_the_base_already_holds_has_no_patch_id(self):
        run = lambda cwd, *args, data=None: subprocess.run(  # noqa: E731
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, input=data)
        self.assertIsNone(gitmerge.own_patch_id(self.root, "main", "main", run))
        self.assertIsNone(gitmerge.own_patch_id(self.root, "no-such-ref", "main", run))


    def test_an_excluded_file_is_left_out_of_the_patch(self):
        run = lambda cwd, *args, data=None: subprocess.run(  # noqa: E731
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, input=data)
        base = self.commit("base.txt", "base\n")
        git(self.root, "branch", "tip", base)
        git(self.root, "checkout", "-q", "-b", "one", base)
        self.commit("feature.txt", "same\n")
        self.commit("noise.txt", "one\n")
        one = git(self.root, "rev-parse", "HEAD")
        git(self.root, "checkout", "-q", "-b", "two", base)
        self.commit("feature.txt", "same\n")
        self.commit("noise.txt", "two\n")
        two = git(self.root, "rev-parse", "HEAD")
        self.assertNotEqual(gitmerge.own_patch_id(self.root, one, "tip", run),
                            gitmerge.own_patch_id(self.root, two, "tip", run))
        a = gitmerge.own_patch_id(self.root, one, "tip", run, exclude=["noise.txt"])
        self.assertTrue(a)
        self.assertEqual(a, gitmerge.own_patch_id(self.root, two, "tip", run, exclude=["noise.txt"]))
        self.assertNotEqual(a, gitmerge.own_patch_id(self.root, one, "tip", run, exclude=["feature.txt"]))

    def test_an_exclude_is_a_literal_path_not_a_glob(self):
        run = lambda cwd, *args, data=None: subprocess.run(  # noqa: E731
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, input=data)
        base = self.commit("base.txt", "base\n")
        git(self.root, "branch", "tip", base)
        git(self.root, "checkout", "-q", "-b", "one", base)
        self.commit("a.txt", "a\n")
        one = git(self.root, "rev-parse", "HEAD")
        whole = gitmerge.own_patch_id(self.root, one, "tip", run)
        self.assertEqual(whole, gitmerge.own_patch_id(self.root, one, "tip", run, exclude=["*.txt"]))
        self.assertNotEqual(whole, gitmerge.own_patch_id(self.root, one, "tip", run, exclude=["a.txt"], empty="x"))

    def test_an_empty_diff_gives_the_empty_text_when_asked(self):
        run = lambda cwd, *args, data=None: subprocess.run(  # noqa: E731
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, input=data)
        self.assertEqual(gitmerge.own_patch_id(self.root, "main", "main", run, empty=""), "")
        self.assertIsNone(gitmerge.own_patch_id(self.root, "main", "main", run))
        self.assertIsNone(gitmerge.own_patch_id(self.root, "no-such-ref", "main", run, empty=""))

    def test_a_diff_whose_files_are_all_excluded_is_empty(self):
        run = lambda cwd, *args, data=None: subprocess.run(  # noqa: E731
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, input=data)
        base = self.commit("base.txt", "base\n")
        git(self.root, "branch", "tip", base)
        git(self.root, "checkout", "-q", "-b", "one", base)
        self.commit("only.txt", "x\n")
        one = git(self.root, "rev-parse", "HEAD")
        self.assertEqual(gitmerge.own_patch_id(self.root, one, "tip", run, exclude=["only.txt"], empty=""), "")
        self.assertIsNone(gitmerge.own_patch_id(self.root, one, "tip", run, exclude=["only.txt"]))


class RemergeDiff(Repo):
    def test_a_hand_resolved_conflict_has_a_remerge_diff(self):
        o, t = self.diverged(("a.txt", "one\nTWO\nthree\n"), ("a.txt", "one\n2\nthree\n"))
        git(self.root, "checkout", "-q", "ours")
        subprocess.run(["git", "-C", str(self.root), "merge", "-q", "--no-commit", t], capture_output=True)
        (self.root / "a.txt").write_text("one\nhand resolved\nthree\n")
        git(self.root, "add", "a.txt")
        git(self.root, "commit", "-q", "-m", "merge theirs")
        text = gitmerge.remerge_diff(self.root, "HEAD")
        self.assertIn("hand resolved", text)
        self.assertIn("a.txt", text)

    def test_a_clean_merge_has_an_empty_remerge_diff(self):
        o, t = self.diverged(("b.txt", "b\n"), ("c.txt", "c\n"))
        git(self.root, "checkout", "-q", "ours")
        git(self.root, "merge", "-q", "--no-ff", "-m", "merge theirs", t)
        self.assertEqual(gitmerge.remerge_diff(self.root, "HEAD"), "")


if __name__ == "__main__":
    unittest.main()
