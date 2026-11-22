"""SPEC §24.6: `ccp usage` and `ccp health` advise on short-lived cache writes, an oversized context and the
coordination share, at plane.json `usage.advice`'s thresholds, from the requests since the advice's start
(`--since`, else `window_hours` back, else every request), which each line names."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ccp import cli, config, usage
from tests.helpers import advice_row as row, Product


def ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


class AdviceCase(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        (self.q / "board").mkdir()
        run = self.q / "runs" / "0001-a" / "implement.json"
        run.parent.mkdir(parents=True)
        run.write_text(json.dumps({"run_id": "0001-a/implement", "task_id": "0001-a", "phase": "implement",
                                   "seat": "implementer", "agent_id": "a1", "started_at": "2027-01-15T07:00:00Z"}))

    def tearDown(self):
        self.p.cleanup()
        self._q.cleanup()

    def sink(self, *rows):
        (self.q / "board" / "usage-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r, _ in rows))
        (self.q / "board" / "usage-spans.jsonl").write_text("".join(json.dumps(s) + "\n" for _, s in rows))

    def ccp(self, *args, code=0):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), \
                mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            self.assertEqual(cli.main(["--root", str(self.p.root), *args]), code, err.getvalue())
        return out.getvalue() if code == 0 else err.getvalue()

    def git_product(self):
        subprocess.run(["git", "-C", str(self.p.root), "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", str(self.p.root), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
                        "--allow-empty", "-m", "init"], check=True)

    def advice(self):
        return [ln for ln in self.ccp("usage").splitlines() if ln.startswith("advice: ")]

    def coordination_sink(self):
        """The lead and the runner at half of all seats' cost, every other measure under its threshold."""
        self.sink(row("l1", "lead", cost=0.3), row("r1", "runner", cost=0.2), row("w1", "worker", cost=0.5))


class Advice(AdviceCase):
    def test_a_runner_on_5_minute_cache_writes_is_advised(self):
        self.sink(row("r1", "runner", written=6000, five=4000), row("r2", "runner", written=4000, five=3000),
                  row("l1", "lead", written=10000, five=5000),  # exactly at the threshold: not more than it
                  row("w1", "worker", cost=0.5), row("w2", "worker", cost=0.5))
        lines = self.advice()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("runner", lines[0])
        self.assertIn("70%", lines[0])
        self.assertIn("subagentPromptCacheTtl", lines[0])

    def test_an_oversized_context_names_the_setting_per_seat(self):
        self.sink(*(row(f"l{i}", "lead", ctx=c) for i, c in enumerate((400000, 500000, 600000))),
                  *(row(f"r{i}", "runner", ctx=c) for i, c in enumerate((300000, 350000, 400000))),
                  *(row(f"w{i}", "worker", ctx=900000, cost=1.0) for i in range(3)))
        lines = self.advice()
        self.assertEqual(len(lines), 2, lines)
        lead = next(x for x in lines if "design-seat" in x)
        self.assertIn("500000", lead)
        self.assertIn("autoCompactWindow", lead)
        runner = next(x for x in lines if "design-seat" not in x)
        self.assertIn("runner", runner)
        self.assertIn("350000", runner)
        self.assertIn("team.sh runner rotate", runner)

    def test_the_median_not_the_mean_decides(self):
        self.sink(*(row(f"l{i}", "lead", ctx=c) for i, c in enumerate((100000, 200000, 1500000))),
                  row("w1", "worker", cost=1.0))
        self.assertEqual(self.advice(), [])

    def test_a_high_coordination_share_is_advised(self):
        self.coordination_sink()
        lines = self.advice()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("coordination", lines[0])
        self.assertIn("50%", lines[0])

    def test_no_coordination_advice_before_a_worker_ran(self):
        self.sink(row("l1", "lead", cost=0.3), row("r1", "runner", cost=0.2))
        self.assertEqual(self.advice(), [])
        self.sink(row("l1", "lead", cost=0.3), row("r1", "runner", cost=0.2), row("w1", "worker", cost=0.1))
        lines = json.loads(self.ccp("usage", "--json"))["advice"]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("coordination", lines[0])
        self.assertIn("83%", lines[0])

    def lead_context_knob(self, tokens):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo",
                                                             "usage": {"advice": {"context_tokens": tokens}}}))

    def test_the_leads_median_counts_only_its_sessions_main_model(self):
        self.lead_context_knob(150000)
        self.sink(*(row(f"l{i}", "lead", ctx=c) for i, c in enumerate((100000, 200000, 300000))),
                  *(row(f"h{i}", "lead", ctx=1000, model="claude-haiku-4-5") for i in range(2)),
                  row("w1", "worker", cost=1.0))
        lines = [x for x in json.loads(self.ccp("usage", "--json"))["advice"] if "design-seat" in x]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("median context 200000 ", lines[0])

    def test_the_main_model_is_each_sessions_own(self):
        self.lead_context_knob(150000)
        # s1 runs on one model with a helper on another; s2 runs on that other model with none
        self.sink(*(row(f"a{i}", "lead", ctx=c) for i, c in enumerate((100000, 400000))),
                  row("a9", "lead", ctx=1000, model="claude-haiku-4-5"),
                  row("b1", "lead", ctx=160000, model="claude-haiku-4-5", session="s2"),
                  row("w1", "worker", cost=1.0))
        lines = [x for x in json.loads(self.ccp("usage", "--json"))["advice"] if "design-seat" in x]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("median context 160000 ", lines[0])

    def test_under_every_threshold_there_is_no_advice(self):
        self.sink(row("l1", "lead", cost=0.1, written=1000, five=400), row("r1", "runner", cost=0.1, ctx=290000),
                  row("w1", "worker", cost=0.8, written=1000, five=500))
        self.assertEqual(self.advice(), [])

    def test_the_thresholds_are_plane_json_knobs(self):
        self.coordination_sink()
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo",
                                                             "usage": {"advice": {"coordination_share": 0.6}}}))
        self.assertEqual(self.advice(), [])
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo",
                                                             "usage": {"advice": {"context_tokens": 500}}}))
        lines = self.advice()  # one knob given keeps the others at their defaults: coordination still fires
        self.assertEqual(sum("coordination" in x for x in lines), 1, lines)
        self.assertEqual(sum("autoCompactWindow" in x for x in lines), 1, lines)

    def test_json_carries_the_advice(self):
        self.coordination_sink()
        r = json.loads(self.ccp("usage", "--json"))
        self.assertEqual(len(r["advice"]), 1)
        self.assertIn("coordination", r["advice"][0])

    def test_without_knobs_the_fold_gives_no_cost_advice(self):
        self.coordination_sink()
        self.assertEqual(usage.fold(self.q)["advice"], [])

    def test_health_carries_the_same_lines(self):
        self.git_product()
        self.coordination_sink()
        want = [ln[len("advice: "):] for ln in self.advice()]
        self.assertEqual(len(want), 1)
        self.assertEqual(json.loads(self.ccp("health", "--json"))["usage_advice"], want)
        self.assertIn(f"Usage advice: {want[0]}", self.ccp("health").splitlines())


class Window(AdviceCase):
    """The runner wrote 5-minute cache writes three days ago and only 1-hour ones in the last hour; plane.json
    sets a 24-hour window."""

    def setUp(self):
        super().setUp()
        self.window(24)
        self.sink(row("r1", "runner", written=8000, five=8000, at=ago(72)),
                  row("r2", "runner", written=2000, five=0, at=ago(0.5)),
                  row("w1", "worker", cost=1.0, at=ago(0.5)))
        self.day = (datetime.now(timezone.utc) - timedelta(days=4)).strftime("%Y-%m-%d")

    def window(self, hours):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo",
                                                             "usage": {"advice": {"window_hours": hours}}}))

    def usage(self, *args):
        return json.loads(self.ccp("usage", "--json", *args))

    @staticmethod
    def five(lines):
        return [x for x in lines if "5-minute" in x]

    def test_the_window_leaves_out_what_the_requests_before_it_showed(self):
        r = self.usage()
        self.assertEqual(self.five(r["advice"]), [])
        start = datetime.strptime(r["advice_since"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs((datetime.now(timezone.utc) - timedelta(hours=24) - start).total_seconds()), 60)

    def test_since_gives_the_start_and_each_line_names_it(self):
        r = self.usage("--since", self.day)
        self.assertEqual(r["advice_since"], f"{self.day}T00:00:00Z")
        lines = self.five(r["advice"])
        self.assertEqual(len(lines), 1, r["advice"])
        self.assertTrue(lines[0].startswith("runner: 80% "), lines)
        self.assertTrue(lines[0].endswith(f" (requests since {self.day}T00:00:00Z)"), lines)
        at = ago(1)
        r = self.usage("--since", at)
        self.assertEqual((r["advice_since"], self.five(r["advice"])), (at, []))

    def test_with_no_window_the_advice_reads_every_request(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo"}))
        r = self.usage()
        self.assertIsNone(r["advice_since"])
        lines = self.five(r["advice"])
        self.assertEqual(len(lines), 1, r["advice"])
        self.assertTrue(lines[0].endswith(" (every request)"), lines)
        self.window(0)
        self.assertEqual(self.usage()["advice"], r["advice"])

    def test_a_since_in_another_form_is_refused(self):
        for bad in ("yesterday", "2026-11-01T10:00:00", "2026-11-01 10:00:00Z", "2026-13-01", "2026-11-01T10:00Z"):
            with self.subTest(since=bad):
                self.assertIn("--since", self.ccp("usage", "--since", bad, code=2))

    def test_the_window_bounds_the_contexts_and_the_worker_runs_and_no_other_figure(self):
        self.sink(*(row(f"l{i}", "lead", ctx=900000, cost=0.3, at=ago(72)) for i in range(3)),
                  row("w1", "worker", cost=0.5, at=ago(72)),
                  row("l9", "lead", ctx=1000, cost=0.3, at=ago(0.5)), row("r1", "runner", cost=0.2, at=ago(0.5)))
        every = self.usage("--since", "2000-01-01")
        self.assertEqual(sum("design-seat: median context" in x for x in every["advice"]), 1, every["advice"])
        self.assertEqual(sum("coordination" in x for x in every["advice"]), 1, every["advice"])
        r = self.usage()
        self.assertEqual(r["advice"], [])
        for k in ("seats", "total", "runs", "coverage"):
            self.assertEqual(r[k], every[k], k)

    def test_a_request_with_no_time_is_outside_a_window(self):
        self.sink(row("r1", "runner", written=8000, five=8000, at=None), row("w1", "worker", cost=1.0, at=ago(0.5)))
        self.assertEqual(self.five(self.usage()["advice"]), [])
        self.window(0)
        self.assertEqual(len(self.five(self.usage()["advice"])), 1)

    def test_health_reads_the_same_window(self):
        self.git_product()
        r = json.loads(self.ccp("health", "--json"))
        self.assertEqual(self.five(r["usage_advice"]), [])
        self.assertIsNotNone(r["usage_advice_since"])
        r = json.loads(self.ccp("health", "--json", "--since", self.day))
        self.assertEqual(r["usage_advice_since"], f"{self.day}T00:00:00Z")
        lines = self.five(r["usage_advice"])
        self.assertEqual(len(lines), 1, r["usage_advice"])
        self.assertTrue(lines[0].endswith(f" (requests since {self.day}T00:00:00Z)"), lines)
        self.assertIn(f"Usage advice: {lines[0]}", self.ccp("health", "--since", self.day).splitlines())


class Knobs(unittest.TestCase):
    def load(self, given):
        p = Product({"usage": given})
        try:
            return config.load(p.root)
        finally:
            p.cleanup()

    def test_defaults_and_one_knob_given(self):
        self.assertEqual(self.load({"advice": {"coordination_share": 0.6}}).usage["advice"],
                         {"cache_5m_share": 0.5, "context_tokens": 300000, "coordination_share": 0.6,
                          "window_hours": 0})
        p = Product()
        try:
            self.assertEqual(config.load(p.root).usage, config.USAGE_DEFAULTS)
        finally:
            p.cleanup()

    def test_bad_values_are_refused(self):
        for given in ({"advice": {"coordination_share": 1.5}}, {"advice": {"cache_5m_share": "half"}},
                      {"advice": {"context_tokens": 0}}, {"advice": {"context_tokens": True}},
                      {"advice": {"window_hours": -1}}, {"advice": {"window_hours": True}},
                      {"advice": {"window_hours": 1.5}}, {"advice": {"window_hours": "24"}},
                      {"advice": "x"}, "x"):
            with self.subTest(given=given), self.assertRaises(config.ConfigError):
                self.load(given)


if __name__ == "__main__":
    unittest.main()
