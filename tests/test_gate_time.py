"""The gate's time against the agent's shell limit (SPEC §14.6): plane.json `gate` holds the limit and
the cut line, every suite run records whether it was cold, `ccp health` judges the latest cold
gate run against both, naming its slowest stage, and reports gate runs killed at the limit."""
from __future__ import annotations

import io
import json
import os
import shlex
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, health, suite
from tests.helpers import Product
from tests.test_suite_stages import StagedFixture, _shell_py

RUN = "0002-second/verify"


def started(sid, lane="gate", at="2026-11-01T10:00:00Z"):
    return {"op": "started", "suite_id": sid, "at": at, "lane": lane, "run_id": RUN, "task_id": "0002-second",
            "phase": "verify"}


def ended(sid, seconds, code=0, tests=900, cached=None, stages=None, at="2026-11-01T10:20:00Z"):
    row = {"op": "ended", "suite_id": sid, "at": at, "exit_code": code, "seconds": seconds, "tests": tests,
           "failed": None, "skipped": None, "ran": None, "cached": cached, "interrupted": None}
    if stages is not None:
        row.update(stages=[{"name": n, "seconds": s, "exit_code": 0} for n, s in stages], failed_stage=None)
    return row


STAGES = [("lint", 40.0), ("tests", 520.5), ("plane-docs", 12.0)]


class GateKnobs(unittest.TestCase):
    def load(self, gate=None, **extra):
        p = Product({**({"gate": gate} if gate is not None else {}), **extra})
        self.addCleanup(p.cleanup)
        return p.cfg

    def test_the_defaults_are_the_harness_limit_and_ninety_percent(self):
        self.assertEqual(config.gate_limits(self.load()), (600, 540))
        self.assertEqual(config.gate_limits(None), (600, 540))

    def test_the_line_follows_the_limit_unless_set(self):
        self.assertEqual(config.gate_limits(self.load({"shell_limit_seconds": 300})), (300, 270))
        self.assertEqual(config.gate_limits(self.load({"shell_limit_seconds": 300, "cut_line_seconds": 200})),
                         (300, 200))
        self.assertEqual(config.gate_limits(self.load({"cut_line_seconds": None})), (600, 540))

    def test_bad_knobs_are_refused(self):
        for bad in ({"shell_limit_seconds": 0}, {"shell_limit_seconds": -5}, {"shell_limit_seconds": True},
                    {"shell_limit_seconds": "600"}, {"cut_line_seconds": 700}, {"cut_line_seconds": 0},
                    {"cut_line_seconds": "500"}, {"shell_limit_seconds": 300, "cut_line_seconds": 301},
                    {"limit": 600}):
            with self.subTest(bad=bad), self.assertRaises(config.ConfigError):
                self.load(bad)

    def test_the_schema_names_the_block_and_the_cold_field(self):
        root = Path(__file__).resolve().parents[1] / "contracts"
        props = json.loads((root / "plane_config.schema.json").read_text())["properties"]
        self.assertEqual(set(props["gate"]["properties"]), {"shell_limit_seconds", "cut_line_seconds"})
        self.assertIn("cold", json.loads((root / "suite_result.schema.json").read_text())["properties"])


class RunsRecordCold(StagedFixture, unittest.TestCase):
    def gate(self, result: dict | None) -> dict:
        write = "import os, sys; open(os.environ['CCP_SUITE_RESULT'], 'w').write(sys.argv[1])"
        cmd = (f"{_shell_py(write)} {shlex.quote(json.dumps(result))}" if result is not None
               else _shell_py("print('Ran 4 tests in 0.1s')"))
        self.lanes({"fast": [{"name": "tests", "cmd": cmd}]})
        r = self.run_suite("--lane", "fast")
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.ended()

    def test_a_run_with_nothing_cached_is_cold(self):
        self.assertIs(self.gate({"tests": 4, "ran": 2, "cached": 0})["cold"], True)
        ev = [e for e in self.events() if e["type"] == "suite"][-1]["payload"]
        self.assertIs(ev["cold"], True)

    def test_a_run_with_units_cached_is_not_cold(self):
        self.assertIs(self.gate({"tests": 4, "ran": 1, "cached": 3})["cold"], False)

    def test_a_run_with_no_cached_count_cannot_tell(self):
        self.assertIsNone(self.gate(None)["cold"])

    def test_the_folded_run_keeps_its_stages_and_coldness(self):
        self.gate({"tests": 4, "ran": 2, "cached": 0})
        s = suite.fold(self.q)[-1]
        self.assertEqual(([x["name"] for x in s["stages"]], s["failed_stage"], s["cold"]), (["tests"], None, True))

    def test_run_cold_reads_only_a_count(self):
        self.assertEqual([suite.run_cold(v) for v in (0, 2, None, True, "0")], [True, False, None, None, None])


class HealthJudgesTheGate(unittest.TestCase):
    def setUp(self):
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        self.addCleanup(self._q.cleanup)
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": self._q.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.product()

    def product(self, cfg=None):
        self.p = Product(cfg)
        self.addCleanup(self.p.cleanup)

    def suites(self, *rows):
        p = self.q / "runs" / "_suites.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def health(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.p.root), "health", *args])
        self.assertEqual(code, 0)
        return out.getvalue()

    def finding(self):
        return json.loads(self.health("--json"))["gate_time"]["finding"]

    def gate_lines(self):
        return [ln for ln in self.health().splitlines() if ln.startswith("Gate over")]

    def test_a_cold_gate_over_the_line_is_reported_with_its_slowest_stage(self):
        self.suites(started("st-a"), ended("st-a", 572.5, cached=0, stages=STAGES))
        f = self.finding()
        self.assertEqual((f["suite_id"], f["seconds"], f["over_limit"]), ("st-a", 572, False))
        self.assertEqual(f["slowest_stage"], {"name": "tests", "seconds": 520})
        g = json.loads(self.health("--json"))["gate_time"]
        self.assertEqual((g["line_s"], g["limit_s"], g["cold_runs"]), (540, 600, 1))
        [line] = self.gate_lines()
        for token in ("st-a", "572 s", "540 s", "600 s", "tests 520 s"):
            self.assertIn(token, line)
        self.assertNotIn("breach", line)

    def test_a_cold_gate_over_the_limit_is_a_breach(self):
        self.suites(started("st-a"), ended("st-a", 640.0, cached=0, stages=STAGES))
        self.assertIs(self.finding()["over_limit"], True)
        [line] = self.gate_lines()
        self.assertIn("breach", line)

    def test_under_the_line_nothing_is_reported(self):
        self.suites(started("st-a"), ended("st-a", 540.0, cached=0, stages=STAGES))
        self.assertIsNone(self.finding())
        self.assertEqual(self.gate_lines(), [])

    def test_a_product_with_no_test_cache_has_cold_runs_without_a_count(self):
        self.suites(started("st-a"), ended("st-a", 580.0, cached=None))
        f = self.finding()
        self.assertEqual((f["suite_id"], f["slowest_stage"]), ("st-a", None))
        self.assertEqual(len(self.gate_lines()), 1)

    def test_warm_runs_are_not_judged(self):
        self.suites(started("st-a"), ended("st-a", 900.0, cached=12, stages=STAGES))
        self.assertIsNone(self.finding())
        self.assertEqual(self.gate_lines(), [])
        self.assertEqual(json.loads(self.health("--json"))["gate_time"]["cold_runs"], 0)

    def test_a_run_that_cannot_be_shown_cold_is_not_judged(self):
        self.product({"verify": {"accept_cache": {"max_age_days": 3}}})  # a test cache, and no count on the run
        self.suites(started("st-a"), ended("st-a", 900.0, cached=None))
        self.assertIsNone(self.finding())

    def test_failed_runs_and_other_lanes_are_not_judged(self):
        self.suites(started("st-a"), ended("st-a", 900.0, code=1, cached=0),
                    started("st-b", lane="full"), ended("st-b", 900.0, cached=0),
                    started("st-c", lane="part"), ended("st-c", 900.0, cached=0))
        self.assertIsNone(self.finding())

    def test_only_the_latest_cold_gate_run_is_judged(self):
        self.suites(started("st-a", at="2026-11-01T10:00:00Z"), ended("st-a", 700.0, cached=0),
                    started("st-b", at="2026-11-02T10:00:00Z"), ended("st-b", 300.0, cached=0),
                    started("st-c", at="2026-11-03T10:00:00Z"), ended("st-c", 950.0, cached=4))
        self.assertIsNone(self.finding())
        self.suites(started("st-d", at="2026-11-04T10:00:00Z"), ended("st-d", 560.0, cached=0))
        self.assertEqual(self.finding()["suite_id"], "st-d")

    def test_the_knobs_and_a_renamed_gate_role_are_read(self):
        self.product({"gate": {"shell_limit_seconds": 300},
                      "suite": {"lanes": {"check": ["true"]}, "roles": {"gate": "check"}}})
        self.suites(started("st-a", lane="check"), ended("st-a", 310.0, cached=0))
        f = self.finding()
        self.assertEqual((f["suite_id"], f["over_limit"]), ("st-a", True))

    def test_the_architects_summary_carries_the_finding(self):
        self.suites(started("st-a"), ended("st-a", 572.5, cached=0, stages=STAGES))
        self.assertIn("st-a", health.summary_text(health.collect(self.p.cfg, self.q)))
        self.assertIsNone(health.gate_text(None))

    def ago(self, seconds):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds))

    def killed(self):
        return json.loads(self.health("--json"))["gate_time"]["killed"]

    def killed_lines(self):
        return [ln for ln in self.health().splitlines() if ln.startswith("Gate killed")]

    def test_a_gate_run_with_no_end_past_the_shell_limit_is_reported_killed(self):
        self.suites(started("st-a", at=self.ago(700)))
        [k] = self.killed()
        self.assertEqual((k["suite_id"], k["task_id"], k["run_id"]), ("st-a", "0002-second", RUN))
        [line] = self.killed_lines()
        for token in ("st-a", "0002-second", "600 s"):
            self.assertIn(token, line)
        self.assertIsNone(self.finding())

    def test_a_long_dead_gate_run_is_still_reported(self):
        self.suites(started("st-a", at="2026-11-01T10:00:00Z"))
        self.assertEqual([k["suite_id"] for k in self.killed()], ["st-a"])

    def test_a_gate_run_still_inside_the_limit_is_not_reported(self):
        self.suites(started("st-a", at=self.ago(60)))
        self.assertEqual(self.killed(), [])
        self.assertEqual(self.killed_lines(), [])

    def test_ended_runs_and_other_lanes_are_not_reported_killed(self):
        self.suites(started("st-a", at=self.ago(3600)), ended("st-a", 300.0, cached=0),
                    started("st-b", at=self.ago(3600)), ended("st-b", 900.0, code=1),
                    started("st-c", lane="full", at=self.ago(3600)),
                    started("st-d", lane="part", at=self.ago(3600)))
        self.assertEqual(self.killed(), [])
        self.assertEqual(self.killed_lines(), [])

    def test_the_shell_limit_knob_and_a_renamed_gate_role_decide_killed(self):
        self.product({"gate": {"shell_limit_seconds": 300},
                      "suite": {"lanes": {"check": ["true"]}, "roles": {"gate": "check"}}})
        self.suites(started("st-a", lane="check", at=self.ago(400)), started("st-b", at=self.ago(400)),
                    started("st-c", lane="check", at=self.ago(200)))
        self.assertEqual([k["suite_id"] for k in self.killed()], ["st-a"])

    def test_every_killed_gate_run_is_listed_and_the_line_names_the_latest(self):
        self.suites(started("st-a", at="2026-11-01T10:00:00Z"), started("st-b", at="2026-11-02T10:00:00Z"))
        self.assertEqual([k["suite_id"] for k in self.killed()], ["st-a", "st-b"])
        [line] = self.killed_lines()
        self.assertIn("st-b", line)
        self.assertNotIn("st-a", line)

    def test_the_architects_summary_carries_the_killed_run(self):
        self.suites(started("st-a", at=self.ago(700)))
        self.assertIn("st-a", health.summary_text(health.collect(self.p.cfg, self.q)))
        self.assertIsNone(health.killed_text(None))

    def test_a_damaged_suites_file_reports_nothing(self):
        p = self.q / "runs" / "_suites.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text("not json\n{\"op\": \"ended\"}\n")
        self.assertIsNone(self.finding())
        self.assertEqual(self.killed(), [])


if __name__ == "__main__":
    unittest.main()
