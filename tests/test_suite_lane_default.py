"""SPEC §16.6 with §14.1: the lane a `ccp suite run` given no `--lane` uses, in a product that declares only a gate
lane, and the wait a run of a held exclusive lane takes when it is given no `--wait`: `auto` for a run bound to a
worker run (§14.2), an exit at once for one bound to none or given `--wait 0`."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import unittest

from ccp import suite
from tests.test_suite import CCP, PY, SuiteFixture
from tests.test_toolkit import git

PASS = "import sys; print('Ran 3 tests in 0.1s', file=sys.stderr)"


def _killpg(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass


class LaneWait(unittest.TestCase):
    def test_an_absent_wait_is_auto_for_a_bound_run_and_zero_for_an_unbound_one(self):
        for bound_by in ("run", "task", "worktree"):
            self.assertEqual(suite.lane_wait(None, bound_by), "auto")
        self.assertEqual(suite.lane_wait(None, None), 0)

    def test_a_given_wait_is_kept_whatever_the_binding(self):
        for bound_by in ("run", None):
            self.assertEqual(suite.lane_wait(0, bound_by), 0)
            self.assertEqual(suite.lane_wait(40, bound_by), 40)
            self.assertEqual(suite.lane_wait("auto", bound_by), "auto")


class GateOnlyProduct(SuiteFixture, unittest.TestCase):
    """A product whose plane.json declares a gate lane and no full lane, the gate lane exclusive."""

    def setUp(self):
        super().setUp()
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg["suite"] = {"lanes": {"gate": [PY, "-c", PASS, "x"]}, "exclusive_lanes": ["gate"]}
        p.write_text(json.dumps(cfg))
        git(self.runner, "add", "--", "docs/delivery/plane.json")
        git(self.runner, "commit", "-q", "-m", "a gate lane only")

    def hold(self, seconds: float) -> subprocess.Popen:
        """A real gate-lane run that holds the lane while it sleeps."""
        before = sum(1 for r in self.rows() if r.get("op") == "started")
        p = subprocess.Popen([CCP, "suite", "run", "--lane", "gate", "--", PY, "-c", f"import time; time.sleep({seconds})"],
                             cwd=self.runner, env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        self.addCleanup(lambda: (_killpg(p), p.wait(timeout=10)))
        for _ in range(200):
            if sum(1 for r in self.rows() if r.get("op") == "started") > before:
                return p
            time.sleep(0.05)
        self.fail("the holding run never started")

    def seed_pass(self, seconds: float = 10) -> None:
        """Record one passing cold run of the gate lane, so `--wait auto` has a usual duration to wait by."""
        p = self.q / "runs" / "_suites.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps({"op": "started", "suite_id": "st-seed-gate", "lane": "gate"}) + "\n")
            fh.write(json.dumps({"op": "ended", "suite_id": "st-seed-gate", "exit_code": 0, "seconds": seconds,
                                 "cold": True}) + "\n")

    def busy_rows(self) -> list[dict]:
        return [r for r in self.rows() if r.get("op") == "busy"]

    def test_a_held_lane_names_the_gate_lane_for_a_run_with_no_lane(self):
        holder = self.hold(seconds=60)
        r = self.run_suite("--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        self.assertIn(b"lane gate", r.stderr)
        self.assertNotIn(b"lane full", r.stderr)
        self.assertEqual(self.busy_rows()[-1].get("lane"), "gate")
        _killpg(holder)
        holder.wait(timeout=30)

    def test_a_passing_run_with_no_lane_lets_the_gate_lane_skip_the_lock_on_its_tree(self):
        r = self.run_suite("--", PY, "-c", PASS, "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        first = [x for x in self.rows() if x.get("op") == "started"][-1]
        self.assertIsNone(first.get("lane"))  # recorded as given
        holder = self.hold(seconds=60)
        r = self.run_suite("--lane", "gate")
        self.assertEqual(r.returncode, 0, r.stderr)
        mine = [x for x in self.rows() if x.get("op") == "started"][-1]
        self.assertEqual((mine.get("lane_skipped"), mine.get("green_from")), (suite.GREEN_TREE, first["suite_id"]))
        self.assertNotIn(b"lane full", r.stderr)
        _killpg(holder)
        holder.wait(timeout=30)

    def test_an_unbound_run_with_no_wait_exits_at_once(self):
        self.seed_pass()
        holder = self.hold(seconds=60)
        t0 = time.monotonic()
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print(1)")
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        self.assertNotIn(b"--wait auto:", r.stderr)
        self.assertIn(b"`--wait SECONDS`", r.stderr)  # it never waited: the busy line offers a wait
        self.assertNotIn("waited_s", self.busy_rows()[-1])
        _killpg(holder)
        holder.wait(timeout=30)

    def test_a_run_bound_to_a_worker_run_with_no_wait_waits_as_auto_does(self):
        self.seed_pass()
        self.implementing()
        holder = self.hold(seconds=3)
        r = self.run_suite("--lane", "gate", "--run", "0002-second/implement", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"--wait auto:", r.stderr)
        started = [x for x in self.rows() if x.get("op") == "started"][-1]
        self.assertGreater(started.get("wait_s", 0), 0.4)
        self.assertFalse(self.busy_rows())
        holder.wait(timeout=30)

    def test_a_bound_run_given_wait_zero_exits_at_once(self):
        self.seed_pass()
        self.implementing()
        holder = self.hold(seconds=60)
        t0 = time.monotonic()
        r = self.run_suite("--lane", "gate", "--run", "0002-second/implement", "--wait", "0", "--", PY, "-c", "print(1)")
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        self.assertNotIn(b"--wait auto:", r.stderr)
        self.assertNotIn("waited_s", self.busy_rows()[-1])
        _killpg(holder)
        holder.wait(timeout=30)


if __name__ == "__main__":
    unittest.main()
