"""A worker report states its follow-ups (SPEC §13.4, ADR-0044 D1): `ccp report` keeps each `## Follow-ups` line on
the run with its id `<run_id>#<n>` and no outcome, refuses a line that is neither a `- ` item nor `none` and one that
looks like a secret, and a corrected report renumbers them, an outcome carrying over only to an identical line."""
from __future__ import annotations

import json
import unittest

from ccp import followups, report, runs
from ccp.queue import lib
from tests.helpers import done_report, REPORT_HEAD as HEAD
from tests.toolkit_fixture import ToolkitFixture

IMPLEMENT = "0002-second/implement"
REVIEW = "0002-second/review"
DROPPED = {"kind": "drop", "reason": "not worth it", "at": "2026-11-21T00:00:00Z", "by": lib.LEAD}
TASKED = {"kind": "task", "ref": "0001-first", "at": "2026-11-21T00:00:00Z", "by": lib.LEAD}


def implement_report(*follow_up_lines: str) -> str:
    return done_report("implement", "PR: #7", f"Head: {HEAD}", *follow_up_lines)


class Table(unittest.TestCase):

    def test_every_phase_s_report_reads_the_section(self):
        for phase in runs.PHASES:
            self.assertIn("follow_ups", [s.key for s in report.sections_for(phase)], phase)


class Carry(unittest.TestCase):

    def test_an_identical_line_keeps_its_outcome_and_another_line_s_outcome_is_dropped(self):
        old = [{"id": "r#1", "text": "a test gap in the parser", "outcome": DROPPED},
               {"id": "r#2", "text": "rename the helper", "outcome": TASKED},
               {"id": "r#3", "text": "still undecided", "outcome": None}]
        new = [{"id": "r#1", "text": "a new step for a later task", "outcome": None},
               {"id": "r#2", "text": "a test gap in the parser", "outcome": None},
               {"id": "r#3", "text": "still undecided", "outcome": None}]
        got, dropped = followups.carry(old, new)
        self.assertEqual([(f["id"], f["text"], f["outcome"]) for f in got],
                         [("r#1", "a new step for a later task", None), ("r#2", "a test gap in the parser", DROPPED),
                          ("r#3", "still undecided", None)])
        self.assertEqual([f["id"] for f in dropped], ["r#2"])

    def test_each_earlier_outcome_carries_to_one_line_at_most(self):
        old = [{"id": "r#1", "text": "same", "outcome": DROPPED}]
        got, dropped = followups.carry(old, [{"id": "r#1", "text": "same", "outcome": None},
                                             {"id": "r#2", "text": "same", "outcome": None}])
        self.assertEqual([f["outcome"] for f in got], [DROPPED, None])
        self.assertEqual(dropped, [])


class Submit(ToolkitFixture, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)

    def run_rec(self, run_id: str = IMPLEMENT) -> dict:
        return json.loads(runs.path(self.q, run_id).read_text())

    def assert_refused(self, text: str, said: str) -> None:
        code, _, out, err = self.report(IMPLEMENT, text)
        self.assertEqual(code, 1, out + err)
        self.assertIn(said, err)
        self.assertFalse(runs.report_path(self.q, IMPLEMENT).exists())
        self.assertIsNone(self.run_rec()["reported_at"])

    def test_two_follow_ups_are_stored_with_their_ids_and_no_outcome(self):
        code, body, out, err = self.report(IMPLEMENT, implement_report(
            "## Follow-ups", "- the parser has no test for a CRLF report", "- move the helper to its own module,",
            "  once the later task lands"))
        self.assertEqual(code, 0, out + err)
        want = [{"id": f"{IMPLEMENT}#1", "text": "the parser has no test for a CRLF report", "outcome": None},
                {"id": f"{IMPLEMENT}#2", "text": "move the helper to its own module, once the later task lands",
                 "outcome": None}]
        self.assertEqual(self.run_rec()["follow_ups"], want)
        self.assertEqual(body["follow_ups"], want)

    def test_a_review_report_s_follow_ups_are_stored_on_its_run(self):
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], REVIEW)
        code, _, out, err = self.report(REVIEW, "\n".join([
            "Outcome: done", "Severity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0", "## Spec beyond intent", "none",
            "## Friction", "none", "## Follow-ups", "- a test gap outside this task", ""]))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.run_rec(REVIEW)["follow_ups"],
                         [{"id": f"{REVIEW}#1", "text": "a test gap outside this task", "outcome": None}])

    def test_a_missing_section_stores_no_follow_ups(self):
        code, _, out, err = self.report(IMPLEMENT, implement_report())
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.run_rec()["follow_ups"], [])

    def test_a_near_miss_heading_stores_none_and_warns(self):
        for heading in ("### Follow-ups", "## Follow ups", "## Followups"):
            code, _, out, err = self.report(IMPLEMENT, done_report("implement", "PR: #7", f"Head: {HEAD}", "## Notes",
                                                                   heading, "- a test gap"))
            self.assertEqual(code, 0, f"{heading}: {out}{err}")
            self.assertEqual(self.run_rec()["follow_ups"], [], heading)
            self.assertIn(f"`{heading}` is not read as the follow-ups", err)

    def test_a_correct_heading_gives_no_near_miss_warning(self):
        code, _, out, err = self.report(IMPLEMENT, implement_report("## Follow-ups", "- a test gap"))
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("is not read as the follow-ups", err)

    def test_an_empty_section_the_line_none_and_the_line_dash_none_store_no_follow_ups(self):
        for lines in ((), ("none",), ("- none",)):
            code, _, out, err = self.report(IMPLEMENT, implement_report("## Follow-ups", *lines))
            self.assertEqual(code, 0, f"{lines}: {out}{err}")
            self.assertEqual(self.run_rec()["follow_ups"], [], lines)

    def test_a_line_that_is_neither_an_item_nor_none_is_refused_and_nothing_is_written(self):
        self.assert_refused(implement_report("## Follow-ups", "- a test gap", "the parser needs a CRLF test"),
                            "`the parser needs a CRLF test`")

    def test_a_star_item_is_refused(self):
        self.assert_refused(implement_report("## Follow-ups", "* a test gap"), "`* a test gap`")

    def test_none_beside_follow_ups_is_refused(self):
        self.assert_refused(implement_report("## Follow-ups", "- a test gap", "- none"),
                            "says `none` beside follow-ups")

    def test_a_secret_like_line_is_refused_and_nothing_is_written(self):
        self.assert_refused(implement_report("## Follow-ups", "- rotate ANTHROPIC_API_KEY=abc123"),
                            "a Follow-ups line looks like it holds a secret")

    def test_a_correction_renumbers_carries_an_identical_line_s_outcome_and_names_the_one_it_drops(self):
        code, _, out, err = self.report(IMPLEMENT, implement_report("## Follow-ups", "- gap one", "- gap two"))
        self.assertEqual(code, 0, out + err)
        rec = self.run_rec()
        rec["follow_ups"][0]["outcome"], rec["follow_ups"][1]["outcome"] = TASKED, DROPPED
        runs.save(self.q, rec)
        code, _, out, err = self.report(IMPLEMENT, implement_report("## Follow-ups", "- gap three", "- gap one"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.run_rec()["follow_ups"],
                         [{"id": f"{IMPLEMENT}#1", "text": "gap three", "outcome": None},
                          {"id": f"{IMPLEMENT}#2", "text": "gap one", "outcome": TASKED}])
        self.assertIn(f"{IMPLEMENT}#2 (`gap two`)", err)
        self.assertNotIn(f"{IMPLEMENT}#1 (`gap one`)", err)


if __name__ == "__main__":
    unittest.main()
