"""The change rounds' `## Tests for new behaviour` section (SPEC §13.4, §13.5): `ccp report` refuses a done implement,
fix, merge or ruling report without it, or with it empty, and the rendered prompt's last part asks for it from the
report table; a review or a report that is not done is not held to it."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp import runs
from tests.toolkit_fixture import ToolkitFixture

HEAD = "a" * 40
HEADING = "## Tests for new behaviour"


def change_report(*section: str) -> str:
    """A done change-round report whose `## Tests for new behaviour` section holds `section` (no section with none)."""
    body = [HEADING, *section] if section else []
    return "\n".join(["Outcome: done", "PR: #7", f"Head: {HEAD}", *body, "## Friction", "none", ""])


class Section(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def open(self, phase: str, *args: str) -> tuple[str, str]:
        code, body, out, err = self.ccp("prompt", phase, "0002", *args)
        self.assertEqual(code, 0, out + err)
        return body["run_id"], Path(body["prompt_path"]).read_text()

    def implement(self) -> str:
        return self.open("implement", "--base", "abc1234")[0]

    def assert_refused(self, run_id: str, text: str) -> None:
        code, _, out, err = self.report(run_id, text)
        self.assertEqual(code, 1, out + err)
        self.assertIn(f"no `{HEADING}` section", err)
        self.assertFalse(runs.report_path(self.q, run_id).exists())
        self.assertIsNone(self.run_rec(run_id)["reported_at"])

    def run_rec(self, run_id: str) -> dict:
        return json.loads(runs.path(self.q, run_id).read_text())

    def test_a_done_implement_report_without_the_section_is_refused_naming_it(self):
        self.assert_refused(self.implement(), change_report())

    def test_an_empty_section_is_refused(self):
        text = change_report().replace("## Friction", f"{HEADING}\n\n## Friction")
        self.assert_refused(self.implement(), text)

    def test_a_bare_none_or_a_line_that_is_not_an_item_is_refused(self):
        run_id = self.implement()
        for section in (("none",), ("- none",), ("the parser is pinned by test_parse",),
                        ("- the parser reads CRLF: test_crlf", "- none")):
            self.assert_refused(run_id, change_report(*section))

    def test_lines_are_accepted_and_the_run_keeps_nothing_new(self):
        run_id = self.implement()
        code, body, out, err = self.report(run_id, change_report(
            "- a done report without the section is refused: test_refused",
            "  (its wrapped line)", "* a blocked one is not: test_blocked"))
        self.assertEqual(code, 0, out + err)
        rec = self.run_rec(run_id)
        self.assertEqual(rec["outcome"], "done")
        self.assertNotIn("tests_for_new_behaviour", rec)
        self.assertNotIn("tests_for_new_behaviour", body)

    def test_a_merge_report_with_the_single_none_line_is_accepted(self):
        run_id, _text = self.open("merge", "--pr", "7", "--head", HEAD)
        code, _, out, err = self.report(run_id, change_report("none: the merge adds no behaviour"))
        self.assertEqual(code, 0, out + err)

    def test_a_blocked_report_without_it_is_accepted(self):
        run_id = self.implement()
        code, _, out, err = self.report(run_id, "Outcome: blocked\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)

    def test_a_review_report_is_not_asked_for_it(self):
        run_id, text = self.open("review", "--pr", "7", "--head", HEAD)
        self.assertNotIn(f"a `{HEADING}` section", text)
        code, _, out, err = self.report(run_id, "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n"
                                                "## Spec beyond intent\nnone\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)

    def test_each_change_round_s_last_part_asks_for_it_and_its_none_form(self):
        rounds = (("implement", ("--base", "abc1234")), ("fix", ("--pr", "7", "--head", HEAD)),
                  ("merge", ("--pr", "7", "--head", HEAD)),
                  ("ruling", ("--pr", "7", "--head", HEAD, "--note", "the field is optional")))
        (self.q / "progress/0002-second").mkdir(parents=True)
        (self.q / "progress/0002-second/review-report.md").write_text("Outcome: done\n")  # a fix's findings
        for phase, args in rounds:
            _run_id, text = self.open(phase, *args, "--supersede")
            part = text[text.index("these lines:\n"):]
            self.assertEqual(text.count(HEADING), 1, phase)
            self.assertIn(f"When done: a `{HEADING}` section", part, phase)
            self.assertIn("beginning `none` followed by why", part, phase)


if __name__ == "__main__":
    unittest.main()
