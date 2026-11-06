"""§25.2 the usage windows and §26.3 the estimator's configurable inputs."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ccp import config, estimate, estimator, forecast, usage
from ccp.queue import QueueError
from tests.helpers import Product

LEGACY = {"five_hour": {"utilization": 40, "resets_at": "2026-11-05T20:00:00+00:00"},
          "seven_day": {"utilization": 55, "resets_at": "2026-11-09T08:00:00+00:00"}}


class Parse(unittest.TestCase):
    def test_the_generic_form(self):
        got = usage.parse_windows({"windows": [{"name": "week", "pct": 12.5, "resets_at": "2026-11-09T08:00:00Z"},
                                               {"name": "bad"}, {"name": "hour", "pct": "7"}]})
        self.assertEqual([(w["name"], w["pct"]) for w in got], [("week", 12.5), ("bad", None), ("hour", 7.0)])

    def test_the_legacy_form_names_its_windows(self):
        got = usage.parse_windows(LEGACY)
        self.assertEqual({w["name"]: w["pct"] for w in got}, {"five_hour": 40.0, "seven_day": 55.0})

    def test_garbage_reads_as_no_window(self):
        self.assertEqual(usage.parse_windows("nope"), [])
        self.assertEqual(usage.parse_windows({"windows": "x"}), [])


class Windows(unittest.TestCase):
    def setUp(self):
        self.q = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.q, ignore_errors=True)

    def product(self, tel: dict) -> Product:
        p = Product({"telemetry": tel})
        self.addCleanup(p.cleanup)
        return p

    def sample(self, p: Product, data: dict, gate: bool = True) -> dict:
        f = p.root / "allow.json"
        f.write_text(json.dumps(data))
        cfg = p.cfg
        cfg.telemetry["allowance_cmd"] = f"cat {f}"
        return usage.sample_allowance(cfg, self.q, gate=gate)

    def test_defaults_read_the_legacy_command_as_before(self):
        p = self.product({"allowance_stop_weekly": 80})
        rec = self.sample(p, LEGACY)
        self.assertEqual((rec["five_hour"], rec["seven_day"], rec["resets_at"], rec["five_hour_resets_at"]),
                         (40.0, 55.0, "2026-11-09T08:00:00+00:00", "2026-11-05T20:00:00+00:00"))
        self.assertEqual((rec["weekly_window"], rec["session_window"]), ("seven_day", "five_hour"))
        self.assertEqual(usage.session_settings(p.cfg, rec)[0], 95.0)
        self.assertEqual(usage.status(p.cfg, self.q, False)["checkpoint"], 80.0)

    def test_a_named_weekly_window_stops_at_its_own_checkpoint(self):
        p = self.product({"windows": {"week": {"kind": "weekly", "stop_pct": 60}}})
        with self.assertRaises(QueueError) as e:
            self.sample(p, {"windows": [{"name": "week", "pct": 61, "resets_at": "2026-11-09T08:00:00Z"}]})
        self.assertEqual(e.exception.code, 5)
        self.assertIn("checkpoint is 60%", str(e.exception))
        rec = self.sample(p, {"windows": [{"name": "week", "pct": 30, "resets_at": "2026-11-09T08:00:00Z"}]})
        self.assertEqual(rec["weekly_window"], "week")

    def test_the_session_window_past_its_park_gates_and_brings_its_own_park(self):
        p = self.product({"session_park_pct": None, "windows": {
            "hour": {"kind": "session", "park_pct": 90}, "day": {"kind": "session", "park_pct": 70}}})
        rec = self.sample(p, {"windows": [{"name": "hour", "pct": 50, "resets_at": "2026-11-05T20:00:00Z"},
                                          {"name": "day", "pct": 75, "resets_at": "2026-11-06T08:00:00Z"}]})
        self.assertEqual((rec["session_window"], rec["five_hour"]), ("day", 75.0))
        self.assertEqual(usage.session_settings(p.cfg, rec)[0], 70.0)

    def test_nearest_its_threshold_when_none_is_past(self):
        p = self.product({"windows": {"hour": {"kind": "session", "park_pct": 90},
                                      "day": {"kind": "session", "park_pct": 50}}})
        rec = self.sample(p, {"windows": [{"name": "hour", "pct": 80}, {"name": "day", "pct": 30}]})
        self.assertEqual(rec["session_window"], "hour")   # 80/90 is nearer than 30/50

    def test_a_session_window_without_a_park_gates_nothing(self):
        p = self.product({"session_park_pct": None, "windows": {"hour": {"kind": "session"}}})
        rec = self.sample(p, {"windows": [{"name": "hour", "pct": 99}]})
        self.assertIsNone(usage.session_settings(p.cfg, rec)[0])

    def test_a_weekly_only_reading_reads_as_no_session_window(self):
        p = self.product({})
        rec = self.sample(p, {"windows": [{"name": "seven_day", "pct": 10}]})
        self.assertIsNone(rec["five_hour"])
        self.assertNotIn("session_window", rec)

    def test_the_forecast_models_the_gating_window_park(self):
        p = self.product({"session_park_pct": None, "windows": {"hour": {"kind": "session", "park_pct": 88}}})
        last = {"session_window": "hour", "five_hour": 10.0, "seven_day": 5.0}
        _s, info = forecast._session(p.cfg, None, None, last, 0.0)
        self.assertEqual((info["window"], info["park_pct"]), ("hour", 88.0))


    def test_any_weekly_window_past_its_own_checkpoint_refuses(self):
        p = self.product({"windows": {"week": {"kind": "weekly", "stop_pct": 60},
                                      "month": {"kind": "weekly", "stop_pct": 90}}})
        data = {"windows": [{"name": "week", "pct": 10, "resets_at": "2026-11-30T08:00:00Z"},
                            {"name": "month", "pct": 95, "resets_at": "2026-11-09T08:00:00Z"}]}
        with self.assertRaises(QueueError) as e:
            self.sample(p, data)
        self.assertIn("the month window is at 95%", str(e.exception))
        self.assertEqual(self.sample(p, data, gate=False)["weekly_window"], "month")

    def test_the_gating_window_holds_on_a_tie_and_ties_go_by_name(self):
        p = self.product({"session_park_pct": None, "windows": {"hour": {"kind": "session", "park_pct": 90},
                                                                "day": {"kind": "session", "park_pct": 50}}})
        tie = {"windows": [{"name": "hour", "pct": 45}, {"name": "day", "pct": 25}]}
        self.assertEqual(self.sample(p, tie)["session_window"], "day")     # first by name
        rules = usage.window_rules(p.cfg)
        wins = usage.parse_windows(tie)
        self.assertEqual(usage.project(p.cfg, wins, prev={"session_window": "hour"})["session_window"], "hour")
        self.assertEqual(usage.project(p.cfg, wins, prev={"session_window": "day"})["session_window"], "day")
        self.assertTrue(rules)

    def test_a_decision_applies_to_its_own_window(self):
        p = self.product({"windows": {"week": {"kind": "weekly", "stop_pct": 60}}, "allowance_stop_weekly": 80})
        self.sample(p, {"windows": [{"name": "week", "pct": 61, "resets_at": "2026-11-09T08:00:00Z"}]}, gate=False)
        rec = usage.continue_(p.cfg, self.q, 75, "operator: carry on")
        self.assertEqual(rec["window"], "week")
        self.assertEqual(usage.checkpoint(p.cfg, self.q, "2026-11-09T08:00:00Z", "week"), 75.0)
        self.assertEqual(usage.checkpoint(p.cfg, self.q, "2026-11-09T08:00:00Z", "seven_day"), 80.0)

    def test_a_legacy_decision_without_a_window_is_seven_days(self):
        p = self.product({"allowance_stop_weekly": 80})
        (self.q / "board").mkdir(parents=True, exist_ok=True)
        (self.q / "board" / "allowance-decisions.jsonl").write_text(json.dumps(
            {"at": "2026-11-05T10:00:00Z", "to": 90, "resets_at": "2026-11-09T08:00:00Z"}) + "\n")
        self.assertEqual(usage.checkpoint(p.cfg, self.q, "2026-11-09T08:00:00Z"), 90.0)
        self.assertEqual(usage.checkpoint(p.cfg, self.q, "2026-11-09T08:00:00Z", "week"), None)

    def test_a_null_figure_keeps_its_reset(self):
        p = self.product({})
        rec = self.sample(p, {"seven_day": {"utilization": None, "resets_at": "2026-11-09T08:00:00+00:00"}})
        self.assertEqual((rec["seven_day"], rec["resets_at"]), (None, "2026-11-09T08:00:00+00:00"))


class ConfigChecks(unittest.TestCase):
    def test_bad_windows_are_refused(self):
        for tel in ({"windows": {"w": {"kind": "monthly"}}}, {"windows": {"w": {"stop_pct": 150}}},
                    {"windows": {"w": {"other": 1}}}, {"windows": ["x"]},
                    {"windows": {"h": {"kind": "session", "stop_pct": 50}}},
                    {"windows": {"w": {"kind": "weekly", "park_pct": 50}}},
                    {"session_park_pct": 90, "windows": {"five_hour": {"park_pct": 80}}},
                    {"allowance_stop_weekly": 80, "windows": {"seven_day": {"stop_pct": 70}}}):
            p = Product({"telemetry": tel})
            try:
                with self.assertRaises(config.ConfigError):
                    _ = p.cfg
            finally:
                p.cleanup()

    def test_bad_estimate_inputs_are_refused(self):
        for bad in ({"spec_paths": "SPEC.md"}, {"path_suffixes": ["py"]}):
            p = Product({"estimate": bad})
            try:
                with self.assertRaises(config.ConfigError):
                    _ = p.cfg
            finally:
                p.cleanup()


class EstimatorInputs(unittest.TestCase):
    def test_defaults_are_unchanged(self):
        p = Product()
        try:
            self.assertEqual(estimate.suffixes(p.cfg), estimate.EXTS)
            self.assertEqual(estimate.family("0042-sf-store", p.cfg), "sf")
            self.assertEqual(estimate.cited("see `a/b.py` and `x.rs`", p.cfg), ["a/b.py"])
        finally:
            p.cleanup()

    def test_configured_suffixes_and_spec_paths(self):
        p = Product({"estimate": {"path_suffixes": [".rs"], "spec_paths": ["design/*.md"]}})
        try:
            self.assertEqual(estimate.cited("see `x.rs` and `y.py`", p.cfg), ["x.rs"])
            p.write("design/rules.md", "# Rules\n\n## S7 — Seven\n\nbody seven\n")
            p.write("docs/SPEC.md", "# SPEC\n\n## S7 — other\n\nnot this one\n")
            out = estimator.spec_excerpts(p.cfg, ["S7"])
            self.assertIn("body seven", out)
            self.assertNotIn("not this one", out)
        finally:
            p.cleanup()


if __name__ == "__main__":
    unittest.main()
