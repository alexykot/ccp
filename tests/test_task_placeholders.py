"""`ccp tasks check` refuses a task copied from the template and not filled in, and plane.json refuses
a lane still holding its placeholder command (SPEC §5)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp import config, tasklog
from tests.helpers import Product

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/docs-delivery/TEMPLATE-task.md"


def front(p: Product, tid: str, old: str, new: str) -> None:
    f = p.root / "docs/delivery/tasks" / f"{tid}.md"
    f.write_text(f.read_text().replace(old, new, 1))


def append(p: Product, tid: str, text: str) -> None:
    f = p.root / "docs/delivery/tasks" / f"{tid}.md"
    f.write_text(f.read_text() + text)


class Placeholders(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def errs(self) -> list[str]:
        self.p.index()
        return tasklog.check(self.p.cfg)

    def placeholder_errs(self) -> list[str]:
        return [e for e in self.errs() if "template placeholder" in e]

    def test_every_placeholder_is_one_the_template_holds(self):
        tmpl = TEMPLATE.read_text()
        self.assertEqual([ph for ph in tasklog.PLACEHOLDERS if ph not in tmpl], [])

    def test_an_unchanged_copy_names_each_placeholder_with_its_line(self):
        self.p.write("docs/delivery/tasks/0001-x.md", TEMPLATE.read_text())
        want = {(n, ph) for n, line in enumerate(TEMPLATE.read_text().splitlines(), 1)
                for ph in tasklog.PLACEHOLDERS if ph in line}
        self.assertEqual({ph for _, ph in want}, set(tasklog.PLACEHOLDERS))
        errs = self.placeholder_errs()
        got = {(n, ph) for n, ph in want
               if any(e.startswith(f"docs/delivery/tasks/0001-x.md:{n}: ") and repr(ph) in e for e in errs)}
        self.assertEqual(got, want)
        self.assertEqual(len(errs), len(want))

    def test_a_filled_task_passes(self):
        self.p.task("0001-a")
        self.assertEqual(self.errs(), [])

    def test_a_placeholder_left_in_a_filled_task_is_refused(self):
        self.p.task("0001-a")
        front(self.p, "0001-a", "updated: 2026-09-30", "updated: YYYY-MM-DD")
        front(self.p, "0001-a", "expect: exit 0", "expect: <concrete, observable result>")
        errs = self.placeholder_errs()
        self.assertEqual(len(errs), 2, errs)
        self.assertIn("'YYYY-MM-DD'", errs[0])
        self.assertIn("'<concrete, observable result>'", errs[1])

    def test_a_quoted_placeholder_passes(self):
        self.p.task("0001-a")
        append(self.p, "0001-a", "- The check names `NNNN-kebab-slug` and ``As a <role>``, and\n"
                                 "  `One line,\n  imperative` and `<preconditions` too.\n\n"
                                 "```\ncreated: YYYY-MM-DD\n```\n\n~~~text\n<concrete, observable result>\n~~~\n")
        self.assertEqual(self.errs(), [])

    def test_a_code_span_does_not_reach_across_a_paragraph(self):
        self.p.task("0001-a")
        append(self.p, "0001-a", "- a stray ` backtick\n\nupdated: YYYY-MM-DD\n\nand ` another\n")
        self.assertEqual(len(self.placeholder_errs()), 1)

    def test_an_unclosed_fence_hides_nothing(self):
        self.p.task("0001-a")
        append(self.p, "0001-a", "```\nupdated: YYYY-MM-DD\n")
        self.assertEqual(len(self.placeholder_errs()), 1)

    def test_done_and_dropped_tasks_are_history_and_not_read(self):
        for tid, status in (("0001-a", "done"), ("0002-b", "dropped")):
            self.p.task(tid, status)
            front(self.p, tid, "title: A task", "title: One line, imperative")
        self.assertEqual(self.placeholder_errs(), [])


class EmptySpecRefs(unittest.TestCase):
    def tearDown(self):
        self.p.cleanup()

    def errs(self) -> str:
        self.p.index()
        return "\n".join(tasklog.check(self.p.cfg))

    def test_an_empty_spec_refs_says_to_list_the_sections_and_cite_them(self):
        self.p = Product()
        self.p.task("0001-a")
        front(self.p, "0001-a", 'spec_refs: ["S1"]', "kind: feature\nspec_refs: []")
        e = self.errs()
        self.assertIn("0001-a.md: cites none of spec_refs", e)
        self.assertIn("list the SPEC sections this task answers to in `spec_refs` and cite them", e)

    def test_with_the_architect_block_a_feature_gets_the_same_hint(self):
        self.p = Product({"task_log": {"refs_any": ["spec_refs", "adr_refs"]}, "architect": {}})
        self.p.task("0001-a")
        front(self.p, "0001-a", 'spec_refs: ["S1"]', "kind: feature\nspec_refs: []")
        self.assertIn("in `spec_refs` and cite them", self.errs())

    def test_a_kind_with_its_own_refs_naming_spec_refs_gets_the_hint(self):
        self.p = Product({"task_log": {"kinds": {"feature": {"refs_any": ["spec_refs"], "forbid": []},
                                                 "refactor": {"refs_any": ["rule_refs"], "forbid": ["spec_refs"]}}},
                          "architect": {}})
        self.p.task("0001-a")
        front(self.p, "0001-a", 'spec_refs: ["S1"]', "spec_refs: []")
        self.assertIn("0001-a.md: a feature cites spec_refs — list the SPEC sections", self.errs())

    def test_a_refactor_is_not_told_to_cite_the_spec(self):
        self.p = Product({"architect": {}})
        self.p.task("0001-r")
        front(self.p, "0001-r", 'spec_refs: ["S1"]', "kind: refactor\nrule_refs: []")
        e = self.errs()
        self.assertIn("a refactor cites rule_refs", e)
        self.assertNotIn("SPEC sections", e)


class LanePlaceholder(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def lanes(self, lanes: dict) -> None:
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "suite": {"lanes": lanes}}))

    def test_a_lane_holding_the_placeholder_is_refused(self):
        self.lanes({"full": ["scripts/test.sh"], "gate": ["sh", "-c", "<your test command> && true"]})
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.p.root)
        msg = str(cm.exception)
        self.assertIn("suite.lanes gate ", msg)
        self.assertIn(config.LANE_PLACEHOLDER, msg)
        self.assertNotIn("full", msg)

    def test_a_lane_with_its_own_command_loads(self):
        self.lanes({"gate": ["scripts/gate.sh"]})
        self.assertEqual(config.load(self.p.root).suite["lanes"], {"gate": ["scripts/gate.sh"]})


if __name__ == "__main__":
    unittest.main()
