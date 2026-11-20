"""SPEC §16.6 (step 4 of the parallel-runners build): exclusive test lanes. A lane plane.json `suite.exclusive_lanes` names
runs one at a time in the queue; a run that finds it held exits 75 at once, runs nothing, says who
holds it, and counts `lane_busy` on its run. Other lanes, and products without the key, are unchanged."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import unittest

from ccp import config, suite
from tests.test_suite import CCP, PY, SuiteFixture


def _killpg(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass


class Lanes(SuiteFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["suite"] = {"exclusive_lanes": ["full", "gate"]}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))

    def hold(self, seconds: float = 4) -> subprocess.Popen:
        """A real exclusive-lane run that holds the lane while it sleeps."""
        before = sum(1 for r in self.rows() if r.get("op") == "started")
        p = subprocess.Popen([CCP, "suite", "run", "--lane", "gate", "--", PY, "-c", f"import time; time.sleep({seconds})"],
                             cwd=self.runner, env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        self.addCleanup(lambda: (_killpg(p), p.wait(timeout=10)))
        for _ in range(200):
            if sum(1 for r in self.rows() if r.get("op") == "started") > before:
                return p
            time.sleep(0.05)
        p.kill()
        self.fail("the holding run never started")

    def test_a_held_lane_answers_at_once_and_runs_nothing(self):
        holder = self.hold(seconds=60)  # held for the whole test; ended below
        t0 = time.monotonic()
        r = self.run_suite("--lane", "full", "--", PY, "-c", "open('ran', 'w').write('x')")
        self.assertLess(time.monotonic() - t0, 3, "a busy lane never waits")
        self.assertEqual(r.returncode, 75, r.stderr)
        self.assertIn(b"busy", r.stderr)
        self.assertIn(b"held by st-", r.stderr)
        self.assertFalse((self.runner / "ran").exists())
        r = self.run_suite("--", PY, "-c", "print(1)")  # no lane counts as full
        self.assertEqual(r.returncode, 75, r.stderr)
        r = self.run_suite("--lane", "unit", "--", PY, "-c", "print(1)")  # not exclusive
        self.assertEqual(r.returncode, 0, r.stderr)
        _killpg(holder)
        holder.wait(timeout=30)
        r = self.run_suite("--lane", "full", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"taken over", r.stderr)  # its holder was killed, not ended
        self.assertEqual(sum(1 for x in self.rows() if x.get("op") == "busy"), 2)

    def test_the_busy_message_names_the_usual_duration_of_passing_runs(self):
        for code in (0, 0, 3):
            self.run_suite("--lane", "gate", "--", PY, "-c", f"import sys; sys.exit({code})")
        holder = self.hold(seconds=60)
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 75, r.stderr)
        self.assertRegex(r.stderr, rb"its usual run is \d+ s")
        _killpg(holder)
        holder.wait(timeout=30)

    def test_a_nested_run_inside_an_exclusive_one_never_busies_itself(self):
        r = self.run_suite("--lane", "gate", "--", CCP, "suite", "run", "--lane", "gate", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_wait_waits_for_the_lane_and_records_it(self):
        """--wait SECONDS instead of exit 75 at once."""
        holder = self.hold(seconds=3)
        r = self.run_suite("--lane", "gate", "--wait", "1", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 75, r.stderr)  # held longer than it waits
        r = self.run_suite("--lane", "gate", "--wait", "30", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"waiting up to 30 s", r.stderr)
        started = [x for x in self.rows() if x.get("op") == "started"][-1]
        self.assertGreater(started.get("wait_s", 0), 0.4)
        holder.wait(timeout=30)

    def seed(self, *runs: tuple[float, bool, int], lane: str = "gate") -> None:
        """Record finished runs of a lane: (seconds, cold, exit code), oldest first."""
        p = self.q / "runs" / "_suites.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            for i, (seconds, cold, code) in enumerate(runs):
                sid = f"st-seed-{lane}-{i}-{len(self.rows())}"
                fh.write(json.dumps({"op": "started", "suite_id": sid, "lane": lane}) + "\n")
                fh.write(json.dumps({"op": "ended", "suite_id": sid, "exit_code": code, "seconds": seconds,
                                     "cold": cold}) + "\n")

    def test_auto_wait_is_the_limit_less_the_median_cold_run_and_a_margin(self):
        cfg = config.load(self.runner)
        self.seed((100, True, 0), (999, True, 1), (120, True, 0), (5, False, 0), (140, True, 0))
        self.assertEqual(suite.auto_wait(cfg, self.q, "gate")[0], 450)  # 600 - 120 - 30
        self.assertIn("limit 600 s, the lane's usual cold run 120 s, margin 30 s", suite.auto_wait(cfg, self.q, "gate")[1])

    def test_auto_wait_without_a_cold_run_uses_the_passing_runs(self):
        cfg = config.load(self.runner)
        self.seed((60, False, 0), (500, True, 1), (80, False, 0), (100, False, 0))
        self.assertEqual(suite.auto_wait(cfg, self.q, "gate")[0], 490)  # 600 - 80 - 30
        self.seed((1000, False, 0), lane="other")  # another lane's runs say nothing
        self.assertEqual(suite.auto_wait(cfg, self.q, "gate")[0], 490)

    def test_auto_wait_never_goes_below_zero(self):
        cfg = config.load(self.runner)
        self.seed((590, True, 0))
        self.assertEqual(suite.auto_wait(cfg, self.q, "gate")[0], 0)

    def test_auto_wait_with_no_passing_run_exits_busy_at_once_and_says_why(self):
        cfg = config.load(self.runner)
        self.seed((50, True, 1))
        self.assertEqual(suite.auto_wait(cfg, self.q, "gate")[0], 0)
        holder = self.hold(seconds=60)
        t0 = time.monotonic()
        r = self.run_suite("--lane", "gate", "--wait", "auto", "--", PY, "-c", "print(1)")
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual(r.returncode, 75, r.stderr)
        self.assertIn(b"--wait auto: the lane has no passing run recorded, so it waits 0 s", r.stderr)
        busy = [x for x in self.rows() if x.get("op") == "busy"][-1]
        self.assertIs(busy.get("wait_auto"), True)
        _killpg(holder)
        holder.wait(timeout=30)

    def test_auto_wait_runs_once_the_lane_is_released(self):
        self.seed((10, True, 0))
        holder = self.hold(seconds=3)
        r = self.run_suite("--lane", "gate", "--wait", "auto", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"waiting up to 560 s (--wait auto: limit 600 s, the lane's usual cold run 10 s, margin 30 s)", r.stderr)
        started = [x for x in self.rows() if x.get("op") == "started"][-1]
        self.assertGreater(started.get("wait_s", 0), 0.4)
        holder.wait(timeout=30)

    def test_wait_takes_seconds_or_auto(self):
        r = self.run_suite("--lane", "gate", "--wait", "soon", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(b"--wait takes seconds or auto", r.stderr)
        r = self.run_suite("--lane", "gate", "--wait", "auto", "--", PY, "-c", "print(1)")  # the lane is free
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_killed_holder_frees_the_lane(self):
        holder = self.hold(seconds=30)
        holder.kill()  # ccp itself dies; its lock goes with it (the sleeping child is left to the cleanup)
        holder.wait(timeout=10)
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print(1)")
        self.assertIn(r.returncode, (0,), r.stderr)

    def test_a_busy_exit_counts_on_the_run(self):
        self.implementing()
        holder = self.hold()
        r = self.run_suite("--lane", "gate", "--run", "0002-second/implement", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 75, r.stderr)
        holder.wait(timeout=30)
        rec = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual(rec["lane_busy"], 1)

    def test_without_the_key_nothing_is_exclusive(self):
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg.pop("suite")
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        holder = self.hold()
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        holder.wait(timeout=30)

    def test_config_is_checked(self):
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["suite"] = {"exclusive_lanes": "gate"}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.runner)
        self.assertIn("suite.exclusive_lanes", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
