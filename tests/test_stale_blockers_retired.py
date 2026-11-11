"""ADR-0034 D6, SPEC §18.3: no seat stale rule and no verify-stale blocker. The board raises neither
for a silent seat or a verifier with no progress, ignores the binding's old threshold knob, heartbeats
are still recorded, and a queue whose last snapshot (retired, §23.4) carries the retired blockers
still builds."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

from tests.test_toolkit import ToolkitFixture

PLANE = Path(__file__).resolve().parents[1]
OBS = PLANE / "scripts/observability"
TID = "0002-second"
NOW = "2026-11-06T20:00:00Z"
SUBMITTED = "2026-11-06T14:00:00Z"   # six hours before NOW: far past the retired 30-minute threshold
OLD_WAKE = "2026-11-06T10:00:00Z"    # a */10 seat silent for ten hours while a task is mid-flight
RETIRED = {"stale_seat", "verify_stale"}


class StaleBlockersRetired(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        obs = self.q / "observability"
        (obs / "seats").mkdir(parents=True, exist_ok=True)
        ev = {"project_id": "demo", "task_id": TID, "actor": "task-runner", "type": "phase", "op": "transition"}
        (obs / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in (
            {**ev, "at": "2026-11-06T09:00:00Z", "payload": {"from": "leased", "to": "implementing"}},
            {**ev, "at": SUBMITTED, "payload": {"from": "implementing", "to": "submitted"}},
            {"at": OLD_WAKE, "project_id": "demo", "task_id": "", "actor": "task-runner", "type": "seat",
             "op": "heartbeat", "payload": {"seat_id": "task-runner", "wake_kind": "cron",
                                            "action_summary": "wake", "cron_expected": "*/10 * * * *"}},
        )))
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / f"{TID}.json").write_text(json.dumps(
            {"task_id": TID, "status": "submitted", "phase": "submitted", "updated_at": SUBMITTED}))
        # A binding that still sets the retired threshold, at its smallest value.
        (self.q / "project.yaml").write_text(
            "project_id: demo\nqueue_root: /tmp/q\ncadence:\n  verifier: event\n  verify_stale_minutes: 1\n")
        self.old_now = {
            "schema_version": 1, "project_id": "demo", "generated_at": "2026-11-06T19:00:00Z",
            "seats": {"task-runner": {"last_wake_at": OLD_WAKE, "wake_kind": "cron", "last_action": "wake",
                                      "cron_expected": "*/10 * * * *", "stale": True}},
            "tasks": [{"task_id": TID, "runtime_status": "submitted"}],
            "blockers": [{"task_id": TID, "kind": "stale_seat", "since": OLD_WAKE, "detail": "task-runner stale"},
                         {"task_id": TID, "kind": "verify_stale", "since": SUBMITTED, "detail": "no verdict"}],
        }
        (obs / "now.json").write_text(json.dumps(self.old_now))

    def obs_env(self, **extra):
        return {**os.environ, "QUEUE_ROOT": str(self.q), "OBS_NOW": NOW, "OBS_SKIP_PS": "1", "PROJECT_ID": "demo",
                **extra}

    def run_obs(self, script, *args, **extra):
        return subprocess.run(["bash", str(OBS / script), *args], env=self.obs_env(**extra),
                              capture_output=True, text=True, timeout=60)

    def test_the_board_and_its_status_raise_neither_blocker(self):
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        board = Path(body["board"]).read_text()
        for kind in RETIRED:
            self.assertNotIn(kind, board)
        code, _, out, err = self.ccp("board", "status")
        self.assertEqual(code, 0, out + err)
        for kind in RETIRED:
            self.assertNotIn(kind, out)

    def test_the_board_builds_over_an_old_snapshot_it_never_rebuilt(self):
        # The board reads no snapshot (§23.4): the old one's retired blockers add nothing to it, and
        # the file is left as it was.
        snap = self.q / "observability" / "now.json"
        old = snap.read_text()
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        over_old = json.loads(Path(body["board"]).read_text())
        self.assertEqual(snap.read_text(), old)
        snap.unlink()
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(over_old["blockers"], json.loads(Path(body["board"]).read_text())["blockers"])
        for kind in RETIRED:
            self.assertNotIn(kind, json.dumps(over_old))

    def test_an_old_seat_stale_flag_alone_is_not_a_blocker(self):
        (self.q / "observability" / "now.json").write_text(json.dumps({**self.old_now, "blockers": []}))
        code, _, out, err = self.ccp("board", "status")
        self.assertEqual(code, 0, out + err)

    def test_heartbeats_are_still_written(self):
        r = self.run_obs("heartbeat.sh", "task-verifier", "--wake-kind", "priority", "--task-id", TID)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        seat = json.loads((self.q / "observability" / "seats" / "task-verifier.json").read_text())
        self.assertTrue(seat["last_wake_at"])
        last = json.loads((self.q / "observability" / "events.jsonl").read_text().splitlines()[-1])
        self.assertEqual((last["type"], last["op"], last["payload"]["seat_id"]), ("seat", "heartbeat", "task-verifier"))
        code, _, out, err = self.ccp("board", "status")
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
