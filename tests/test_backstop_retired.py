"""ADR-0032 D2: the twelve-hour runaway backstop is retired. A task running for longer than twelve
hours is not blocked or flagged, and a queue whose last snapshot still carries backstop data
rebuilds cleanly (plane task 0001, check compat-01)."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

from tests.test_toolkit import ToolkitFixture

PLANE = Path(__file__).resolve().parents[1]
REBUILD = PLANE / "scripts/observability/rebuild-now.sh"
TID = "0002-second"
NOW = "2026-11-05T20:00:00Z"
STARTED = "2026-11-05T02:00:00Z"   # 18 hours before NOW: past the retired twelve-hour line


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

    def test_an_old_queue_rebuilds_and_nothing_is_blocked_by_a_backstop(self):
        env = {**os.environ, "QUEUE_ROOT": str(self.q), "OBS_NOW": NOW, "OBS_SKIP_PS": "1", "PROJECT_ID": "demo"}
        r = subprocess.run(["bash", str(REBUILD)], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        now = json.loads((self.q / "observability" / "now.json").read_text())
        row = next(t for t in now["tasks"] if t["task_id"] == TID)
        self.assertGreater(row["wall_hours"], 12)            # the wall timer still runs, as a diagnostic
        self.assertNotIn("backstop_breached", row)
        self.assertNotIn("backstop", {b["kind"] for b in now["blockers"]})
        status = (self.q / "observability" / "STATUS.md").read_text()
        self.assertNotIn("BREACH", status)

        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        board = json.loads(Path(body["board"]).read_text())
        self.assertNotIn("backstop", json.dumps(board.get("blockers") or []))


if __name__ == "__main__":
    unittest.main()
