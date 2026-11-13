"""SPEC §15.2, plane.json `verify.provers` with `skips: review`: a declared prover that exits 0 on the fix
round's diff sends the fix straight to verify, its name, command and exit recorded on the verify run.
`verify.skip_review`, when set, is tried first; a prover that fails or times out keeps the refusal."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from tests import test_review_gate, test_review_skip
from tests.test_toolkit import ToolkitFixture

PROVE = '"$PROOF_BIN" {task_id} {reviewed} {head} {from}'


class ReviewProvers(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON,
                  "verify": {"provers": [{"name": "comments", "command": PROVE, "skips": "review"}]}}
    run_phase = test_review_gate.ReviewGate.run_phase
    review = test_review_gate.ReviewGate.review
    verdict = test_review_gate.ReviewGate.verdict
    commit = test_review_skip.SkipReview.commit
    push = test_review_skip.SkipReview.push
    reviewed = test_review_skip.SkipReview.reviewed
    fix = test_review_skip.SkipReview.fix
    verify = test_review_skip.SkipReview.verify

    def setUp(self):
        super().setUp()
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        t = Path(self._tmp.name)
        (t / "proof").write_text(test_review_skip.PROOF)
        (t / "proof").chmod(0o755)
        self.log = t / "proof.log"
        os.environ.update(PROOF_BIN=str(t / "proof"), PROOF_LOG=str(self.log))  # the fixture's env patch restores it
        self.ccp("tasks", "claim", "0002")
        self.wt = self.main / ".rt" / "impl-0002"  # the claim made it, on task/0002-second

    def plane(self, body: dict) -> None:
        """The plane.json `ccp` reads here, the runner checkout's."""
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(body))

    def refused(self, head: str, label: str, why: str) -> None:
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn(f"({label} does not apply: {why}", err)
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())  # nothing opened

    def test_a_proven_fix_goes_straight_to_verify_with_the_prover_on_record(self):
        reviewed = self.reviewed()
        head = self.fix("feature.txt", "built  # a comment\n")  # no paths rule: the prover alone judges
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        want = {"reviewed": reviewed, "head": head, "fix": "0002-second/fix", "files": 1,
                "prover": "comments", "command": PROVE, "exit_code": 0}
        self.assertEqual(body["review_skip"], want)
        run = json.loads((self.q / "runs/0002-second/verify.json").read_text())
        self.assertEqual(run["review_skip"], want)
        task, got_reviewed, got_head, _start = self.log.read_text().split()
        self.assertEqual((task, got_reviewed, got_head), ("0002-second", reviewed, head))
        code, _, out, err = self.verdict(head)
        self.assertEqual(code, 0, out + err)  # the approve stands on the proven skip

    def test_a_failing_prover_keeps_the_review(self):
        self.reviewed()
        head = self.fix()
        os.environ["PROOF_EXIT"] = "2"
        self.refused(head, "verify.provers", "the prover comments (verify.provers) exited 2")

    def test_a_prover_that_times_out_proves_nothing(self):
        self.reviewed()
        head = self.fix()
        os.environ["PROOF_SLEEP"] = "5"
        with mock.patch("ccp.verify.PROOF_TIMEOUT", 1):
            self.refused(head, "verify.provers", "the prover comments (verify.provers) timed out after 1s")

    def test_a_fix_that_changes_no_file_runs_no_prover(self):
        reviewed = self.reviewed()
        self.run_phase("fix", reviewed, f"PR: #7\nHead: {reviewed}")
        self.refused(reviewed, "verify.provers", "the fix changes no file of its own")
        self.assertFalse(self.log.exists())

    def test_the_first_prover_to_pass_skips_the_review(self):
        self.plane(({**self.PLANE_JSON, "verify": {"provers": [
            {"name": "never", "command": "exit 1", "skips": "review"},
            {"name": "comments", "command": PROVE, "skips": "review"}]}}))
        self.reviewed()
        head = self.fix()
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"]["prover"], "comments")

    def test_skip_review_is_tried_first_then_the_provers(self):
        both = {"skip_review": {"paths": ["tests"], "proof": "exit 0"},
                "provers": [{"name": "comments", "command": PROVE, "skips": "review"}]}
        self.plane(({**self.PLANE_JSON, "verify": both}))
        reviewed = self.reviewed()
        head = self.fix()
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"], {"reviewed": reviewed, "head": head, "fix": "0002-second/fix", "files": 1})
        self.assertFalse(self.log.exists())  # skip_review proved it: no prover ran

    def test_a_prover_proves_what_skip_review_does_not(self):
        both = {"skip_review": {"paths": ["tests"], "proof": "exit 0"},
                "provers": [{"name": "comments", "command": PROVE, "skips": "review"}]}
        self.plane(({**self.PLANE_JSON, "verify": both}))
        self.reviewed()
        head = self.fix("feature.txt", "built  # a comment\n")
        os.environ["PROOF_EXIT"] = "1"
        self.refused(head, "verify.skip_review and verify.provers",
                     "the fix touches 1 file(s) outside verify.skip_review.paths (feature.txt); "
                     "the prover comments (verify.provers) exited 1")
        os.environ["PROOF_EXIT"] = "0"
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"]["prover"], "comments")

    def test_a_gate_stage_prover_does_not_judge_the_review(self):
        self.plane(({**self.PLANE_JSON, "suite": {
            "lanes": {"gate": [{"name": "suite", "cmd": "true"}]}},
            "verify": {"provers": [{"name": "comments", "command": PROVE, "skips": "suite"}]}}))
        self.reviewed()
        head = self.fix()
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertNotIn("does not apply", err)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
