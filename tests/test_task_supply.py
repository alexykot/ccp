"""SPEC §26.4, §27.1: the accepted ADR decisions that no task cites (`adr.untasked`), named by `ccp health`
and `ccp forecast`, which only read; §23.2: the runner slots left with nothing ready (`ccp tasks next --holder`
records each stretch once) and the slot-hours `ccp health` reports them idle."""
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

    def test_a_decision_with_no_recorded_state_is_not_listed(self):
        fields = {"id": "ADR-0002", "title": "T", "status": "accepted", "date": "2026-01-01", "decisions": ["D1 not_built"]}
        self.p.write("docs/adr/0002-a.md", adr.emit(fields) + body(3))
        self.assertEqual(self.untasked(), [{"adr": "ADR-0002", "decisions": ["1"]}])

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

    def test_two_files_with_one_number_are_each_read_on_their_own(self):
        self.adr(3, "accepted", ["not_built"])
        self.p.write("docs/adr/0003-b.md", adr_file(3, "accepted", ["built", "built"]))
        self.assertEqual(self.untasked(), [{"adr": "ADR-0003", "decisions": ["1"]}])

    def test_a_ref_naming_only_the_adr_cites_all_its_decisions(self):
        self.adr(1, "accepted", ["not_built", "not_built"])
        self.adr(2, "accepted", ["not_built"])
        self.task("0001-a", "pending", ["ADR-0001"])
        self.task("0002-b", "pending", ["0002"])
        self.assertEqual(self.untasked(), [])

    def test_a_section_anchor_ref_cites_no_decision(self):
        self.adr(1, "accepted", ["not_built", "not_built"])
        self.task("0001-a", "pending", ["0001 Implementation 2"])
        self.assertEqual(self.untasked(), [{"adr": "ADR-0001", "decisions": ["1", "2"]}])

    def test_a_ref_naming_the_adr_file_cites_all_its_decisions(self):
        self.adr(1, "accepted", ["not_built", "not_built"])
        self.adr(2, "accepted", ["not_built"])
        self.task("0001-a", "pending", ["docs/adr/0001-a.md"])
        self.task("0002-b", "pending", ["adr/0002-a.md"])
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
        self.assertEqual(ts, {"untasked_decisions": [{"adr": "ADR-0040", "decisions": [str(i) for i in range(1, 7)]}],
                              "idle_slots": None})

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
        self.assertEqual(json.loads(self.run_health("--json"))["task_supply"], {"untasked_decisions": [], "idle_slots": None})

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



def at(hours: float) -> str:
    """An RFC3339 time `hours` after 2026-11-20 08:00 UTC."""
    from datetime import datetime, timedelta, timezone
    return (datetime(2026, 11, 20, 8, tzinfo=timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(hours: float, typ: str, op: str, **payload) -> dict:
    return {"at": at(hours), "project_id": "demo", "task_id": "", "actor": "task-runner", "type": typ, "op": op,
            "payload": payload}


def starved_ev(hours: float, slot: str) -> dict:
    return ev(hours, "runner", "starved", slot=slot, scope=[], in_flight=0)


class QueueBase(Base):
    def setUp(self):
        super().setUp()
        self.q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.q, True)
        (self.q / "observability").mkdir()
        self.task("0001-a", "done", [])

    def ledger(self, *events: dict) -> None:
        with (self.q / "observability" / "events.jsonl").open("a") as fh:
            fh.writelines(json.dumps(e) + "\n" for e in events)

    def events(self, typ: str, op: str) -> list[dict]:
        p = self.q / "observability" / "events.jsonl"
        rows = [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []
        return [e for e in rows if (e["type"], e["op"]) == (typ, op)]

    def next(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            code = cli.main(["--root", str(self.p.root), "tasks", "next", "--scope", "0001", *args])
        return code, err.getvalue()


class Starved(QueueBase):
    def test_the_json_path_records_one_event_per_stretch_and_a_claim_ends_it(self):
        self.assertEqual(self.next("--holder", "runner-1", "--json")[0], 3)
        evs = self.events("runner", "starved")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["payload"], {"slot": "runner-1", "scope": ["0001"], "in_flight": 0})
        self.assertEqual(evs[0]["task_id"], "")
        self.assertEqual(self.next("--holder", "runner-1", "--json")[0], 3)
        self.assertEqual(len(self.events("runner", "starved")), 1)
        self.ledger(ev(0, "lease", "set", holder="runner-2"))  # another slot's claim leaves this stretch open
        self.assertEqual(self.next("--holder", "runner-1", "--json")[0], 3)
        self.assertEqual(len(self.events("runner", "starved")), 1)
        self.ledger(ev(0, "lease", "set", holder="runner-1"))
        self.assertEqual(self.next("--holder", "runner-1", "--json")[0], 3)
        self.assertEqual(len(self.events("runner", "starved")), 2)

    def test_the_plain_path_records_it_and_no_holder_records_nothing(self):
        self.assertEqual(self.next()[0], 3)
        self.assertEqual(self.next("--json")[0], 3)
        self.assertEqual(self.events("runner", "starved"), [])
        self.assertEqual(self.next("--holder", "runner")[0], 3)
        self.assertEqual([e["payload"]["slot"] for e in self.events("runner", "starved")], ["runner"])

    def test_the_actor_is_the_callers(self):
        with mock.patch.dict(os.environ, {"ACTOR": "design-seat"}):
            self.next("--holder", "runner")
        self.assertEqual([e["actor"] for e in self.events("runner", "starved")], ["design-seat"])

    def test_in_flight_counts_the_tasks_the_slot_holds(self):
        (self.q / "work.json").write_text(json.dumps({"in_flight": ["0002-b", "0003-c", "0004-d"]}))
        (self.q / "tasks").mkdir()
        for tid, holder, status in (("0002-b", "runner-1", "implementing"), ("0003-c", "runner-2", "reviewing"),
                                    ("0004-d", "runner-1", "done")):
            (self.q / "tasks" / f"{tid}.json").write_text(json.dumps({"lease_holder": holder, "status": status}))
        self.assertEqual(self.next("--holder", "runner-1")[0], 3)
        self.assertEqual([e["payload"]["in_flight"] for e in self.events("runner", "starved")], [1])

    def test_a_failed_write_is_a_warning_and_keeps_the_exit_code(self):
        from ccp.queue import QueueError
        with mock.patch("ccp.queue.emit", side_effect=QueueError("disk full")):
            code, err = self.next("--holder", "runner-1")
        self.assertEqual(code, 3)
        self.assertIn("warning:", err)
        self.assertEqual(self.events("runner", "starved"), [])

    def test_a_found_task_records_nothing(self):
        self.task("0002-b", "pending", [])
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()), mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            self.assertEqual(cli.main(["--root", str(self.p.root), "tasks", "next", "--holder", "runner-1"]), 0)
        self.assertEqual(self.events("runner", "starved"), [])


class StretchOpen(unittest.TestCase):
    def test_what_ends_a_stretch(self):
        s = [starved_ev(0, "runner-1")]
        self.assertTrue(health.starved_open(s, "runner-1"))
        self.assertFalse(health.starved_open(s, "runner-2"))
        self.assertFalse(health.starved_open([], "runner-1"))
        for closing, closes in ((ev(1, "lease", "set", holder="runner-1"), True),
                                (ev(1, "lease", "set", holder="runner-2"), False),
                                (ev(1, "lease", "clear", holder="runner-1"), False),
                                (ev(1, "runner", "stop", name="r", reason="stop", slot="runner-1"), True),
                                (ev(1, "runner", "stop", name="r", reason="stop", slot="runner-2"), False),
                                (ev(1, "runner", "stop", name="r", reason="stop", slot=None), True),
                                (ev(1, "runner", "stop", name="r", reason="stop"), True),
                                (ev(1, "runner", "spawn", name="r", scope=[], prompt_ref="p", slot="runner-1"), True),
                                (ev(1, "runner", "spawn", name="r", scope=[], prompt_ref="p", slot="runner-2"), False),
                                (ev(1, "runner", "spawn", name="r", scope=[], prompt_ref="p"), True),
                                (ev(1, "runner", "rotate", name="r", reason="r", slot="runner-1"), False)):
            self.assertEqual(health.starved_open(s + [closing], "runner-1"), not closes, closing)
            self.assertTrue(health.starved_open(s + [closing, starved_ev(2, "runner-1")], "runner-1"))


class StarvedHours(QueueBase):
    NOW = health._epoch(at(10))

    def test_a_stretch_closed_by_a_stop_two_hours_later(self):
        self.ledger(starved_ev(0, "runner-1"), ev(2, "runner", "stop", name="r", reason="stop", slot="runner-1"))
        self.assertEqual(health.starved(self.q, None, now=self.NOW), {"slot_hours": 2.0, "stretches": 1, "open": []})

    def test_a_stretch_with_no_closing_event_runs_to_now_and_is_open(self):
        self.ledger(starved_ev(0, "runner-1"), starved_ev(4, "runner-2"), starved_ev(5, "runner-2"),
                    ev(6, "lease", "set", holder="runner-1"))
        self.assertEqual(health.starved(self.q, None, now=self.NOW), {"slot_hours": 12.0, "stretches": 2,
                                                                      "open": ["runner-2"]})

    def test_a_stop_with_no_slot_ends_every_stretch(self):
        self.ledger(starved_ev(0, "runner-1"), starved_ev(1, "runner-2"), ev(3, "runner", "stop", name="r", reason="stop"))
        self.assertEqual(health.starved(self.q, None, now=self.NOW), {"slot_hours": 5.0, "stretches": 2, "open": []})

    def test_only_the_part_inside_the_window_counts(self):
        self.ledger(starved_ev(0, "runner-1"), ev(2, "lease", "set", holder="runner-1"),
                    starved_ev(3, "runner-1"), ev(6, "lease", "set", holder="runner-1"))
        self.assertEqual(health.starved(self.q, health._epoch(at(4)), now=self.NOW),
                         {"slot_hours": 2.0, "stretches": 1, "open": []})
        self.assertEqual(health.starved(self.q, None, now=self.NOW)["stretches"], 2)

    def run_health(self, *args: str) -> str:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()), mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            self.assertEqual(cli.main(["--root", str(self.p.root), "health", *args]), 0)
        return out.getvalue()

    def test_the_idle_slots_line_with_a_stretch_and_not_without(self):
        self.assertNotIn("Idle slots", self.run_health())
        self.assertEqual(json.loads(self.run_health("--json"))["task_supply"]["idle_slots"],
                         {"slot_hours": 0.0, "stretches": 0, "open": []})
        self.ledger(starved_ev(0, "runner-1"), ev(2, "runner", "stop", name="r", reason="stop", slot="runner-1"))
        line = next(x for x in self.run_health().splitlines() if x.startswith("Idle slots:"))
        self.assertIn("2.0 slot-hour(s)", line)
        self.assertIn("(1 stretch(es))", line)
        self.assertEqual(json.loads(self.run_health("--json"))["task_supply"]["idle_slots"],
                         {"slot_hours": 2.0, "stretches": 1, "open": []})
        self.assertIsNone(health.idle_text(None))


if __name__ == "__main__":
    unittest.main()
