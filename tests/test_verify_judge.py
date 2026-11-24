"""One judge of a verification record: `ccp verify merge-ok` and `ccp verify check` refuse the same records."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, prhost, verify
from tests.helpers import now_iso, Product
from tests.report_helpers import approve_verdict as approve, HEAD_A, HEAD_B

TASK = "0001-a"


def without_head(**fields: object) -> dict:
    rec = approve(TASK, checked_at=now_iso(), **fields)
    del rec["head_sha"]
    return rec


class Judge(unittest.TestCase):
    """`verify.judge` on plain records and `PrFacts` values."""

    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)

    def tearDown(self):
        self.p.cleanup()
        self._q.cleanup()

    def judge(self, rec: dict, head: str = HEAD_A, facts: prhost.PrFacts | None = None, **kw: object) -> list[str]:
        return verify.judge(self.p.cfg, self.q, rec, TASK, head, facts, **kw)[0]

    def facts(self, **fields: object) -> prhost.PrFacts:
        return prhost.PrFacts(**{"number": 7, "state": "open", "head": HEAD_A, **fields})

    def test_an_approval_at_the_head_is_accepted_with_and_without_the_pr(self):
        rec = approve(TASK, checked_at=now_iso())
        self.assertEqual(self.judge(rec), [])
        self.assertEqual(self.judge(rec, facts=self.facts()), [])
        reasons, body = verify.judge(self.p.cfg, self.q, rec, TASK, HEAD_A, self.facts())
        self.assertEqual((reasons, body["match_head_commit"]), ([], HEAD_A))
        self.assertNotIn("match_head_commit", verify.judge(self.p.cfg, self.q, rec, TASK, HEAD_A)[1])

    def test_a_record_with_no_head_sha_is_refused_naming_it(self):
        reasons = self.judge(without_head())
        self.assertEqual(len(reasons), 1, reasons)
        self.assertIn("names no head_sha", reasons[0])
        self.assertTrue(self.judge(without_head(), facts=self.facts()))

    def test_another_head_is_refused_and_a_short_sha_is_the_same_head(self):
        reasons = self.judge(approve(TASK, checked_at=now_iso()), head=HEAD_B)
        self.assertEqual(len(reasons), 1, reasons)
        self.assertIn("is not the approved head", reasons[0])
        self.assertEqual(self.judge(approve(TASK, head_sha=HEAD_A[:7], checked_at=now_iso())), [])
        self.assertEqual(self.judge(approve(TASK, checked_at=now_iso()), head=HEAD_A[:7]), [])

    def test_a_failed_gate_run_and_a_missing_gate_are_refused(self):
        bad = {"runs": [{"command": "scripts/unit.sh", "exit_code": 1}]}
        reasons = self.judge(approve(TASK, checked_at=now_iso(), gate=bad))
        self.assertEqual(reasons, ["gate run 'scripts/unit.sh' exited 1"])
        self.assertIn("carries no gate", "\n".join(self.judge(approve(TASK, checked_at=now_iso(), gate=None))))

    def test_a_ruling_seats_evidence_is_refused_naming_the_check(self):
        checks = [{"dod_check_id": "data-01", "pass": True, "evidence": "ran it", "produced_by": "lead"}]
        reasons = self.judge(approve(TASK, checked_at=now_iso(), checks=checks))
        self.assertEqual(len(reasons), 1, reasons)
        self.assertIn("checks[0] (data-01)", reasons[0])
        self.assertIn("produced by the lead", reasons[0])

    def test_a_closed_pr_is_refused_only_when_its_facts_are_given(self):
        rec = approve(TASK, checked_at=now_iso())
        self.assertEqual(self.judge(rec, facts=self.facts(state="closed")), ["PR 7 is closed"])
        self.assertEqual(self.judge(rec, facts=self.facts(state="closed"), pr="07"), ["PR 07 is closed"])
        self.assertEqual(self.judge(rec), [])

    def test_the_head_comes_from_the_caller_not_from_the_facts(self):
        rec = approve(TASK, checked_at=now_iso())
        self.assertEqual(self.judge(rec, head=HEAD_A, facts=self.facts()), [])
        self.assertTrue(self.judge(rec, head=HEAD_B, facts=self.facts()))


class SameRefusal(unittest.TestCase):
    """For a record refusal, `check` says what `merge-ok` says."""

    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def write(self, rec: dict) -> None:
        d = self.q / "verification"
        d.mkdir(exist_ok=True)
        (d / f"{TASK}.json").write_text(json.dumps(rec))

    def check(self, head: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "check", TASK, "--head", head])
        return code, err.getvalue()

    def merge_ok(self, head: str) -> list[str]:
        facts = prhost.PrFacts(number=7, state="open", head=head)
        with mock.patch.object(prhost, "view", return_value=facts):
            return verify.merge_ok(self.p.cfg, self.q, "7", TASK)[0]

    def test_each_record_refusal_is_the_same_from_both(self):
        ruled = [{"dod_check_id": "data-01", "pass": True, "evidence": "ran it", "produced_by": "runner"}]
        cases = {
            "no head": (without_head(), HEAD_A, "names no head_sha"),
            "another head": (approve(TASK, checked_at=now_iso()), HEAD_B, "is not the approved head"),
            "failed gate": (approve(TASK, checked_at=now_iso(),
                                    gate={"runs": [{"command": "scripts/unit.sh", "exit_code": 2}]}),
                            HEAD_A, "exited 2"),
            "no gate": (approve(TASK, checked_at=now_iso(), gate=None), HEAD_A, "carries no gate"),
            "failed check": (approve(TASK, checked_at=now_iso(),
                                     checks=[{"dod_check_id": "cmd-01", "pass": False, "evidence": "exit 1",
                                              "produced_by": "verifier"}]), HEAD_A, "a failed check (cmd-01)"),
            "reject": (approve(TASK, checked_at=now_iso(), verdict="reject"), HEAD_A, "not approve"),
            "another project": (approve(TASK, checked_at=now_iso(), project_id="other"), HEAD_A, "not demo"),
            "a ruling seat": (approve(TASK, checked_at=now_iso(), checks=ruled), HEAD_A, "produced by the runner"),
        }
        for name, (rec, head, needle) in cases.items():
            with self.subTest(name):
                self.write(rec)
                code, err = self.check(head)
                reasons = self.merge_ok(head)
                self.assertEqual(code, 1, err)
                self.assertTrue(reasons)
                self.assertIn(needle, err)
                self.assertEqual(err.strip(), "ccp verify: " + "; ".join(reasons))

    def test_an_approval_at_the_head_passes_both(self):
        self.write(approve(TASK, checked_at=now_iso()))
        self.assertEqual(self.check(HEAD_A)[0], 0)
        self.assertEqual(self.merge_ok(HEAD_A), [])


if __name__ == "__main__":
    unittest.main()
