"""SPEC §23.4, ADR-0034 D7: the board is the status. Nothing writes or reads the older snapshot: its
scripts are gone, no command leaves a snapshot file in the queue, an old one left there is ignored, and
`ccp board status` lists the waits, gates and questions the snapshot used to show."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.test_toolkit import ToolkitFixture

PLANE = Path(__file__).resolve().parents[1]
OBS = PLANE / "scripts/observability"
SNAPSHOT = ("now.json", "STATUS.md")


class SnapshotRetired(ToolkitFixture, unittest.TestCase):
    def test_the_snapshot_scripts_are_gone(self):
        for name in ("rebuild-now.sh", "status.sh"):
            self.assertFalse((OBS / name).exists(), name)

    def test_no_command_writes_a_snapshot(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("tasks", "wait", "0002", "design_seat", "--detail", "x")
        self.assertEqual(self.ccp("board", "build")[0], 0)
        self.ccp("board", "status")
        # The shared ledger library is no longer a snapshot command.
        subprocess.run([sys.executable, str(OBS / "lib.py"), "rebuild", "--queue-root", str(self.q)],
                       capture_output=True, text=True, timeout=60)
        subprocess.run([sys.executable, str(OBS / "lib.py"), "status", "--queue-root", str(self.q)],
                       capture_output=True, text=True, timeout=60)
        for name in SNAPSHOT:
            self.assertFalse((self.q / "observability" / name).exists(), name)

    def test_an_old_snapshot_left_in_the_queue_is_ignored(self):
        obs = self.q / "observability"
        obs.mkdir(parents=True, exist_ok=True)
        old = json.dumps({"schema_version": 1, "project_id": "demo", "generated_at": "2026-11-01T00:00:00Z",
                          "tasks": [{"task_id": "0002-second", "runtime_status": "implementing",
                                     "waiting_on": "quota"}],
                          "blockers": [{"task_id": "0002-second", "kind": "quota", "since": "2026-11-01T00:00:00Z",
                                        "detail": "waiting_on=quota"}]})
        (obs / "now.json").write_text(old)
        (obs / "STATUS.md").write_text("- **quota** `0002-second`\n")
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        board = json.loads(Path(body["board"]).read_text())
        self.assertEqual((board["blockers"], board["now"]["waits"]), ([], []))
        code, _, out, err = self.ccp("board", "status")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("quota", out)
        self.assertEqual((obs / "now.json").read_text(), old)   # read by nothing, rewritten by nothing

    def test_board_status_lists_a_wait_a_gate_and_a_question_and_exits_non_zero(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("tasks", "wait", "0002", "design_seat", "--detail", "x")
        g = self.q / "escalations/0002-second/1.json"
        g.parent.mkdir(parents=True)
        g.write_text(json.dumps({"escalation_id": "0002-second-1", "task_id": "0002-second", "status": "open",
                                 "class": "operator", "brief": "run it by hand"}))
        (self.q / "questions").mkdir()
        (self.q / "questions/sm-1.json").write_text(json.dumps(
            {"question_id": "sm-1", "task_id": "0002-second", "status": "open"}))
        code, _, out, _ = self.ccp("board", "status")
        self.assertEqual(code, 1, out)
        self.assertIn("waiting: 0002-second on design_seat", out)
        self.assertIn("gate 0002-second-1 (operator) open", out)
        self.assertIn("question sm-1 open", out)


if __name__ == "__main__":
    unittest.main()
