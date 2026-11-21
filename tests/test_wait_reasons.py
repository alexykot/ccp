"""The runtime waits (SPEC §10.1, §23.2): lib's one table, what waiting_on's single writer accepts on `set`, the
task contract's enum and the §23.2 payload row; the one `ccp` function that calls the writer, and `ccp tasks wait`'s
options."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from ccp import lifecycle
from ccp.queue import QueueError
from tests.test_toolkit import ToolkitFixture

PLANE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLANE / "scripts" / "observability"))

import lib  # noqa: E402

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


class SetWait(unittest.TestCase):
    """lifecycle.set_wait, the writer's one caller in `ccp`, on plain values: the writer's process is mocked."""

    cfg = types.SimpleNamespace(project_id="demo")

    def call(self, code: int = 0, **kw):
        done = subprocess.CompletedProcess([], code, "", "observability: no")
        with mock.patch.object(lifecycle.subprocess, "run", return_value=done) as run:
            lifecycle.set_wait(self.cfg, Path("/q"), "set", TASK, "quota", **kw)
        return run.call_args

    def test_every_option_reaches_the_writer(self) -> None:
        call = self.call(actor="design-seat", task_only=True, quota_class="credit", resets_at="2026-11-21T10:00:00Z",
                         planned_resume_at="2026-11-21T10:05:00Z", detail="why")
        cmd = call.args[0]
        self.assertEqual(Path(cmd[0]).name, WRITER.name)
        self.assertEqual(cmd[1:4], ["set", TASK, "quota"])
        pairs = dict(zip(cmd[4::2], cmd[5::2]))
        self.assertEqual(pairs["--actor"], "design-seat")
        self.assertEqual(pairs["--project-id"], "demo")
        self.assertEqual(pairs["--quota-class"], "credit")
        self.assertEqual(pairs["--resets-at"], "2026-11-21T10:00:00Z")
        self.assertEqual(pairs["--planned-resume-at"], "2026-11-21T10:05:00Z")
        self.assertEqual(pairs["--detail"], "why")
        self.assertIn("--task-only", cmd)
        self.assertEqual(call.kwargs["env"]["QUEUE_ROOT"], "/q")

    def test_without_options_the_actor_is_the_queue_s_and_work_json_is_not_left_alone(self) -> None:
        with mock.patch.dict(os.environ, {"ACTOR": "task-runner"}):
            cmd = self.call().args[0]
        self.assertEqual(cmd[cmd.index("--actor") + 1], "task-runner")
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


if __name__ == "__main__":
    unittest.main()
