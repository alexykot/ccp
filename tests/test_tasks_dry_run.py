"""SPEC §21.1 `ccp tasks dry-run`: a task's dod_check commands run at the integration tip in a temporary
worktree, their output printed and, with `--write`, written as each check's dry-run record; a done, dropped
or claimed task is refused (§10.5)."""
from __future__ import annotations

import unittest

from ccp import config, dryrun, tasklog
from tests.helpers import TASK, Product
from tests.test_toolkit import ToolkitFixture, git

CHECKS = """- id: `cmd-01`
  story: As a writer, my check's command runs.
  steps:
    1. Run `echo one`.
  expect: prints one.

- id: `cmd-02`
  story: As a writer, a prose step is not run.
  steps:
    1. Open the board and read it.
  expect: it reads.
  dry run: n/a — a prose step.
"""
FILE = "docs/delivery/tasks/0003-third.md"


def with_checks(text: str, checks: str) -> str:
    head, rest = text.split("## dod_checks\n", 1)
    return f"{head}## dod_checks\n\n{checks}\n## Implementation notes{rest.split('## Implementation notes', 1)[1]}"


class StepsAndRecords(unittest.TestCase):
    """What a dry run runs and what it writes, on plain values."""

    def test_only_a_step_that_is_one_backticked_command_and_nothing_else_is_run(self):
        block = ("\n  steps:\n    1. Run `echo one`.\n    2. run ``echo `two` ``\n    3. On the head, run `echo three`.\n"
                 "    4. Run `a` and `b`.\n    5. Run `ccp tasks check\n       --lease`.\n    6. Read the log.\n"
                 "  expect: fine.\n  dry run: n/a — none yet.\n")
        self.assertEqual(tasklog.check_steps(block),
                         [("1", "echo one"), ("2", "echo `two`"), ("3", None), ("4", None),
                          ("5", "ccp tasks check --lease"), ("6", None)])

    def test_write_replaces_a_record_there_adds_a_missing_one_and_changes_nothing_else(self):
        text = with_checks(TASK.format(tid="0003-third", title="Third", status="pending", deps="", ver="*x*"),
                           CHECKS.replace("  dry run: n/a — a prose step.\n", "")
                           + "\n- id: `cmd-03`\n  story: s.\n  steps:\n    1. Run `true`.\n  expect: e.\n"
                             "  dry run (`aaaaaaa`): old,\n    wrapped onto a second line.\n")
        new = tasklog.with_dry_runs(text, "bbbbbbb", {"cmd-01": "R1.", "cmd-03": "R3."})
        self.assertIn("  expect: prints one.\n  dry run (`bbbbbbb`): R1.\n\n- id: `cmd-02`", new)
        self.assertIn("  expect: e.\n  dry run (`bbbbbbb`): R3.\n", new)
        self.assertNotIn("wrapped onto", new)
        back = new.replace("\n  dry run (`bbbbbbb`): R1.", "").replace(
            "dry run (`bbbbbbb`): R3.", "dry run (`aaaaaaa`): old,\n    wrapped onto a second line.")
        self.assertEqual(back, text)
        self.assertEqual(tasklog.with_dry_runs(text, "bbbbbbb", {}), text)

    def test_the_record_gives_each_step_its_exit_code_line_count_and_first_line(self):
        ran = [dryrun.outcome("1", "x", 0, "one\ntwo\n"), dryrun.outcome("2", "y", 2, ""),
               dryrun.outcome("3", "z", None, "a `tick`\n")]
        self.assertEqual([(r.code, r.lines, r.first) for r in ran], [(0, 2, "one"), (2, 0, ""), (None, 1, "a `tick`")])
        rec = dryrun.record(ran)
        self.assertIn("exited 0, 2 lines", rec)
        self.assertIn("`` a `tick` ``", rec)
        self.assertIn(f"after {dryrun.STEP_TIMEOUT_S} s", rec)
        self.assertEqual(len(dryrun.outcome("1", "x", 0, "y" * 1000).first), dryrun.FIRST_LINE_CAP + 1)

    def test_a_done_dropped_or_claimed_task_is_refused(self):
        self.assertIsNone(dryrun.refusal("t", "pending", False))
        for status in tasklog.TERMINAL:
            self.assertIsNotNone(dryrun.refusal("t", status, False))
        self.assertIsNotNone(dryrun.refusal("t", "pending", True))
        self.assertTrue(dryrun.claimed({"lease_holder": "runner", "status": "implementing"}))
        self.assertFalse(dryrun.claimed({"lease_holder": "runner", "status": "done"}))
        self.assertFalse(dryrun.claimed({"lease_holder": None}))


class ConfigLoad(unittest.TestCase):
    def test_a_check_may_load_the_config_from_a_str(self):
        p = Product()
        self.addCleanup(p.cleanup)
        self.assertEqual(config.load(str(p.root)).project_id, p.cfg.project_id)
        self.assertEqual(config.load(str(p.root)).root, p.root)


class DryRunCommand(ToolkitFixture, unittest.TestCase):
    """The command against a product with a bare origin and a clone: 0003 pending with a check that runs
    `echo one` and one whose step is prose; 0002 claimed."""

    def setUp(self):
        super().setUp()
        text = TASK.format(tid="0003-third", title="Third", status="pending", deps="", ver="*Append-only.*")
        self.write(FILE, with_checks(text, CHECKS))
        tasklog.write_index(self.cfg_main())
        git(self.main, "add", FILE, "docs/delivery/INDEX.yaml")
        git(self.main, "commit", "-qm", "add 0003")
        git(self.main, "push", "-q", "origin", "main")
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def dry_run(self, *args: str):
        code, _, out, err = self.ccp("tasks", "dry-run", *args, root=self.main)
        return code, out, err

    def test_a_dry_run_leaves_the_checkout_as_it_was(self):
        before = git(self.main, "worktree", "list").splitlines()
        code, out, err = self.dry_run("0003")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(git(self.main, "worktree", "list").splitlines()), len(before))
        self.assertEqual(git(self.main, "status", "--porcelain"), "")
        lines = out.splitlines()
        first, second = lines.index("  cmd-01:"), lines.index("  cmd-02:")
        self.assertIn("exited 0, 1 line, first: `one`", lines[first + 1])
        self.assertIn(dryrun.NOT_RUN, lines[second + 1])
        self.assertIn(git(self.main, "rev-parse", "--short=7", "origin/main"), lines[0])

    def test_write_sets_the_run_checks_record_and_keeps_the_others(self):
        before = (self.main / FILE).read_text()
        code, out, err = self.dry_run("0003", "--write")
        self.assertEqual(code, 0, out + err)
        after = (self.main / FILE).read_text()
        sha = git(self.main, "rev-parse", "--short=7", "origin/main")
        line = f"  dry run (`{sha}`): step 1 exited 0, 1 line, first: `one`."
        self.assertIn(f"  expect: prints one.\n{line}\n", after)
        self.assertEqual(after.replace(f"\n{line}", ""), before)
        self.assertEqual(tasklog.check(self.cfg_main()), [])

    def test_a_claimed_task_is_refused_and_nothing_written(self):
        before = (self.main / "docs/delivery/tasks/0002-second.md").read_text()
        worktrees = git(self.main, "worktree", "list")
        code, out, err = self.dry_run("0002", "--write")
        self.assertNotEqual(code, 0, out + err)
        self.assertEqual((self.main / "docs/delivery/tasks/0002-second.md").read_text(), before)
        self.assertEqual(git(self.main, "worktree", "list"), worktrees)
        self.assertEqual(git(self.main, "status", "--porcelain"), "")

    def test_a_done_task_is_refused(self):
        code, out, err = self.dry_run("0001", "--write")
        self.assertEqual(code, dryrun.REFUSED, out + err)
        self.assertEqual(git(self.main, "status", "--porcelain"), "")

    def cfg_main(self):
        return config.load(self.main)


if __name__ == "__main__":
    unittest.main()
