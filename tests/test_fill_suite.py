"""`report.judge_suite` (SPEC §14.1): what a report's `Suite:` line takes from the folded suite runs, decided on
plain rows. `ccp report`'s wiring of it (`fill_suite`) is tested end to end in tests.test_suite."""
from __future__ import annotations

import unittest

from ccp import report

RUN = "0002-second/implement"
LANES = ("gate", "full")


def row(sid: str, state: str = "passed", lane: str = "full", run_id: str | None = RUN, tests: int | None = 7,
        **more) -> dict:
    return {"suite_id": sid, "run_id": run_id, "lane": lane, "state": state, "tests": tests, "seconds": 3.24,
            "exit_code": 0 if state == "passed" else 1, **more}


def judge(rows: list[dict], parsed: dict, phase: str = "implement", accept_cache: bool = False):
    return report.judge_suite(rows, RUN, phase, parsed, accept_cache, LANES)


class FromALine(unittest.TestCase):
    def test_a_hand_written_line_stays(self):
        parsed = {"suite_tests": 12, "suite_seconds": 3}
        self.assertEqual(judge([row("st-1")], parsed), ([], [], {}))

    def test_an_unparsed_line_warns_and_fills_nothing(self):
        errs, warns, update = judge([row("st-1")], {"suite_unparsed": "Suite: all green"})
        self.assertEqual((errs, update), ([], {}))
        self.assertIn("`Suite: all green` line is neither", warns[0])

    def test_from_an_unknown_run_is_refused(self):
        errs, warns, update = judge([row("st-1")], {"suite_from": "st-9"})
        self.assertIn("no suite run st-9 is recorded", errs[0])
        self.assertEqual((warns, update), ([], {}))

    def test_from_another_runs_suite_run_is_refused(self):
        errs, _, update = judge([row("st-1", run_id="0003-third/implement")], {"suite_from": "st-1"})
        self.assertIn("recorded against 0003-third/implement, not " + RUN, errs[0])
        self.assertEqual(update, {})
        errs, _, _ = judge([row("st-1", run_id=None)], {"suite_from": "st-1"})
        self.assertIn("recorded against no run", errs[0])

    def test_from_a_run_not_ended_is_refused(self):
        errs, _, update = judge([row("st-1", state="open")], {"suite_from": "st-1"})
        self.assertIn("has not ended with a test count", errs[0])
        self.assertEqual(update, {})

    def test_from_a_run_with_no_count_is_refused(self):
        errs, _, update = judge([row("st-1", tests=None)], {"suite_from": "st-1"})
        self.assertIn("has not ended with a test count", errs[0])
        self.assertEqual(update, {})

    def test_from_a_run_with_no_cache_counts_is_refused_in_verify_with_accept_cache(self):
        errs, _, update = judge([row("st-1")], {"suite_from": "st-1"}, phase="verify", accept_cache=True)
        self.assertIn("recorded none", errs[0])
        self.assertEqual(update, {})
        self.assertEqual(judge([row("st-1")], {"suite_from": "st-1"}, phase="implement", accept_cache=True)[0], [])

    def test_from_a_good_run_fills_its_numbers(self):
        rows = [row("st-1", tests=7), row("st-2", lane="part", tests=1)]
        self.assertEqual(judge(rows, {"suite_from": "st-1"}),
                         ([], [], {"suite_tests": 7, "suite_seconds": 3.2, "suite_filled": "from", "suite_passed": True}))
        failed = judge([row("st-3", state="failed", tests=4)], {"suite_from": "st-3"})[2]
        self.assertEqual((failed["suite_tests"], failed["suite_passed"]), (4, False))

    def test_from_an_all_cached_gate_takes_zero_tests_ran(self):
        rows = [row("st-1", lane="gate", tests=0, ran=0, cached=3)]
        update = judge(rows, {"suite_from": "st-1"}, phase="verify", accept_cache=True)[2]
        self.assertEqual((update["suite_tests"], update["suite_ran"], update["suite_cached"]), (0, 0, 3))


class WithNoLine(unittest.TestCase):
    def test_no_matching_run_fills_nothing(self):
        rows = [row("st-1", lane="part"), row("st-2", run_id="0003-third/implement"), row("st-3", tests=None),
                row("st-4", state="open")]
        self.assertEqual(judge(rows, {}), ([], [], {}))

    def test_a_failed_latest_run_warns_and_fills_nothing(self):
        errs, warns, update = judge([row("st-1"), row("st-2", state="failed", tests=4)], {})
        self.assertEqual((errs, update), ([], {}))
        self.assertIn("latest full suite run (st-2) failed with exit 1: nothing was filled in", warns[0])

    def test_a_passed_latest_run_fills_auto(self):
        rows = [row("st-1", tests=3), row("st-2", lane="gate", tests=9), row("st-3", lane="part", tests=1)]
        self.assertEqual(judge(rows, {}), ([], [], {"suite_tests": 9, "suite_seconds": 3.2, "suite_from": "st-2",
                                                     "suite_filled": "auto", "suite_passed": True}))

    def test_a_run_with_no_cache_counts_fills_nothing_and_warns_nothing_in_verify_with_accept_cache(self):
        self.assertEqual(judge([row("st-1")], {}, phase="verify", accept_cache=True), ([], [], {}))
        update = judge([row("st-1", ran=2, cached=5)], {}, phase="verify", accept_cache=True)[2]
        self.assertEqual((update["suite_ran"], update["suite_cached"], update["suite_filled"]), (2, 5, "auto"))


if __name__ == "__main__":
    unittest.main()
