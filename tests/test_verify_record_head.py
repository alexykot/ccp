"""SPEC §15.4: `ccp verify record` refuses a `head_sha` that is not the head of the task's open verify run,
before any other check, naming both heads."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from ccp import config
from tests.helpers import PLANE_ROOT, run_clock
from tests.review_flow import PROOF, SKIP_REVIEW_PLANE, SkipFlow
from tests.toolkit_fixture import ToolkitFixture


class RecordHead(SkipFlow, ToolkitFixture, unittest.TestCase):
    """A task whose last round is a fix the product's proof proved, with a verify run open at the fix's head."""

    PLANE_JSON = SKIP_REVIEW_PLANE

    def setUp(self):
        super().setUp()
        run_clock(self)
        t = Path(self._tmp.name)
        (t / "proof").write_text(PROOF)
        (t / "proof").chmod(0o755)
        self.log = t / "proof.log"
        os.environ.update(PROOF_BIN=str(t / "proof"), PROOF_LOG=str(self.log))  # the fixture's env patch restores it
        self.ccp("tasks", "claim", "0002")
        self.wt = self.main / config.WORKTREES_DIR / "impl-0002"
        self.reviewed()
        self.head = self.fix()
        code, body, out, err = self.verify(self.head)
        self.assertEqual(code, 0, out + err)
        self.run_id = body["run_id"]
        self.typo = ("0" if self.head[0] != "0" else "1") + self.head[1:]  # one character off

    def refused_as_a_head_mismatch(self, verdict: str) -> str:
        code, _, out, err = self.verdict(self.typo, verdict)
        self.assertEqual(code, 1, out + err)
        self.assertFalse((self.q / "verification/0002-second.json").exists())  # nothing written
        for token in (self.typo[:12], self.head[:12], self.run_id):  # both heads and the run, named
            self.assertIn(token, err)
        return err

    def test_an_approve_of_another_head_after_a_proven_fix_is_refused_as_a_head_mismatch(self):
        err = self.refused_as_a_head_mismatch("approve")
        self.assertNotIn("ccp prompt review", err)

    def test_a_reject_of_another_head_is_refused_as_a_head_mismatch(self):
        self.refused_as_a_head_mismatch("reject")

    def test_a_reject_with_no_head_sha_is_not_held_to_the_runs_head(self):
        rec = json.loads((PLANE_ROOT / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", verdict="reject")
        rec.pop("head_sha", None)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": False, "evidence": "ran it", "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)

    def test_a_record_at_the_runs_head_passes(self):
        code, _, out, err = self.verdict(self.head)
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
