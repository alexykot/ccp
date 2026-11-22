"""Formal-submit, `ccp tasks submit` (SPEC §15.1): each failed item refuses, exit 4, naming it and moving nothing; a
pass moves the task to `submitted` and reports the suite run it does not judge; `ccp prompt verify` does not need it."""
from __future__ import annotations

import json
import unittest

from ccp import submit
from tests.review_flow import CLEAN, PhaseFlow, A, B
from tests.test_toolkit import ToolkitFixture


class Submit(PhaseFlow, ToolkitFixture, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.start()

    def refused(self, item: str) -> str:
        before = self.status()
        code, _, out, err = self.ccp("tasks", "submit", "0002")
        self.assertEqual(code, 4, out + err)
        self.assertIn(item, err)
        self.assertEqual(self.status(), before)
        return err

    def test_a_task_with_no_pr_is_refused_naming_pr_exists(self):
        self.refused("pr_exists")

    def test_a_head_no_review_record_covers_is_refused_naming_review_artifact_present(self):
        self.implemented()
        self.reviewed_as(CLEAN)
        self.fix(A, B)  # the record's review judged A; the PR head is now B
        self.refused("review_artifact_present")

    def test_an_open_spec_question_is_refused_naming_no_open_spec_escalation(self):
        self.implemented()
        self.reviewed_as(CLEAN)
        qid = "sm-20261022T100000Z-abcd"
        (self.q / "questions").mkdir()
        (self.q / "questions" / f"{qid}.json").write_text(json.dumps(
            {"task_id": "0001-first", "question_id": qid, "class": "spec", "status": "open", "blocks": ["0002-second"]}))
        err = self.refused("no_open_spec_escalation")
        self.assertIn(qid, err)

    def test_a_pass_with_no_suite_run_at_the_head_moves_the_task_to_submitted_and_says_so(self):
        implement = self.implemented()
        self.reviewed_as(CLEAN)
        code, body, out, err = self.ccp("tasks", "submit", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["from"], body["to"], self.status()), ("reviewed", "submitted", "submitted"))
        self.assertEqual(body["unit_lint"], {"run_id": implement, "head": A, "suite_id": None})
        self.assertIn("unit_lint", err)

    def test_prompt_verify_opens_a_verify_for_a_task_never_submitted(self):
        self.implemented()
        self.reviewed_as(CLEAN)
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["run_id"], self.status()), ("0002-second/verify", "verifying"))


class Failures(unittest.TestCase):
    """The checklist on plain facts."""

    RECORD = {"review_run_id": "t/review", "pr": 7}

    def facts(self, **kw) -> submit.Facts:
        base = dict(pr=7, head=A, record=self.RECORD, latest_review="t/review", latest_clean=True, uncovered=None,
                    open_refs=[])
        return submit.Facts(**{**base, **kw})

    def test_all_items_met_is_no_failure(self):
        self.assertEqual(submit.failures("t", self.facts()), [])

    def test_each_gap_in_the_review_record_fails_review_artifact_present(self):
        for kw, word in ((dict(record=None), "no review record"),
                         (dict(latest_review="t/review-2"), "t/review-2"),
                         (dict(latest_clean=False), "BLOCKER or MAJOR"),
                         (dict(pr=8), "PR 8"),
                         (dict(head=None), "no round reported a head"),
                         (dict(uncovered="fix round newer"), "fix round newer")):
            with self.subTest(kw=kw):
                failed = submit.failures("t", self.facts(**kw))
                self.assertEqual([f.split(":")[0] for f in failed if not f.startswith("pr_exists")],
                                 ["review_artifact_present"])
                self.assertIn(word, failed[-1])

    def test_failures_are_named_in_item_order(self):
        failed = submit.failures("t", self.facts(pr=None, record=None, open_refs=["sm-1"]))
        self.assertEqual([f.split(":")[0] for f in failed], list(submit.ITEMS))


if __name__ == "__main__":
    unittest.main()
