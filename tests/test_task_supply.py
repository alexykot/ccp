"""SPEC §26.4, §27.1: the accepted ADR decisions that no task cites (`adr.untasked`), named by `ccp health`
and `ccp forecast`, which only read."""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import adr, cli, health
from tests.helpers import TASK, Product


def body(n: int) -> str:
    return "# T\n\n## Decision\n\n" + "".join(f"### D{i}. Decision {i}\n\nText.\n\n" for i in range(1, n + 1))


def adr_file(num: int, status: str, states: list[str]) -> str:
    fields = {"id": f"ADR-{num:04d}", "title": "T", "status": status, "date": "2026-01-01",
              "decisions": [f"D{i} {s}" for i, s in enumerate(states, 1)]}
    return adr.emit(fields) + body(len(states))


def task_text(tid: str, status: str, refs: list[str]) -> str:
    ver = "- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*"
    text = TASK.format(tid=tid, title="A task", status=status, deps="", ver=ver)
    return text.replace('spec_refs: ["S1"]\n', 'spec_refs: ["S1"]\nadr_refs: [' + ", ".join(f'"{r}"' for r in refs) + "]\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.p = Product({"adr": {"dir": "docs/adr"}})
        self.addCleanup(self.p.cleanup)

    def adr(self, num: int, status: str, states: list[str]) -> None:
        self.p.write(f"docs/adr/{num:04d}-a.md", adr_file(num, status, states))

    def task(self, tid: str, status: str, refs: list[str]) -> None:
        self.p.write(f"docs/delivery/tasks/{tid}.md", task_text(tid, status, refs))

    def untasked(self) -> list[dict]:
        from ccp import tasklog
        return adr.untasked(self.p.cfg, tasklog.load(self.p.cfg))


class Untasked(Base):
    def test_a_decision_no_task_cites_is_listed_in_order_by_adr_number(self):
        self.adr(7, "accepted", ["not_built", "not_built"])
        self.adr(3, "in-progress", ["not_built"])
        self.assertEqual(self.untasked(), [{"adr": "ADR-0003", "decisions": ["1"]},
                                           {"adr": "ADR-0007", "decisions": ["1", "2"]}])

    def test_a_pending_task_citing_a_decision_takes_only_that_decision_out(self):
        self.adr(1, "accepted", ["not_built", "not_built", "not_built"])
        self.task("0001-a", "pending", ["0001 D2"])
        self.assertEqual(self.untasked(), [{"adr": "ADR-0001", "decisions": ["1", "3"]}])

    def test_a_done_task_also_cites(self):
        self.adr(1, "accepted", ["not_built", "not_built"])
        self.task("0001-a", "done", ["ADR-0001 D1", "ADR-0001 D2"])
        self.assertEqual(self.untasked(), [])

    def test_a_task_dropped_cites_nothing(self):
        self.adr(1, "accepted", ["not_built", "not_built"])
        self.task("0001-a", "dropped", ["0001 D1"])
        self.assertEqual(self.untasked(), [{"adr": "ADR-0001", "decisions": ["1", "2"]}])

    def test_a_ref_naming_only_the_adr_cites_all_its_decisions(self):
        self.adr(1, "accepted", ["not_built", "not_built"])
        self.adr(2, "accepted", ["not_built"])
        self.task("0001-a", "pending", ["ADR-0001"])
        self.task("0002-b", "pending", ["0002"])
        self.assertEqual(self.untasked(), [])

    def test_a_dropped_task_naming_only_the_adr_cites_nothing(self):
        self.adr(1, "accepted", ["not_built"])
        self.task("0001-a", "dropped", ["ADR-0001"])
        self.assertEqual(self.untasked(), [{"adr": "ADR-0001", "decisions": ["1"]}])

    def test_only_not_built_decisions_count(self):
        self.adr(1, "accepted", ["built", "live", "retired", "not_built"])
        self.assertEqual(self.untasked(), [{"adr": "ADR-0001", "decisions": ["4"]}])

    def test_only_accepted_and_in_progress_adrs_count(self):
        for n, st in enumerate(["proposed", "implemented", "rejected", "superseded", "withdrawn", "retired"], 1):
            self.adr(n, st, ["not_built"])
        self.assertEqual(self.untasked(), [])

    def test_no_adr_block_is_empty(self):
        p = Product({"adr": None}, bare=True)
        self.addCleanup(p.cleanup)
        p.write("docs/adr/0001-a.md", adr_file(1, "accepted", ["not_built"]))
        from ccp import tasklog
        self.assertEqual(adr.untasked(p.cfg, tasklog.load(p.cfg)), [])


class Health(Base):
    def run_health(self, *args: str) -> str:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QUEUE_ROOT", None)
            self.assertEqual(cli.main(["--root", str(self.p.root), "health", *args]), 0)
        return out.getvalue()

    def test_the_text_line_and_the_json_key_with_a_list(self):
        self.adr(40, "accepted", ["not_built"] * 6)
        text = self.run_health()
        line = next(x for x in text.splitlines() if x.startswith("Task supply:"))
        self.assertIn("6 accepted", line)
        self.assertIn("ADR-0040 D1-D6", line)
        ts = json.loads(self.run_health("--json"))["task_supply"]
        self.assertEqual(ts, {"untasked_decisions": [{"adr": "ADR-0040", "decisions": [str(i) for i in range(1, 7)]}]})

    def test_the_line_and_a_gap_in_the_decisions(self):
        self.adr(1, "accepted", ["not_built", "built", "not_built", "not_built"])
        line = next(x for x in self.run_health().splitlines() if x.startswith("Task supply:"))
        self.assertIn("3 accepted", line)
        self.assertIn("ADR-0001 D1,D3-D4", line)

    def test_a_decision_id_with_a_letter_is_named_after_the_numbers(self):
        text = adr.emit({"id": "ADR-0001", "title": "T", "status": "accepted", "date": "2026-01-01",
                         "decisions": ["D1 not_built", "D2 not_built", "D2a not_built"]})
        self.p.write("docs/adr/0001-a.md", text + "# T\n\n## Decision\n\n" + "".join(
            f"### D{i}. Decision {i}\n\nText.\n\n" for i in ("1", "2", "2a")))
        self.assertEqual([d for u in self.untasked() for d in u["decisions"]], ["1", "2", "2a"])
        line = next(x for x in self.run_health().splitlines() if x.startswith("Task supply:"))
        self.assertIn("3 accepted", line)
        self.assertIn("ADR-0001 D1-D2,D2a", line)
        self.assertEqual(health._decision_runs(["1", "3", "3b"]), "D1,D3,D3b")

    def test_the_line_names_five_adrs_then_an_ellipsis(self):
        for n in range(1, 8):
            self.adr(n, "accepted", ["not_built"])
        line = next(x for x in self.run_health().splitlines() if x.startswith("Task supply:"))
        self.assertIn("7 accepted", line)
        self.assertTrue(line.endswith("ADR-0005 D1, …)"), line)
        self.assertNotIn("ADR-0006", line)

    def test_no_line_and_an_empty_list_when_every_decision_is_cited(self):
        self.adr(1, "accepted", ["not_built"])
        self.task("0001-a", "pending", ["0001 D1"])
        self.assertNotIn("Task supply", self.run_health())
        self.assertEqual(json.loads(self.run_health("--json"))["task_supply"], {"untasked_decisions": []})

    def test_the_text_helper_is_silent_without_a_list(self):
        self.assertIsNone(health.supply_text(None))
        self.assertIsNone(health.supply_text({"untasked_decisions": []}))


class Forecast(Base):
    def setUp(self):
        super().setUp()
        self.q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.q, True)
        self.task("0001-a", "pending", [])
        (self.q / "estimates").mkdir()
        (self.q / "estimates" / "0001-a.jsonl").write_text(json.dumps({
            "at": "2026-10-22T10:00:00Z", "task_id": "0001-a", "version": 1, "source": "baseline",
            "total": {"p50_s": 600, "p90_s": 900}, "tokens": {"p50": 1e6, "p90": 2e6},
            "cost_usd": {"p50": 1.0, "p90": 2.0}}) + "\n")

    def run_forecast(self, *args: str) -> str:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            self.assertEqual(cli.main(["--root", str(self.p.root), "forecast", *args]), 0, err.getvalue())
        return out.getvalue()

    def test_the_line_after_the_backlog_and_the_json_key_with_a_list(self):
        self.adr(1, "accepted", ["not_built", "not_built"])
        self.adr(2, "in-progress", ["not_built"])
        text = self.run_forecast("--backlog")
        line = next(x for x in text.splitlines() if x.startswith("Not yet tasked:"))
        self.assertIn("3 accepted", line)
        self.assertIn("2 ADR(s)", line)
        self.assertLess(text.index("Open backlog"), text.index(line))
        self.assertEqual(json.loads(self.run_forecast("--backlog", "--json"))["untasked_decisions"],
                         [{"adr": "ADR-0001", "decisions": ["1", "2"]}, {"adr": "ADR-0002", "decisions": ["1"]}])

    def test_no_line_and_an_empty_list_when_every_decision_is_cited(self):
        self.adr(1, "accepted", ["not_built"])
        self.task("0002-b", "pending", ["ADR-0001"])
        self.assertNotIn("Not yet tasked", self.run_forecast("--backlog"))
        self.assertEqual(json.loads(self.run_forecast("--backlog", "--json"))["untasked_decisions"], [])

    def test_the_point_view_has_no_line(self):
        self.adr(1, "accepted", ["not_built"])
        self.assertIn("Not yet tasked", self.run_forecast())
        self.assertNotIn("Not yet tasked", self.run_forecast("--point", "R1"))
        self.assertEqual(len(json.loads(self.run_forecast("--point", "R1", "--json"))["untasked_decisions"]), 1)

    def test_the_line_follows_the_note_when_no_task_is_open(self):
        self.adr(1, "accepted", ["not_built", "not_built"])
        self.task("0001-a", "done", [])
        for args in ((), ("--backlog",)):
            text = self.run_forecast(*args)
            self.assertIn("no open task to forecast", text)
            line = next(x for x in text.splitlines() if x.startswith("Not yet tasked:"))
            self.assertIn("2 accepted", line)
            self.assertLess(text.index("no open task"), text.index(line))
        self.assertNotIn("Not yet tasked", self.run_forecast("--point", "R1"))
        self.assertEqual(len(json.loads(self.run_forecast("--json"))["untasked_decisions"]), 1)

    def test_the_line_follows_the_note_when_no_open_task_has_an_estimate(self):
        self.adr(1, "accepted", ["not_built"])
        (self.q / "estimates" / "0001-a.jsonl").unlink()
        text = self.run_forecast("--backlog")
        self.assertIn("no open task has an estimate", text)
        self.assertIn("Not yet tasked: 1 accepted", text)

    def test_no_line_with_the_note_when_every_decision_is_cited(self):
        self.adr(1, "accepted", ["not_built"])
        self.task("0001-a", "done", ["0001 D1"])
        text = self.run_forecast()
        self.assertIn("no open task to forecast", text)
        self.assertNotIn("Not yet tasked", text)


if __name__ == "__main__":
    unittest.main()
