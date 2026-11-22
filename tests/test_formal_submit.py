"""Formal-submit, `ccp tasks submit` (SPEC §15.1): each failed item refuses, exit 4, naming it and moving nothing; a
pass moves the task to `submitted` and reports the suite run it does not judge; `ccp prompt verify` does not need it."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ccp import config, submit, suite
from tests.helpers import done_report
from tests.review_flow import CLEAN, PROOF, SKIP_REVIEW_PLANE, PhaseFlow, SkipFlow, A, B
from tests.test_toolkit import PLANE, ToolkitFixture

MINOR_ONLY = "BLOCKER=0 MAJOR=0 MINOR=2 NIT=0"


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

    def question(self, qid: str, status: str, answer: dict | None = None) -> None:
        (self.q / "questions").mkdir(exist_ok=True)
        (self.q / "questions" / f"{qid}.json").write_text(json.dumps(
            {"task_id": "0001-first", "question_id": qid, "class": "spec", "status": status, "blocks": ["0002-second"]}))
        if answer is not None:
            (self.q / "questions" / f"{qid}.answer.json").write_text(json.dumps({"question_id": qid, **answer}))

    def test_a_spec_question_escalated_to_the_operator_is_refused_though_answered(self):
        self.implemented()
        self.reviewed_as(CLEAN)
        qid = "sm-20261022T100000Z-beef"
        self.question(qid, "escalated", {"verdict": "needs_operator"})
        self.assertIn(qid, self.refused("no_open_spec_escalation"))

    def test_an_answered_spec_question_does_not_refuse(self):
        self.implemented()
        self.reviewed_as(CLEAN)
        self.question("sm-20261022T100000Z-cafe", "answered")
        code, _, out, err = self.ccp("tasks", "submit", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.status(), "submitted")

    def test_a_task_past_submitted_is_refused_exit_3_and_not_moved(self):
        self.implemented()
        self.reviewed_as(CLEAN)
        self.ccp("tasks", "phase", "0002", "verifying")
        code, _, out, err = self.ccp("tasks", "submit", "0002")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(self.status(), "verifying")

    def submitted_after_suite_run(self, *lane: str) -> tuple[str, list[str], dict]:
        """An implement round that records a passed `ccp suite run` (lane args as given), reports head A, a clean
        review, then submit: (the round's run id, its suite ids, submit's body)."""
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        rid = body["run_id"]
        code, _, out, err = self.ccp("suite", "run", "--run", rid, *lane)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(rid, done_report("implement", "PR: #7", f"Head: {A}"))
        self.assertEqual(code, 0, out + err)
        self.reviewed_as(CLEAN)
        sids = [r["suite_id"] for r in suite.fold(self.q) if r.get("run_id") == rid and r.get("state") == "passed"]
        self.assertTrue(sids)
        code, body, out, err = self.ccp("tasks", "submit", "0002")
        self.assertEqual(code, 0, out + err)
        return rid, sids, body

    def test_a_passed_gate_lane_run_of_the_round_that_reported_the_head_is_reported_with_no_warning(self):
        rid, sids, body = self.submitted_after_suite_run("--lane", "gate")
        self.assertEqual(body["unit_lint"], {"run_id": rid, "head": A, "suite_id": sids[-1]})
        self.assertNotIn("warnings", body)

    def test_a_passed_part_lane_run_is_not_the_unit_lint_and_leaves_the_warning(self):
        rid, _, body = self.submitted_after_suite_run("--lane", "part", "--", sys.executable, "-c", "pass")
        self.assertEqual(body["unit_lint"], {"run_id": rid, "head": A, "suite_id": None})
        self.assertIn("unit_lint", " ".join(body["warnings"]))

    def test_an_open_spec_escalation_of_the_task_is_refused_and_another_class_is_not(self):
        self.implemented()
        self.reviewed_as(CLEAN)
        d = self.q / "escalations" / "0002-second"
        d.mkdir(parents=True)
        (d / "1.json").write_text(json.dumps({"task_id": "0002-second", "escalation_id": "0002-second-1",
                                              "class": "operator", "status": "open"}))
        code, _, out, err = self.ccp("tasks", "submit", "0002")
        self.assertEqual(code, 0, out + err)
        (d / "2.json").write_text(json.dumps({"task_id": "0002-second", "escalation_id": "0002-second-2",
                                              "class": "spec", "status": "waiting_operator"}))
        self.assertIn("0002-second-2", self.refused("no_open_spec_escalation"))

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


class SubmitAfterClean(PhaseFlow, ToolkitFixture, unittest.TestCase):
    """Under `verify.skip_review_after_clean`, the fix of a clean review's MINOR findings is submitted with no new
    review, as `ccp prompt verify` would open its verify."""

    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "verify": {"skip_review_after_clean": True}}

    def setUp(self):
        super().setUp()
        self.start()

    def test_the_fix_of_a_clean_review_with_minor_findings_is_submitted(self):
        self.implemented()
        self.reviewed_as(MINOR_ONLY)
        self.fix(A, B)
        code, body, out, err = self.ccp("tasks", "submit", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["head"], self.status()), (B, "submitted"))


class SubmitProvenFix(SkipFlow, ToolkitFixture, unittest.TestCase):
    """Under `verify.skip_review`, a fix of a clean review that the proof passes is submitted with no new review."""

    PLANE_JSON = SKIP_REVIEW_PLANE

    def setUp(self):
        super().setUp()
        t = Path(self._tmp.name)
        (t / "proof").write_text(PROOF)
        (t / "proof").chmod(0o755)
        self.log = t / "proof.log"
        os.environ.update(PROOF_BIN=str(t / "proof"), PROOF_LOG=str(self.log))  # the fixture's env patch restores it
        self.ccp("tasks", "claim", "0002")
        self.wt = self.main / config.WORKTREES_DIR / "impl-0002"  # the claim made it, on task/0002-second

    def test_a_proven_fix_of_a_clean_review_is_submitted(self):
        self.commit("feature.txt", "built\n")
        reviewed = self.push()
        self.run_phase("review", reviewed, f"Severity: {CLEAN}")
        head = self.fix()
        code, body, out, err = self.ccp("tasks", "submit", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["head"], body["to"]), (head, "submitted"))
        self.assertEqual(self.log.read_text().split()[:3], ["0002-second", reviewed, head])  # the proof ran


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
        for kw, token in ((dict(record=None), "review/t.json"),
                          (dict(latest_review="t/review-2"), "t/review-2"),
                          (dict(latest_clean=False), "t/review"),
                          (dict(pr=8), "PR 8"),
                          (dict(head=None), None),
                          (dict(uncovered="fix round newer"), "fix round newer")):
            with self.subTest(kw=kw):
                failed = submit.failures("t", self.facts(**kw))
                self.assertEqual([f.split(":")[0] for f in failed if not f.startswith("pr_exists")],
                                 ["review_artifact_present"])
                if token:
                    self.assertIn(token, failed[-1])

    def test_failures_are_named_in_item_order(self):
        failed = submit.failures("t", self.facts(pr=None, record=None, open_refs=["sm-1"]))
        self.assertEqual([f.split(":")[0] for f in failed], list(submit.ITEMS))

    def test_the_items_are_the_standing_dods_formal_submit_items(self):
        text = (PLANE / "dod" / "standing.yaml").read_text()
        block = re.search(r"- id: formal_submit\n(.*?)(?=\n  - id: |\Z)", text, re.S)
        must = re.search(r"\n    must:\n((?:      - .*\n)+)", block.group(1) if block else "")
        self.assertIsNotNone(must)
        self.assertEqual({line.strip()[2:].split("#")[0].strip() for line in must.group(1).splitlines()},
                         {*submit.ITEMS, "unit_lint"})

    def test_only_a_task_mid_flight_and_not_past_submitted_may_be_submitted(self):
        for status in sorted(submit.SUBMITTABLE):
            self.assertIsNone(submit.phase_refusal("t", status), status)
        for status in ("done", "pending", None, "verifying", "merging", "dropped"):
            self.assertIsNotNone(submit.phase_refusal("t", status), status)


class Script(unittest.TestCase):
    """The kept script only runs `ccp tasks submit` and exits with its code."""

    def test_the_script_runs_ccp_tasks_submit_with_the_task_and_exits_with_its_code(self):
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "ccp"
            stub.write_text('#!/bin/sh\necho "$@" > "$(dirname "$0")/argv"\nexit 4\n')
            stub.chmod(0o755)
            r = subprocess.run(["bash", str(PLANE / "scripts/formal-submit.template.sh"), "0009-x"], capture_output=True,
                               text=True, env={**os.environ, "PATH": f"{d}:{os.environ['PATH']}"})
            self.assertEqual(r.returncode, 4, r.stderr)
            self.assertEqual((Path(d) / "argv").read_text().split(), ["tasks", "submit", "0009-x"])


if __name__ == "__main__":
    unittest.main()
