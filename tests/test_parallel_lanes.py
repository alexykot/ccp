"""SPEC §16.6 (step 4 of the parallel-runners build): exclusive test lanes. A lane plane.json `suite.exclusive_lanes` names
runs one at a time in the queue; a run that finds it held and does not wait (§16.6) exits 75 at once, runs nothing, says who
holds it, and counts `lane_busy` on its run. Other lanes, and products without the key, are unchanged."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import unittest

from ccp import config, suite
from tests.suite_fixture import CCP, PY, SuiteFixture
from tests.toolkit_fixture import git


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
        self.assertNotIn(b"`--wait SECONDS`", r.stderr)  # its wait is used up: no offer to wait
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
        self.seed((100, True, 0), (999, True, 1), (120, True, 0), (400, False, 0), (140, True, 0))
        self.assertEqual(suite.auto_wait(cfg, self.q, "gate")[0], 450)  # 600 - 120 - 30
        self.assertIn("120 s", suite.auto_wait(cfg, self.q, "gate")[1])

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
        self.assertIn(suite.WAIT_AUTO_NO_RUN.encode(), r.stderr)
        _killpg(holder)
        holder.wait(timeout=30)

    def test_auto_wait_runs_once_the_lane_is_released(self):
        self.seed((10, True, 0))
        holder = self.hold(seconds=3)
        r = self.run_suite("--lane", "gate", "--wait", "auto", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"560 s", r.stderr)
        self.assertIn(b"--wait auto", r.stderr)
        self.assertEqual(r.stderr.count(b"waiting up to"), 1, r.stderr)
        started = [x for x in self.rows() if x.get("op") == "started"][-1]
        self.assertGreater(started.get("wait_s", 0), 0.4)
        holder.wait(timeout=30)

    def test_wait_takes_seconds_or_auto(self):
        r = self.run_suite("--lane", "gate", "--wait", "soon", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(b"--wait takes seconds or auto", r.stderr)
        r = self.run_suite("--lane", "gate", "--wait", "auto", "--", PY, "-c", "print(1)")  # the lane is free
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(b"waiting up to", r.stderr)

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

    # §16.6: a run of a tree a passing run of the lane already ran does not queue for the lock

    PASS = "import sys; print('Ran 3 tests in 0.1s', file=sys.stderr)"

    def commit(self, rel: str = "docs/delivery/plane.json", text: str | None = None) -> str:
        """Commit the runner checkout's state (after writing `text` to `rel`): clean, its tree returned."""
        if text is not None:
            (self.runner / rel).write_text(text)
        git(self.runner, "add", "--", rel)
        git(self.runner, "commit", "-q", "-m", "state")
        return git(self.runner, "rev-parse", "HEAD^{tree}")

    def started_rows(self) -> list[dict]:
        return [x for x in self.rows() if x.get("op") == "started"]

    def test_a_passing_run_of_this_tree_runs_past_the_held_lane(self):
        tree = self.commit()
        r = self.run_suite("--lane", "gate", "--", PY, "-c", self.PASS, "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        green = self.started_rows()[-1]
        self.assertEqual(green.get("tree"), tree)
        holder = self.hold(seconds=60)  # its argument count differs: it takes the lock
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "import sys; sys.exit(3)", "x")
        self.assertEqual(r.returncode, 3, r.stderr)
        mine = self.started_rows()[-1]
        self.assertEqual((mine.get("lane_skipped"), mine.get("green_from")), (suite.GREEN_TREE, green["suite_id"]))
        self.assertIn(green["suite_id"].encode(), r.stderr)
        self.assertFalse(any(x.get("op") == "busy" for x in self.rows()))
        _killpg(holder)
        holder.wait(timeout=30)

    def test_a_failed_run_another_tree_or_another_lane_leaves_the_lane_held(self):
        def busy() -> None:
            holder = self.hold(seconds=60)
            r = self.run_suite("--lane", "gate", "--", PY, "-c", self.PASS, "x")
            self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
            _killpg(holder)
            holder.wait(timeout=30)
        self.commit()
        self.run_suite("--lane", "gate", "--", PY, "-c", self.PASS + "; sys.exit(1)", "x")
        busy()  # a failed run of this lane and tree
        self.run_suite("--lane", "full", "--", PY, "-c", self.PASS, "x")
        busy()  # a passing run of another lane, this tree
        self.run_suite("--lane", "gate", "--", PY, "-c", self.PASS, "x")
        self.commit("docs/LOG.md", "# Log\n\nchanged\n")
        busy()  # a passing run of this lane, another tree

    def test_an_uncommitted_change_records_no_tree_and_queues(self):
        self.commit()
        r = self.run_suite("--lane", "gate", "--", PY, "-c", self.PASS, "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        holder = self.hold(seconds=60)
        git(self.runner, "config", "status.showUntrackedFiles", "no")  # a config hiding them changes nothing
        (self.runner / "untracked.txt").write_text("x")
        r = self.run_suite("--lane", "gate", "--", PY, "-c", self.PASS, "x")
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        (self.runner / "untracked.txt").unlink()
        (self.runner / "docs/LOG.md").write_text("edited\n")
        r = self.run_suite("--lane", "gate", "--", PY, "-c", self.PASS, "x")  # a tracked edit: busy too
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        r = self.run_suite("--lane", "unit", "--", PY, "-c", self.PASS, "x")  # not exclusive: it runs and records
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("tree", self.started_rows()[-1])
        _killpg(holder)
        holder.wait(timeout=30)

    def test_a_run_bound_to_a_cold_gate_task_queues(self):
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["verify"] = {"accept_cache": {"max_age_days": 3, "cold_tasks": ["0002-*"]}}
        self.commit(text=json.dumps(cfg))
        r = self.run_suite("--lane", "gate", "--", PY, "-c", self.PASS, "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        holder = self.hold(seconds=60)
        r = self.run_suite("--lane", "gate", "--run", "0002-second/implement", "--wait", "0", "--", PY, "-c", self.PASS,
                           "x")
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        r = self.run_suite("--lane", "gate", "--run", "0001-first/implement", "--", PY, "-c", self.PASS, "x")
        self.assertEqual(r.returncode, 0, r.stderr)  # its gate is not cold
        _killpg(holder)
        holder.wait(timeout=30)

    def test_green_run_matches_lane_tree_command_and_a_clean_pass(self):
        mine = {"lane": "gate", "tree": "t1", "cmd": "python3", "argc": 2}

        def rows(sid: str, ended: dict, **started) -> list[dict]:
            return [{"op": "started", "suite_id": sid, **{**mine, **started}},
                    {"op": "ended", "suite_id": sid, **{"exit_code": 0, "tests": 3, "interrupted": None, **ended}}]
        self.assertEqual(suite.green_run(rows("a", {}), mine, "full"), "a")
        self.assertEqual(suite.green_run(rows("a", {}) + rows("b", {}), mine, "full"), "b")  # the latest
        self.assertIsNone(suite.green_run(rows("a", {}), {**mine, "tree": None}, "full"))
        for ended, started in (({"exit_code": 1}, {}), ({"tests": 0}, {}), ({"tests": None}, {}), ({"tests": True}, {}),
                               ({"interrupted": "SIGTERM"}, {}), ({}, {"tree": "t2"}), ({}, {"lane": "full"}),
                               ({}, {"cmd": "sh"}), ({}, {"argc": 3}), ({}, {"tree": None})):
            self.assertIsNone(suite.green_run(rows("a", ended, **started), mine, "full"), (ended, started))
        self.assertIsNone(suite.green_run(rows("a", {})[:1], mine, "full"))  # never ended
        self.assertEqual(suite.green_run(rows("a", {}, lane=None), {**mine, "lane": "full"}, "full"), "a")  # no lane: full
        self.assertIsNone(suite.green_run(["junk", {"op": "ended"}], mine, "full"))

    def test_config_is_checked(self):
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["suite"] = {"exclusive_lanes": "gate"}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.runner)
        self.assertIn("suite.exclusive_lanes", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
