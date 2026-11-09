"""ADR-0032 D2: the twelve-hour runaway backstop is retired. A task running for longer than twelve
hours is not blocked or flagged, and a queue whose last snapshot (retired, §23.4) still carries
backstop data builds a board cleanly."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.test_toolkit import ToolkitFixture

TID = "0002-second"
STARTED = "2026-11-05T02:00:00Z"   # long before any run of this test: past the retired twelve-hour line


class BackstopRetired(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        obs = self.q / "observability"
        obs.mkdir(exist_ok=True)
        events = [
            {"at": STARTED, "project_id": "demo", "task_id": TID, "actor": "task-runner",
             "type": "phase", "op": "transition", "payload": {"from": "leased", "to": "implementing"}},
        ]
        (obs / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / f"{TID}.json").write_text(json.dumps(
            {"task_id": TID, "status": "implementing", "phase": "implementing",
             "implementation_started_at": STARTED, "lease_holder": "runner"}))
        # The last snapshot, written before the backstop was retired, still carries its fields.
        (obs / "now.json").write_text(json.dumps({
            "schema_version": 1, "project_id": "demo", "generated_at": "2026-11-05T19:00:00Z",
            "tasks": [{"task_id": TID, "runtime_status": "implementing", "wall_hours": 17.0,
                       "backstop_hours": 12, "backstop_breached": True}],
            "blockers": [{"task_id": TID, "kind": "backstop", "since": STARTED,
                          "detail": "wall_hours=17.0 >= 12.0 and runtime_status=implementing"}],
        }))

    def test_an_old_queue_builds_and_nothing_is_blocked_by_a_backstop(self):
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        board = json.loads(Path(body["board"]).read_text())
        self.assertNotIn("backstop", json.dumps(board.get("blockers") or []))
        code, _, out, err = self.ccp("board", "status")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("backstop", out)


if __name__ == "__main__":
    unittest.main()
