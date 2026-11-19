"""Whether close may catch a verified head up itself (§16.5 rule 4) is `lifecycle.catch_up_blocked`: the first
condition that fails, on plain values."""
from __future__ import annotations

import unittest

from ccp.lifecycle import catch_up_blocked


class NoDeclaredPaths(unittest.TestCase):
    def test_a_task_declaring_no_paths_is_blocked(self):
        why = catch_up_blocked([], [], [], [], False)
        self.assertTrue(why and why.startswith("no declared paths:"))

    def test_it_is_named_before_any_tip_file_is_looked_at(self):
        why = catch_up_blocked([], ["a.py"], ["a.py"], [], True)
        self.assertTrue(why and why.startswith("no declared paths:"))


class Overlap(unittest.TestCase):
    def test_a_disjoint_tip_is_not_blocked(self):
        self.assertIsNone(catch_up_blocked(["ccp/a.py"], ["docs/x.md"], ["ccp/a.py"], [], False))

    def test_a_tip_file_the_diff_changes_but_does_not_declare_is_named(self):
        why = catch_up_blocked(["ccp/a.py"], ["extra.py"], ["ccp/a.py", "extra.py"], [], False)
        self.assertTrue(why and why.startswith("overlap:") and "extra.py" in why)

    def test_a_tip_file_under_a_declared_directory_the_diff_leaves_is_named(self):
        why = catch_up_blocked(["ccp/"], ["ccp/other.py"], ["ccp/a.py"], [], False)
        self.assertTrue(why and why.startswith("overlap:") and "ccp/other.py" in why)

    def test_a_tip_file_covered_by_shared_is_not_an_overlap(self):
        self.assertIsNone(catch_up_blocked(["docs/INDEX.yaml"], ["docs/INDEX.yaml"], ["docs/INDEX.yaml"],
                                           ["docs/INDEX.yaml"], False))

    def test_a_covered_file_does_not_hide_an_uncovered_one(self):
        why = catch_up_blocked(["ccp/", "docs/INDEX.yaml"], ["docs/INDEX.yaml", "ccp/b.py"], ["ccp/a.py"],
                               ["docs/INDEX.yaml"], False)
        self.assertTrue(why and why.startswith("overlap:") and "ccp/b.py" in why and "INDEX" not in why)


class BuildSignOff(unittest.TestCase):
    def test_a_shared_file_the_task_changes_is_refused_when_a_sign_off_is_due(self):
        why = catch_up_blocked(["ccp/a.py"], ["docs/INDEX.yaml"], ["ccp/a.py", "docs/INDEX.yaml"],
                               ["docs/INDEX.yaml"], True)
        self.assertTrue(why and why.startswith("build sign-off:") and "docs/INDEX.yaml" in why)

    def test_the_same_tip_is_allowed_when_no_sign_off_is_due(self):
        self.assertIsNone(catch_up_blocked(["ccp/a.py"], ["docs/INDEX.yaml"], ["ccp/a.py", "docs/INDEX.yaml"],
                                           ["docs/INDEX.yaml"], False))

    def test_a_disjoint_tip_is_allowed_when_a_sign_off_is_due(self):
        self.assertIsNone(catch_up_blocked(["ccp/a.py"], ["docs/x.md"], ["ccp/a.py", "docs/INDEX.yaml"],
                                           ["docs/INDEX.yaml"], True))

    def test_a_shared_file_the_task_does_not_change_is_allowed_when_a_sign_off_is_due(self):
        self.assertIsNone(catch_up_blocked(["ccp/a.py"], ["docs/INDEX.yaml"], ["ccp/a.py"],
                                           ["docs/INDEX.yaml"], True))


class Order(unittest.TestCase):
    def test_overlap_is_named_before_the_sign_off(self):
        why = catch_up_blocked(["ccp/a.py"], ["ccp/a.py"], ["ccp/a.py"], [], True)
        self.assertTrue(why and why.startswith("overlap:"))

    def test_an_overlap_is_named_before_the_sign_off_with_a_shared_file_changed_by_both(self):
        why = catch_up_blocked(["ccp/a.py"], ["ccp/a.py", "s.txt"], ["ccp/a.py", "s.txt"], ["s.txt"], True)
        self.assertTrue(why and why.startswith("overlap:") and "s.txt" not in why)


class FiveFiles(unittest.TestCase):
    FILES = [f"ccp/f{n}.py" for n in range(8)]

    def test_an_overlap_names_at_most_five_files(self):
        why = catch_up_blocked(["ccp/"], self.FILES, [], [], False)
        self.assertTrue(why)
        self.assertEqual([f for f in self.FILES if f in why], self.FILES[:5])

    def test_a_sign_off_names_at_most_five_files(self):
        why = catch_up_blocked(["docs/z.md"], self.FILES, self.FILES, self.FILES, True)
        self.assertTrue(why and why.startswith("build sign-off:"))
        self.assertEqual([f for f in self.FILES if f in why], self.FILES[:5])


class Clashes(unittest.TestCase):
    """Under `parallel.schedule: clashes` the file condition is the patch test alone."""

    def blocked(self, declared=("ccp/a.py",), tip=("ccp/a.py",), task=("ccp/a.py",), shared=(), signed=False, **kw):
        return catch_up_blocked(list(declared), list(tip), list(task), list(shared), signed, "clashes", **kw)

    def test_a_tip_changing_a_file_the_task_changes_and_declares_is_allowed_when_its_patch_is_unchanged(self):
        self.assertIsNone(self.blocked(patch_same=True, whole_patch_same=True))

    def test_a_task_declaring_no_paths_is_allowed_when_its_patch_is_unchanged(self):
        self.assertIsNone(self.blocked(declared=(), patch_same=True, whole_patch_same=True))

    def test_a_changed_patch_is_refused_naming_it(self):
        why = self.blocked(declared=(), tip=(), task=(), patch_same=False)
        self.assertTrue(why and why.startswith("patch changed"))

    def test_an_unread_patch_is_refused_naming_it(self):
        why = self.blocked(patch_same=None)
        self.assertTrue(why and why.startswith("patch unread"))

    def test_a_patch_not_given_is_unread(self):
        why = self.blocked()
        self.assertTrue(why and why.startswith("patch unread"))

    def test_the_patch_is_named_before_the_sign_off(self):
        why = self.blocked(signed=True, patch_same=False, whole_patch_same=False)
        self.assertTrue(why and why.startswith("patch changed"))

    def test_a_sign_off_due_is_carried_when_the_whole_patch_is_unchanged(self):
        self.assertIsNone(self.blocked(signed=True, patch_same=True, whole_patch_same=True))

    def test_a_sign_off_due_is_refused_when_only_a_shared_path_changed_in_the_patch(self):
        why = self.blocked(signed=True, patch_same=True, whole_patch_same=False)
        self.assertTrue(why and why.startswith("build sign-off:"))

    def test_the_whole_patch_is_not_looked_at_when_no_sign_off_is_due(self):
        self.assertIsNone(self.blocked(patch_same=True, whole_patch_same=False))

    def test_an_unread_whole_patch_refuses_a_sign_off(self):
        why = self.blocked(signed=True, patch_same=True, whole_patch_same=None)
        self.assertTrue(why and why.startswith("build sign-off:"))


class PathsSchedule(unittest.TestCase):
    """The schedule given as `paths` is the default: the patch inputs are not looked at."""

    def test_overlap_is_still_refused(self):
        args = (["ccp/a.py"], ["ccp/a.py"], ["ccp/a.py"], [], False)
        for extra in ((), ("paths", True, True)):
            why = catch_up_blocked(*args, *extra)
            self.assertTrue(why and why.startswith("overlap:"))

    def test_no_declared_paths_is_still_refused(self):
        for extra in ((), ("paths", True, True)):
            why = catch_up_blocked([], [], [], [], False, *extra)
            self.assertTrue(why and why.startswith("no declared paths:"))


if __name__ == "__main__":
    unittest.main()
