"""SPEC §15.2, plane.json `verify.skip_review`: a fix round whose diff touches only the declared paths, and
that the product's proof command passes (exit 0), goes to verify with no new review. A failing proof, a
file outside the paths, or a diff that cannot be judged keeps the refusal."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from ccp import config
from tests import test_review_gate
from tests.test_toolkit import PLANE, ToolkitFixture, git

PROOF = '#!/bin/sh\necho "$@" >> "$PROOF_LOG"\nsleep "${PROOF_SLEEP:-0}"\nexit "${PROOF_EXIT:-0}"\n'


class SkipReview(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON,
                  "verify": {"skip_review": {"paths": ["tests"], "proof": '"$PROOF_BIN" {task_id} {reviewed} {head} {from}'}}}
    run_phase = test_review_gate.ReviewGate.run_phase
    review = test_review_gate.ReviewGate.review
    verdict = test_review_gate.ReviewGate.verdict

    def setUp(self):
        super().setUp()
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        t = Path(self._tmp.name)
        (t / "proof").write_text(PROOF)
        (t / "proof").chmod(0o755)
        self.log = t / "proof.log"
        os.environ.update(PROOF_BIN=str(t / "proof"), PROOF_LOG=str(self.log))  # the fixture's env patch restores it
        self.ccp("tasks", "claim", "0002")
        self.wt = self.main / ".rt" / "impl-0002"  # the claim made it, on task/0002-second

    def commit(self, rel: str, text: str, wt: Path | None = None) -> str:
        wt = wt or self.wt
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
        git(wt, "add", rel)
        git(wt, "commit", "-q", "-m", f"change {rel}")
        return git(wt, "rev-parse", "HEAD")

    def push(self) -> str:
        git(self.wt, "push", "-q", "-u", "origin", "task/0002-second")
        return git(self.wt, "rev-parse", "HEAD")

    def reviewed(self) -> str:
        self.commit("feature.txt", "built\n")
        self.commit("tests/test_feature.txt", "check it\n")
        head = self.push()
        self.review(head)
        return head

    def fix(self, rel: str = "tests/test_feature.txt", text: str = "check it  # comment fixed\n") -> str:
        reviewed = git(self.wt, "rev-parse", "HEAD")
        self.commit(rel, text)
        head = self.push()
        self.run_phase("fix", reviewed, f"PR: #7\nHead: {head}")
        return head

    def on_main(self, rel: str, text: str) -> None:
        other = self.main / ".rt" / "other"  # another task merges to main meanwhile
        git(self.main, "worktree", "add", "-q", "--detach", str(other), "origin/main")
        self.commit(rel, text, other)
        git(other, "push", "-q", "origin", "HEAD:main")

    def verify(self, head: str, *extra: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head, *extra)

    def refused(self, head: str, why: str) -> str:
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("run `ccp prompt review` first", err)
        self.assertIn(f"(verify.skip_review does not apply: {why}", err)
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())  # nothing opened
        return err

    def test_a_proven_fix_within_the_paths_goes_straight_to_verify(self):
        reviewed = self.reviewed()
        head = self.fix()
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        want = {"reviewed": reviewed, "head": head, "fix": "0002-second/fix", "files": 1}
        self.assertEqual(body["review_skip"], want)
        self.assertNotIn("allow_unreviewed_fix", body)
        run = json.loads((self.q / "runs/0002-second/verify.json").read_text())
        self.assertEqual(run["review_skip"], want)
        task, got_reviewed, got_head, start = self.log.read_text().split()
        self.assertEqual((task, got_reviewed, got_head), ("0002-second", reviewed, head))
        self.assertEqual(git(self.main, "diff", "--name-only", start, head), "tests/test_feature.txt")
        code, _, out, err = self.verdict(head)
        self.assertEqual(code, 0, out + err)  # the approve stands on the proven skip

    def test_a_proof_that_fails_keeps_the_review(self):
        self.reviewed()
        head = self.fix()
        os.environ["PROOF_EXIT"] = "1"
        self.refused(head, "the proof (verify.skip_review.proof) exited 1")

    def test_a_proof_that_times_out_proves_nothing(self):
        self.reviewed()
        head = self.fix()
        os.environ["PROOF_SLEEP"] = "5"
        with mock.patch("ccp.verify.PROOF_TIMEOUT", 1):
            self.refused(head, "the proof (verify.skip_review.proof) timed out after 1s")

    def test_a_file_outside_the_paths_keeps_the_review_and_runs_no_proof(self):
        self.reviewed()
        head = self.fix("feature.txt", "built better\n")
        self.refused(head, "the fix touches 1 file(s) outside verify.skip_review.paths (feature.txt)")
        self.assertFalse(self.log.exists())

    def test_a_rename_into_the_paths_counts_the_path_it_left(self):
        self.reviewed()
        git(self.wt, "mv", "feature.txt", "tests/feature.txt")
        git(self.wt, "commit", "-q", "-m", "move it")
        head = self.push()
        self.run_phase("fix", head, f"PR: #7\nHead: {head}")
        self.refused(head, "the fix touches 1 file(s) outside verify.skip_review.paths (feature.txt)")

    def test_a_rename_within_the_paths_counts_both_of_its_paths(self):
        self.reviewed()
        git(self.wt, "mv", "tests/test_feature.txt", "tests/test_renamed.txt")
        git(self.wt, "commit", "-q", "-m", "rename it")
        head = self.push()
        self.run_phase("fix", head, f"PR: #7\nHead: {head}")
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"]["files"], 2)

    def test_a_fix_that_changes_no_file_is_reviewed(self):
        reviewed = self.reviewed()
        self.run_phase("fix", reviewed, f"PR: #7\nHead: {reviewed}")
        self.refused(reviewed, "the fix changes no file of its own")

    def test_commits_with_no_fix_round_since_the_review_are_reviewed(self):
        self.reviewed()
        self.commit("tests/test_feature.txt", "check it  # comment fixed\n")
        head = self.push()
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("the head the last review 0002-second/review judged", err)
        self.assertNotIn("verify.skip_review", err)
        self.assertFalse(self.log.exists())

    def test_an_integration_merge_after_the_review_is_not_the_fixs(self):
        reviewed = self.reviewed()
        self.on_main("other.txt", "x\n")
        git(self.wt, "fetch", "-q", "origin")
        git(self.wt, "merge", "-q", "--no-edit", "origin/main")
        head = self.fix()
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["review_skip"]["reviewed"], body["review_skip"]["files"]), (reviewed, 1))

    def test_a_reviewed_change_that_conflicts_with_the_new_base_is_reviewed(self):
        self.reviewed()
        self.on_main("feature.txt", "built elsewhere\n")
        git(self.wt, "fetch", "-q", "origin")
        r = subprocess.run(["git", "-C", str(self.wt), "merge", "-q", "--no-edit", "origin/main"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)  # the conflict, resolved by hand
        (self.wt / "feature.txt").write_text("built\n")
        git(self.wt, "add", "feature.txt")
        git(self.wt, "commit", "-q", "--no-edit")
        head = self.fix()
        self.refused(head, "the reviewed head does not merge cleanly onto the head's base on origin/main")

    def test_a_git_that_cannot_write_the_merge_tree_is_named(self):
        self.reviewed()
        head = self.fix()
        from ccp import queue
        real = queue.git

        def old_git(cwd, *args, **kw):  # a git before 2.38, which lacks `merge-tree --write-tree`
            if args[:2] == ("merge-tree", "--write-tree"):
                return subprocess.CompletedProcess(["git", *args], 129, "", "usage: git merge-tree")
            return real(cwd, *args, **kw)
        with mock.patch("ccp.queue.git", side_effect=old_git):
            self.refused(head, "`git merge-tree --write-tree` failed (exit 129); it needs git 2.38 or later")
        self.assertFalse(self.log.exists())

    def test_a_head_that_cannot_be_fetched_is_reviewed(self):
        self.reviewed()
        self.fix()
        self.refused("b" * 40, f"{'b' * 12} could not be fetched")

    def test_verify_record_holds_an_approve_to_the_proven_head(self):
        self.reviewed()
        head = self.fix()
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        later = self.fix(text="check it  # comment fixed again\n")  # pushed while the verifier ran
        code, _, out, err = self.verdict(later)
        self.assertEqual(code, 1, out + err)
        self.assertIn("or verify.skip_review proved this head's fix", err)


    def test_an_override_is_taken_as_given_and_runs_no_proof(self):
        self.reviewed()
        head = self.fix()  # a fix the proof would pass
        code, body, out, err = self.verify(head, "--allow-unreviewed-fix", "--reason", "lead: verify it now")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["allow_unreviewed_fix"]["reason"], "lead: verify it now")
        self.assertNotIn("review_skip", body)
        run = json.loads((self.q / "runs/0002-second/verify.json").read_text())
        self.assertEqual((run["allow_unreviewed_fix"]["reason"], "review_skip" in run), ("lead: verify it now", False))
        notes = [json.loads(x) for x in (self.q / "health/notes.jsonl").read_text().splitlines()]
        self.assertEqual(notes[-1]["source"], "allow-unreviewed-fix")
        self.assertFalse(self.log.exists())

    def test_an_abandoned_fix_round_is_not_the_fix(self):
        self.reviewed()
        head = self.fix()
        code, body, out, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", head)
        self.assertEqual(code, 0, out + err)
        f = self.q / "runs" / f"{body['run_id']}.json"
        f.write_text(json.dumps({**json.loads(f.read_text()), "abandoned_at": "2026-10-22T11:00:00Z"}))
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["review_skip"]["fix"], "0002-second/fix")

    def test_several_fix_rounds_since_the_review_are_judged_as_one_diff(self):
        self.reviewed()
        self.fix("feature.txt", "built better\n")
        head = self.fix()  # the last round alone is within the paths
        self.refused(head, "the fix touches 1 file(s) outside verify.skip_review.paths (feature.txt)")
        self.assertFalse(self.log.exists())

    def test_a_review_that_did_not_report_done_is_not_the_last_review(self):
        reviewed = self.reviewed()
        head = self.fix()
        self.run_phase("review", head, "Severity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0")
        f = self.q / "runs/0002-second/review-2.json"
        f.write_text(json.dumps({**json.loads(f.read_text()), "outcome": "blocked"}))
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["review_skip"]["reviewed"], body["review_skip"]["head"]), (reviewed, head))

    def test_a_review_with_no_head_on_record_gives_no_skip(self):
        self.reviewed()
        head = self.fix()
        f = self.q / "runs/0002-second/review.json"
        f.write_text(json.dumps({k: v for k, v in json.loads(f.read_text()).items() if k != "head"}))
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("run `ccp prompt review` first", err)
        self.assertNotIn("verify.skip_review", err)
        self.assertFalse(self.log.exists())


class SkipReviewSetting(ToolkitFixture, unittest.TestCase):
    """The setting is off (null) by default; set, it names paths relative to the root and a proof."""

    def plane(self, value) -> None:
        self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "verify": {"skip_review": value}}))

    def test_the_setting_is_validated(self):
        self.assertIsNone(config.load(self.main).verify["skip_review"])
        for bad in ("tests", [], {"paths": ["tests"]}, {"proof": "true"}, {"paths": ["tests"], "proof": "true", "x": 1},
                    {"paths": [], "proof": "true"}, {"paths": "tests", "proof": "true"},
                    {"paths": ["tests"], "proof": ""}, {"paths": ["tests"], "proof": 3}):
            with self.subTest(bad=bad):
                self.plane(bad)
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.main)
                self.assertIn("verify.skip_review", str(cm.exception))
        for path in ("", " ", "/tests", "../tests", "tests/../..", ":!tests", ".", "./", "./.", "tests/..", 3):
            with self.subTest(path=path):
                self.plane({"paths": ["docs", path], "proof": "true"})
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.main)
                self.assertIn("verify.skip_review.paths", str(cm.exception))
        for every in (".", "./", "*", "**", "./*"):  # an entry that matches every path, named
            with self.subTest(every=every):
                self.plane({"paths": ["docs", every], "proof": "true"})
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.main)
                self.assertIn(f"verify.skip_review.paths: {every!r} matches every path", str(cm.exception))
        self.plane({"paths": ["tests", "./docs/notes", "*.md"], "proof": "scripts/prove.sh {from} {head}"})
        self.assertEqual(config.load(self.main).verify["skip_review"],
                         {"paths": ["tests", "./docs/notes", "*.md"], "proof": "scripts/prove.sh {from} {head}"})
        self.plane(None)
        self.assertIsNone(config.load(self.main).verify["skip_review"])

    def test_the_schema_has_the_setting(self):
        schema = json.loads((PLANE / "contracts/plane_config.schema.json").read_text())
        verify = schema["properties"]["verify"]["properties"]
        self.assertEqual(set(verify), set(config.VERIFY_DEFAULTS))
        self.assertEqual(set(verify["skip_review"]["properties"]), config.SKIP_REVIEW_KEYS)
        self.assertEqual(set(verify["skip_review"]["required"]), config.SKIP_REVIEW_KEYS)


if __name__ == "__main__":
    unittest.main()
