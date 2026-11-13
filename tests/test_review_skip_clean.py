"""SPEC §15.2, plane.json `verify.skip_review_after_clean`: when the latest review found nothing above
MINOR, the fix round that answers it goes to verify with no new review, the run records the skip
(`minor-only`, the review run, the head it judged, its report's path, its counts below MAJOR), and the verify prompt names those findings.
A BLOCKER or MAJOR, the setting off, a head other than the fix's, or a verify reject since the review
keeps the review."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from ccp import config
from tests import test_review_gate
from tests.test_toolkit import PLANE, ToolkitFixture

A, B, C = "a" * 40, "b" * 40, "c" * 40
CLEAN = "Severity: BLOCKER=0 MAJOR=0 MINOR=2 NIT=0"


class Rounds(ToolkitFixture):
    """A claimed task whose runs open a minute apart, with the rounds the gate orders by."""

    run_phase = test_review_gate.ReviewGate.run_phase
    verdict = test_review_gate.ReviewGate.verdict

    def setUp(self):
        super().setUp()
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")

    def review(self, severity: str = CLEAN, head: str = A) -> str:
        return self.run_phase("review", head, severity)

    def fix(self, head: str = A, to: str = B, *extra: str) -> str:
        return self.run_phase("fix", head, f"PR: #7\nHead: {to}", *extra)

    def verify(self, head: str = B, *extra: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head, *extra)

    def refused(self, head: str = B) -> str:
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("run `ccp prompt review` first", err)
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())  # nothing opened
        return err


class SkipAfterClean(Rounds, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "verify": {"skip_review_after_clean": True}}

    def test_a_fix_after_a_clean_review_goes_straight_to_verify(self):
        self.review()
        self.fix()
        code, body, out, err = self.verify()
        self.assertEqual(code, 0, out + err)
        report = str(self.q / "progress/0002-second/review-report.md")
        want = {"reason": "minor-only", "review_run": "0002-second/review", "reviewed": A, "report": report,
                "findings": {"MINOR": 2, "NIT": 0}}
        self.assertEqual(body["review_skip"], want)
        self.assertNotIn("allow_unreviewed_fix", body)
        run = json.loads((self.q / "runs/0002-second/verify.json").read_text())
        self.assertEqual(run["review_skip"], want)
        prompt = Path(body["prompt_path"]).read_text()
        self.assertIn("verify.skip_review_after_clean", prompt)
        self.assertIn("MINOR=2, NIT=0", prompt)
        self.assertIn(report, prompt)
        self.assertIn("Read that report", prompt)
        self.assertIn(f"from {A} to {B}", prompt)  # the fix diff runs from the head the review judged
        code, _, out, err = self.verdict(B)
        self.assertEqual(code, 0, out + err)  # the approve stands on the skip

    def test_nits_alone_count_as_findings_below_major(self):
        self.review("Severity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=3")
        self.fix()
        code, body, out, err = self.verify()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"]["findings"], {"MINOR": 0, "NIT": 3})

    def test_a_major_or_blocker_keeps_the_review(self):
        for sev, said in (("BLOCKER=0 MAJOR=1 MINOR=2 NIT=0", "found 1 MAJOR"),
                          ("BLOCKER=1 MAJOR=0 MINOR=2 NIT=0", "found 1 BLOCKER")):
            with self.subTest(sev=sev):
                self.review(f"Severity: {sev}", head=A)
                self.fix()
                err = self.refused()
                self.assertIn(f"(verify.skip_review_after_clean does not apply: the last review", err)
                self.assertIn(said, err)

    def test_a_review_with_no_findings_gives_the_fix_nothing_to_answer(self):
        self.review("Severity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0")
        self.fix()
        self.assertIn("found nothing for a fix round to answer", self.refused())

    def test_a_review_with_no_severity_on_record_gives_no_skip(self):
        self.review()
        self.fix()
        f = self.q / "runs/0002-second/review.json"
        f.write_text(json.dumps({k: v for k, v in json.loads(f.read_text()).items() if k != "severity"}))
        self.assertIn("recorded no Severity counts", self.refused())

    def test_a_head_other_than_the_fixs_keeps_the_review(self):
        self.review()
        self.fix()
        self.assertIn(f"head {C[:12]} is not {B[:12]}, the head 0002-second/fix reported", self.refused(C))

    def test_a_fix_that_has_not_reported_keeps_the_review(self):
        self.review()
        code, _, out, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        self.assertIn("0002-second/fix has reported no head", self.refused())

    def test_a_verify_reject_since_the_review_sends_the_task_back_to_review(self):
        self.review()
        self.fix()
        code, _, out, err = self.verify()
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.verdict(B, "reject")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report("0002-second/verify", f"Outcome: done\nVerdict: reject\nHead: {B}\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        self.fix(B, C)
        code, _, out, err = self.verify(C)
        self.assertEqual(code, 4, out + err)
        self.assertIn("0002-second/verify rejected since the last review: the task goes back to review", err)
        self.assertFalse((self.q / "runs/0002-second/verify-2.json").exists())
        self.review(head=C)  # a new review, clean again: its fix may skip once more
        self.fix(C, A)
        code, body, out, err = self.verify(A)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"]["review_run"], "0002-second/review-2")

    def test_verify_record_holds_an_approve_to_the_verify_runs_head(self):
        self.review()
        self.fix()
        code, _, out, err = self.verify()
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.verdict(C)
        self.assertEqual(code, 1, out + err)
        self.assertIn("skip_review_after_clean", err)
        self.assertFalse((self.q / "verification/0002-second.json").exists())

    def test_a_verify_with_no_skip_has_no_minor_only_section(self):
        self.review()
        code, body, out, err = self.verify(A)  # no fix round: nothing skipped
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("review_skip", body)
        self.assertNotIn("verify.skip_review_after_clean", Path(body["prompt_path"]).read_text())


class SkipAfterCleanOff(Rounds, unittest.TestCase):
    """Off by default: a fix after a clean review is reviewed again, as before the setting."""

    def test_off_by_default_the_fix_is_reviewed(self):
        self.assertIs(config.load(self.main).verify["skip_review_after_clean"], False)
        self.review()
        self.fix()
        self.assertNotIn("skip_review_after_clean", self.refused())

    def test_the_setting_is_validated(self):
        for bad in ("true", 1, None, {"on": True}):
            with self.subTest(bad=bad):
                self.write("docs/delivery/plane.json",
                           json.dumps({"project_id": "demo", "verify": {"skip_review_after_clean": bad}}))
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.main)
                self.assertIn("verify.skip_review_after_clean must be true or false", str(cm.exception))

    def test_the_schema_has_the_setting(self):
        schema = json.loads((PLANE / "contracts/plane_config.schema.json").read_text())
        knob = schema["properties"]["verify"]["properties"]["skip_review_after_clean"]
        self.assertEqual((knob["type"], knob["default"]), ("boolean", config.VERIFY_DEFAULTS["skip_review_after_clean"]))


if __name__ == "__main__":
    unittest.main()
