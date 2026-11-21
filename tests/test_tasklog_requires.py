"""SPEC §21.1: `ccp tasks check` reports a pending task citing a decision whose `requires` prerequisite,
resolved through `retired by` (§6.5), is neither built nor cited by the task or a task in its
`depends_on` closure; a failure under `adr.strict`, a warning otherwise."""
from __future__ import annotations

import unittest

from ccp import adr, tasklog
from tests.helpers import TASK, Product


def decision_adr(n: int, states: list[str], requires: list[str] | None = None) -> dict:
    """One ADR as `adr.load` reads it, on plain values: body decisions D1.. and their recorded states."""
    return {"_number": n, "_decisions": [{"id": str(i + 1)} for i in range(len(states))],
            "decisions": [f"D{i + 1} {s}" for i, s in enumerate(states)], "requires": requires or []}


def task(tid: str, refs: list[str], deps: list[str] | None = None, status: str = "pending") -> dict:
    return {"task_id": tid, "status": status, "adr_refs": refs, "depends_on": deps or []}


class RequiresReport(unittest.TestCase):
    def index(self, *adrs: dict) -> adr.DecisionIndex:
        return adr.DecisionIndex.build(list(adrs))

    def setUp(self):
        # ADR-0002 D1 rests on ADR-0001 D1, which is not built yet
        self.idx = self.index(decision_adr(1, ["not_built", "built"]),
                              decision_adr(2, ["not_built"], ["D1 ADR-0001 D1"]))

    def test_an_uncited_prerequisite_is_reported_naming_the_decide(self):
        lines = tasklog.requires_report([task("0002-b", ["0002 D1"])], self.idx, strict=False)
        self.assertEqual(len(lines), 1, lines)
        for token in ("0002-b", "ADR-0002 D1", "ADR-0001 D1", "`ccp adr decide 1 D1 built`"):
            self.assertIn(token, lines[0])

    def test_a_task_citing_the_prerequisite_outside_the_closure_is_named_as_the_depends_on(self):
        tasks = [task("0001-a", ["0001 D1"]), task("0002-b", ["0002 D1"])]
        lines = tasklog.requires_report(tasks, self.idx, strict=False)
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("0002-b:"), lines)
        self.assertIn("depends_on on 0001-a", lines[0])
        self.assertNotIn("adr decide", lines[0])

    def test_cleared_by_a_task_in_the_depends_on_closure_citing_it(self):
        direct = [task("0001-a", ["0001 D1"]), task("0002-b", ["0002 D1"], ["0001-a"])]
        self.assertEqual(tasklog.requires_report(direct, self.idx, strict=False), [])
        through = [task("0001-a", ["0001 D1"]), task("0003-c", []),
                   task("0002-b", ["0002 D1"], ["0003-c"])]
        self.assertEqual(len(tasklog.requires_report(through, self.idx, strict=False)), 1)
        through[1]["depends_on"] = ["0001-a"]
        self.assertEqual(tasklog.requires_report(through, self.idx, strict=False), [])

    def test_cleared_when_the_task_cites_the_prerequisite_itself(self):
        tasks = [task("0002-b", ["0002 D1", "0001 D1"])]
        self.assertEqual(tasklog.requires_report(tasks, self.idx, strict=False), [])

    def test_cleared_once_the_prerequisite_is_built_or_live(self):
        for state in ("built", "live"):
            idx = self.index(decision_adr(1, [state, "built"]), decision_adr(2, ["not_built"], ["D1 ADR-0001 D1"]))
            self.assertEqual(tasklog.requires_report([task("0002-b", ["0002 D1"])], idx, strict=False), [], state)

    def test_only_pending_tasks_are_reported(self):
        for status in ("done", "dropped"):
            tasks = [task("0002-b", ["0002 D1"], status=status)]
            self.assertEqual(tasklog.requires_report(tasks, self.idx, strict=False), [], status)

    def test_a_whole_adr_citation_cites_each_of_its_decisions(self):
        lines = tasklog.requires_report([task("0002-b", ["ADR-0002"])], self.idx, strict=False)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("ADR-0001 D1", lines[0])
        tasks = [task("0001-a", ["0001"]), task("0002-b", ["0002"], ["0001-a"])]
        self.assertEqual(tasklog.requires_report(tasks, self.idx, strict=False), [])
        # a section citation names no decision
        self.assertEqual(tasklog.requires_report([task("0002-b", ["0002 Context"])], self.idx, strict=False), [])

    def test_a_retired_prerequisite_resolves_to_its_replacement(self):
        idx = self.index(decision_adr(1, ["retired by ADR-0003 D1"]),
                         decision_adr(2, ["not_built"], ["D1 ADR-0001 D1"]),
                         decision_adr(3, ["not_built"]))
        lines = tasklog.requires_report([task("0002-b", ["0002 D1"])], idx, strict=False)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("ADR-0003 D1", lines[0])
        self.assertIn("`ccp adr decide 3 D1 built`", lines[0])
        # a task citing the retired decision does not build its replacement; one citing the replacement does
        old = [task("0001-a", ["0001 D1"]), task("0002-b", ["0002 D1"], ["0001-a"])]
        self.assertEqual(len(tasklog.requires_report(old, idx, strict=False)), 1)
        new = [task("0003-c", ["0003 D1"]), task("0002-b", ["0002 D1"], ["0003-c"])]
        self.assertEqual(tasklog.requires_report(new, idx, strict=False), [])
        built = self.index(decision_adr(1, ["retired by ADR-0003 D1"]),
                           decision_adr(2, ["not_built"], ["D1 ADR-0001 D1"]),
                           decision_adr(3, ["built"]))
        self.assertEqual(tasklog.requires_report([task("0002-b", ["0002 D1"])], built, strict=False), [])

    def test_a_chain_adr_check_reports_is_left_to_it(self):
        for first in ("retired", "retired by ADR-0001", "retired by ADR-0001 D1"):
            idx = self.index(decision_adr(1, [first]), decision_adr(2, ["not_built"], ["D1 ADR-0001 D1"]))
            self.assertEqual(tasklog.requires_report([task("0002-b", ["0002 D1"])], idx, strict=False), [], first)
        gone = self.index(decision_adr(1, ["built"]), decision_adr(2, ["not_built"], ["D1 ADR-0001 D7"]))
        self.assertEqual(tasklog.requires_report([task("0002-b", ["0002 D1"])], gone, strict=False), [])


ADR_BODY = "# T\n\n## Decision\n\n### D1. First\n\nOne.\n"


class StrictOrNot(unittest.TestCase):
    """The report fails `ccp tasks check` under `adr.strict` and only warns without it."""

    def product(self, strict: bool) -> Product:
        p = Product({"adr": {"dir": "docs/adr", "strict": strict}})
        self.addCleanup(p.cleanup)
        for n, fields in ((1, {"decisions": ["D1 not_built"]}),
                          (2, {"decisions": ["D1 not_built"], "requires": ["D1 ADR-0001 D1"]})):
            p.write(f"docs/adr/000{n}-a.md", adr.emit({"id": f"ADR-000{n}", "title": "T", "status": "accepted",
                                                        "date": "2026-01-01", **fields}) + ADR_BODY)
        text = TASK.format(tid="0002-b", title="A task", status="pending", deps="", ver="*Append-only.*")
        p.write("docs/delivery/tasks/0002-b.md",
                text.replace('spec_refs: ["S1"]\n', 'spec_refs: ["S1"]\nadr_refs: ["0002 D1"]\n'))
        p.index()
        return p

    @staticmethod
    def about(lines: list[str]) -> list[str]:
        return [x for x in lines if "requires ADR-0001 D1" in x]

    def test_a_failure_under_strict(self):
        p = self.product(strict=True)
        self.assertEqual(len(self.about(tasklog.check(p.cfg))), 1)
        self.assertEqual(self.about(tasklog.warnings(p.cfg)), [])

    def test_a_warning_otherwise(self):
        p = self.product(strict=False)
        self.assertEqual(self.about(tasklog.check(p.cfg)), [])
        self.assertEqual(len(self.about(tasklog.warnings(p.cfg))), 1)


if __name__ == "__main__":
    unittest.main()
