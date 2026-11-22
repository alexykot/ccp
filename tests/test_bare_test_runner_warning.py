"""SPEC §21.1: `ccp tasks check` warns about a task not yet done with a check step that runs the language pack's
test command outside `ccp suite run`, naming the checks, so the run is recorded and its log can be cited."""
from __future__ import annotations

import unittest

from ccp import doclang, tasklog
from ccp.config import lane_for
from tests.helpers import TASK, Product

RUNNER = doclang.get("python").test_command
REL = "docs/delivery/tasks/0001-a.md"
PART = "part"
BARE_STEP = "python3 -B -m unittest -v tests.x 2>&1 | grep OK"
SUITE_RUN_STEP = "CCP_DEV=1 ./bin/ccp suite run --lane part -- python3 -m unittest tests.x"


def task_text(*steps: str, status: str = "pending") -> str:
    """A task file whose dod_checks are `cmd-01`, `cmd-02`…, each with one step running the given command."""
    text = TASK.format(tid="0001-a", title="A task", status=status, deps="", ver="*Append-only.*")
    head, rest = text.split("- id: `cmd-01`", 1)
    tail = rest.split("\n## Implementation notes", 1)[1]
    checks = "".join(f"- id: `cmd-{n:02d}`\n  story: As an operator, I run it.\n  steps:\n    1. Run `{s}`.\n"
                     "  expect: exit 0\n  dry run: n/a — a fixture\n\n" for n, s in enumerate(steps, 1))
    return head + checks + "## Implementation notes" + tail


def warned(*steps: str, status: str = "pending", runner: str | None = RUNNER) -> list[str]:
    return tasklog.bare_runner({"_text": task_text(*steps, status=status), "status": status}, REL, runner, PART)


class BareRunnerWarning(unittest.TestCase):
    def test_a_pending_task_running_the_tests_bare_gets_one_warning_naming_the_check(self):
        got = warned(BARE_STEP)
        self.assertEqual(len(got), 1, got)
        self.assertTrue(got[0].startswith(f"{REL}: "), got)
        self.assertIn("`cmd-01`", got[0])
        self.assertIn(f"`{RUNNER}`", got[0])
        self.assertIn(f"--lane {PART} --", got[0])

    def test_two_bare_checks_share_one_warning_and_a_clean_check_is_not_named(self):
        got = warned(BARE_STEP, "git diff --stat", f"timeout 60 env A=1 time {BARE_STEP}")
        self.assertEqual(len(got), 1, got)
        self.assertIn("`cmd-01`, `cmd-03`", got[0])
        self.assertNotIn("cmd-02", got[0])

    def test_a_run_through_ccp_suite_run_is_not_bare(self):
        self.assertEqual(warned(SUITE_RUN_STEP), [])
        self.assertEqual(warned("ccp suite run --lane part -- python3 -m unittest tests.x | grep OK"), [])

    def test_a_done_or_dropped_task_s_bare_step_is_not_warned(self):
        for status in tasklog.TERMINAL:
            with self.subTest(status=status):
                self.assertEqual(warned(BARE_STEP, status=status), [])

    def test_a_pack_with_no_test_command_warns_of_no_bare_step(self):
        self.assertEqual(warned(BARE_STEP, runner=None), [])
        self.assertEqual(warned(BARE_STEP, runner=doclang.get("none").test_command), [])


class RunsBare(unittest.TestCase):
    """`runs_bare` on one simple command's words."""

    def bare(self, cmd: str) -> bool:
        return tasklog.runs_bare(tasklog._tokens(cmd), tasklog._tokens(RUNNER))

    def test_bare_past_assignments_env_time_timeout_and_dash_words(self):
        for cmd in ("python3 -m unittest", "python3 -B -m unittest -q tests.x", "PYTHONPATH=. python3 -m unittest",
                    "env A=1 python3 -m unittest tests.x", "time python3 -m unittest", "timeout 30 python3 -m unittest"):
            with self.subTest(cmd=cmd):
                self.assertTrue(self.bare(cmd))

    def test_a_ccp_command_or_another_command_is_not_bare(self):
        for cmd in ("ccp suite run --lane part -- python3 -m unittest", "./bin/ccp mutate --test tests.x",
                    "A=1 bin/ccp suite run --lane part -- python3 -m unittest tests.x", "python3 -c 'import unittest'",
                    "git grep -n unittest", "python3 -X dev -m unittest", "timeout python3 -m unittest"):
            with self.subTest(cmd=cmd):
                self.assertFalse(self.bare(cmd))


class TasksCheckWiring(unittest.TestCase):
    """`tasklog.warnings` reads the product's pack and part lane; the branches are `BareRunnerWarning`'s (E15)."""

    def test_tasks_check_warns_on_a_bare_step_with_the_pack_s_command_and_part_lane(self):
        p = Product({"language": "python"})
        self.addCleanup(p.cleanup)
        p.task("0001-a", body=task_text(BARE_STEP))
        p.index()
        cfg = p.cfg
        got = [w for w in tasklog.warnings(cfg) if "outside `ccp suite run`" in w]
        self.assertEqual(len(got), 1, got)
        self.assertIn(f"`{RUNNER}`", got[0])
        self.assertIn(f"--lane {lane_for(cfg, 'part')} --", got[0])


if __name__ == "__main__":
    unittest.main()
