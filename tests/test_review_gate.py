"""SPEC §15.2: a fix round is reviewed again before it is
verified. `ccp prompt verify` refuses a task whose latest fix run is newer than its last review, or a
head other than the one that review judged; `ccp verify record` refuses the approve likewise. The
lead's override is recorded as a friction note and a ledger event."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from tests.test_toolkit import PLANE, ToolkitFixture, git

A, B = "a" * 40, "b" * 40


class ReviewGate(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        # runs open a minute apart: `opened_at` has one-second resolution, and the gate orders by it
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")

    def run_phase(self, phase: str, head: str, lines: str, *extra: str):
        code, body, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", head, *extra)
        self.assertEqual(code, 0, f"{phase}: {out}{err}")
        code, _, out, err = self.report(body["run_id"], f"Outcome: done\n{lines}\n## Friction\nnone\n")
        self.assertEqual(code, 0, f"{phase} report: {out}{err}")
        return body["run_id"]

    def review(self, head: str = A):
        return self.run_phase("review", head, "Severity: BLOCKER=0 MAJOR=1 MINOR=0 NIT=0")

    def fix(self, head: str = A, to: str = B):
        return self.run_phase("fix", head, f"PR: #7\nHead: {to}")

    def verdict(self, head: str, verdict: str = "approve"):
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head, verdict=verdict)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": verdict == "approve", "evidence": "ran it",
                          "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        return self.ccp("verify", "record", str(f))

    def test_a_fix_after_the_review_is_refused(self):
        self.review()
        self.fix()
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", B)
        self.assertEqual(code, 4, out + err)
        self.assertIn("fix round 0002-second/fix is newer than the last review 0002-second/review: "
                      "run `ccp prompt review` first (runner brief step 7)", err)
        self.assertNotIn("verify.skip_review", err)  # off by default: no skip is tried
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())  # nothing opened

    def test_a_review_after_the_fix_is_allowed(self):
        self.review()
        self.fix()
        self.review(B)
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", B)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("allow_unreviewed_fix", body)

    def test_no_fix_round_is_allowed_and_no_review_at_all_too(self):
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        self.review()
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A, "--supersede")
        self.assertEqual(code, 0, out + err)

    def test_a_head_the_last_review_did_not_judge_is_refused(self):
        self.review(A)
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", B)
        self.assertEqual(code, 4, out + err)
        self.assertIn(f"head {B[:12]} is not {A[:12]}, the head the last review 0002-second/review judged", err)
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A[:12])
        self.assertEqual(code, 0, out + err)  # a short sha of the judged head is the same head

    def test_the_latest_fix_that_is_not_abandoned_is_the_one_named(self):
        self.review()
        self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", A)
        self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", A, "--supersede")  # fix abandoned, fix-2 pending
        code, _, _, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 4)
        self.assertIn("fix round 0002-second/fix-2 is newer", err)

    def test_the_override_is_recorded_as_a_friction_note_and_an_event(self):
        self.review()
        self.fix()
        code, _, _, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", B, "--allow-unreviewed-fix")
        self.assertEqual(code, 2)
        self.assertIn("needs --reason", err)
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", B,
                                        "--allow-unreviewed-fix", "--reason", "operator: post-merge review of the fix commits")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["allow_unreviewed_fix"]["reason"], "operator: post-merge review of the fix commits")
        run = json.loads((self.q / "runs/0002-second/verify.json").read_text())
        self.assertIn("is newer than the last review", run["allow_unreviewed_fix"]["was"])
        notes = [json.loads(x) for x in (self.q / "health/notes.jsonl").read_text().splitlines()]
        self.assertEqual(notes[-1]["source"], "allow-unreviewed-fix")
        self.assertIn("operator: post-merge review", notes[-1]["text"])
        ev = [e for e in self.events() if (e["type"], e["op"]) == ("note", "set")][-1]
        self.assertEqual((ev["payload"]["source"], ev["payload"]["run_id"]), ("allow-unreviewed-fix", "0002-second/verify"))
        code, _, out, err = self.verdict(B)
        self.assertEqual(code, 0, out + err)  # the override stands for this verify run's approve

    def test_the_override_flag_belongs_to_verify(self):
        code, _, _, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", A, "--allow-unreviewed-fix",
                                   "--reason", "x")
        self.assertEqual(code, 2)
        self.assertIn("for `ccp prompt verify` only", err)

    def test_verify_record_refuses_an_approve_with_an_unreviewed_fix(self):
        self.review()
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        self.fix()  # a fix pushed while the verifier ran
        code, _, out, err = self.verdict(B)
        self.assertEqual(code, 1, out + err)
        self.assertIn("fix round 0002-second/fix is newer than the last review", err)
        self.assertFalse((self.q / "verification/0002-second.json").exists())
        code, _, out, err = self.verdict(B, "reject")
        self.assertEqual(code, 0, out + err)  # a reject is never held back

    def test_verify_record_refuses_an_approve_of_a_head_the_review_did_not_judge(self):
        self.review(A)
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A)
        code, _, out, err = self.verdict(B)
        self.assertEqual(code, 1, out + err)
        self.assertIn("the head the last review 0002-second/review judged", err)
        code, _, out, err = self.verdict(A)
        self.assertEqual(code, 0, out + err)



class RepeatVerify(ToolkitFixture, unittest.TestCase):
    """SPEC §15.6 rule 4: a verify round with no fix round since the last says why, from the
    runner's `--note`, and the reason reaches the verifier's record."""
    run_phase = ReviewGate.run_phase
    review = ReviewGate.review
    fix = ReviewGate.fix
    verdict = ReviewGate.verdict

    def setUp(self):
        super().setUp()
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")

    def verify_round(self, head: str = A, verdict: str = "reject"):
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.verdict(head, verdict)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(body["run_id"], f"Outcome: done\nVerdict: {verdict}\nHead: {head}\n"
                                                         "## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        return body["run_id"]

    def test_a_second_verify_with_no_fix_since_needs_a_note(self):
        self.review()
        first = self.verify_round()
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 4, out + err)
        self.assertIn("SPEC §15.6 rule 4", err)
        self.assertIn(first, err)
        self.assertFalse((self.q / "runs/0002-second/verify-2.json").exists())  # nothing opened
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A,
                                        "--note", "the gate timed out on a slow runner")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["repeat_verify"], {"after": first})
        run = json.loads((self.q / "runs/0002-second/verify-2.json").read_text())
        self.assertEqual(run["repeat_verify"], {"after": first})
        self.assertEqual(run["note"], "the gate timed out on a slow runner")

    def test_a_note_file_gives_the_reason_too(self):
        self.review()
        self.verify_round()
        f = Path(self._tmp.name) / "why.txt"
        f.write_text("head moved by an integration merge\n")
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A, "--note-file", str(f))
        self.assertEqual(code, 0, out + err)

    def test_a_fix_round_since_the_last_verify_needs_no_note(self):
        self.review()
        self.verify_round()
        self.fix()
        self.review(B)
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", B)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("repeat_verify", body)

    def test_a_verify_run_that_never_reported_is_no_round(self):
        self.review()
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A)
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A, "--supersede")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("repeat_verify", body)

    def test_a_fix_opened_in_the_same_second_counts_and_an_abandoned_one_does_not(self):
        from ccp import verify
        self.review()
        first = self.verify_round()
        self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", A)
        runs_dir = self.q / "runs/0002-second"
        fix = json.loads((runs_dir / "fix.json").read_text())
        fix["opened_at"] = json.loads((runs_dir / "verify.json").read_text())["opened_at"]
        (runs_dir / "fix.json").write_text(json.dumps(fix))
        self.assertIsNone(verify.repeat_round(self.q, "0002-second"))
        fix["abandoned_at"] = fix["opened_at"]
        (runs_dir / "fix.json").write_text(json.dumps(fix))
        self.assertEqual(verify.repeat_round(self.q, "0002-second"), first)

    def test_the_reason_reaches_the_verifiers_record(self):
        self.review()
        first = self.verify_round()
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A, "--note", "flaky gate, rerun")
        code, _, out, err = self.verdict(A)
        self.assertEqual(code, 0, out + err)
        rec = json.loads((self.q / "verification/0002-second.json").read_text())
        held = [f for f in rec["findings"] if "flaky gate, rerun" in f]
        self.assertEqual(len(held), 1, rec["findings"])
        self.assertIn(first, held[0])

    def test_a_finding_that_already_holds_the_reason_is_not_repeated(self):
        self.review()
        self.verify_round()
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A, "--note", "flaky gate, rerun")
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=A, verdict="approve", findings=["flaky gate, rerun"])
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it",
                          "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        rec = json.loads((self.q / "verification/0002-second.json").read_text())
        self.assertEqual(rec["findings"], ["flaky gate, rerun"])

    def test_another_statement_ending_with_the_reason_does_not_swallow_it(self):
        self.review()
        first = self.verify_round()
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A, "--note", "flaky gate, rerun")
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=A, verdict="approve", findings=["lint warned: flaky gate, rerun"])
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it",
                          "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        findings = json.loads((self.q / "verification/0002-second.json").read_text())["findings"]
        self.assertEqual(len(findings), 2, findings)
        self.assertEqual(findings[0], "lint warned: flaky gate, rerun")
        self.assertTrue(findings[1].endswith(": flaky gate, rerun") and first in findings[1], findings)

    def test_a_short_reason_inside_another_finding_is_still_added(self):
        self.review()
        first = self.verify_round()
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A, "--note", "rerun")
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=A, verdict="approve", findings=["flaky gate, rerun"])
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it",
                          "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        findings = json.loads((self.q / "verification/0002-second.json").read_text())["findings"]
        self.assertEqual(findings[0], "flaky gate, rerun")
        self.assertEqual(len(findings), 2, findings)
        self.assertTrue(findings[1].endswith(": rerun") and first in findings[1], findings)
        f.write_text(json.dumps({**rec, "findings": findings}))  # recorded again: the reason is not repeated
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads((self.q / "verification/0002-second.json").read_text())["findings"], findings)

    def test_a_first_verify_leaves_the_findings_alone(self):
        self.review()
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", A, "--note", "first look")
        code, _, out, err = self.verdict(A)
        self.assertEqual(code, 0, out + err)
        rec = json.loads((self.q / "verification/0002-second.json").read_text())
        self.assertFalse(any("first look" in f for f in rec.get("findings") or []))


class MergeIn(ToolkitFixture, unittest.TestCase):
    """§15.2: merging the integration branch in, the PR's own change
    unchanged, needs no new review; a changed diff still does."""
    run_phase = ReviewGate.run_phase
    review = ReviewGate.review

    def setUp(self):
        super().setUp()
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")
        (self.q / "project.yaml").write_text((self.q / "project.yaml").read_text() + f"product_root: {self.main}\n")

    def commit(self, wt, rel, text, msg):
        (wt / rel).write_text(text)
        git(wt, "add", rel)
        git(wt, "commit", "-q", "-m", msg)
        return git(wt, "rev-parse", "HEAD")

    def test_a_merge_in_with_the_same_change_needs_no_new_review(self):
        wt = self.main / ".rt" / "impl-0002"
        reviewed = self.commit(wt, "feature.txt", "built\n", "Task 0002: build it")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        self.review(reviewed)
        other = self.main / ".rt" / "other"  # another task merges to main meanwhile
        git(self.main, "worktree", "add", "-q", "--detach", str(other), "origin/main")
        self.commit(other, "other.txt", "x\n", "Task 0009: other")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(wt, "fetch", "-q", "origin")
        git(wt, "merge", "-q", "--no-edit", "origin/main")
        merged = git(wt, "rev-parse", "HEAD")
        git(wt, "push", "-q", "origin", "task/0002-second")
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", merged)
        self.assertEqual(code, 0, out + err)
        # a change of its own after the review still needs one
        changed = self.commit(wt, "feature.txt", "built twice\n", "Task 0002: change it")
        git(wt, "push", "-q", "origin", "task/0002-second")
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", changed, "--supersede")
        self.assertEqual(code, 4, out + err)
        self.assertIn("the head the last review", err)

    def test_heads_with_no_change_of_their_own_never_match(self):
        """Two heads the integration branch already holds have empty diffs: that is no match."""
        from ccp import runs
        tip = git(self.main, "rev-parse", "origin/main")
        root = git(self.main, "rev-list", "--max-parents=0", "origin/main")
        self.assertFalse(runs.same_change(self.q, root, tip))


if __name__ == "__main__":
    unittest.main()
