"""The architect seat is on without a block, and enforces from the product's adoption point (SPEC §19.11):
the cadence and its blocks at `ccp tasks next`, the kind and refactor-reference checks of `ccp tasks check`, the
refactor lane and the house rules doc. Only `"architect": false` turns the seat off; with no adoption point
(`architect.shape_from_task`) the seat is on and enforces nothing, and says so."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import architect, cli, config, parallel, quality, rules, tasklog
from tests.helpers import PLANE_ROOT, Product
from tests.architect_fixture import Harness
from tests.upgrade_fixture import UpgradeFixture

REFACTOR = "kind: refactor\n"
E7 = "E7: app/big.py has 9 lines > 5"


def cite(f: Path, *rule_ids: str) -> None:
    """Give the task file `f` a `rule_refs` list of `rule_ids`."""
    refs = ", ".join(f'"{r}"' for r in rule_ids)
    f.write_text(f.read_text().replace('spec_refs: ["S1"]', f'spec_refs: ["S1"]\nrule_refs: [{refs}]'))


class Seat(unittest.TestCase):
    """A product with `done` tasks 0001..000<done> and `pending` more, whose plane.json holds `architect`
    as given, or no `architect` key at all (`architect=None`)."""

    def make(self, architect=None, done: int = 10, pending: int = 6, **plane) -> Product:
        p = Product({**plane, "architect": architect if architect is not None else {}})
        raw = json.loads((p.root / "docs/delivery/plane.json").read_text())
        if architect is None:
            del raw["architect"]
        p.write("docs/delivery/plane.json", json.dumps(raw))
        for i in range(1, done + pending + 1):
            p.task(f"{i:04d}-t{i}", "done" if i <= done else "pending")
        p.index()
        self.addCleanup(p.cleanup)
        q = tempfile.TemporaryDirectory()
        self.addCleanup(q.cleanup)
        self.q = Path(q.name)
        env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), "ACTOR": "task-runner"})
        env.start()
        self.addCleanup(env.stop)
        return p

    def ccp(self, p: Product, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = cli.main(["--root", str(p.root), *args])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 2
        return code, out.getvalue(), err.getvalue()

    def due(self, p: Product) -> dict:
        code, out, err = self.ccp(p, "architect", "due")
        self.assertEqual(code, 0 if json.loads(out)["due"] else 3, out + err)  # `due` exits 3 while nothing is due
        return json.loads(out)

    def merge(self, p: Product, n: int) -> None:
        p.task(f"{n:04d}-t{n}", "done")
        p.index()


class NoAdoptionPoint(Seat):
    def setUp(self):
        self.p = self.make()  # ten done tasks, no architect key, no adoption point

    def test_the_seat_is_on_and_says_it_enforces_nothing(self):
        d = self.due(self.p)
        self.assertIs(d["enabled"], True)
        self.assertIs(d["due"], False)
        self.assertEqual(d["reason"], architect.NO_ADOPTION_POINT)
        self.assertIn("architect.shape_from_task", d["reason"])
        self.assertEqual(d["reasons"], [])

    def test_ten_merges_owe_no_pass_and_next_is_not_blocked(self):
        code, out, err = self.ccp(self.p, "tasks", "next")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("0011-t11"))
        self.assertNotIn("architect", err)

    def test_next_needs_no_queue_root(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("QUEUE_ROOT")
            code, out, err = self.ccp(self.p, "tasks", "next")
        self.assertEqual(code, 0, out + err)

    def test_the_gate_names_nothing_blocked(self):
        g = architect.gate(self.p.cfg, self.q, None, None)
        self.assertIsNone(g["blocked"])
        self.assertEqual(g["notices"], [])

    def test_a_report_awaiting_triage_does_not_block_an_unadopted_seat(self):
        (self.q / "architect.json").write_text(json.dumps({"reviews": {"ar-1": {
            "status": "reported", "mode": "pass", "done_at_report": ["0001-t1"]}}}))
        g = architect.gate(self.p.cfg, self.q, None, None)
        self.assertEqual((g["blocked"], g["notices"]), (None, []))
        self.assertEqual(self.ccp(self.p, "tasks", "next")[0], 0)

    def test_a_done_refactor_citing_the_spec_passes_tasks_check(self):
        f = self.p.task("0004-t4", "done")
        f.write_text(f.read_text().replace("status: done", "status: done\n" + REFACTOR.strip()))
        self.p.index()
        code, out, err = self.ccp(self.p, "tasks", "check")
        self.assertEqual(code, 0, out + err)

    def test_a_forced_pass_still_runs_its_prompt(self):
        cfg = self.p.cfg
        text = architect.prompt_for(cfg, self.q, "ar-1", "pass", ["structure"], "abc", None, False, None, "forced", None)
        self.assertIn("docs/ENGINEERING.md is missing, so this pass runs without house rules", text)

    def test_the_refactor_lane_does_not_reorder_tasks(self):
        for n in (12, 13, 14, 15):
            f = self.p.task(f"{n:04d}-t{n}", "pending")
        f = self.p.task("0016-t16", "pending")
        f.write_text(f.read_text().replace("status: pending", "status: pending\n" + REFACTOR.strip()))
        order = [t["task_id"] for t, _ in tasklog.ranked(self.p.cfg, None, since=9)]
        self.assertEqual(order, sorted(order))

    def test_waiting_refactors_and_the_review_points_are_not_read_unadopted(self):
        from ccp import board, selection
        f = self.p.task("0016-t16", "pending")
        f.write_text(f.read_text().replace("status: pending", "status: pending\n" + REFACTOR.strip()))
        cfg = self.p.cfg
        self.assertEqual(tasklog.waiting_refactors(cfg, ["0011"]), [])
        self.assertEqual(tasklog.refactor_reach(cfg, tasklog.load(cfg), ["0011"]), {})
        self.assertIsNone(board._refactors_waiting(cfg, ["0011"]))
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0011"],
                                                      "review_point_refactors": ["0011"]}))
        self.assertEqual(selection.inputs(cfg, self.q)["first"], [])

    def test_a_refactor_outside_the_scope_is_not_pulled_in_unadopted(self):
        p = self.make({"refactor_in_scope": True})
        f = p.task("0016-t16", "pending")
        f.write_text(f.read_text().replace("status: pending", "status: pending\n" + REFACTOR.strip()))
        self.assertEqual(tasklog.refactor_reach(p.cfg, tasklog.load(p.cfg), ["0011"]), {})
        adopted = self.make({"refactor_in_scope": True, "shape_from_task": "0001"})
        g = adopted.task("0016-t16", "pending")
        g.write_text(g.read_text().replace("status: pending", "status: pending\n" + REFACTOR.strip()))
        self.assertEqual(list(tasklog.refactor_reach(adopted.cfg, tasklog.load(adopted.cfg), ["0011"])), ["0016-t16"])

    def test_a_refactor_numbered_before_the_adoption_point_is_no_refactor_for_the_lane(self):
        from ccp import board, forecast
        p = self.make({"shape_from_task": "0015", "refactor_in_scope": True}, done=10, pending=6)
        for n in (13, 16):  # 0013 is before the point, 0016 from it
            f = p.task(f"{n:04d}-t{n}", "pending")
            f.write_text(f.read_text().replace("status: pending", "status: pending\n" + REFACTOR.strip()))
        cfg = p.cfg
        tasks = tasklog.load(cfg)
        ids = lambda rows: [t["task_id"] for t, _ in rows]  # noqa: E731
        self.assertEqual(ids(tasklog.ranked(cfg, None, since=9))[0], "0016-t16")  # a refactor is due: the one from the point
        self.assertEqual(ids(tasklog.ranked(cfg, ["0011"], since=9))[:2], ["0016-t16", "0011-t11"])
        self.assertEqual(list(tasklog.refactor_reach(cfg, tasks, ["0011"])), ["0016-t16"])
        self.assertEqual([t["task_id"] for t in tasklog.waiting_refactors(cfg, ["0011"])], [])
        self.assertEqual(board._refactors_waiting(cfg, [])["ids"], ["0016-t16"])
        merged = [f"{i:04d}-t{i}" for i in range(1, 11)]
        order = forecast.sequence(cfg, self.q, tasks, merged)["order"]
        self.assertEqual(order, ["0016-t16", "0011-t11", "0012-t12", "0013-t13", "0014-t14", "0015-t15"])

    def test_the_forecast_order_has_no_refactor_lane_unadopted_and_has_one_adopted(self):
        from ccp import forecast
        orders = {}
        for name, block in (("unadopted", None), ("adopted", {"shape_from_task": "0001"})):
            p = self.make(block, done=4, pending=5)
            f = p.task("0009-t9", "pending")
            f.write_text(f.read_text().replace("status: pending", "status: pending\n" + REFACTOR.strip()))
            merged = [f"{i:04d}-t{i}" for i in range(1, 5)]
            orders[name] = forecast.sequence(p.cfg, self.q, tasklog.load(p.cfg), merged)["order"]
        self.assertEqual(orders["unadopted"], sorted(orders["unadopted"]))
        self.assertEqual(orders["adopted"][0], "0009-t9")

    def test_the_board_sections_see_the_seat_on(self):
        cfg = self.p.cfg
        self.assertTrue(config.architect_on(cfg))
        self.assertIsNotNone(quality.house_rules(cfg))
        self.assertIsNotNone(quality.architect(cfg, self.q, tasklog.load(cfg), None))

    def test_the_default_rules_doc_missing_is_no_failure_but_a_named_one_is(self):
        self.assertEqual(rules.check(self.p.cfg), [])
        named = self.make({"rules_doc": "docs/HOUSE.md"})
        self.assertEqual(len(rules.check(named.cfg)), 1)
        self.assertIn("docs/HOUSE.md: missing", rules.check(named.cfg)[0])


class AdoptedAt0011(Seat):
    def setUp(self):
        self.p = self.make({"shape_from_task": "0011"})

    def test_ten_older_merges_owe_nothing(self):
        d = self.due(self.p)
        self.assertEqual((d["enabled"], d["due"], d["done_since_last"], d["adoption_point"]), (True, False, 0, 11))
        self.assertIn("0 of 4 tasks done", d["reason"])

    def test_it_is_due_after_four_more_merges_and_not_before(self):
        for n in (11, 12, 13):
            self.merge(self.p, n)
            self.assertIs(self.due(self.p)["due"], False, n)
        self.merge(self.p, 14)
        d = self.due(self.p)
        self.assertEqual((d["due"], d["done_since_last"]), (True, 4))
        self.assertIn("4 task(s) done since none", d["reason"])

    def test_the_block_at_next_counts_from_the_adoption_point(self):
        for n in (11, 12, 13, 14, 15):
            self.merge(self.p, n)
        code, out, err = self.ccp(self.p, "tasks", "next")
        self.assertEqual(code, 4, out + err)
        self.assertIn("architect pass due: 5 task(s) done since none", out)

    def test_kinds_are_read_only_from_the_adoption_point(self):
        f = self.p.task("0010-t10", "done")
        f.write_text(f.read_text().replace("status: done", "status: done\n" + REFACTOR.strip()))
        self.p.index()
        self.assertEqual(self.ccp(self.p, "tasks", "check")[0], 0)  # before the point: an old refactor citing the spec
        g = self.p.task("0011-t11", "done")
        g.write_text(g.read_text().replace("status: done", "status: done\n" + REFACTOR.strip()))
        self.p.index()
        code, out, err = self.ccp(self.p, "tasks", "check")
        self.assertEqual(code, 1, out + err)
        self.assertIn("0011-t11.md: a refactor changes no rule", out + err)
        self.assertNotIn("0010-t10.md", out + err)

    def test_a_missing_rules_doc_is_reported_and_a_present_one_is_named(self):
        self.assertEqual(self.due(self.p)["rules_doc"], "missing: docs/ENGINEERING.md")
        self.p.write("docs/ENGINEERING.md", "# Rules\n")
        self.assertEqual(self.due(self.p)["rules_doc"], "docs/ENGINEERING.md")


class SeatOff(Seat):
    def test_false_turns_it_off_and_the_gate_never_asks_for_a_queue(self):
        p = self.make(False)
        self.assertFalse(config.architect_on(p.cfg))
        self.assertIsNone(p.cfg.architect)
        d = self.due(p)
        self.assertEqual((d["enabled"], d["due"]), (False, False))
        self.assertIn('"architect": false', d["reason"])
        with mock.patch.dict(os.environ):
            os.environ.pop("QUEUE_ROOT")
            self.assertEqual(self.ccp(p, "tasks", "next")[0], 0)

    def test_a_pass_run_without_force_is_disabled_and_with_it_is_not(self):
        p = self.make(False)
        code, out, _ = self.ccp(p, "architect", "run")
        self.assertEqual((code, json.loads(out)["outcome"]), (3, "disabled"))


class NoPassOwedAtAdoption(Seat):
    """Before a product's first pass each trigger counts only what follows the adoption point (§19.6), so a
    product that adopts the seat with history owes no pass at once."""

    def setUp(self):
        self.p = self.make({"shape_from_task": "0011"})  # tasks 0001..0010 are done and predate the adoption point
        self.notes_due = self.p.cfg.architect["notes_due"]
        self.drift = {"drift": True, "drift_ratio": 2.0}

    def info(self, record: bool = True, scope=None, budgets=()) -> dict:
        with mock.patch.object(architect.health, "trend", return_value=self.drift), \
                mock.patch.object(architect.rules, "budget_failures", return_value=list(budgets)):
            return architect.due_info(self.p.cfg, self.q, scope, record=record)

    def note(self, n: int, task: str | None) -> None:
        for i in range(n):
            architect.health.add_note(self.q, f"friction {i}", task_id=task)

    def state(self) -> dict:
        f = self.q / "architect.json"
        return json.loads(f.read_text()) if f.is_file() else {}

    def test_history_owes_nothing(self):
        self.note(self.notes_due + 5, "0003-t3")
        self.note(self.notes_due, None)  # a note with no task does not count
        scope = ["0001", "0002", "0003"]  # a done review-point scope of pre-adoption tasks
        for record in (False, True, True):
            info = self.info(record, scope, budgets=["E7: app/big.py has 9 lines > 5"])
            self.assertEqual((info["reasons"], info["due"]), ([], False), record)
        self.assertEqual(self.ccp(self.p, "architect", "due")[0], 3)

    def test_cadence_from_the_adoption_point(self):
        cfg = self.p.cfg
        for n in range(11, 11 + cfg.architect["every_n_tasks"] * int(parallel.settings(cfg)["max_in_flight"])):
            self.merge(self.p, n)
        self.note(self.notes_due + 5, "0003-t3")
        info = self.info(budgets=["E7: app/big.py has 9 lines > 5"])
        self.assertEqual(len(info["reasons"]), 1, info["reasons"])
        self.assertIn("task(s) done since none", info["reasons"][0])

    def test_new_work_still_triggers(self):
        self.note(self.notes_due, "0011-t11")
        info = self.info()
        self.assertEqual(len(info["reasons"]), 1, info["reasons"])
        self.assertIn(f"{self.notes_due} friction note(s) since none", info["reasons"][0])
        # With a recorded pass, the notes since it count whatever their task.
        (self.q / "architect.json").write_text(json.dumps({"schema_version": 1, "reviews": {}, "last": {
            "review_id": "ar-20261020T100000Z-abcd", "started_at": "2026-10-20T10:00:00Z", "done": [],
            "health_drift": True}}))
        info = self.info()
        self.assertEqual(len(info["reasons"]), 1, info["reasons"])
        self.assertIn(f"{self.notes_due} friction note(s) since ar-20261020T100000Z-abcd", info["reasons"][0])

    def last_pass(self, **extra) -> None:
        (self.q / "architect.json").write_text(json.dumps({"schema_version": 1, "reviews": {}, "last": {
            "review_id": "ar-20261020T100000Z-abcd", "started_at": "2026-10-20T10:00:00Z", "done": [], **extra}}))

    def test_after_a_pass_the_notes_of_any_task_count(self):
        self.last_pass(health_drift=True)
        self.note(self.notes_due - 1, None)  # no task
        self.note(1, "0003-t3")  # a task before the adoption point
        info = self.info()
        self.assertEqual(len(info["reasons"]), 1, info["reasons"])
        self.assertIn(f"{self.notes_due} friction note(s) since ar-20261020T100000Z-abcd", info["reasons"][0])

    def test_after_a_pass_drift_that_the_pass_did_not_see_triggers(self):
        self.last_pass()
        info = self.info()
        self.assertEqual(len(info["reasons"]), 1, info["reasons"])
        self.assertIn("health drift", info["reasons"][0])
        self.last_pass(health_drift=True)  # drift the last pass already saw is not new
        self.assertEqual(self.info()["reasons"], [])

    def test_a_budget_breached_after_adoption_triggers(self):
        a, b = "a: app/a.py has 9 lines > 5", "b: app/b.py has 9 lines > 5"
        self.assertEqual(self.info(record=False, budgets=[a])["reasons"], [])
        self.assertNotIn("budget_baseline", self.state())  # a read computes the baseline and never writes it
        self.assertEqual(self.info(budgets=[a])["reasons"], [])
        self.assertEqual(self.state()["budget_baseline"], ["a"])
        info = self.info(budgets=[a, b])
        self.assertEqual(info["reasons"], [f"budget check fails: {b}"])
        self.assertEqual(self.info(budgets=[a])["reasons"], [])  # the baseline is kept, not rewritten
        self.assertEqual(self.state()["budget_baseline"], ["a"])

    def test_a_breach_a_pending_task_cites_calls_no_pass_until_that_task_is_done(self):
        self.assertEqual(self.info()["reasons"], [])  # the baseline: no budget failing
        cite(self.p.task("0016-t16", "pending"), "E8")  # a pending task citing another rule leaves the breach new
        self.p.index()
        self.assertEqual(self.info(budgets=[E7])["reasons"], [f"budget check fails: {E7}"])
        cite(self.p.task("0016-t16", "pending"), "E8", "E7")
        self.p.index()
        info = self.info(budgets=[E7])
        self.assertEqual((info["reasons"], info["budget_failures"]), ([], [E7]))  # still listed, calls no pass
        cite(self.p.task("0016-t16", "done"), "E8", "E7")
        self.p.index()
        self.assertEqual(self.info(budgets=[E7])["reasons"], [f"budget check fails: {E7}"])


class CadenceScalesWithSlots(Seat):
    """§19.6: the cadence waits for `every_n_tasks` times the tasks the product runs at once."""

    def slots(self, n: int) -> Product:
        return self.make({"shape_from_task": "0011", "every_n_tasks": 4},
                         parallel={"max_in_flight": n, "schedule": "paths"})

    def test_three_slots_wait_for_twelve_merges(self):
        p = self.slots(3)
        for n in range(11, 22):
            self.merge(p, n)
        d = self.due(p)
        self.assertEqual((d["due"], d["reasons"], d["cadence_tasks"]), (False, [], 12))
        self.assertIn("11 of 12 tasks done", d["reason"])
        self.merge(p, 22)
        d = self.due(p)
        self.assertEqual((d["due"], len(d["reasons"]), d["merges_since_due"]), (True, 1, 0), d["reasons"])
        self.assertIn("12 task(s) done since none", d["reasons"][0])
        self.merge(p, 23)  # the merges since it fell due count from the twelfth
        self.assertEqual(self.due(p)["merges_since_due"], 1)

    def test_one_slot_waits_for_four_merges(self):
        p = self.slots(1)
        for n in (11, 12, 13):
            self.merge(p, n)
        d = self.due(p)
        self.assertEqual((d["due"], d["cadence_tasks"]), (False, 4))
        self.merge(p, 14)
        d = self.due(p)
        self.assertEqual((d["due"], len(d["reasons"])), (True, 1), d["reasons"])
        self.assertIn("4 task(s) done since none", d["reasons"][0])


class APassAndATaskedBreach(Harness):
    """A pass does not record a breach a pending task cites as seen (§19.6), so the breach calls the next pass
    once that task is done."""

    def test_the_breach_calls_a_pass_once_the_citing_task_is_done(self):
        e9 = "E9: app/other.py has 9 lines > 5"
        cite(self.p.task("0008-t8"), "E7")
        self.merge(1)
        self.stub_report([])
        with mock.patch.object(architect.rules, "budget_failures", return_value=[E7, e9]):
            code, res, _ = self.dpj("architect", "run", "--force")
            self.assertEqual((code, res["outcome"]), (0, "no_findings"), res)
            self.assertEqual(self.state()["last"]["budget_ids"], ["E9"])
            self.assertEqual(architect.due_info(self.p.cfg, self.q)["reasons"], [])
            self.merge(8)
            self.assertEqual(architect.due_info(self.p.cfg, self.q)["reasons"], [f"budget check fails: {E7}"])


class Adoption(Seat):
    def test_an_unadopted_seat_is_not_adopted_and_an_adopted_one_is(self):
        self.assertFalse(config.architect_adopted(self.make().cfg))
        self.assertFalse(config.architect_adopted(self.make(False).cfg))
        self.assertTrue(config.architect_adopted(self.make({"shape_from_task": "0003"}).cfg))


class AdoptionStep(UpgradeFixture, unittest.TestCase):
    """§29.3: `ccp upgrade status` lists the adoption-point step until the product records it or sets
    `"architect": false`, and proposes its next task number."""

    def setUp(self):
        super().setUp()
        self.plane_task("0001-arc", "done", "Arc", "required: plane.json architect.shape_from_task (the adoption point)")
        self.commit("plane")
        for i in (1, 2, 3):
            self.product.task(f"{i:04d}-t{i}", "done")

    def steps(self, **plane) -> list[dict]:
        self.product_json(**plane)
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        return [s for s in body["steps"] if s["task"] == "0001-arc"]

    def test_it_proposes_the_next_task_number_or_the_seat_off(self):
        (step,) = self.steps()
        self.assertTrue(step["required"])
        self.assertIn("to 0004, the next task number", step["change"])
        self.assertIn('"architect": false', step["change"])

    def test_a_recorded_point_or_the_seat_off_has_taken_it(self):
        self.assertEqual(self.steps(architect={"shape_from_task": "0004"}), [])
        self.assertEqual(self.steps(architect=False), [])

    def test_a_block_without_the_point_has_not_taken_it(self):
        self.assertEqual(len(self.steps(architect={"grace_tasks": 2})), 1)


class Plane(unittest.TestCase):
    def test_the_schema_accepts_false_and_a_block_and_not_true(self):
        schema = json.loads((PLANE_ROOT / "contracts/plane_config.schema.json").read_text())
        arch = schema["properties"]["architect"]
        self.assertEqual(arch["type"], ["object", "boolean"])
        self.assertEqual(arch["then"], {"const": False})
        self.assertEqual(arch["properties"]["rules_doc"]["default"], "docs/ENGINEERING.md")
        self.assertEqual(config.ARCHITECT_DEFAULTS["rules_doc"], "docs/ENGINEERING.md")


if __name__ == "__main__":
    unittest.main()
