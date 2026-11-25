"""SPEC §16.6: an exclusive lane's cache probe (plane.json `suite.cache_probe`). A run that finds the lane held asks the
probe once, before any wait; exit 0 lets it run without the lock, recorded `lane_skipped: "cache_probe"`, and anything
else leaves it taking the lock. A free lane, and a run bound to a cold-gate task, run no probe."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import unittest
from typing import Any
from unittest import mock

from ccp import config, suite
from tests.suite_fixture import CCP, PY, SuiteFixture


def _killpg(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass


class CacheProbe(SuiteFixture, unittest.TestCase):
    def configure(self, probe: Any, suite_keys: dict | None = None, **extra) -> None:
        """The runner's plane.json: `full` and `gate` exclusive, `gate`'s probe (none when None, the whole
        `cache_probe` value when not a list), more suite keys, and other blocks."""
        def edit(cfg: dict) -> None:
            cache = {} if probe is None else {"cache_probe": {"gate": probe} if isinstance(probe, list) else probe}
            cfg["suite"] = {"exclusive_lanes": ["full", "gate"], **cache, **(suite_keys or {})}
            cfg.update(extra)
        self.edit_plane(edit, where=self.runner)

    def probe(self, code: int, sleep: float = 0) -> list[str]:
        """A probe that notes it ran (its arguments and CCP_SUITE_LANE) in `probed`, sleeps, and exits `code`."""
        note = self.runner / "probed"
        return [PY, "-c", "import json, os, sys, time; open(sys.argv[1], 'a').write(json.dumps("
                f"[sys.argv[2:], os.environ.get('CCP_SUITE_LANE')]) + '\\n'); time.sleep({sleep}); sys.exit({code})",
                str(note)]

    def probed(self) -> list:
        note = self.runner / "probed"
        return [json.loads(x) for x in note.read_text().splitlines()] if note.is_file() else []

    def hold(self, seconds: float = 60) -> subprocess.Popen:
        """A real gate-lane run that holds the lock while it sleeps."""
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

    def started_rows(self) -> list[dict]:
        return [x for x in self.rows() if x.get("op") == "started"]

    def test_a_probe_that_exits_zero_skips_the_lock(self):
        self.configure(self.probe(0))
        self.hold()
        r = self.run_suite("--lane", "gate", "--wait", "0", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        mine = self.started_rows()[-1]
        self.assertEqual(mine.get("lane_skipped"), suite.CACHE_PROBE)
        self.assertNotIn("green_from", mine)
        self.assertNotIn("wait_s", mine)
        self.assertFalse(any(x.get("op") == "busy" for x in self.rows()))
        self.assertEqual(len(self.probed()), 1)

    def test_a_probe_that_fails_or_times_out_takes_the_lock(self):
        self.configure(self.probe(1))
        self.hold()
        r = self.run_suite("--lane", "gate", "--wait", "0", "--", PY, "-c", "open('ran', 'w').write('x')")
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        self.assertFalse((self.runner / "ran").exists())
        self.assertEqual(len(self.probed()), 1)
        self.configure([str(self.runner / "no-such-probe")])
        r = self.run_suite("--lane", "gate", "--wait", "0", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        self.assertIn(b"could not start", r.stderr)
        # plain values: a nonzero exit says no, silently; a probe that hangs is ended whole, with a warning
        env = dict(os.environ)
        self.assertEqual(suite.run_cache_probe([PY, "-c", "import sys; sys.exit(3)"], "gate", env), (False, None))
        self.assertEqual(suite.run_cache_probe([PY, "-c", "pass"], "gate", env), (True, None))
        child = self.runner / "child.pid"
        hang = [PY, "-c", "import subprocess, sys, time; p = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(60)']); open(sys.argv[1], 'w').write(str(p.pid)); time.sleep(60)", str(child)]
        with mock.patch.object(suite, "CACHE_PROBE_TIMEOUT_S", 1):
            t0 = time.monotonic()
            yes, why = suite.run_cache_probe(hang, "gate", env)
        self.assertLess(time.monotonic() - t0, 20)
        self.assertFalse(yes)
        self.assertIsNotNone(why)
        pid = int(child.read_text())
        for _ in range(100):  # its whole process group is ended, its child too
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            self.fail("the probe's child outlived its timeout")
        yes, why = suite.run_cache_probe([str(self.runner / "no-such-probe")], "gate", env)
        self.assertFalse(yes)
        self.assertIsNotNone(why)

    def test_the_probe_gets_the_runs_command_arguments(self):
        self.configure(self.probe(0))
        self.hold()
        r = self.run_suite("--lane", "gate", "--wait", "0", "--", PY, "-c", "print(1)", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.probed(), [[[PY, "-c", "print(1)", "x"], "gate"]])
        # plain values: a lane declared with stages appends nothing; a lane with no probe has none
        self.configure(self.probe(0), {"lanes": {"gate": [{"name": "unit", "cmd": "true"},
                                                          {"name": "lint", "cmd": "true"}]}})
        c = config.load(self.runner)
        staged = suite.resolve_stages(c, "gate", None)
        self.assertEqual(suite.cache_probe_argv(c, "gate", staged), self.probe(0))
        self.assertEqual(suite.cache_probe_argv(c, "gate", [{"argv": ["t", "a"]}]), [*self.probe(0), "t", "a"])
        self.assertIsNone(suite.cache_probe_argv(c, "full", [{"argv": ["t"]}]))
        self.assertIsNone(suite.cache_probe_argv(None, "gate", [{"argv": ["t"]}]))

    def test_a_cold_gate_task_takes_the_lock_whatever_the_probe_says(self):
        self.configure(self.probe(0), verify={"accept_cache": {"max_age_days": 3, "cold_tasks": ["0002-*"]}})
        self.hold()
        r = self.run_suite("--lane", "gate", "--run", "0002-second/implement", "--wait", "0", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        self.assertEqual(self.probed(), [])
        r = self.run_suite("--lane", "gate", "--run", "0001-first/implement", "--wait", "0", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)  # its gate is not cold
        self.assertEqual(self.started_rows()[-1].get("lane_skipped"), suite.CACHE_PROBE)

    def test_the_key_must_map_a_lane_to_a_command(self):
        self.configure(None)
        self.assertEqual(config.load(self.runner).suite["cache_probe"], {})
        self.configure(["probe", "--quick"])
        self.assertEqual(config.load(self.runner).suite["cache_probe"], {"gate": ["probe", "--quick"]})
        self.configure({"unit": ["probe"]})  # a lane that is not exclusive: accepted, never run
        self.assertEqual(config.load(self.runner).suite["cache_probe"], {"unit": ["probe"]})
        for bad in ("probe", 7, [["probe"]], {"gate": "probe"}, {"gate": []}, {"gate": ["probe", " "]}, {"gate": [1]},
                    {"Gate!": ["probe"]}, {"gate": None}):
            self.configure(bad)
            with self.assertRaises(config.ConfigError, msg=repr(bad)) as cm:
                config.load(self.runner)
            self.assertIn("suite.cache_probe must map", str(cm.exception))

    def test_a_free_lane_runs_no_probe(self):
        self.configure(self.probe(0))
        r = self.run_suite("--lane", "gate", "--wait", "0", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.probed(), [])
        self.assertNotIn("lane_skipped", self.started_rows()[-1])

    def test_the_probes_time_counts_against_the_wait(self):
        self.configure(self.probe(1, sleep=3))
        holder = self.hold()
        r = self.run_suite("--lane", "gate", "--wait", "2", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, suite.BUSY_EXIT, r.stderr)
        waited = [x for x in self.rows() if x.get("op") == "busy"][-1]["waited_s"]
        self.assertGreaterEqual(waited, 2.9)  # the probe's 3 s are part of the wait
        self.assertLess(waited, 4.8)  # and leave none of the 2 s bound to wait after it
        _killpg(holder)
        holder.wait(timeout=30)
        self.hold(seconds=1)  # gone before the probe answers: the run takes the lock after it
        r = self.run_suite("--lane", "gate", "--wait", "30", "--", PY, "-c", "print(1)")
        self.assertEqual(r.returncode, 0, r.stderr)
        mine = self.started_rows()[-1]
        self.assertNotIn("lane_skipped", mine)
        self.assertGreaterEqual(mine.get("wait_s", 0), 2.9)  # wait_s includes the probe's time


if __name__ == "__main__":
    unittest.main()
