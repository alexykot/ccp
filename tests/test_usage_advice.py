"""SPEC §24.6: `ccp usage` and `ccp health` advise on short-lived cache writes, an oversized context and the
coordination share, at plane.json `usage.advice`'s thresholds."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, usage
from tests.helpers import Product

SPANS = {"lead": {}, "runner": {"agent_id": "runner@session-abc"}, "worker": {"agent_id": "a1"}}


def row(rid, who, ctx=None, cost=0.01, written=0, five=0, model="claude-opus-5-5", session="s1"):
    """One request of `who` (lead, runner or worker) on `model` in `session`, sending `ctx` context tokens
    (default: the writes and a thousand more), `written` of them cache writes, `five` of those at 5 minutes."""
    ctx = written + 1000 if ctx is None else ctx
    return ({"request_id": rid, "at": "2027-01-15T08:00:00Z", "session_id": session, "model": model,
             "effort": "high", "query_source": "repl_main_thread" if who == "lead" else "agent:custom",
             "input_tokens": 1, "output_tokens": 10, "cache_read_tokens": ctx - 1 - written,
             "cache_creation_tokens": written, "cache_creation_5m_tokens": five,
             "cache_creation_1h_tokens": written - five, "cost_usd": cost},
            {"request_id": rid, **SPANS[who]})


class Advice(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\nrunner:\n  name: runner\n")
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

    def ccp(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()), \
                mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            self.assertEqual(cli.main(["--root", str(self.p.root), *args]), 0)
        return out.getvalue()

    def advice(self):
        return [ln for ln in self.ccp("usage").splitlines() if ln.startswith("advice: ")]

    def coordination_sink(self):
        """The lead and the runner at half of all seats' cost, every other measure under its threshold."""
        self.sink(row("l1", "lead", cost=0.3), row("r1", "runner", cost=0.2), row("w1", "worker", cost=0.5))

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
        self.assertIn("runner.rotate_at_context_tokens", runner)

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
        subprocess.run(["git", "-C", str(self.p.root), "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", str(self.p.root), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
                        "--allow-empty", "-m", "init"], check=True)
        self.coordination_sink()
        want = [ln[len("advice: "):] for ln in self.advice()]
        self.assertEqual(len(want), 1)
        self.assertEqual(json.loads(self.ccp("health", "--json"))["usage_advice"], want)
        self.assertIn(f"Usage advice: {want[0]}", self.ccp("health").splitlines())


class Knobs(unittest.TestCase):
    def load(self, given):
        p = Product({"usage": given})
        try:
            return config.load(p.root)
        finally:
            p.cleanup()

    def test_defaults_and_one_knob_given(self):
        self.assertEqual(self.load({"advice": {"coordination_share": 0.6}}).usage["advice"],
                         {"cache_5m_share": 0.5, "context_tokens": 300000, "coordination_share": 0.6})
        p = Product()
        try:
            self.assertEqual(config.load(p.root).usage, config.USAGE_DEFAULTS)
        finally:
            p.cleanup()

    def test_bad_values_are_refused(self):
        for given in ({"advice": {"coordination_share": 1.5}}, {"advice": {"cache_5m_share": "half"}},
                      {"advice": {"context_tokens": 0}}, {"advice": {"context_tokens": True}},
                      {"advice": "x"}, "x"):
            with self.subTest(given=given), self.assertRaises(config.ConfigError):
                self.load(given)

    def test_the_schema_names_the_knobs(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "plane_config.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["usage"]["properties"]), set(config.USAGE_DEFAULTS))
        self.assertEqual(set(schema["properties"]["usage"]["properties"]["advice"]["properties"]),
                         set(config.USAGE_DEFAULTS["advice"]))


if __name__ == "__main__":
    unittest.main()
