"""Merge and ruling rounds (SPEC §13.2): `ccp prompt merge` only merges the integration tip into the task
branch, `ccp prompt ruling` only applies a lead's ruling. Each is a run of its own kind, with its own
prompt, and review and verify treat its head as a fix round's (§15.2, §15.6 rule 4)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from ccp import report, runs, verify
from tests import test_review_gate
from tests.test_report_fields import HEAD, MIGRATION, implement_report
from tests.test_toolkit import ToolkitFixture

A, B = "a" * 40, "b" * 40
RULING = "Lead ruling: the field is optional."


class Rounds(ToolkitFixture, unittest.TestCase):
    run_phase = test_review_gate.ReviewGate.run_phase
    review = test_review_gate.ReviewGate.review
    fix = test_review_gate.ReviewGate.fix
    verdict = test_review_gate.ReviewGate.verdict
    verify_round = test_review_gate.RepeatVerify.verify_round

    def setUp(self):
        super().setUp()
        # runs open a minute apart: `opened_at` has one-second resolution, and the gates order by it
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")

    def merge(self, head: str = A, to: str = B) -> str:
        return self.run_phase("merge", head, f"PR: #7\nHead: {to}")

    def ruling(self, head: str = A, to: str = B) -> str:
        return self.run_phase("ruling", head, f"PR: #7\nHead: {to}", "--note", RULING)

    def verify(self, head: str, *extra: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head, *extra)

    def test_a_merge_round_is_recorded_as_one(self):
        code, body, out, err = self.ccp("prompt", "merge", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["run_id"], body["phase"]), ("0002-second/merge", "merge"))
        run = json.loads((self.q / "runs/0002-second/merge.json").read_text())
        self.assertEqual((run["phase"], run["seat"], run["agent_type"]), ("merge", "implementer", "delivery-implementer"))
        self.assertEqual(run["worktree"], str(self.main / ".rt" / "impl-0002"))  # the task's own worktree
        self.assertFalse((self.q / "runs/0002-second/implement-2.json").exists())
        prompt = Path(body["prompt_path"])
        self.assertEqual(prompt.name, "merge-prompt.md")
        self.assertIn("merge round 1", prompt.read_text())
        self.assertEqual(json.loads((self.q / "tasks/0002-second.json").read_text())["status"], "fixing")
        self.assertEqual(body["agent_call"]["description"], "0002 merge")
        code, _, out, err = self.report("0002-second/merge", "Outcome: done\nPR: #7\n## Friction\nnone\n")
        self.assertEqual(code, 1, out + err)
        self.assertIn("no `Head: <sha>` line", err)
        code, _, out, err = self.report("0002-second/merge", f"Outcome: done\nPR: #7\nHead: {B}\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "merge", "0002", "--pr", "7", "--head", B)
        self.assertEqual((code, body["run_id"]), (0, "0002-second/merge-2"), out + err)

    def test_a_ruling_round_needs_the_ruling_and_no_prior_review(self):
        code, _, out, err = self.ccp("prompt", "ruling", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 2, out + err)
        self.assertIn("--note or --note-file", err)
        self.assertFalse((self.q / "runs/0002-second").exists())  # nothing opened
        code, _, _, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 2)  # a fix needs findings to fix from; a ruling does not
        code, body, out, err = self.ccp("prompt", "ruling", "0002", "--pr", "7", "--head", A, "--note", RULING)
        self.assertEqual(code, 0, out + err)
        run = json.loads((self.q / "runs/0002-second/ruling.json").read_text())
        self.assertEqual((run["phase"], run["seat"], run["note"]), ("ruling", "implementer", RULING))
        text = Path(body["prompt_path"]).read_text()
        self.assertEqual(Path(body["prompt_path"]).name, "ruling-prompt.md")
        self.assertIn("ruling round 1", text)
        self.assertIn(RULING, text)

    def test_the_new_rounds_need_the_pr_and_head(self):
        for phase in ("merge", "ruling"):
            code, _, _, err = self.ccp("prompt", phase, "0002", "--note", RULING)
            self.assertEqual(code, 2, phase)
            self.assertIn("give --pr and --head", err)

    def test_the_review_and_verify_prompts_list_their_reports(self):
        merge, ruling = self.merge(), self.ruling(B, A)
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        for run_id in (merge, ruling):
            self.assertIn(str(runs.report_path(self.q, run_id)), text)

    def test_a_ruling_after_the_review_is_reviewed_again(self):
        self.review(A)
        run_id = self.ruling(A, B)
        code, _, out, err = self.verify(B)
        self.assertEqual(code, 4, out + err)
        self.assertIn(f"ruling round {run_id} is newer than the last review 0002-second/review", err)
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())
        self.review(B)
        code, _, out, err = self.verify(B)
        self.assertEqual(code, 0, out + err)

    def test_a_merge_that_left_the_reviewed_change_alone_needs_no_new_review(self):
        self.review(A)
        self.merge(A, B)
        with mock.patch("ccp.runs.same_change", return_value=True) as same:
            code, _, out, err = self.verify(B)
        self.assertEqual(code, 0, out + err)
        same.assert_called_with(self.q, A, B)

    def test_a_merge_that_moved_the_reviewed_change_is_reviewed_again(self):
        self.review(A)
        run_id = self.merge(A, B)
        with mock.patch("ccp.runs.same_change", return_value=False):
            code, _, out, err = self.verify(B)
        self.assertEqual(code, 4, out + err)
        self.assertIn(f"merge round {run_id} is newer than the last review", err)

    def test_a_merge_before_any_review_is_reviewed(self):
        self.merge(A, B)
        with mock.patch("ccp.runs.same_change", return_value=True):
            code, _, out, err = self.verify(B)
        self.assertEqual(code, 4, out + err)
        self.assertIn("merge round 0002-second/merge is newer than the last review (none)", err)

    def test_a_fix_before_the_merge_still_needs_its_review(self):
        self.review(A)
        self.fix(A, B)
        self.merge(B, B)
        with mock.patch("ccp.runs.same_change", return_value=True):
            self.assertIsNotNone(runs.unreviewed_fix(self.q, "0002-second", B))
            code, _, out, err = self.verify(B)
        self.assertEqual(code, 4, out + err)
        self.assertIn("merge round 0002-second/merge is newer", err)

    def round_since_the_last_verify(self, kind: str) -> None:
        self.review(A)
        self.verify_round()
        code, _, out, err = self.verify(A)
        self.assertEqual(code, 4, out + err)  # no round since: the reason is asked for
        self.assertIn("SPEC §15.6 rule 4", err)
        getattr(self, kind)(A, A)
        self.review(A)
        code, body, out, err = self.verify(A)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("repeat_verify", body)
        self.assertIsNone(verify.repeat_round(self.q, "0002-second"))

    def test_a_merge_round_since_the_last_verify_needs_no_reason(self):
        self.round_since_the_last_verify("merge")

    def test_a_ruling_round_since_the_last_verify_needs_no_reason(self):
        self.round_since_the_last_verify("ruling")


class RunIds(unittest.TestCase):
    def test_merge_and_ruling_run_ids_parse(self):
        self.assertEqual(runs.parse_id("0002-second/merge-2"), ("0002-second", "merge", 2))
        self.assertEqual(runs.parse_id("0002-second/ruling"), ("0002-second", "ruling", 1))
        self.assertEqual(runs.report_path(Path("/q"), "0002-second/ruling-3"),
                         Path("/q/progress/0002-second/ruling-3-report.md"))

    def test_their_reports_carry_the_pr_and_head(self):
        for phase in ("merge", "ruling"):
            got, errs = report.parse(phase, "Outcome: done\n## Friction\nnone\n")
            self.assertIn("no `PR: #<number>` line", errs, phase)
            self.assertIn("no `Head: <sha>` line", errs, phase)
            got, errs = report.parse(phase, f"Outcome: done\nPR: #7\nHead: {A}\n## Friction\nnone\n")
            self.assertEqual((errs, got["pr"], got["head"]), ([], "7", A), phase)


class Verdicts(ToolkitFixture, unittest.TestCase):
    """§13.4: the declared verdicts are asked of a merge or ruling report too, and the review shows its."""
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "report": {"required_fields": [MIGRATION]}}

    def test_a_merge_report_states_the_verdicts_and_the_review_shows_them(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.report("0002-second/implement", implement_report("Migration: required"))
        code, body, out, err = self.ccp("prompt", "merge", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        self.assertIn("`migration: required|not required`", Path(body["prompt_path"]).read_text())
        code, _, _, err = self.report("0002-second/merge", implement_report())
        self.assertEqual(code, 1)
        self.assertIn("migration", err)
        code, _, out, err = self.report("0002-second/merge", implement_report("Migration: not required"))
        self.assertEqual(code, 0, out + err)
        for run_id in ("0002-second/implement", "0002-second/merge"):  # one second: the later round wins
            f = self.q / "runs" / (run_id + ".json")
            rec = json.loads(f.read_text())
            rec.update(reported_at="2026-01-01T00:01:00Z")
            f.write_text(json.dumps(rec))
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["report_fields"], {"run_id": "0002-second/merge", "fields": {"migration": "not required"}})


if __name__ == "__main__":
    unittest.main()
