"""SPEC §2.4: `ccp usage --by-model --seat implementer` compares one seat's tasks by the model they ran on,
for a trial of plane.json `workers.implementer_model`: per model, tasks, cost per task, rounds per task and
MAJOR review findings per task."""
from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ccp import cli, otel, usage
from tests.helpers import api_request as req, Product, T0

OPUS, SONNET = "claude-opus-5-5", "claude-sonnet-5-5"


class UsageByModel(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.q = self.p.root / "queue"
        (self.q / "board").mkdir(parents=True)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        self.reqs: list[dict] = []
        self.spans: list[dict] = []
        self.clock = 0
        # Two tasks whose implement ran on opus: one with a fix round, one MAJOR finding between them.
        self.mkrun("0001-a/implement", "implementer", OPUS, [(OPUS, 3.0)])
        self.mkrun("0001-a/fix", "implementer", OPUS, [(OPUS, 1.0)])
        self.mkrun("0001-a/review", "reviewer", SONNET, [(SONNET, 0.5)], severity={"MAJOR": 1, "MINOR": 2})
        self.mkrun("0002-b/implement", "implementer", OPUS, [(OPUS, 2.0)])
        self.mkrun("0002-b/review", "reviewer", SONNET, [(SONNET, 0.5)], severity={"MAJOR": 0, "MINOR": 1})
        # Three tasks on sonnet (the knob's pick): one with two fix rounds and three MAJOR findings, one whose
        # fix ran on the definition's opus, one whose report carries the findings rather than its run.
        self.mkrun("0003-c/implement", "implementer", SONNET, [(SONNET, 1.0), ("claude-haiku-5-5", 0.1)])
        self.mkrun("0003-c/fix", "implementer", OPUS, [(OPUS, 0.5)])
        self.mkrun("0003-c/fix-2", "implementer", OPUS, [(OPUS, 0.4)])
        self.mkrun("0003-c/review", "reviewer", SONNET, [(SONNET, 0.5)], severity={"MAJOR": 2})
        self.mkrun("0003-c/review-2", "reviewer", SONNET, [(SONNET, 0.5)], severity={"MAJOR": 1})
        self.mkrun("0004-d/implement", "implementer", SONNET, [(SONNET, 0.8)])
        self.mkrun("0005-e/implement", "implementer", OPUS, [])  # recorded nothing: its pinned model counts
        self.mkrun("0005-e/review", "reviewer", SONNET, [], report="Severity: BLOCKER=0 MAJOR=2 MINOR=0 NIT=0\n")
        self.mkrun("0005-e/implement-2", "implementer", OPUS, [], abandoned=True, started=False)  # never started
        self.mkrun("0005-e/implement-3", "implementer", OPUS, [(OPUS, 0.7)])
        self.flush()

    def tearDown(self):
        self.p.cleanup()

    def iso(self, s: int) -> str:
        return datetime.fromtimestamp(T0 / 1e9 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mkrun(self, rid: str, seat: str, model: str, calls: list[tuple[str, float]], severity: dict | None = None,
            report: str | None = None, abandoned: bool = False, started: bool = True) -> None:
        task, phase = rid.split("/")
        self.clock += 100
        agent = f"agent-{rid}" if started else None
        rec = {"run_id": rid, "task_id": task, "phase": phase.split("-")[0], "seat": seat,
               "round": int(phase.split("-")[1]) if "-" in phase else 1, "agent_type": f"delivery-{seat}",
               "expected_model": model, "expected_effort": "high", "agent_id": agent, "opened_at": self.iso(self.clock),
               "started_at": self.iso(self.clock) if started else None, "stopped_at": self.iso(self.clock + 50)}
        if severity is not None:
            rec["severity"] = severity
        if abandoned:
            rec["abandoned_at"] = self.iso(self.clock + 60)
        p = self.q / "runs" / task / f"{phase}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec))
        if report is not None:
            (self.q / "progress" / task).mkdir(parents=True, exist_ok=True)
            (self.q / "progress" / task / f"{phase}-report.md").write_text(report)
        for i, (m, cost) in enumerate(calls):
            rid_ = f"{rid}#{i}"
            r = req(rid_, self.clock + i + 1, model=m, cost_usd=cost)
            t = r.pop("t")
            self.reqs.append({k.replace("__", "_"): v for k, v in r.items()} | {"at": otel._iso(t)})
            self.spans.append({"request_id": rid_, "agent_id": agent})

    def flush(self) -> None:
        for name, rows in (("usage-requests.jsonl", self.reqs), ("usage-spans.jsonl", self.spans)):
            (self.q / "board" / name).write_text("".join(json.dumps(r) + "\n" for r in rows))

    def cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "usage", *args])
        return code, out.getvalue(), err.getvalue()

    def test_one_row_per_model_with_the_figures_per_task(self):
        code, out, err = self.cli("--by-model", "--seat", "implementer", "--json")
        self.assertEqual(code, 0, err)
        rows = {r["model"]: r for r in json.loads(out)["models"]}
        self.assertEqual(set(rows), {OPUS, SONNET})
        opus, sonnet = rows[OPUS], rows[SONNET]
        self.assertEqual((opus["tasks"], opus["task_ids"]), (3, ["0001-a", "0002-b", "0005-e"]))
        self.assertEqual(opus["cost_per_task"], round((3.0 + 1.0 + 2.0 + 0.7) / 3, 4))
        self.assertEqual(opus["rounds_per_task"], round(5 / 3, 2))  # 2 + 1 + 2 (the unstarted round left out)
        self.assertEqual(opus["major_per_task"], 1.0)  # 1 + 0 + 2 from the report's Severity line
        self.assertEqual((sonnet["tasks"], sonnet["task_ids"]), (2, ["0003-c", "0004-d"]))
        self.assertEqual(sonnet["cost_per_task"], round((1.0 + 0.1 + 0.5 + 0.4 + 0.8) / 2, 4))
        self.assertEqual(sonnet["rounds_per_task"], 2.0)  # 3 + 1
        self.assertEqual(sonnet["major_per_task"], 1.5)  # 3 + 0

    def test_the_table_prints_a_row_per_model(self):
        code, out, err = self.cli("--by-model")
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertIn("COST$/TASK", lines[0])
        sonnet = next(x for x in lines if x.startswith(SONNET)).split()
        self.assertEqual(sonnet[1:], ["2", "0", "1.40", "2.00", "1.50"])

    def test_another_seat_groups_by_its_own_runs(self):
        bm = usage.by_model(self.q, usage.fold(self.q), "reviewer")
        self.assertEqual([(r["model"], r["tasks"]) for r in bm["models"]], [(SONNET, 4)])

    def test_with_no_runs_of_the_seat_it_says_so(self):
        code, out, err = self.cli("--by-model", "--seat", "architect")
        self.assertEqual(code, 0, err)
        self.assertIn("no architect runs recorded yet", out)

    def test_the_plain_usage_report_leaves_out_the_per_run_models(self):
        code, out, err = self.cli("--json")
        self.assertEqual(code, 0, err)
        self.assertNotIn("run_models", json.loads(out))


if __name__ == "__main__":
    unittest.main()
