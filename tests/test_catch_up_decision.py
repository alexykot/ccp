"""Whether close may catch a verified head up itself (§16.5 rule 4) is `lifecycle.catch_up_blocked`: the first
condition that fails, on plain values. The rest of the catch-up's decisions are tested here too, each without a
queue, a gate or a pull request: the merge commit and its shared-file union, the files each side changes and the
task's own patch, on a throwaway repository, and the sign-off and the record that carry a catch-up, on plain
values. `tests.test_behind_tip_catch_up` holds the paths through close."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from ccp import config, lifecycle, queue, verify
from ccp.lifecycle import catch_up_blocked
from tests.helpers import Product
from tests.test_toolkit import git


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


class NoDeclaredPathsUnderClashes(unittest.TestCase):
    def test_a_task_declaring_no_paths_is_caught_up_whatever_the_tip_changes(self):
        for tip in ([], ["other/b.txt"], ["feature.txt"]):
            self.assertIsNone(catch_up_blocked([], tip, ["feature.txt"], [], False, "clashes", True, True), tip)

    def test_the_declared_paths_are_not_looked_at_whichever_the_schedule(self):
        why = catch_up_blocked([], ["a.py"], ["a.py"], [], False, "clashes", False, False)
        self.assertTrue(why and why.startswith("patch changed"))


class OnAThrowawayRepo(unittest.TestCase):
    """The git side of the catch-up's decisions on `Product`'s root, made a repository: `main` holds a
    shared file, a declared directory and two docs; a `task` branch and a `tip` branch are cut from it."""

    README = "# Package a\n\nIntro.\n\n## Files\n- `one.py`: one\n- `two.py`: two\n"
    TEN = "".join(f"line {i}\n" for i in range(1, 11))
    SHARED = ["docs/*/README.md"]

    def setUp(self):
        self.p = Product({"parallel": {"max_in_flight": 2, "schedule": "paths", "shared": self.SHARED}})
        self.addCleanup(self.p.cleanup)
        self.root = self.p.root
        git(self.root, "init", "-q", "-b", "main")
        self.write("shared.txt", self.TEN)
        self.write("area/x.txt", "x\n")
        self.write("docs/a/README.md", self.README)
        self.write("docs/notes.md", "notes\n")
        self.commit("the product's code")
        for name in ("task", "tip"):
            git(self.root, "branch", name, "main")

    def write(self, rel: str, text: str) -> None:
        self.p.write(rel, text)

    def commit(self, msg: str) -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)
        return git(self.root, "rev-parse", "HEAD")

    def on(self, branch: str, files: dict[str, str]) -> str:
        """`files` committed on `branch`; its head."""
        git(self.root, "checkout", "-q", branch)
        for rel, text in files.items():
            self.write(rel, text)
        return self.commit(f"change {', '.join(files)}")

    def merge(self, task: dict[str, str], tip: dict[str, str]) -> tuple[str, list[str], str, str]:
        """The catch-up's merge commit of `tip` into `task`: it, the files resolved as a union, and both heads."""
        head, tip_head = self.on("task", task), self.on("tip", tip)
        merged, unioned = lifecycle._catch_up_commit(self.p.cfg, head, tip_head, "task/0002-second", "main",
                                                     self.SHARED)
        return merged, unioned, head, tip_head

    def refused(self, task: dict[str, str], tip: dict[str, str], *names: str) -> str:
        with self.assertRaises(lifecycle._NoCatchUp) as cm:
            self.merge(task, tip)
        for n in names:
            self.assertIn(n, str(cm.exception))
        return str(cm.exception)

    def blob(self, commit: str, rel: str) -> str:
        return git(self.root, "show", f"{commit}:{rel}") + "\n"

    # ------------------------------------------------------------------ the merge commit

    def test_a_disjoint_tip_merges_clean_with_both_heads_as_parents(self):
        merged, unioned, head, tip = self.merge({"feature.txt": "built\n"}, {"other/b.txt": "b\n"})
        self.assertEqual(unioned, [])
        self.assertEqual(git(self.root, "rev-list", "--parents", "-n1", merged).split()[1:], [head, tip])
        self.assertEqual((self.blob(merged, "feature.txt"), self.blob(merged, "other/b.txt")), ("built\n", "b\n"))

    def test_a_tip_changing_a_shared_file_elsewhere_than_the_task_merges_clean(self):
        merged, unioned, _, _ = self.merge({"docs/a/README.md": self.README + "- `task.py`: the task's\n"},
                                           {"docs/a/README.md": self.README.replace("# Package a\n", "# Package a, renamed\n")})
        self.assertEqual(unioned, [])
        self.assertEqual(self.blob(merged, "docs/a/README.md"),
                         self.README.replace("# Package a\n", "# Package a, renamed\n") + "- `task.py`: the task's\n")

    def test_a_tip_editing_a_file_far_from_the_task_s_hunk_merges_clean(self):
        merged, unioned, _, _ = self.merge({"shared.txt": self.TEN.replace("line 1\n", "line one\n")},
                                           {"shared.txt": self.TEN.replace("line 10\n", "line ten\n")})
        self.assertEqual(unioned, [])
        self.assertEqual(self.blob(merged, "shared.txt"), self.TEN.replace("line 1\n", "line one\n")
                         .replace("line 10\n", "line ten\n"))

    def test_a_tip_changing_what_the_task_changes_is_refused_naming_the_conflict(self):
        why = self.refused({"shared.txt": self.TEN.replace("line 1\n", "line one, built\n")},
                           {"shared.txt": self.TEN.replace("line 1\n", "line one, other\n")}, "conflict", "shared.txt")
        self.assertNotIn("docs", why)

    # ------------------------------------------------------------------ parallel.shared files

    def test_lines_both_sides_append_to_a_shared_file_are_the_tip_s_then_the_task_s(self):
        merged, unioned, _, _ = self.merge({"docs/a/README.md": self.README + "- `task.py`: the task's\n"},
                                           {"docs/a/README.md": self.README + "- `tip.py`: the tip's\n"})
        self.assertEqual(unioned, ["docs/a/README.md"])
        self.assertEqual(self.blob(merged, "docs/a/README.md"),
                         self.README + "- `tip.py`: the tip's\n- `task.py`: the task's\n")

    def test_lines_appended_at_several_places_keep_their_places(self):
        task = self.README.replace("## Files\n", "## Files\n- `a.py`: the task's\n") + "the task's end\n"
        tip = self.README.replace("## Files\n", "## Files\n- `b.py`: the tip's\n") + "the tip's end\n"
        merged, unioned, _, _ = self.merge({"docs/a/README.md": task}, {"docs/a/README.md": tip})
        self.assertEqual(unioned, ["docs/a/README.md"])
        self.assertEqual(self.blob(merged, "docs/a/README.md"),
                         self.README.replace("## Files\n", "## Files\n- `b.py`: the tip's\n- `a.py`: the task's\n")
                         + "the tip's end\nthe task's end\n")

    def test_a_changed_line_in_a_shared_file_is_refused_naming_it(self):
        self.refused({"docs/a/README.md": self.README.replace("- `one.py`: one\n", "- `one.py`: uno\n")},
                     {"docs/a/README.md": self.README.replace("- `one.py`: one\n", "- `one.py`: first\n")},
                     "conflicts in", "docs/a/README.md")

    def test_a_side_that_removes_a_line_of_a_shared_file_is_refused(self):
        self.refused({"docs/a/README.md": self.README + "- `task.py`: the task's\n"},
                     {"docs/a/README.md": self.README.replace("- `one.py`: one\n", "") + "- `tip.py`: the tip's\n"},
                     "conflicts in", "docs/a/README.md")

    def test_appended_lines_in_a_file_not_shared_beside_a_shared_one_are_refused(self):
        self.refused({"docs/a/README.md": self.README + "- `task.py`: the task's\n", "docs/notes.md": "notes\nthe task's\n"},
                     {"docs/a/README.md": self.README + "- `tip.py`: the tip's\n", "docs/notes.md": "notes\nthe tip's\n"},
                     "conflicts in", "docs/notes.md")

    def test_appended_lines_conflict_when_no_path_is_shared(self):
        head, tip = self.on("task", {"docs/a/README.md": self.README + "- `task.py`: the task's\n"}), \
            self.on("tip", {"docs/a/README.md": self.README + "- `tip.py`: the tip's\n"})
        with self.assertRaises(lifecycle._NoCatchUp) as cm:
            lifecycle._catch_up_commit(self.p.cfg, head, tip, "task/0002-second", "main", [])
        self.assertIn("docs/a/README.md", str(cm.exception))

    # ------------------------------------------------------------------ the files each side changes

    def test_a_rename_changes_both_its_names_on_either_side(self):
        git(self.root, "checkout", "-q", "tip")
        git(self.root, "mv", "shared.txt", "renamed.txt")
        tip = self.commit("a rename")
        git(self.root, "checkout", "-q", "task")
        git(self.root, "mv", "area/x.txt", "area/y.txt")
        head = self.commit("a rename")
        cfg = self.p.cfg
        self.assertEqual(lifecycle._tip_files(cfg, head, tip), ["renamed.txt", "shared.txt"])
        self.assertEqual(lifecycle._task_files(cfg, head, tip), ["area/x.txt", "area/y.txt"])

    def test_the_task_log_and_the_ignored_paths_are_not_the_tip_s_files(self):
        head = self.on("task", {"feature.txt": "built\n"})
        tip = self.on("tip", {"other/b.txt": "b\n", "docs/delivery/tasks/0009-other.md": "task\n"})
        self.assertEqual(lifecycle._tip_files(self.p.cfg, head, tip), ["other/b.txt"])

    # ------------------------------------------------------------------ the task's own patch

    def patches(self, task: dict[str, str], tip: dict[str, str]) -> tuple[dict, dict]:
        """The task's own patch before the merge and after it, as `_catch_up` compares them under `clashes`."""
        merged, _, head, tip_head = self.merge(task, tip)
        files = lifecycle._task_files(self.p.cfg, head, tip_head)
        return (lifecycle._own_patches(self.p.cfg, head, tip_head, self.SHARED, files),
                lifecycle._own_patches(self.p.cfg, merged, tip_head, self.SHARED))

    def test_a_tip_edit_far_from_the_task_s_hunk_leaves_its_patch_unchanged(self):
        before, after = self.patches({"shared.txt": self.TEN.replace("line 1\n", "line one\n")},
                                     {"shared.txt": self.TEN.replace("line 10\n", "line ten\n")})
        self.assertTrue(before["kept"])
        self.assertEqual(before, after)

    def test_a_tip_edit_inside_the_task_s_hunk_context_changes_its_patch(self):
        before, after = self.patches({"shared.txt": self.TEN.replace("line 1\n", "line one\n")},
                                     {"shared.txt": self.TEN.replace("line 3\n", "line three\n")})
        self.assertNotEqual(before["kept"], after["kept"])

    def test_a_union_in_a_shared_path_changes_the_whole_patch_not_the_kept_one(self):
        before, after = self.patches({"feature.txt": "built\n", "docs/a/README.md": self.README + "- `task.py`: the task's\n"},
                                     {"docs/a/README.md": self.README + "- `tip.py`: the tip's\n"})
        self.assertEqual(before["kept"], after["kept"])
        self.assertNotEqual(before["whole"], after["whole"])


class TheCatchUpsGateEnvironment(unittest.TestCase):
    """`_task_worktree_env`: the environment close gives the catch-up's gate in its merge worktree."""

    def setUp(self):
        self.p = Product({"prompts": {"worker_env": {"SCRATCH": "{{kind}}_{{nnnn}}"}}})
        self.addCleanup(self.p.cleanup)
        git(self.p.root, "init", "-q", "-b", "main")
        self._q = tempfile.TemporaryDirectory()
        self.addCleanup(self._q.cleanup)
        self.q = Path(self._q.name)
        self.wt = self.p.root / config.WORKTREES_DIR / "merge-0002"
        self.wt.mkdir(parents=True)

    def impl(self, **fields) -> None:
        d = self.p.root / config.WORKTREES_DIR / "impl-0002"
        d.mkdir(parents=True, exist_ok=True)
        (self.q / "worktrees").mkdir(exist_ok=True)
        (self.q / "worktrees" / "impl-0002.json").write_text(json.dumps(
            {"name": "impl-0002", "kind": "impl", "task_id": "0002-second", "nnnn": "0002", "path": str(d),
             "seat": "impl", "tag": "t1", "round": 2, **fields}))

    def env(self) -> dict[str, str]:
        return lifecycle._task_worktree_env(self.p.cfg, self.q, "0002-second", self.wt)

    def test_the_gate_gets_the_merge_worktree_s_fields_the_task_and_worker_env(self):
        self.impl()
        got = self.env()
        self.assertEqual((got["CCP_WT_WORKTREE"], got["CCP_WT_KIND"], got["CCP_WT_NAME"], got["CCP_TASK_ID"],
                          got["CCP_NNNN"], got["CCP_WT_SEAT"], got["CCP_WT_TAG"], got["CCP_WT_ROUND"], got["SCRATCH"]),
                         (str(self.wt), "merge", "merge-0002", "0002-second", "0002", "impl", "t1", "2", "merge_0002"))

    def test_an_impl_record_missing_a_field_gives_that_variable_empty(self):
        self.impl(seat=None)
        got = self.env()
        self.assertEqual((got["CCP_WT_SEAT"], got["CCP_WT_NAME"], got["CCP_WT_TAG"]), ("", "merge-0002", "t1"))

    def test_with_no_recorded_impl_worktree_seat_and_tag_are_empty_with_a_warning(self):
        err = io.StringIO()
        with redirect_stderr(err):
            got = self.env()
        self.assertEqual((got["CCP_WT_SEAT"], got["CCP_WT_TAG"], got["CCP_WT_ROUND"], got["CCP_NNNN"]), ("", "", "1", "0002"))
        self.assertIn("no recorded impl worktree", err.getvalue())


class ABuildSignOffIsCarriedOnlyByTheCatchUp(unittest.TestCase):
    """`lifecycle.sign_off_gaps`: a build sign-off recorded for another head is stale unless close's catch-up of
    the signed head, on the verification record, carried it."""

    SIGNED, MERGED = "a" * 40, "b" * 40
    META = {"task_id": "0002-second", "sign_off": "build"}

    def setUp(self):
        self._q = tempfile.TemporaryDirectory()
        self.addCleanup(self._q.cleanup)
        self.q = Path(self._q.name)
        ev = queue.events_path(self.q)
        ev.parent.mkdir(parents=True, exist_ok=True)
        ev.write_text(json.dumps({"type": "sign_off", "op": "recorded", "task_id": "0002-second", "at": "2026-11-13T10:00:00Z",
                                  "payload": {"stage": "build", "by": "op", "words": "ship it", "head": self.SIGNED}}) + "\n")

    def carry(self, **cu) -> None:
        (self.q / "verification").mkdir(exist_ok=True)
        (self.q / "verification/0002-second.json").write_text(json.dumps({
            "verdict": "approve", "head_sha": self.SIGNED,
            "catch_up": {"from": self.SIGNED, "to": self.MERGED, "sign_off_carried": self.SIGNED, **cu}}))

    def gaps(self, head: str) -> list[str]:
        return lifecycle.sign_off_gaps(self.q, self.META, ["build"], head)

    def test_the_signed_head_holds(self):
        self.assertEqual(self.gaps(self.SIGNED), [])

    def test_another_head_is_stale(self):
        [why] = self.gaps(self.MERGED)
        self.assertIn("build sign-off is stale", why)

    def test_the_head_a_catch_up_carried_the_sign_off_to_holds(self):
        self.carry()
        self.assertEqual(self.gaps(self.MERGED), [])
        self.assertIn("stale", self.gaps("c" * 40)[0])  # another head than the catch-up's

    def test_a_catch_up_that_does_not_name_the_signed_head_carries_nothing(self):
        self.carry(sign_off_carried="c" * 40)
        self.assertIn("stale", self.gaps(self.MERGED)[0])


class TheRecordReadsTheCatchUp(unittest.TestCase):
    """`verify.sign_off_carried` reads a catch-up only from a record that is an approve."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.q = Path(self._tmp.name)

    def test_sign_off_carried_is_read_only_from_a_catch_up_that_starts_at_the_signed_head_and_ends_at_the_head(self):
        a, b, c = "a" * 40, "b" * 40, "c" * 40
        (self.q / "verification").mkdir(exist_ok=True)

        def put(verdict="approve", **cu):
            (self.q / "verification/0002-second.json").write_text(json.dumps({
                "verdict": verdict, "head_sha": a,
                "catch_up": {"from": a, "to": b, "sign_off_carried": a, **cu}}))
        put(verdict="reject")  # a catch-up on a record that is not an approve carries nothing
        self.assertFalse(verify.sign_off_carried(self.q, "0002-second", a, b))
        put()
        self.assertTrue(verify.sign_off_carried(self.q, "0002-second", a, b))
        self.assertTrue(verify.sign_off_carried(self.q, "0002-second", a[:12], b[:12]))
        self.assertFalse(verify.sign_off_carried(self.q, "0002-second", a, c))  # another head than the catch-up's
        self.assertFalse(verify.sign_off_carried(self.q, "0002-second", c, b))  # another head signed
        put(sign_off_carried=c)
        self.assertFalse(verify.sign_off_carried(self.q, "0002-second", a, b))
        put(**{"from": c})  # the catch-up starts elsewhere than the signed head
        self.assertFalse(verify.sign_off_carried(self.q, "0002-second", a, b))
        (self.q / "verification/0002-second.json").write_text(json.dumps({
            "verdict": "approve", "head_sha": a, "catch_up": {"from": a, "to": b}}))  # no sign_off_carried
        self.assertFalse(verify.sign_off_carried(self.q, "0002-second", a, b))
        self.assertFalse(verify.sign_off_carried(self.q, "0009-none", a, b))


class MergeOkReadsTheCatchUp(unittest.TestCase):
    """`ccp verify merge-ok` takes a caught-up head only through a catch-up from the approved head whose gate run
    is a passed run of the gate lane bound to the task."""

    H, M = "a" * 40, "b" * 40

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.q = Path(self._tmp.name)
        (self.q / "runs").mkdir()
        self.cfg = SimpleNamespace(suite={"roles": {"gate": "gate"}})
        self.rows = []

    def tearDown(self):
        self._tmp.cleanup()

    def run_(self, sid, task="0002-second", lane="gate", code=0):
        at = "2026-11-13T10:00:00Z"
        self.rows += [{"op": "started", "suite_id": sid, "at": at, "lane": lane, "task_id": task, "run_id": None},
                      {"op": "ended", "suite_id": sid, "at": at, "exit_code": code}]
        (self.q / "runs/_suites.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.rows))

    def why(self, gate_run="st-ok", frm=None, to=None, head=None):
        rec = {"head_sha": self.H, "catch_up": {"from": frm or self.H, "to": to or self.M, "tip": "c" * 40,
                                                "gate_run": gate_run, "merge_tree": "clean", "tip_files": [],
                                                "task_files": []}}
        return verify.catch_up_refusal(self.cfg, self.q, rec, "0002-second", head or self.M)

    def test_a_passed_gate_run_of_the_task_covers_the_catch_up(self):
        self.run_("st-ok")
        self.assertIsNone(self.why())

    def test_every_other_catch_up_is_refused(self):
        self.run_("st-ok")
        self.run_("st-red", code=1)
        self.run_("st-other", task="0003-third")
        self.run_("st-full", lane="full")
        for case, want in ((dict(gate_run="st-none"), "not recorded"), (dict(gate_run="st-red"), "did not pass"),
                           (dict(gate_run="st-other"), "0003-third"), (dict(gate_run="st-full"), "gate lane"),
                           (dict(frm="d" * 40), "approved head"), (dict(head="e" * 40), "not eeeeeee")):
            self.assertIn(want, self.why(**case) or "", case)


if __name__ == "__main__":
    unittest.main()
