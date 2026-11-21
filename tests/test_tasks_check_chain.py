"""`ccp tasks check` notes each review point's longest `depends_on` chain and the tasks at each depth, and
warns on a long, narrow plan; the exit code never changes. Fenced temp products, the index rebuilt."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ccp import cli, plan
from tests.helpers import TASK, Product


class Chain(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.q = tempfile.mkdtemp()

    def tearDown(self):
        self.p.cleanup()

    def add(self, n, deps=(), point=None, status="pending"):
        tid = f"{n:04d}-t{n}"
        text = TASK.format(tid=tid, title="T", status=status, deps=", ".join(f'"{d}"' for d in deps),
                           ver="- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*")
        if point:
            text = text.replace("spec_refs:", f"review_point: {point}\nspec_refs:", 1)
        self.p.write(f"docs/delivery/tasks/{tid}.md", text)
        return tid

    def check(self):
        self.p.index()
        o = io.StringIO()
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": self.q, "CCP_NO_ESTIMATOR_SPAWN": "1"}), \
                redirect_stdout(o), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.p.root), "tasks", "check"])
        out = o.getvalue()
        lines = out.splitlines()
        return (code, [x for x in lines if "longest depends_on chain" in x and "warning:" not in x],
                [x for x in lines if "longest depends_on chain is" in x and "warning:" in x])

    def test_a_point_with_a_shallow_branching_plan_gets_its_note_and_no_warning(self):
        d = self.add(1, status="done", point="R1")
        a = self.add(2, [d], "R1")
        b = self.add(3, [a], "R1")
        self.add(4, [a], "R1")
        self.add(5, [b], "R1")
        self.add(6, point="R1")
        self.add(7, point="R1")
        code, notes, warns = self.check()
        self.assertEqual(code, 0)
        self.assertEqual([n.strip() for n in notes],
                         ["note: R1: 6 pending tasks, longest depends_on chain 3, width by depth 3, 2, 1"])
        self.assertEqual(warns, [])

    def test_a_chain_in_a_narrow_plan_warns_with_its_ids_in_run_order(self):
        # 0003 depends on 0004: the dependency has the higher number
        self.add(1, point="R2")
        self.add(2, ["0001-t1"], "R2")
        self.add(4, ["0002-t2"], "R2")
        self.add(3, ["0004-t4"], "R2")
        self.add(5, point="R2")
        self.add(6, point="R2")
        code, notes, warns = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("R2: the longest depends_on chain is 4 tasks "
                      "(0001-t1 → 0002-t2 → 0004-t4 → 0003-t3)", warns[0])
        self.assertIn("1.5 tasks wide", warns[0])
        self.assertEqual(len(notes), 1)

    def test_a_wide_plan_a_short_chain_and_the_unpointed_group_do_not_warn(self):
        n = 0
        prev: list[str] = []
        for depth in range(4):   # R3: widths 2, 2, 2, 2
            cur = []
            for _ in range(2):
                n += 1
                cur.append(self.add(n, prev[:1], "R3"))
            prev = cur
        n += 1
        first = self.add(n, point="R4")
        n += 1
        self.add(n, [first], "R4")
        for _ in range(3):
            n += 1
            self.add(n)
        code, notes, warns = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(warns, [])
        self.assertEqual([x.strip() for x in notes], [
            "note: R3: 8 pending tasks, longest depends_on chain 4, width by depth 2, 2, 2, 2",
            "note: R4: 2 pending tasks, longest depends_on chain 2, width by depth 1, 1",
            "note: no review point: 3 pending tasks, longest depends_on chain 1, width by depth 3"])

    def test_a_point_of_one_pending_task_has_no_note(self):
        self.add(1, point="R5")
        self.add(2, status="done", point="R5")
        self.assertEqual(self.check()[1:], ([], []))

    def test_a_dependency_in_another_point_does_not_lengthen_the_chain(self):
        a = self.add(1, point="R6")
        b = self.add(2, [a], "R7")
        self.add(3, [b], "R7")
        self.add(4, point="R6")
        notes = self.check()[1]
        self.assertEqual([x.strip() for x in notes], [
            "note: R6: 2 pending tasks, longest depends_on chain 1, width by depth 2",
            "note: R7: 2 pending tasks, longest depends_on chain 2, width by depth 1, 1"])

    def test_a_chain_warning_names_only_tasks_of_its_own_point(self):
        a = self.add(1, point="R6")
        b = self.add(2, [a], "R7")
        c = self.add(3, [b], "R7")
        self.add(4, [a, c], "R7")
        self.add(5, point="R6")
        code, _, warns = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("R7: the longest depends_on chain is 3 tasks (0002-t2 → 0003-t3 → 0004-t4)", warns[0])

    def test_a_group_with_a_dependency_cycle_is_left_to_the_check_that_refuses_it(self):
        self.add(1, ["0002-t2"], "R8")
        self.add(2, ["0001-t1"], "R8")
        self.add(3, point="R8")
        code, notes, warns = self.check()
        self.assertEqual(code, 1)
        self.assertEqual((notes, warns), ([], []))

    def test_a_group_whose_only_cycle_is_a_task_depending_on_itself_is_left_to_the_check(self):
        ts = [{"task_id": "a", "status": "pending", "review_point": "R1", "depends_on": ["a"]},
              {"task_id": "b", "status": "pending", "review_point": "R1"}]
        self.assertEqual(plan.chain_report(self.p.cfg, ts), ([], []))

    def test_the_report_reads_the_loaded_tasks_and_the_thresholds_are_the_rules(self):
        self.assertEqual((plan.CHAIN_WARN_MIN, plan.CHAIN_WARN_WIDTH), (3, 2))
        ts = [{"task_id": "a", "status": "pending", "review_point": "R1"},
              {"task_id": "b", "status": "pending", "review_point": "R1", "depends_on": ["a"]},
              {"task_id": "c", "status": "pending", "review_point": "R1", "depends_on": ["b"]}]
        notes, warns = plan.chain_report(self.p.cfg, ts)
        self.assertEqual(len(notes), 1)
        self.assertIn("(a → b → c)", warns[0])
        self.assertIn("1.0 tasks wide", warns[0])
        two = plan.chain_report(self.p.cfg, ts[:2])
        self.assertEqual((len(two[0]), two[1]), (1, []))   # a chain of 2 never warns


if __name__ == "__main__":
    unittest.main()
