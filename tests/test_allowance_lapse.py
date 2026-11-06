"""SPEC §25.3: a checkpoint decision lapses at a counter reset (operator, 2026-10-22: "It should lapse.")."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ccp import board, usage
from tests.test_board_drill import Fixture
from tests import test_board_layout

W = "2026-10-27T04:00:00.24Z"   # this week's window, as a product read it
W2 = "2026-10-27T03:59:59.52Z"  # the same window, jittered
NEXT = "2026-11-03T04:00:00Z"


class Lapse(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.q = Path(self._d.name)
        (self.q / "board").mkdir()
        self.cfg = SimpleNamespace(telemetry={"allowance_stop_weekly": 80})

    def tearDown(self):
        self._d.cleanup()

    def samples(self, *rows):
        with (self.q / "board/allowance.jsonl").open("a") as fh:
            for at, pct, resets in rows:
                fh.write(json.dumps({"at": at, "five_hour": None, "seven_day": pct, "resets_at": resets}) + "\n")

    def decide(self, at, to, resets=W):
        with (self.q / "board/allowance-decisions.jsonl").open("a") as fh:
            fh.write(json.dumps({"at": at, "by": "design-seat", "to": to, "reason": "operator: go on",
                                 "resets_at": resets, "seven_day_then": 80}) + "\n")

    def test_a_sharp_drop_is_a_reset(self):
        self.samples(("2026-10-22T07:56:02Z", 97.0, W2), ("2026-10-22T08:09:57Z", 0.0, W), ("2026-10-22T08:48:22Z", 4.0, W))
        self.assertEqual(usage.counter_resets(self.q, W), ["2026-10-22T08:09:57Z"])

    def test_jitter_and_an_unknown_reading_are_not_resets(self):
        self.samples(("2026-10-22T01:00:00Z", 85.0, W), ("2026-10-22T02:00:00Z", 84.0, W2),
                     ("2026-10-22T03:00:00Z", None, W), ("2026-10-22T04:00:00Z", 86.0, W),
                     ("2026-10-22T05:00:00Z", 86.0 - usage.RESET_DROP_PP + 0.5, W))
        self.assertEqual(usage.counter_resets(self.q, W), [])

    def test_a_window_change_is_not_a_counter_reset(self):
        self.samples(("2026-10-27T03:50:00Z", 97.0, W), ("2026-10-27T04:10:00Z", 0.0, NEXT))
        self.assertEqual(usage.counter_resets(self.q, NEXT), [])
        self.assertEqual(usage.counter_resets(self.q, W), [])

    def test_a_decision_before_the_reset_lapses_one_after_it_holds(self):
        self.samples(("2026-10-21T20:30:00Z", 80.0, W))
        self.decide("2026-10-21T20:35:57Z", 95.0)
        self.assertEqual(usage.checkpoint(self.cfg, self.q, W), 95.0)
        self.samples(("2026-10-22T07:56:02Z", 97.0, W), ("2026-10-22T08:09:57Z", 0.0, W2))
        self.assertEqual(usage.checkpoint(self.cfg, self.q, W), 80.0)
        st = usage.status(self.cfg, self.q, False)
        self.assertEqual((st["checkpoint"], st["decisions"][0]["lapsed_at"], st["decision_lapsed_at"]),
                         (80.0, "2026-10-22T08:09:57Z", "2026-10-22T08:09:57Z"))
        self.samples(("2026-10-22T20:00:00Z", 81.0, W))
        self.decide("2026-10-22T20:05:00Z", 90.0)
        st = usage.status(self.cfg, self.q, False)
        self.assertEqual((st["checkpoint"], [d["lapsed_at"] for d in st["decisions"]], st["decision_lapsed_at"]),
                         (90.0, ["2026-10-22T08:09:57Z", None], None))

    def test_multiple_decisions_and_resets(self):
        self.samples(("2026-10-21T10:00:00Z", 80.0, W))
        self.decide("2026-10-21T10:05:00Z", 90.0)
        self.decide("2026-10-21T11:00:00Z", 95.0)
        self.samples(("2026-10-21T12:00:00Z", 92.0, W), ("2026-10-21T13:00:00Z", 1.0, W))  # reset 1
        self.samples(("2026-10-22T10:00:00Z", 82.0, W))
        self.decide("2026-10-22T10:05:00Z", 88.0)
        self.samples(("2026-10-22T12:00:00Z", 87.0, W), ("2026-10-22T13:00:00Z", 2.0, W))  # reset 2
        self.decide("2026-10-22T14:00:00Z", 85.0)
        st = usage.status(self.cfg, self.q, False)
        self.assertEqual([d["lapsed_at"] for d in st["decisions"]],
                         ["2026-10-21T13:00:00Z", "2026-10-21T13:00:00Z", "2026-10-22T13:00:00Z", None])
        self.assertEqual((st["checkpoint"], st["counter_resets"]), (85.0, ["2026-10-21T13:00:00Z", "2026-10-22T13:00:00Z"]))

    def test_continue_after_a_reset_is_measured_against_the_project_checkpoint(self):
        self.samples(("2026-10-21T20:30:00Z", 80.0, W))
        self.decide("2026-10-21T20:35:57Z", 95.0)
        self.samples(("2026-10-22T07:56:02Z", 97.0, W), ("2026-10-22T08:09:57Z", 0.0, W), ("2026-10-22T19:00:00Z", 81.0, W))
        rec = usage.continue_(SimpleNamespace(telemetry={"allowance_stop_weekly": 80}, project_id="p"), self.q, 90.0, "operator: to 90")
        self.assertEqual(rec["to"], 90.0)  # 90 raises the 80% in force, though 95% was recorded earlier
        self.assertEqual(usage.checkpoint(self.cfg, self.q, W), 90.0)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class LapsedOnTheBoard(Fixture, unittest.TestCase):
    page = test_board_layout.Layout.page

    def test_status_text_blocker_and_page_say_the_decision_lapsed(self):
        self.seed()
        b = self.build()[0]
        b["now"]["allowance"] = {"latest": {"seven_day": 85.0, "resets_at": W, "at": "2026-10-22T19:00:00Z"},
                                 "checkpoint": 80.0, "project_checkpoint": 80, "counter_resets": ["2026-10-22T08:09:57Z"],
                                 "decision_lapsed_at": "2026-10-22T08:09:57Z",
                                 "decisions": [{"at": "2026-10-21T20:35:57Z", "by": "design-seat", "to": 95.0,
                                                "seven_day_then": 80, "reason": "go on", "resets_at": W,
                                                "lapsed_at": "2026-10-22T08:09:57Z"}]}
        self.assertIn("decision lapsed at the counter reset 2026-10-22T08:09:57Z", board.status_text(b))
        self.assertTrue(any("decision lapsed at the counter reset" in x for x in board._blockers(b)))
        html, _ = self.page(b)
        head = html.split('<div class="pane grid"', 1)[0]
        self.assertIn("decision lapsed at the counter reset 2026-10-22 08:09", head)
        card = html.split("<h2>Allowance</h2>", 1)[1]
        self.assertIn("decision lapsed at the counter reset 2026-10-22 08:09", card)
        self.assertIn("lapsed at the counter reset 2026-10-22 08:09</span>", card)


if __name__ == "__main__":
    unittest.main()
