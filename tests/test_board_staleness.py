"""SPEC §28: work.json and runs/*.json are written only at
phase changes, so a phase longer than STALE_MINUTES is not a stale source while its open run's
telemetry or suite rows are fresh. With everything old, they are still stale."""
from __future__ import annotations

import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ccp import board, usage
from tests.test_toolkit import ToolkitFixture

RUN = "0002-second/implement"


def at(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Staleness(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        old = time.time() - 70 * 60  # the phase began 70 minutes ago
        for f in [self.q / "work.json", *(self.q / "runs").rglob("*.json")]:
            os.utime(f, (old, old))

    def telemetry(self, recent: list[dict] | None):
        """`ccp usage`'s fold with these requests as the open run's latest (`recent`)."""
        real = usage.fold

        def fold(*a, **k):
            out = real(*a, **k)
            if recent is not None:
                out["recent"] = {"runs": {RUN: recent}, "seats": {}}
            return out
        return mock.patch.object(board.usage, "fold", side_effect=fold)

    def build(self, recent: list[dict] | None = None) -> dict:
        with self.telemetry(recent):
            code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        return json.loads(Path(body["board"]).read_text())

    def suite_row(self, minutes_ago: float, ended: float | None = None) -> None:
        with (self.q / "runs" / "_suites.jsonl").open("a") as fh:
            fh.write(json.dumps({"op": "started", "suite_id": f"st-{minutes_ago}", "at": at(minutes_ago), "run_id": RUN,
                                 "task_id": "0002-second", "phase": "implement", "lane": "part"}) + "\n")
            if ended is not None:
                fh.write(json.dumps({"op": "ended", "suite_id": f"st-{minutes_ago}", "at": at(ended), "exit_code": 0,
                                     "seconds": 60, "tests": 1}) + "\n")

    def test_old_files_and_no_live_evidence_are_stale(self):
        b = self.build()
        self.assertEqual(sorted(set(b["health"]["stale_sources"]) & {"work", "runs"}), ["runs", "work"])
        self.assertIn("stale source: work", b["blockers"])

    def test_fresh_telemetry_of_the_open_run_says_live(self):
        b = self.build([{"at": at(0.15)}])
        h = b["health"]
        self.assertFalse({"work", "runs"} & set(h["stale_sources"]))
        self.assertRegex(h["sources"]["work"]["live"], r"^live \(telemetry \d+s ago, 0002-second/implement\)$")
        self.assertIn("live (telemetry", h["sources"]["runs"]["live"])
        self.assertNotIn("stale source: work", b["blockers"])
        with self.telemetry([{"at": at(0.15)}]):
            code, _, out, _ = self.ccp("board", "status")
        self.assertIn("source work: live (telemetry", out)

    def test_a_fresh_suite_row_of_the_open_run_says_live(self):
        self.suite_row(3, ended=2)
        b = self.build()
        self.assertFalse({"work", "runs"} & set(b["health"]["stale_sources"]))
        self.assertIn("live (suite 2 min ago", b["health"]["sources"]["work"]["live"])

    def test_a_suite_still_running_of_the_open_run_says_live_for_an_hour(self):
        self.suite_row(50)  # started 50 minutes ago, no end yet
        b = self.build()
        self.assertFalse({"work", "runs"} & set(b["health"]["stale_sources"]))
        since = (datetime.now(timezone.utc) - timedelta(minutes=50)).strftime("%H:%M")
        self.assertEqual(b["health"]["sources"]["work"]["live"],
                         f"live (suite running since {since}, 0002-second/implement)")

    def test_a_suite_started_over_an_hour_ago_with_no_end_does_not_count(self):
        self.suite_row(65)
        b = self.build()
        self.assertEqual(sorted(set(b["health"]["stale_sources"]) & {"work", "runs"}), ["runs", "work"])

    def test_old_telemetry_and_suite_rows_are_still_stale(self):
        self.suite_row(45, ended=44)
        b = self.build([{"at": at(40)}])
        self.assertEqual(sorted(set(b["health"]["stale_sources"]) & {"work", "runs"}), ["runs", "work"])
        self.assertNotIn("live", b["health"]["sources"]["work"])

    def test_telemetry_of_a_run_that_is_not_open_does_not_count(self):
        self.report(RUN, "Outcome: done\nPR: #7\nHead: " + "a" * 40 + "\n## Friction\nnone\n")
        for f in [self.q / "work.json", *(self.q / "runs").rglob("*.json")]:
            os.utime(f, (time.time() - 70 * 60,) * 2)
        b = self.build([{"at": at(0.1)}])
        self.assertIn("work", b["health"]["stale_sources"])


if __name__ == "__main__":
    unittest.main()
