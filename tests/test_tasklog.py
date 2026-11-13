"""ccp tasks: the durable task log rules (SPEC §21.1)."""
from __future__ import annotations

import json
import unittest

from ccp import tasklog
from tests.helpers import Product


class TaskLogTest(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def errs(self):
        return tasklog.check(self.p.cfg)

    def test_clean_log(self):
        self.p.task("0001-first", "done")
        self.p.task("0002-second", deps=["0001-first"])
        self.p.index()
        self.assertEqual(self.errs(), [])

    def test_frontmatter_strips_inline_comments(self):
        fm = tasklog.frontmatter('---\nstatus: pending   # a | b\ntitle: "a # b"\nx: [a, "b"]  # c\ny: ["p, q", r]\n---\n')
        self.assertEqual(fm, {"status": "pending", "title": "a # b", "x": ["a", "b"], "y": ["p, q", "r"]})

    def test_missing_and_stale_index(self):
        self.p.task("0001-first")
        self.assertIn("docs/delivery/INDEX.yaml: missing — run `ccp tasks index`", self.errs())
        self.p.index()
        self.p.task("0002-second")
        self.assertIn("docs/delivery/INDEX.yaml: stale — run `ccp tasks index`", self.errs())

    def test_index_carries_project_id_and_no_date(self):
        self.p.task("0001-first")
        out = tasklog.render_index(self.p.cfg)
        self.assertIn("project_id: demo\n", out)
        self.assertIn("  - id: 0001-first\n    status: pending\n", out)
        self.assertNotIn("updated", out)

    def assertFails(self, needle):
        self.p.index()
        errs = self.errs()
        self.assertTrue(any(needle in e for e in errs), f"{needle!r} not in {errs}")

    def test_task_numbers_take_only_task_files_at_the_width(self):
        self.p.task("0001-first")
        self.p.task("0042-second")
        for stray in ("README.md", "INDEX.md", "042-short.md", "00007-long.md", "0003-Upper-Slug.md",
                      "0004-notes.txt"):
            self.p.write(f"docs/delivery/tasks/{stray}", "x")
        self.assertEqual(tasklog.task_numbers(self.p.cfg), frozenset({"0001", "0042"}))

    def test_bad_filename(self):
        self.p.write("docs/delivery/tasks/1-Bad.md", "x")
        self.assertFails("filename must be NNNN-kebab-slug.md")

    def test_reused_number(self):
        self.p.task("0001-a")
        self.p.task("0001-b")
        self.assertFails("NNNN 0001 already used")

    def test_task_id_mismatch_and_bad_status(self):
        f = self.p.task("0001-a", status="leased")
        f.write_text(f.read_text().replace("task_id: 0001-a", "task_id: 0001-z"))
        self.assertFails("does not match the filename")
        self.assertFails("status 'leased' is not one of")

    def test_next_respects_scope(self):
        self.p.task("0001-a", "done")
        self.p.task("0002-b", deps=["0001-a"])
        self.p.task("0003-c", deps=["0001-a"])
        self.p.task("0004-d", deps=["0002-b"])
        self.assertEqual(tasklog.next_task(self.p.cfg)["task_id"], "0002-b")
        self.assertEqual(tasklog.next_task(self.p.cfg, ["0003"])["task_id"], "0003-c")
        self.assertEqual(tasklog.next_task(self.p.cfg, ["0003-c", "0002"])["task_id"], "0002-b")
        self.assertIsNone(tasklog.next_task(self.p.cfg, ["0004-d"]))  # its dependency, out of scope, isn't done

    def test_dependency_missing_is_refused_and_a_later_one_is_not(self):
        self.p.task("0001-a", deps=["0009-nope"])
        self.p.task("0002-b", deps=["0003-c"])
        self.p.task("0003-c")
        self.assertFails("depends_on `0009-nope`, which does not exist")
        self.assertEqual([e for e in self.errs() if "0002-b" in e], [])

    def test_a_task_waits_for_a_later_numbered_dependency_and_runs_after_it(self):
        self.p.task("0001-a", "done")
        self.p.task("0003-c", deps=["0005-e"])
        self.p.task("0004-d", deps=["0003-c"])
        self.p.task("0005-e", deps=["0001-a"])
        self.p.index()
        code, out = self._cli("check")
        self.assertEqual(code, 0, out)
        code, out = self._cli("next", "--json")
        self.assertEqual((code, json.loads(out)["task_id"]), (0, "0005-e"))
        self.assertEqual([t["task_id"] for t, _ in tasklog.ranked(self.p.cfg)], ["0005-e"])
        self.p.task("0005-e", "done", deps=["0001-a"])
        self.assertEqual([t["task_id"] for t, _ in tasklog.ranked(self.p.cfg)], ["0003-c"])
        self.p.task("0003-c", "done", deps=["0005-e"])
        self.assertEqual(tasklog.next_task(self.p.cfg)["task_id"], "0004-d")

    def test_ranked_orders_ready_tasks_by_number_whatever_order_it_is_given(self):
        self.p.task("0001-a")
        self.p.task("0002-b")
        self.p.task("0003-c")
        tasks = list(reversed(tasklog.load(self.p.cfg)))
        self.assertEqual([t["task_id"] for t, _ in tasklog.ranked(self.p.cfg, tasks=tasks)],
                         ["0001-a", "0002-b", "0003-c"])

    def test_a_dependency_cycle_is_refused_and_named(self):
        self.p.task("0003-c", deps=["0005-e"])
        self.p.task("0005-e", deps=["0003-c"])
        self.p.index()
        errs = self.errs()
        self.assertEqual([e for e in errs if "cycle" in e],
                         ["docs/delivery/tasks/0003-c.md: depends_on forms a cycle: 0003-c → 0005-e → 0003-c "
                          "— no task in it can ever be ready"])
        code, out = self._cli("check")
        self.assertEqual(code, 1, out)
        self.assertIn("0003-c → 0005-e → 0003-c", out)

    def test_cycles_are_named_from_their_lowest_task_once_each(self):
        self.p.task("0001-a", deps=["0001-a"])
        self.p.task("0002-b", deps=["0004-d"])
        self.p.task("0003-c", deps=["0002-b"])
        self.p.task("0004-d", deps=["0003-c", "0009-nope"])
        self.p.task("0005-e", deps=["0004-d"])
        self.assertEqual(tasklog.dependency_cycles(tasklog.load(self.p.cfg)),
                         [["0001-a"], ["0002-b", "0004-d", "0003-c"]])
        self.p.task("0001-a")
        self.p.task("0002-b")
        self.assertEqual(tasklog.dependency_cycles(tasklog.load(self.p.cfg)), [])

    def test_no_refs(self):
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace('spec_refs: ["S1"]', "spec_refs: []"))
        self.assertFails("cites none of spec_refs")

    def test_missing_section(self):
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace("## Scope\n", "## Range\n"))
        self.assertFails("missing section `## Scope`")

    def test_no_checks_too_many_and_duplicates(self):
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace("- id: `cmd-01`", "- id: cmd-01"))
        self.assertFails("no dod_checks")
        f.write_text(self.p.task("0001-a").read_text().replace(
            "- id: `cmd-01`", "\n".join(f"- id: `cmd-0{i}`" for i in range(1, 8))))
        self.assertFails("7 dod_checks — more than 6")
        f.write_text(self.p.task("0001-a").read_text().replace("- id: `cmd-01`", "- id: `cmd-01`\n- id: `cmd-01`"))
        self.assertFails("duplicate dod_check ids")

    def test_soft_language_only_inside_checks(self):
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace("expect: exit 0", "expect: it should work"))
        self.assertFails("soft language 'should'")
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace("- background", "- it may rain"))
        self.p.index()
        self.assertEqual(self.errs(), [])

    def test_done_needs_verification_notes(self):
        self.p.task("0001-a", "done", ver="*Append-only.*")
        self.assertFails("status is done with no verification notes")

    def test_next_task_respects_dependencies(self):
        self.p.task("0001-a", "done")
        self.p.task("0002-b", deps=["0003-c"])
        self.p.task("0003-c")
        self.assertEqual(tasklog.next_task(self.p.cfg)["task_id"], "0003-c")
        self.p.task("0003-c", "done")
        self.assertEqual(tasklog.next_task(self.p.cfg)["task_id"], "0002-b")
        self.p.task("0002-b", "done")
        self.assertIsNone(tasklog.next_task(self.p.cfg))

    def test_next_number(self):
        self.assertEqual(tasklog.next_number(self.p.cfg), "0001")
        self.p.task("0007-a")
        self.assertEqual(tasklog.next_number(self.p.cfg), "0008")

    def test_runtime_keys_in_frontmatter_fail(self):
        # A task once carried a runtime wait in its frontmatter.
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace("created:", "waiting_on: operator_step\nlease_expires_at: x\ncreated:"))
        self.assertFails("frontmatter carries `waiting_on`, which is runtime state")
        self.assertFails("frontmatter carries `lease_expires_at`")

    def _cli(self, *args: str) -> tuple[int, str]:
        import io
        from contextlib import redirect_stdout

        from ccp import cli
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["--root", str(self.p.root), "tasks", *args])
        return code, out.getvalue()

    def test_a_deleted_task_file_is_refused_by_index_and_check(self):
        # PROC-18: 0189's file was deleted and its id left unused.
        import subprocess

        def git(*a: str) -> None:
            subprocess.run(["git", "-C", str(self.p.root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                           check=True, capture_output=True)
        self.p.task("0001-a")
        gone = self.p.task("0002-b")
        self.p.index()
        git("init", "-q")
        git("add", "-A")
        git("commit", "-qm", "log")
        gone.unlink()
        index = (self.p.root / "docs/delivery/INDEX.yaml").read_text()
        code, out = self._cli("index")
        self.assertEqual(code, 1, out)
        self.assertIn("0002-b: its task file is gone (listed in INDEX.yaml)", out)
        self.assertEqual((self.p.root / "docs/delivery/INDEX.yaml").read_text(), index)
        # Committed anyway, with the index written by hand: git history still knows.
        (self.p.root / "docs/delivery/INDEX.yaml").write_text(tasklog.render_index(self.p.cfg))
        git("add", "-A")
        git("commit", "-qm", "delete 0002")
        self.assertFails("0002-b: its task file is gone (deleted in ")
        self.p.task("0002-b", status="dropped")
        self.p.index()
        self.assertEqual(self.errs(), [])

    def _git(self, *a: str) -> None:
        import subprocess
        subprocess.run(["git", "-C", str(self.p.root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                       check=True, capture_output=True)

    def test_an_amended_id_is_a_rename_not_a_deletion(self):
        # S1: a new slug for the same NNNN (the owner may amend ids, §17.4) wedged check and index.
        git = self._git
        self.p.task("0001-a")
        self.p.task("0002-old-slug")
        self.p.write("docs/delivery/tasks/notes.md", "a stray file, not a task\n")
        git("init", "-q")
        git("add", "-A")
        git("commit", "-qm", "log")
        git("rm", "-q", "docs/delivery/tasks/notes.md")
        old = self.p.root / "docs/delivery/tasks/0002-old-slug.md"
        old.rename(old.with_name("0002-new-slug.md"))
        new = old.with_name("0002-new-slug.md")
        new.write_text(new.read_text().replace("0002-old-slug", "0002-new-slug")
                       .replace("created:", "renamed_from: 0002-old-slug\ncreated:"))
        code, out = self._cli("index")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.errs(), [])
        git("add", "-A")
        git("commit", "-qm", "amend 0002's id; drop the stray file")
        self.assertEqual(self.errs(), [])
        self.assertEqual(tasklog.missing_task_files(self.p.cfg), [])

    def test_a_rename_that_does_not_say_so_is_a_reused_number(self):
        # Same NNNN, new slug, no renamed_from: indistinguishable from a reused number, so refused.
        self.p.task("0001-a")
        self.p.task("0002-old-slug")
        self.p.index()
        self._git("init", "-q")
        self._git("add", "-A")
        self._git("commit", "-qm", "log")
        old = self.p.root / "docs/delivery/tasks/0002-old-slug.md"
        new = old.with_name("0002-new-slug.md")
        new.write_text(old.read_text().replace("0002-old-slug", "0002-new-slug"))
        old.unlink()
        code, out = self._cli("index")
        self.assertEqual(code, 1, out)
        self.assertIn("0002-old-slug: its task file is gone (listed in INDEX.yaml) and its number now "
                      "belongs to 0002-new-slug", out)
        self.assertIn("`renamed_from: 0002-old-slug`", out)

    def test_a_deleted_tasks_number_reused_by_another_task_is_refused(self):
        # R1: delete 0002-b, then a later commit gives 0002 to an unrelated task.
        self.p.task("0001-a")
        gone = self.p.task("0002-b")
        self.p.index()
        self._git("init", "-q")
        self._git("add", "-A")
        self._git("commit", "-qm", "log")
        gone.unlink()
        self._git("add", "-A")
        self._git("commit", "-qm", "delete 0002-b")
        self.p.task("0002-something-else", title="Unrelated")
        self.p.index()
        self._git("add", "-A")
        self._git("commit", "-qm", "reuse 0002")
        self.assertFails("0002-b: its task file is gone (deleted in ")
        self.assertFails("its number now belongs to 0002-something-else. A number is never reused")

    def test_outside_git_the_index_on_disk_names_a_missing_file(self):
        self.p.task("0001-a")
        gone = self.p.task("0002-b")
        self.p.index()
        gone.unlink()
        self.assertIn("0002-b: its task file is gone (listed in INDEX.yaml). "
                      "A task file is never deleted: restore it with `status: dropped` and a note naming "
                      "what replaced it", self.errs())

    def test_a_later_task_named_as_a_prerequisite_in_prose_warns(self):
        # PROC-08: 0186 said "gated on 0197" in prose, where nothing holds it back; depends_on may point forward.
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace("- background", "- gated on 0003 being done; after 2026-10-18; "
                                                             "requires 0009, which does not exist"))
        self.p.task("0002-b", "done")
        self.p.task("0003-c")
        g = self.p.task("0004-d")
        g.write_text(g.read_text().replace("- background", "- blocked by `0003` (earlier: no warning)"))
        self.p.index()
        self.assertEqual(self.errs(), [])
        ws = tasklog.warnings(self.p.cfg)
        self.assertEqual(len(ws), 1, ws)
        self.assertIn("'gated on 0003' names 0003-c, which has a higher number", ws[0])
        self.assertIn("List it in depends_on", ws[0])
        code, out = self._cli("check")
        self.assertEqual(code, 0, out)
        self.assertIn("  warning: docs/delivery/tasks/0001-a.md: 'gated on 0003'", out)
        f.write_text(f.read_text().replace("status: pending", "status: dropped"))
        self.assertEqual(tasklog.warnings(self.p.cfg), [])

    def test_a_number_in_context_without_a_command_on_its_line_warns_and_does_not_fail(self):
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace("- background", "- only 2 call sites exist"))
        g = self.p.task("0002-b")
        g.write_text(g.read_text().replace("- background", "- `git grep -c foo` at abc1234: 2 call sites"))
        self.p.index()
        code, out = self._cli("check")
        self.assertEqual(code, 0, out)
        line = f.read_text().split("\n").index("- only 2 call sites exist") + 1
        self.assertIn(f"  warning: docs/delivery/tasks/0001-a.md:{line}: Context states a number (2)", out)
        self.assertNotIn("0002-b.md", out)
        for status in ("done", "dropped"):
            f.write_text(f.read_text().replace("status: pending", f"status: {status}"))
            self.assertEqual(tasklog.warnings(self.p.cfg), [], status)
            f.write_text(f.read_text().replace(f"status: {status}", "status: pending"))
        f.write_text(f.read_text().replace("## Context (not verified)\n\n- only 2 call sites exist",
                                           "## Context (not verified)\n\n- background\n\n## Scope\n\n- only 2"))
        self.assertEqual(tasklog.warnings(self.p.cfg), [], "a number outside Context is not read")
        f.write_text(f.read_text().replace("- background\n\n## Scope\n\n- only 2", "- only 2 call sites exist")
                     .replace("task_id: 0001-a", "task_id: a"))
        self.assertIn(f"0001-a.md:{line}: Context states a number (2)", "\n".join(tasklog.warnings(self.p.cfg)),
                      "a task id that does not parse as a number is still read")

    def test_what_counts_as_a_number_and_as_a_command_in_context(self):
        f = self.p.task("0001-a")
        quiet = ["1. per §31.1, R5, ADR-0033, PR #89 and task 0197, on 2026-11-12 at 07:57, sha abc1234",
                 "- the operator's ruling of 11 Nov 2026, and of November 11, 2026",
                 "- `ls src | wc -l` at abc1234 gives 12", "- `the 4 files`",
                 "```", "40 lines in a fence", "```"]
        loud = ["- `src/a.py` has 3 call sites", "- `src/a.py` has 7 call sites in `src/b.py`",
                "- the 9 sites (`x`), then `y`", "- it takes 40% of the run", "- 3.5 s per test", "- 0 callers"]
        f.write_text(f.read_text().replace("- background", "\n".join(quiet + loud)))
        lines = f.read_text().split("\n")
        ws = tasklog.warnings(self.p.cfg)
        self.assertEqual([w.split(": Context")[0] for w in ws],
                         [f"docs/delivery/tasks/0001-a.md:{lines.index(l) + 1}" for l in loud], ws)
        self.assertEqual([w.split("number (")[1].split(")")[0] for w in ws], ["3", "7", "9", "40", "3.5", "0"])

    def test_a_scope_path_marked_removed_is_not_warned_about_whether_or_not_it_exists(self):
        self.p.write("src/still_here.py", "x = 1\n")
        f = self.p.task("0001-a")
        f.write_text(f.read_text().replace(
            "- **In:** it", "- **In:** `src/retired.py` (removed), `src/still_here.py` (removed), `src/lost.py`"))
        self.p.index()
        code, out = self._cli("check")
        self.assertEqual(code, 0, out)
        self.assertIn("Scope names `src/lost.py`, which does not exist", out)
        self.assertNotIn("`src/retired.py`", out)
        self.assertNotIn("`src/still_here.py`", out)
        f.write_text(f.read_text().replace("`src/retired.py` (removed)", "`src/retired.py`"))
        self.assertIn("Scope names `src/retired.py`, `src/lost.py`, which does not exist", self._cli("check")[1])


if __name__ == "__main__":
    unittest.main()


class TemplatesStayValid(unittest.TestCase):
    """The plane's own example log passes `ccp tasks check` and INDEX is what `ccp tasks index` writes."""

    def test_examples(self):
        import shutil
        from pathlib import Path
        dd = Path(__file__).resolve().parent.parent / "templates" / "docs-delivery"
        p = Product()
        try:
            shutil.copy(dd / "example-plane.json", p.root / "docs/delivery/plane.json")
            for f in (dd / "example-tasks").glob("*.md"):
                shutil.copy(f, p.root / "docs/delivery/tasks" / f.name)
            shutil.copy(dd / "example-INDEX.yaml", p.root / "docs/delivery/INDEX.yaml")
            self.assertEqual(tasklog.check(p.cfg), [])
            self.assertEqual(tasklog.next_task(p.cfg)["task_id"], "0001-hello-delivery-log")
        finally:
            p.cleanup()


class DryRunLines(unittest.TestCase):
    """§21 task_log.dry_run: a check that runs a command records its dry run."""

    CHECKS = """## dod_checks

- id: `code-01`
  story: As a maintainer, the files stay in sync.
  steps:
    1. Run `ops/sync.py --check`.
  expect: exit 0.
{dry01}
- id: `code-02`
  story: As a maintainer, I read it.
  steps:
    1. Read `docs/x.md`.
  expect: it says so. A later run `x` is not a step.

- id: `code-03`
  story: As a maintainer, the call exists.
  steps:
    1. Read the notes.
    2. run `git grep -n "<the call 0323 publishes>" -- grok`.
  expect: one line.
{dry03}
"""

    def setUp(self):
        self.p = Product({"task_log": {"dry_run": True}})

    def tearDown(self):
        self.p.cleanup()

    def task(self, tid="0001-a", status="pending", dry01="", dry03=""):
        f = self.p.task(tid, status)
        text = f.read_text()
        start, end = text.index("## dod_checks"), text.index("## Implementation notes")
        f.write_text(text[:start] + self.CHECKS.format(dry01=dry01, dry03=dry03) + "\n" + text[end:])
        self.p.index()

    def dry_errs(self):
        return [e for e in tasklog.check(self.p.cfg) if "dry run" in e]

    def test_a_command_check_without_a_dry_run_fails_and_a_read_check_does_not(self):
        self.task()
        errs = self.dry_errs()
        self.assertEqual(len(errs), 2, errs)
        self.assertIn("docs/delivery/tasks/0001-a.md: dod_check `code-01` runs a command", errs[0])
        self.assertIn("WRITING-tasks.md", errs[0])
        self.assertIn("`code-03`", errs[1])  # a step's `run` in any case, not the first step

    def test_a_dry_run_line_or_a_reasoned_na_passes(self):
        self.task(dry01="  dry run (`86d135dd`): step 1 exited 0.", dry03="  dry run: n/a — 0323 publishes the call")
        self.assertEqual(self.dry_errs(), [])
        self.task(dry01="  dry run (86d135d): 12 lines.", dry03="  Dry run: n/a - not published yet")
        self.assertEqual(self.dry_errs(), [])

    def test_a_short_sha_or_a_bare_na_does_not_count(self):
        self.task(dry01="  dry run (`86d1`): ran it.", dry03="  dry run: n/a")
        self.assertEqual(len(self.dry_errs()), 2)

    def test_done_and_dropped_tasks_are_not_judged(self):
        self.task("0001-a", "done")
        self.task("0002-b", "dropped")
        self.assertEqual(self.dry_errs(), [])

    def test_a_line_counts_for_its_own_check_only_and_open_states_are_judged(self):
        self.task(dry01="  dry run (`86d135dd`): step 1 exited 0.")
        errs = self.dry_errs()
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("`code-03`", errs[0])
        for status in ("in_progress", "blocked"):
            self.task(status=status)
            self.assertEqual(len(self.dry_errs()), 2, status)

    def test_step_forms_a_writer_uses(self):
        forms = ("    1. Change the seed and run `app seed load`.",  # mid-sentence
                 "    1. Run\n       `make x`.",                    # the command wrapped
                 "    1) Run `x`.")
        for form in forms:
            self.task()
            f = self.p.root / "docs/delivery/tasks/0001-a.md"
            f.write_text(f.read_text().replace("    1. Run `ops/sync.py --check`.", form))
            errs = self.dry_errs()
            self.assertTrue(any("`code-01`" in e for e in errs), form)
        self.task()  # "rerun" or "run" outside a numbered step is not a command step: code-02 stays clean
        self.assertFalse(any("`code-02`" in e for e in self.dry_errs()))

    def test_records_say_something(self):
        # an indented record under a step, and a reason wrapped onto the next line, count
        self.task(dry01="      dry run (`86d135dd`): exit 0.", dry03="  dry run: n/a —\n    0323 adds the call")
        self.assertEqual(self.dry_errs(), [])
        # an empty record or the template's placeholder does not
        self.task(dry01="  dry run (`86d135dd`):", dry03="  dry run: n/a — <why>")
        self.assertEqual(len(self.dry_errs()), 2)

    def test_crlf_task_files_read_the_same(self):
        self.task(dry01="  dry run (`86d135dd`): exit 0.")
        f = self.p.root / "docs/delivery/tasks/0001-a.md"
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
        errs = self.dry_errs()
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("`code-03`", errs[0])

    def test_a_dry_run_quoting_soft_words_is_not_soft_language(self):
        soft = Product({"task_log": {"dry_run": True, "soft_words": ["should"]}})
        try:
            soft.task("0001-a")
            f = soft.root / "docs/delivery/tasks/0001-a.md"
            text = f.read_text()
            start, end = text.index("## dod_checks"), text.index("## Implementation notes")
            f.write_text(text[:start] + self.CHECKS.format(
                dry01="  dry run (`86d135dd`): printed 'it should load'.", dry03="  dry run: n/a — 0323 adds it")
                + "\n" + text[end:])
            soft.index()
            self.assertEqual([e for e in tasklog.check(soft.cfg) if "soft language" in e], [])
        finally:
            soft.cleanup()

    def test_off_by_default_and_must_be_a_bool(self):
        p = Product()
        try:
            p.task("0001-a")
            f = p.root / "docs/delivery/tasks/0001-a.md"
            f.write_text(f.read_text().replace("    1. run\n", "    1. Run `make x`.\n"))
            p.index()
            self.assertEqual([e for e in tasklog.check(p.cfg) if "dry run" in e], [])
        finally:
            p.cleanup()
        from ccp import config
        bad = Product({"task_log": {"dry_run": "yes"}})
        try:
            with self.assertRaises(config.ConfigError) as cm:
                _ = bad.cfg
            self.assertIn("task_log.dry_run must be true or false", str(cm.exception))
        finally:
            bad.cleanup()
