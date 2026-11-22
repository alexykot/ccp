"""The runtime waits (SPEC §10.1, §23.2): lib's one table, what waiting_on's single writer accepts on `set`, the
task contract's enum and the §23.2 payload row; lib's one builder of the writer's command, the one `ccp` function and
the spec-question script's function that run it, and `ccp tasks wait`'s options."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from ccp import lifecycle, usage
from ccp.queue import QueueError
from tests.helpers import as_lead, PLANE_ROOT
from tests.toolkit_fixture import ToolkitFixture

PLANE = PLANE_ROOT
sys.path.insert(0, str(PLANE / "scripts" / "observability"))

import lib  # noqa: E402
import spec_maintainer as sm  # noqa: E402

WRITER = PLANE / "scripts" / "observability" / "set-waiting-on.sh"
TASK = "0001-a"


def spec_reasons() -> tuple[list[str], list[str]]:
    """The backticked names inside the parentheses after `reason` in §23.2's `waiting_on` `set` row: those before
    the `;`, and those after it."""
    text = (PLANE / "docs" / "spec" / "04-observability.md").read_text()
    row = next(x for x in text.splitlines() if x.startswith("| `waiting_on` | `set` |"))
    inside = re.search(r"`reason` \(([^)]*)\)", row)
    assert inside is not None, row
    written, _, read_only = inside.group(1).partition(";")
    names = re.compile(r"`([^`]+)`")
    return names.findall(written), names.findall(read_only)


class OneTable(unittest.TestCase):
    def test_the_task_contract_enum_is_lib_s_table(self) -> None:
        schema = json.loads((PLANE / "contracts" / "task.schema.json").read_text())
        enum = [x for x in schema["properties"]["waiting_on"]["enum"] if x is not None]
        self.assertEqual(sorted(enum), sorted(lib.WAIT_REASONS + lib.WAIT_READ_ONLY))
        self.assertFalse(set(lib.WAIT_REASONS) & set(lib.WAIT_READ_ONLY))

    def test_the_spec_row_names_the_written_and_the_read_only_reasons(self) -> None:
        written, read_only = spec_reasons()
        self.assertEqual(sorted(written), sorted(lib.WAIT_REASONS))
        self.assertEqual(sorted(read_only), sorted(lib.WAIT_READ_ONLY))


class TheWriter(unittest.TestCase):
    """set-waiting-on.sh, run on a scratch queue."""

    def setUp(self) -> None:
        self.q = Path(tempfile.mkdtemp())
        (self.q / "tasks").mkdir()
        self.put("design_seat")

    def tearDown(self) -> None:
        shutil.rmtree(self.q)

    def put(self, waiting: str | None) -> None:
        (self.q / "tasks" / f"{TASK}.json").write_text(json.dumps(
            {"task_id": TASK, "project_id": "demo", "waiting_on": waiting}))

    def waiting(self) -> str | None:
        return json.loads((self.q / "tasks" / f"{TASK}.json").read_text())["waiting_on"]

    def events(self) -> list[dict]:
        p = self.q / "observability" / "events.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def run_writer(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "ACTOR", "PROJECT_ID")}
        env["QUEUE_ROOT"] = str(self.q)
        return subprocess.run(["bash", str(WRITER), *args], capture_output=True, text=True, env=env, timeout=60)

    def test_set_accepts_every_reason_in_the_table(self) -> None:
        for reason in lib.WAIT_REASONS:
            proc = self.run_writer("set", TASK, reason)
            self.assertEqual(proc.returncode, 0, f"{reason}: {proc.stderr}")
            self.assertEqual(self.waiting(), reason)

    def test_set_steerer_is_refused_and_the_wait_is_unchanged(self) -> None:
        for reason in lib.WAIT_READ_ONLY:
            proc = self.run_writer("set", TASK, reason)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertEqual(self.waiting(), "design_seat")
        self.assertEqual(self.events(), [])

    def test_a_steerer_wait_from_an_older_queue_still_clears(self) -> None:
        self.put("steerer")
        proc = self.run_writer("clear", TASK, "spec_resolved")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsNone(self.waiting())
        self.assertEqual(self.events()[-1]["payload"]["was"], "steerer")


class WriterCommand(unittest.TestCase):
    """lib.wait_writer_cmd, the one builder of the writer's argv."""

    def test_the_writer_then_the_three_words_then_the_seat_then_each_option_set(self) -> None:
        cmd = lib.wait_writer_cmd("set", TASK, "quota", actor=lib.RUNNER, project_id="demo", task_only=True,
                                  quota_class="credit", resets_at="2026-11-21T10:00:00Z",
                                  planned_resume_at="2026-11-21T10:05:00Z", detail="why")
        self.assertEqual(Path(cmd[0]), WRITER)
        self.assertEqual(cmd[1:8], ["set", TASK, "quota", "--actor", lib.RUNNER, "--project-id", "demo"])
        self.assertEqual(cmd[-1], "--task-only")
        self.assertEqual(dict(zip(cmd[8:-1:2], cmd[9:-1:2])),
                         {"--quota-class": "credit", "--resets-at": "2026-11-21T10:00:00Z",
                          "--planned-resume-at": "2026-11-21T10:05:00Z", "--detail": "why"})

    def test_an_option_not_set_is_left_out(self) -> None:
        cmd = lib.wait_writer_cmd("clear", TASK, "released", actor=lib.RUNNER, project_id="demo", detail="")
        self.assertEqual(cmd[1:], ["clear", TASK, "released", "--actor", lib.RUNNER, "--project-id", "demo"])


class SpecQuestionSetWait(unittest.TestCase):
    """spec_maintainer.set_wait runs lib's command, the writer itself (no shell prefix), and dies on its failure."""

    def call(self, code: int = 0):
        done = subprocess.CompletedProcess([], code, "", "observability: no")
        with mock.patch.object(sm.subprocess, "run", return_value=done) as run:
            sm.set_wait(Path("/q"), "set", TASK, "spec_maintainer", lib.RUNNER, "demo", "sm-1",
                        resets_at="2026-11-21T10:00:00Z", quota_class="session")
        return run.call_args

    def test_it_runs_lib_s_command(self) -> None:
        call = self.call()
        self.assertEqual(call.args[0], lib.wait_writer_cmd(
            "set", TASK, "spec_maintainer", actor=lib.RUNNER, project_id="demo", quota_class="session",
            resets_at="2026-11-21T10:00:00Z", detail="sm-1"))
        self.assertEqual(call.kwargs["env"]["QUEUE_ROOT"], "/q")

    def test_a_failure_dies(self) -> None:
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(io.StringIO()):
            self.call(code=2)
        self.assertEqual(ctx.exception.code, 1)


class SetWait(unittest.TestCase):
    """lifecycle.set_wait, the writer's one caller in `ccp`, on plain values: the writer's process is mocked."""

    cfg = types.SimpleNamespace(project_id="demo")

    def call(self, code: int = 0, **kw):
        done = subprocess.CompletedProcess([], code, "", "observability: no")
        with mock.patch.object(lifecycle.subprocess, "run", return_value=done) as run:
            lifecycle.set_wait(self.cfg, Path("/q"), "set", TASK, "quota", **kw)
        return run.call_args

    def test_every_option_reaches_the_writer(self) -> None:
        call = self.call(actor=lib.LEAD, task_only=True, quota_class="credit", resets_at="2026-11-21T10:00:00Z",
                         planned_resume_at="2026-11-21T10:05:00Z", detail="why")
        cmd = call.args[0]
        self.assertEqual(Path(cmd[0]).name, WRITER.name)
        self.assertEqual(cmd[1:4], ["set", TASK, "quota"])
        pairs = dict(zip(cmd[4::2], cmd[5::2]))
        self.assertEqual(pairs["--actor"], lib.LEAD)
        self.assertEqual(pairs["--project-id"], "demo")
        self.assertEqual(pairs["--quota-class"], "credit")
        self.assertEqual(pairs["--resets-at"], "2026-11-21T10:00:00Z")
        self.assertEqual(pairs["--planned-resume-at"], "2026-11-21T10:05:00Z")
        self.assertEqual(pairs["--detail"], "why")
        self.assertIn("--task-only", cmd)
        self.assertEqual(call.kwargs["env"]["QUEUE_ROOT"], "/q")

    def test_without_options_the_actor_is_the_queue_s_and_work_json_is_not_left_alone(self) -> None:
        with as_lead():
            cmd = self.call().args[0]
        self.assertEqual(cmd[cmd.index("--actor") + 1], lib.LEAD)
        for flag in ("--task-only", "--quota-class", "--resets-at", "--planned-resume-at", "--detail"):
            self.assertNotIn(flag, cmd)

    def test_the_writer_s_exit_1_and_2_pass_through_and_any_other_failure_is_1(self) -> None:
        for writer, want in ((1, 1), (2, 2), (3, 1), (127, 1)):
            with self.assertRaises(QueueError) as ctx:
                self.call(code=writer)
            self.assertEqual(ctx.exception.code, want, writer)

    def test_a_writer_that_hangs_is_exit_1(self) -> None:
        late = subprocess.TimeoutExpired(["set-waiting-on.sh"], lifecycle.WAIT_WRITER_TIMEOUT_S)
        with mock.patch.object(lifecycle.subprocess, "run", side_effect=late), self.assertRaises(QueueError) as ctx:
            lifecycle.set_wait(self.cfg, Path("/q"), "clear", TASK, "released")
        self.assertEqual(ctx.exception.code, 1)


    def test_sync_clears_task_only_and_passes_the_writer_s_code_through(self) -> None:
        refused = QueueError("set-waiting-on: 0001-a: observability: no", 2)
        with mock.patch.object(lifecycle.runs, "abandon_task_runs"), \
                mock.patch.object(lifecycle, "set_wait", side_effect=refused) as sw, \
                self.assertRaises(QueueError) as ctx:
            lifecycle._apply(self.cfg, Path("/q"), TASK, {"waiting_on": "quota"}, "done")  # noqa: SLF001
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(sw.call_args.args[2:], ("clear", TASK, "done_in_log"))
        self.assertEqual(sw.call_args.kwargs, {"task_only": True})


    def test_lifting_a_park_is_task_only(self) -> None:
        with mock.patch.object(usage, "parked", return_value=[{"task_id": TASK}]), \
                mock.patch.object(lifecycle, "set_wait") as sw:
            self.assertTrue(usage.clear_park(self.cfg, Path("/q"), TASK))
        self.assertEqual(sw.call_args.args[2:], ("clear", TASK, "session_reset"))
        self.assertEqual(sw.call_args.kwargs, {"task_only": True})


class TasksWait(ToolkitFixture, unittest.TestCase):
    """`ccp tasks wait` end to end, on a scratch product."""

    def test_quota_class_reaches_the_task_s_queue_file(self) -> None:
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        code, _, out, err = self.ccp("tasks", "wait", "0002", "quota", "--quota-class", "credit",
                                     "--until", "2026-11-21T10:00:00Z")
        self.assertEqual(code, 0, out + err)
        st = json.loads((self.q / "tasks" / "0002-second.json").read_text())
        self.assertEqual((st["waiting_on"], st["quota_class"]), ("quota", "credit"))

    def test_steerer_is_refused_with_the_writer_s_exit_2(self) -> None:
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        code, _, out, err = self.ccp("tasks", "wait", "0002", "steerer")
        self.assertEqual(code, 2, out + err)
        self.assertIsNone(json.loads((self.q / "tasks" / "0002-second.json").read_text()).get("waiting_on"))

    def test_release_clears_the_wait_as_the_releasing_seat_task_only(self) -> None:
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        self.assertEqual(self.ccp("tasks", "wait", "0002", "design_seat", "--detail", "g-1")[0], 0)
        env = {k: v for k, v in os.environ.items() if k != "ACTOR"}  # the release's own default seat, the lead
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(lifecycle, "set_wait", wraps=lifecycle.set_wait) as sw:
            code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "re-planned")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(sw.call_args.kwargs, {"actor": lib.LEAD, "task_only": True})
        clear = [e for e in self.events() if (e["type"], e["op"]) == ("waiting_on", "clear")]
        self.assertEqual((clear[-1]["actor"], clear[-1]["payload"]["was"]), (lib.LEAD, "design_seat"))


if __name__ == "__main__":
    unittest.main()
