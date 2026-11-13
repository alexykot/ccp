"""SPEC §15.2, plane.json `verify.provers` with `skips: review`: a declared prover that exits 0 on the fix
round's diff sends the fix straight to verify, its name and exit recorded on the verify run (no command text).
`verify.skip_review`, when set, is tried first; a prover that fails or times out keeps the refusal. Both are
read from the integration branch's plane.json, never from the head under test or the runner's checkout, and
run in a clean checkout of that branch's tip, removed when the judgement ends."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import config
from tests import test_review_gate, test_review_skip
from tests.test_toolkit import ToolkitFixture, git

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

    def plane(self, body: dict, **files: str) -> None:
        """plane.json on the integration branch, where `ccp` reads the skip rules, with `files` (a path with
        `__` for `/`) beside it: pushed to origin/main and merged into the task branch, so the head is not
        behind the tip."""
        other = Path(tempfile.mkdtemp(dir=self._tmp.name))
        git(self.main, "worktree", "add", "-q", "--detach", str(other), "origin/main")
        for rel, text in files.items():
            self.commit(rel.replace("__", "/"), text, other)
        self.commit("docs/delivery/plane.json", json.dumps(body), other)
        git(other, "push", "-q", "origin", "HEAD:main")
        git(self.wt, "fetch", "-q", "origin")
        git(self.wt, "merge", "-q", "--no-edit", "origin/main")

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
                "prover": "comments", "exit_code": 0}
        self.assertEqual(body["review_skip"], want)
        run = json.loads((self.q / "runs/0002-second/verify.json").read_text())
        self.assertEqual(run["review_skip"], want)
        # the records name the prover, never its command: plane.json looks the command up by the name
        self.assertNotIn("PROOF_BIN", (self.q / "runs/0002-second/verify.json").read_text())
        self.assertNotIn("PROOF_BIN", (self.q / "observability" / "events.jsonl").read_text())
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

    def test_a_prover_only_the_head_or_the_checkout_declares_does_not_apply(self):
        self.plane({**ToolkitFixture.PLANE_JSON, "verify": {}})  # the integration branch declares no prover
        self.reviewed()
        # the fix adds a prover in its own diff; the runner's checkout still has the class's prover too
        head = self.fix("docs/delivery/plane.json", json.dumps(
            {**ToolkitFixture.PLANE_JSON, "verify": {"provers": [{"name": "always", "command": "true", "skips": "review"}]}}))
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertNotIn("does not apply", err)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())

    def scripted(self, text: str) -> None:
        """A review prover that runs a script of the repo, on the integration branch with it: `text` decides
        the script's exit, whatever the diff."""
        self.plane({**self.PLANE_JSON, "verify": {"provers": [
            {"name": "scripted", "command": "sh scripts/prove.sh {task_id} {reviewed} {head} {from}",
             "skips": "review"}]}}, **{"scripts__prove.sh": text})

    def test_a_fix_that_edits_the_provers_script_gets_the_integration_branchs_verdict(self):
        self.scripted("exit 1\n")  # the integration branch's script proves nothing
        self.reviewed()
        head = self.fix("scripts/prove.sh", "exit 0\n")  # the task's copy would prove anything
        self.refused(head, "verify.provers", "the prover scripted (verify.provers) exited 1)")  # not 127: it ran

    def test_a_fix_that_breaks_the_provers_script_still_skips(self):
        self.scripted("exit 0\n")
        reviewed = self.reviewed()
        head = self.fix("scripts/prove.sh", "exit 1\n")
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"], {"reviewed": reviewed, "head": head, "fix": "0002-second/fix",
                                               "files": 1, "prover": "scripted", "exit_code": 0})

    def test_a_fix_that_edits_plane_json_still_gets_the_integration_branchs_verdict(self):
        self.reviewed()
        head = self.fix("docs/delivery/plane.json", json.dumps({**ToolkitFixture.PLANE_JSON, "verify": {}}))
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"]["prover"], "comments")

    def worktrees(self) -> str:
        return git(self.runner, "worktree", "list", "--porcelain")

    def test_the_prover_runs_in_a_clean_checkout_of_the_integration_tip_removed_after(self):
        seen = Path(self._tmp.name) / "where"
        self.plane({**self.PLANE_JSON, "verify": {"provers": [
            {"name": "where", "command": f"pwd -P > {seen}; git rev-parse HEAD >> {seen}; "
                                         f"git status --porcelain >> {seen}; exit 1", "skips": "review"}]}})
        tip = git(self.wt, "rev-parse", "origin/main")
        self.reviewed()
        head = self.fix()
        before = self.worktrees()
        self.refused(head, "verify.provers", "the prover where (verify.provers) exited 1")
        where, rev, *dirty = seen.read_text().splitlines()
        self.assertNotIn(Path(where), (self.runner.resolve(), self.wt.resolve()))
        self.assertEqual((rev, dirty), (tip, []))
        self.assertFalse(Path(where).exists())
        self.assertEqual(self.worktrees(), before)

    def test_the_provers_checkout_is_removed_after_an_error(self):
        from ccp import verify
        self.reviewed()
        head = self.fix()
        seen: list[Path] = []

        def boom(_cfg, _cmd, _timeout, cwd=None):
            seen.append(Path(cwd))
            raise RuntimeError("the prover broke")
        before = self.worktrees()
        with mock.patch("ccp.rules.run_command", boom), self.assertRaises(RuntimeError):
            verify.skip_review(config.load(self.runner), self.q, "0002-second", head, "7")
        self.assertTrue(seen)
        self.assertFalse(seen[0].exists())
        self.assertEqual(self.worktrees(), before)

    def test_an_integration_plane_json_that_does_not_load_skips_nothing_and_says_so(self):
        self.plane({**self.PLANE_JSON, "verify": {"provers": [{"name": "x", "command": "true", "skips": "nowhere"}]}})
        self.reviewed()
        head = self.fix()
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("(nothing is skipped: plane.json on origin/main does not load", err)
        self.assertFalse(self.log.exists())

    def test_verify_fetches_the_integration_branch_before_reading_the_provers(self):
        self.plane({**ToolkitFixture.PLANE_JSON, "verify": {}})  # no prover, as the runner last fetched it
        reviewed = self.reviewed()
        # another clone adds the prover to the integration branch and pushes a fix that merges it in; the
        # runner's checkout has fetched neither
        other = Path(self._tmp.name) / "other-clone"
        git(Path(self._tmp.name), "clone", "-q", git(self.main, "remote", "get-url", "origin"), str(other))
        self.commit("docs/delivery/plane.json", json.dumps(self.PLANE_JSON), other)
        git(other, "push", "-q", "origin", "HEAD:main")
        git(other, "checkout", "-q", "-b", "fix", "origin/task/0002-second")
        git(other, "merge", "-q", "--no-edit", "main")
        head = self.commit("tests/test_feature.txt", "check it  # comment fixed\n", other)
        git(other, "push", "-q", "origin", "HEAD:task/0002-second")
        self.run_phase("fix", reviewed, f"PR: #7\nHead: {head}")
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["review_skip"]["reviewed"], body["review_skip"]["prover"]), (reviewed, "comments"))

    def test_a_failed_fetch_skips_nothing_and_says_so(self):
        self.reviewed()
        head = self.fix()
        git(self.main, "remote", "set-url", "origin", str(Path(self._tmp.name) / "no-such-remote"))
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("(nothing is skipped: the fetch of origin/main failed", err)
        self.assertFalse(self.log.exists())

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
