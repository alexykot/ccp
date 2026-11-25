"""The tests' one run clock (`tests.helpers.run_clock`): runs open a minute apart from the real time, so a rule that
compares a run's stamp with the real time, a pending run's expiry (SPEC §11.1), sees a run opened now."""
from __future__ import annotations

import time
import unittest
from datetime import datetime

from ccp import report, runs
from tests.helpers import run_clock


def ts(stamp: str) -> float:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


class RunClock(unittest.TestCase):
    def test_a_run_opened_on_the_default_clock_has_not_expired(self):
        run_clock(self)
        stamps = [runs.iso() for _ in range(3)]
        self.assertLess(abs(ts(stamps[0]) - time.time()), 120)
        self.assertEqual(stamps, sorted(set(stamps)))
        pending = {"run_id": "0002-second/implement", "opened_at": stamps[0], "agent_id": None}
        self.assertEqual(runs.state(pending), "pending")
        self.assertFalse(runs.expired(pending, time.time()))

    def test_one_clock_runs_across_every_name_it_patches(self):
        run_clock(self, "ccp.runs.iso", "ccp.report.iso")
        stamps = [runs.iso(), report.iso(), runs.iso(), report.iso()]
        self.assertEqual([ts(b) - ts(a) for a, b in zip(stamps, stamps[1:])], [60.0, 60.0, 60.0])

    def test_start_sets_the_first_stamp(self):
        run_clock(self, start="2026-01-02T03:04:00Z")
        self.assertEqual([runs.iso(), runs.iso()], ["2026-01-02T03:04:00Z", "2026-01-02T03:05:00Z"])


if __name__ == "__main__":
    unittest.main()
