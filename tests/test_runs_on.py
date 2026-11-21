"""SPEC §5.5, §21.1: a dod_check the workers cannot take carries `runs_on: operator-machine` right after its
`setup:` line; `ccp tasks check` refuses another value or another place, `ccp tasks checks` reports each check's
mark, and `ccp tasks dry-run` does not run a marked check nor rewrite its dry-run line."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ccp import cli, config, dryrun, tasklog
from tests.helpers import TASK, Product
from tests.test_toolkit import ToolkitFixture, git

MARK = f"{tasklog.RUNS_ON_KEY}: {tasklog.RUNS_ON_OPERATOR}"
NA = "dry run: n/a — runs on the operator's machine"
FILE = "docs/delivery/tasks/0003-third.md"


def marked_check(cid: str = "dev-02", mark: str = MARK, cmd: str = "echo device") -> str:
    return (f"- id: `{cid}`\n  story: As an operator, the device answers.\n  setup: the build on the device.\n"
            f"  {mark}\n  steps:\n    1. Run `{cmd}`.\n  expect: it answers.\n  {NA}\n")


WORKERS = ("- id: `cmd-01`\n  story: As a writer, my check's command runs.\n  setup: a checkout.\n  steps:\n"
           "    1. Run `echo one`.\n  expect: prints one.\n")


def with_checks(text: str, checks: str) -> str:
    """`text`, a task file, with its dod_checks section's body replaced by `checks`."""
    head, rest = text.split("## dod_checks\n", 1)
    return f"{head}## dod_checks\n\n{checks}\n## Implementation notes{rest.split('## Implementation notes', 1)[1]}"


def task_text(tid: str, checks: str, status: str = "pending") -> str:
    ver = "- 2026-09-30 — `dev-02` pass — ran it" if status == "done" else "*Append-only.*"
    return with_checks(TASK.format(tid=tid, title="A task", status=status, deps="", ver=ver), checks)


class TheMark(unittest.TestCase):
    """The mark as the one parser reads it, and what is wrong with a mark, on plain values."""

    def test_a_marked_check_reads_operator_machine_and_an_unmarked_one_none(self):
        got = tasklog.checks(task_text("0001-a", WORKERS + "\n" + marked_check()))
        self.assertEqual([(c.id, c.runs_on, c.on_operator_machine) for c in got],
                         [("cmd-01", None, False), ("dev-02", tasklog.RUNS_ON_OPERATOR, True)])
        self.assertEqual([tasklog.runs_on_errors(c) for c in got], [[], []])

    def test_a_mark_after_a_wrapped_setup_is_right_after_it(self):
        text = task_text("0001-a", marked_check().replace("  setup: the build on the device.\n",
                                                          "  setup: the build on the device,\n    signed with the key: the operator's.\n"))
        (c,) = tasklog.checks(text)
        self.assertTrue(c.on_operator_machine)
        self.assertEqual(tasklog.runs_on_errors(c), [])

    def test_another_value_is_wrong(self):
        (c,) = tasklog.checks(task_text("0001-a", marked_check(mark=f"{tasklog.RUNS_ON_KEY}: operator-box")))
        self.assertEqual(c.runs_on, "operator-box")
        self.assertFalse(c.on_operator_machine)
        self.assertEqual(len(tasklog.runs_on_errors(c)), 1)
        self.assertIn("operator-box", tasklog.runs_on_errors(c)[0])

    def test_a_mark_anywhere_but_right_after_setup_is_wrong(self):
        base = marked_check().replace(f"  {MARK}\n", "")
        for line in ("  story: As an operator, the device answers.\n", "  steps:\n", "  expect: it answers.\n"):
            (c,) = tasklog.checks(task_text("0001-a", base.replace(line, f"{line}  {MARK}\n", 1)))
            self.assertTrue(c.on_operator_machine, line)
            self.assertEqual(len(tasklog.runs_on_errors(c)), 1, line)
        nested = base.replace("    1. Run", f"    {MARK}\n    1. Run")  # deeper than the check's keys
        (c,) = tasklog.checks(task_text("0001-a", nested))
        self.assertEqual(len(tasklog.runs_on_errors(c)), 1)
        under = marked_check().replace(f"  {MARK}\n", f"    {MARK}\n")  # read as the setup's wrapped line, no key
        (c,) = tasklog.checks(task_text("0001-a", under))
        self.assertIsNone(c.runs_on)
        self.assertEqual(len(tasklog.runs_on_errors(c)), 1)
        first = base.replace("  story:", f"  {MARK}\n  story:")  # no key before it
        (c,) = tasklog.checks(task_text("0001-a", first))
        self.assertEqual(len(tasklog.runs_on_errors(c)), 1)
        twice = marked_check().replace(f"  {MARK}\n", f"  {MARK}\n  {MARK}\n")
        (c,) = tasklog.checks(task_text("0001-a", twice))
        self.assertEqual(len(tasklog.runs_on_errors(c)), 1)


class TasksCheck(unittest.TestCase):
    """`ccp tasks check` on a product whose task carries a mark."""

    def setUp(self):
        self.p = Product({"task_log": {"dry_run": True}})
        self.addCleanup(self.p.cleanup)

    def errs(self, checks: str, status: str = "pending") -> list[str]:
        self.p.write("docs/delivery/tasks/0001-a.md", task_text("0001-a", checks, status))
        self.p.index()
        return tasklog.check(self.p.cfg)

    def test_a_marked_check_with_the_operator_machines_dry_run_line_passes(self):
        self.assertEqual(self.errs(WORKERS.replace("  expect: prints one.\n", "  expect: prints one.\n"
                                                   "  dry run: n/a — none yet.\n") + "\n" + marked_check()), [])

    def test_without_its_dry_run_line_a_marked_check_that_runs_a_command_is_refused(self):
        errs = self.errs(marked_check().replace(f"  {NA}\n", ""))
        self.assertEqual(len(errs), 1)
        self.assertIn("`dev-02`", errs[0])

    def test_another_value_is_refused_naming_the_task_and_the_check(self):
        errs = self.errs(marked_check(mark=f"{tasklog.RUNS_ON_KEY}: operator-box"))
        self.assertEqual(len(errs), 1)
        self.assertIn("0001-a.md", errs[0])
        self.assertIn("`dev-02`", errs[0])
        self.assertIn("operator-box", errs[0])

    def test_a_mark_after_steps_is_refused_naming_the_task_and_the_check(self):
        moved = marked_check().replace(f"  {MARK}\n", "").replace("  steps:\n", f"  steps:\n  {MARK}\n")
        errs = self.errs(moved)
        self.assertEqual(len(errs), 1)
        self.assertIn("0001-a.md", errs[0])
        self.assertIn("`dev-02`", errs[0])

    def test_a_done_tasks_wrong_mark_is_refused_too(self):
        errs = self.errs(marked_check(mark=f"{tasklog.RUNS_ON_KEY}: anywhere"), status="done")
        self.assertEqual(len(errs), 1)
        self.assertIn("`dev-02`", errs[0])


class TasksChecks(unittest.TestCase):
    """`ccp tasks checks <task> [--json]`: each check's id and mark, at the checkout."""

    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        self.p.write("docs/delivery/tasks/0001-a.md", task_text("0001-a", WORKERS + "\n" + marked_check()))

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_json_lists_each_check_with_its_runs_on_or_null(self):
        code, out, err = self.run_cli("tasks", "checks", "0001", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), [{"id": "cmd-01", "runs_on": None},
                                           {"id": "dev-02", "runs_on": tasklog.RUNS_ON_OPERATOR}])

    def test_text_gives_one_line_per_check(self):
        code, out, err = self.run_cli("tasks", "checks", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertEqual([line.split() for line in out.splitlines()],
                         [["cmd-01", "-"], ["dev-02", tasklog.RUNS_ON_OPERATOR]])

    def test_an_unknown_task_exits_2(self):
        code, out, err = self.run_cli("tasks", "checks", "0009", "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("0009", err)


class DryRunPlan(unittest.TestCase):
    def test_only_a_check_marked_operator_machine_is_left_out_and_printed_as_not_run(self):
        text = task_text("0001-a", WORKERS + "\n" + marked_check() + "\n"
                         + marked_check("dev-03", mark=f"{tasklog.RUNS_ON_KEY}: operator-box"))
        skip = dryrun.marked(text)
        self.assertEqual(skip, {"dev-02"})
        lines = dryrun.printout("0001-a", "abc1234", "origin/main", dryrun.plan(text), {}, skip)
        at = lines.index("  dev-02:")
        self.assertIn(dryrun.NOT_RUN, lines[at + 1])
        self.assertIn(tasklog.RUNS_ON_OPERATOR, lines[at + 1])
        self.assertEqual(lines[at + 2], "  dev-03:")


class DryRunCommand(ToolkitFixture, unittest.TestCase):
    """`ccp tasks dry-run --write` on a pending task with one workers' check and one marked check whose command
    would leave a file behind if it ran."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.trace = Path(tmp.name) / "marked-ran"
        self.write(FILE, task_text("0003-third", WORKERS + "\n" + marked_check(cmd=f"touch '{self.trace}'")))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", FILE, "docs/delivery/INDEX.yaml")
        git(self.main, "commit", "-qm", "add 0003")
        git(self.main, "push", "-q", "origin", "main")

    def test_write_runs_only_the_workers_check_and_keeps_the_marked_checks_line(self):
        before = (self.main / FILE).read_text()
        code, _, out, err = self.ccp("tasks", "dry-run", "0003", "--write", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertFalse(self.trace.exists())
        lines = out.splitlines()
        self.assertIn(dryrun.NOT_RUN, lines[lines.index("  dev-02:") + 1])
        after = (self.main / FILE).read_text()
        sha = git(self.main, "rev-parse", "--short=7", "origin/main")
        line = f"  dry run (`{sha}`): step 1 exited 0, 1 line, first: `one`."
        self.assertIn(f"  expect: prints one.\n{line}\n", after)
        self.assertEqual(after.replace(f"\n{line}", ""), before)
        self.assertIn(f"  {NA}\n", after)


if __name__ == "__main__":
    unittest.main()
