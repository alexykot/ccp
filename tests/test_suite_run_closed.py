"""`ccp suite run --run` on a run that is no longer open (SPEC §14.2): refused with exit 2 before the
command starts, nothing recorded, the task's open run named; an open run still binds."""
from __future__ import annotations

import unittest

from ccp import runs, suite
from tests.suite_fixture import PY, SuiteFixture

FIRST = "0002-second/implement"
SECOND = "0002-second/implement-2"


class Refusal(unittest.TestCase):
    def test_an_open_run_is_never_refused(self):
        for state in runs.OPEN:
            self.assertIsNone(suite.closed_run_refusal(FIRST, state, None))

    def test_a_closed_run_names_its_state_and_the_open_run(self):
        why = suite.closed_run_refusal(FIRST, "reported", SECOND)
        self.assertIn("reported", why)
        self.assertIn(f"--run {SECOND}", why)

    def test_a_closed_run_with_no_open_run_names_none(self):
        why = suite.closed_run_refusal(FIRST, "abandoned", None)
        self.assertIn("abandoned", why)
        self.assertNotIn("--run", why)


class ClosedRun(SuiteFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.implementing()
        rec = runs.load(self.q, FIRST)
        rec["reported_at"] = "2026-11-10T00:00:00Z"
        runs.save(self.q, rec)
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(runs.state(runs.load(self.q, SECOND)), "pending")

    def test_a_reported_run_is_refused_before_the_command_starts(self):
        r = self.run_suite("--run", FIRST, "--lane", "full", "--", PY, "-c", "open('ran', 'w').write('x')")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(b"reported", r.stderr)
        self.assertIn(SECOND.encode(), r.stderr)
        self.assertFalse((self.runner / "ran").exists())
        self.assertEqual([x for x in self.rows() if x.get("op") == "started"], [])

    def test_the_open_run_still_binds(self):
        r = self.run_suite("--run", SECOND, "--lane", "full", "--", PY, "-c", "pass")
        self.assertEqual(r.returncode, 0, r.stderr)
        started = [x for x in self.rows() if x.get("op") == "started"]
        self.assertEqual([(x["run_id"], x["bound_by"]) for x in started], [(SECOND, "run")])


if __name__ == "__main__":
    unittest.main()
