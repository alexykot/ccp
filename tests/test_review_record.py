"""`ccp report` moves a task through `implemented` and `reviewed` and writes its review record (SPEC §10.1, §15.1):
an implement round done with a head moves it to `implemented`, a review done and clean to `reviewed`, writing
`review/<task_id>.json`; a rework round and a correction move nothing."""
from __future__ import annotations

import json
import unittest

from ccp import report
from tests.review_flow import CLEAN, MAJOR, PhaseFlow, A, B
from tests.toolkit_fixture import ToolkitFixture


class Moves(PhaseFlow, ToolkitFixture, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.start()

    def transitions(self) -> list[str]:
        return [e["payload"]["to"] for e in self.events() if (e["type"], e["op"]) == ("phase", "transition")]

    def test_an_implement_round_done_with_a_head_moves_the_task_to_implemented(self):
        self.implemented()
        self.assertEqual(self.status(), "implemented")
        progress = json.loads((self.q / "progress/0002-second.json").read_text())
        self.assertEqual((progress["events"][-1]["from"], progress["events"][-1]["to"]), ("implementing", "implemented"))

    def test_a_fix_round_done_leaves_its_phase_as_it_was(self):
        self.implemented()
        self.reviewed_as(MAJOR)
        self.fix(A, B)
        self.assertEqual(self.status(), "fixing")
        self.assertEqual(self.transitions()[-1], "fixing")

    def test_a_clean_review_writes_the_record_with_the_implementer_session_and_moves_the_task_to_reviewed(self):
        implement = self.implemented()
        review = self.reviewed_as(CLEAN)
        self.assertEqual(self.status(), "reviewed")
        rec = json.loads(self.review_record().read_text())
        self.assertEqual((rec["mk_pr_run_id"], rec["mk_pr_session_id"]), (implement, self.IMPLEMENTER_SESSION))
        self.assertEqual((rec["review_run_id"], rec["review_session_id"], rec["pr"], rec["head"]),
                         (review, "sess-reviewer", 7, A))
        recorded = [e["payload"] for e in self.events() if (e["type"], e["op"]) == ("review", "recorded")]
        self.assertEqual(recorded[-1]["verdict"], "clean")

    def test_a_review_with_a_major_finding_writes_no_record(self):
        self.implemented()
        self.reviewed_as(MAJOR)
        self.assertFalse(self.review_record().exists())
        self.assertEqual(self.status(), "reviewing")

    def test_a_later_clean_review_replaces_the_record_and_names_the_fix_rounds_since_the_pr_opened(self):
        self.implemented()
        self.reviewed_as(MAJOR)
        fix = self.fix(A, B)
        review = self.reviewed_as(CLEAN, B, "sess-second-reviewer")
        rec = json.loads(self.review_record().read_text())
        self.assertEqual((rec["review_run_id"], rec["head"], rec["safe_fixes_applied"]), (review, B, [fix]))

    def test_a_correction_moves_nothing(self):
        self.implemented()
        review = self.reviewed_as(MAJOR)
        before = self.transitions()
        code, _, out, err = self.report(review, f"Outcome: done\nSeverity: {CLEAN}\n"
                                                "## Spec beyond intent\nnone\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.status(), "reviewing")
        self.assertEqual(self.transitions(), before)
        self.assertEqual(json.loads(self.review_record().read_text())["review_run_id"], review)  # corrected to clean


class PhaseAfter(unittest.TestCase):
    """The phase a first report moves its task to, on plain values."""

    def test_only_a_done_implement_with_a_head_and_a_done_clean_review_move(self):
        clean = {"BLOCKER": 0, "MAJOR": 0, "MINOR": 2, "NIT": 0}
        cases = [("implement", {"outcome": "done", "head": A}, "implemented"),
                 ("implement", {"outcome": "done"}, None),
                 ("implement", {"outcome": "failed", "head": A}, None),
                 ("fix", {"outcome": "done", "head": A}, None),
                 ("merge", {"outcome": "done", "head": A}, None),
                 ("review", {"outcome": "done", "severity": clean}, "reviewed"),
                 ("review", {"outcome": "done", "severity": {**clean, "BLOCKER": 1}}, None),
                 ("review", {"outcome": "blocked", "severity": clean}, None),
                 ("review", {"outcome": "done"}, None),
                 ("verify", {"outcome": "done", "head": A}, None)]
        for phase, parsed, want in cases:
            with self.subTest(phase=phase, parsed=parsed):
                self.assertEqual(report.phase_after(phase, parsed), want)


class Record(unittest.TestCase):
    """The review record built from a task's runs, on plain values."""

    def run_rec(self, run_id, phase, opened, reported=None, outcome="done", **kw):
        return {"run_id": run_id, "task_id": "0009-x", "phase": phase, "opened_at": opened, "reported_at": reported,
                "outcome": outcome if reported else None, **kw}

    def test_the_first_round_reporting_the_pr_opened_it_and_rework_rounds_before_the_review_are_its_fixes(self):
        rs = [self.run_rec("0009-x/implement", "implement", "T01", "T02", outcome="failed", pr=None),
              self.run_rec("0009-x/implement-2", "implement", "T03", "T04", pr="#5", head=A, session_id="s-impl"),
              self.run_rec("0009-x/fix", "fix", "T05", "T06", pr="5", head=B),
              self.run_rec("0009-x/merge", "merge", "T07", None, pr=None, abandoned_at="T08"),
              self.run_rec("0009-x/review", "review", "T09", "T10", pr="5", head=B, session_id="s-rev",
                           report="/q/progress/0009-x/review-report.md"),
              self.run_rec("0009-x/fix-2", "fix", "T11", "T12", pr="5", head=A)]
        rec = report.review_record("demo", rs[4], rs, ["sm-1"], "2026-11-22T00:00:00Z")
        self.assertEqual((rec["pr"], rec["head"], rec["mk_pr_run_id"], rec["mk_pr_session_id"]),
                         (5, B, "0009-x/implement-2", "s-impl"))
        self.assertEqual(rec["safe_fixes_applied"], ["0009-x/fix"])
        self.assertEqual(rec["decisions"], [{"class": "spec", "question_ref": "sm-1"}])
        self.assertEqual(rec["review_artifact_path"], "/q/progress/0009-x/review-report.md")

    def test_a_review_of_a_pr_no_round_reported_records_no_opener(self):
        review = self.run_rec("0009-x/review", "review", "T09", "T10", pr="8", head=B)
        rec = report.review_record("demo", review, [review], [], "2026-11-22T00:00:00Z")
        self.assertEqual((rec["pr"], rec["mk_pr_run_id"], rec["mk_pr_session_id"]), (8, None, None))


if __name__ == "__main__":
    unittest.main()
