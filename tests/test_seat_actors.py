"""SPEC §18.3, house rule E9: the seat ids are `task-runner`, `task-verifier` and `design-seat`. The retired
watchdog seat is a value only read: a row an old ledger holds still validates and folds, and nothing writes one.
A seat's heartbeat records its last wake and no cadence."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import queue
from tests.helpers import PLANE_ROOT

OBS = PLANE_ROOT / "scripts" / "observability"
sys.path.insert(0, str(OBS))

import lib  # noqa: E402

RETIRED = "delivery-watchdog"
WAKE = "2026-10-01T10:00:00Z"
OLD_ROW = {"at": WAKE, "project_id": "demo", "task_id": "", "actor": RETIRED, "type": "seat", "op": "heartbeat",
           "payload": {"seat_id": RETIRED, "wake_kind": "cron", "action_summary": "tick",
                       "cron_expected": "*/30 * * * *"}}


class SeatActors(unittest.TestCase):
    def setUp(self) -> None:
        self.q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.q)

    def heartbeat(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k not in ("ACTOR", "QUEUE_ROOT")}
        env["QUEUE_ROOT"] = str(self.q)
        env["PROJECT_ID"] = "demo"
        return subprocess.run(["bash", str(OBS / "heartbeat.sh"), *args], capture_output=True, text=True, env=env,
                              timeout=60)

    def test_a_ledger_holding_a_watchdog_row_folds_with_the_seats_last_wake(self) -> None:
        ledger = lib.events_path(self.q)
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps(OLD_ROW) + "\n")
        events = lib.load_events(ledger)
        self.assertEqual([lib.validate_event(ev, reading=True) for ev in events], [[]])
        seats: dict = {}
        for ev in events:
            lib.apply_event({}, seats, {}, ev)
        self.assertEqual(seats[RETIRED]["last_wake_at"], WAKE)
        self.assertNotIn("cron_expected", seats[RETIRED])

    def test_a_watchdog_row_is_refused_where_a_row_is_written(self) -> None:
        self.assertIn(f"invalid actor '{RETIRED}'", lib.validate_event(OLD_ROW))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            lib.append_event(self.q, OLD_ROW)
        self.assertIn("invalid actor", err.getvalue())
        self.assertFalse(lib.events_path(self.q).exists())

    def test_the_watchdog_is_no_seat_and_no_actor_ccp_records_as(self) -> None:
        self.assertEqual(lib.SEAT_IDS, (lib.RUNNER, lib.VERIFIER, lib.LEAD))
        self.assertNotIn(RETIRED, lib.ACTORS)
        self.assertIn(RETIRED, lib.LEGACY_ACTORS)
        with mock.patch.dict(os.environ, {"ACTOR": RETIRED}):
            self.assertEqual(queue.actor(), lib.RUNNER)
            self.assertEqual(queue.actor(lib.LEAD), lib.LEAD)

    def test_a_run_s_seat_maps_to_the_verifier_s_actor_or_else_the_runner_s(self) -> None:
        self.assertEqual(queue.seat_actor("verifier"), lib.VERIFIER)
        for seat in ("implementer", "reviewer", "runner", None):
            self.assertEqual(queue.seat_actor(seat), lib.RUNNER, seat)

    def test_heartbeat_refuses_the_watchdog_and_writes_the_lead_with_no_cadence(self) -> None:
        r = self.heartbeat(RETIRED, "--wake-kind", "manual")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse((self.q / "observability" / "seats" / f"{RETIRED}.json").exists())
        r = self.heartbeat(lib.LEAD, "--wake-kind", "manual")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        seat = json.loads((self.q / "observability" / "seats" / f"{lib.LEAD}.json").read_text())
        self.assertEqual((seat["wake_kind"], seat["last_action"]), ("manual", "wake"))
        self.assertNotIn("cron_expected", seat)
        row = json.loads(lib.events_path(self.q).read_text().splitlines()[-1])
        self.assertNotIn("cron_expected", row["payload"])

    def test_heartbeat_defaults_to_a_manual_wake_and_takes_no_cadence_option(self) -> None:
        r = self.heartbeat(lib.RUNNER)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads((self.q / "observability" / "seats" / f"{lib.RUNNER}.json").read_text())["wake_kind"],
                         "manual")
        r = self.heartbeat(lib.RUNNER, "--cron-expected", "event")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unknown arg", r.stderr)

    def test_a_fresh_seat_folds_with_no_cadence(self) -> None:
        self.assertEqual(lib.empty_seat(), {"last_wake_at": None, "wake_kind": None, "last_action": ""})


if __name__ == "__main__":
    unittest.main()
