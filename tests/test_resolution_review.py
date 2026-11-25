"""A resolution review (SPEC §13.2): after a merge round whose merge conflicted, `ccp prompt review --mode
resolution` reviews only the resolution, its report says how far it reaches and which checks it can affect
(§13.4), the verify that follows reruns those checks (§15.6 rule 3) and `ccp verify record` holds an approve to
it. The history is real git: a task branch, an integration tip that conflicts with it, and a hand-resolved
merge commit."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from ccp import cli, health, report, runs, verify
from tests.review_flow import ReviewFlow
from tests.helpers import GIT_ENV, PLANE_ROOT, run_clock
from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture

SECOND_CHECK = """- id: `cmd-02`
  story: As an operator, I run it again.
  steps:
    1. run
  expect: exit 0

## Implementation notes"""


def sh(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env={**os.environ, **GIT_ENV})


def parse_resolution(line: str) -> tuple[dict, list[str]]:
    """A done resolution review's report whose `Resolution:` line is `line`, parsed (§13.4)."""
    return report.parse("review", f"Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n{line}\n"
                                  "Affected checks: none\n## Spec beyond intent\nnone\n## Friction\nnone\n",
                        mode="resolution", checks=["cmd-01"])


class BeyondReason(unittest.TestCase):
    """`Resolution: beyond` says why: a word after its punctuation and markup (§13.4)."""

    def test_a_bare_beyond_is_refused(self):
        for line in ("Resolution: beyond", "Resolution: beyond.", "Resolution: beyond —", "**Resolution:** beyond `_`"):
            got, errs = parse_resolution(line)
            self.assertNotIn("resolution", got, line)
            self.assertTrue(any("`Resolution: beyond` needs its reason" in e for e in errs), (line, errs))

    def test_beyond_with_a_reason_is_accepted(self):
        got, errs = parse_resolution("Resolution: beyond the merge rewrote a helper")
        self.assertEqual((errs, got["resolution"]), ([], "beyond"))
        got, errs = parse_resolution("Resolution: contained")  # contained needs none
        self.assertEqual((errs, got["resolution"]), ([], "contained"))


class Resolution(ReviewFlow, ToolkitFixture, unittest.TestCase):

    def setUp(self):
        super().setUp()
        run_clock(self)
        self.ccp("tasks", "claim", "0002")
        task = self.runner / "docs/delivery/tasks/0002-second.md"
        task.write_text(task.read_text().replace("## Implementation notes", SECOND_CHECK, 1))

    def start(self) -> str:
        """The task branch's head H1, forked from the integration branch before its tip moves."""
        m = self.main
        self.write("shared.txt", "one\ntwo\nthree\n")
        self.write("other.txt", "alpha\n")
        git(m, "add", "shared.txt", "other.txt")
        git(m, "commit", "-q", "-m", "base")
        git(m, "push", "-q", "origin", "main")
        git(m, "checkout", "-q", "-b", "feat")
        self.write("shared.txt", "one\ntask change\nthree\n")
        git(m, "commit", "-q", "-am", "task change")
        h1 = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return h1

    def move_tip(self, conflict: bool = True) -> str:
        """The integration tip moves; the task branch merges it, as H2: with `conflict`, both changed one line
        and the merge commit holds a hand resolution, else the merge was clean."""
        m = self.main
        if conflict:
            self.write("shared.txt", "one\ntip change\nthree\n")
        else:
            self.write("other.txt", "alpha\nbeta\n")
        git(m, "commit", "-q", "-am", "tip change")
        git(m, "push", "-q", "origin", "main")
        git(m, "checkout", "-q", "feat")
        merged = sh(m, "merge", "-q", "--no-edit", "origin/main")
        self.assertEqual(merged.returncode, 1 if conflict else 0, merged.stdout + merged.stderr)
        if conflict:
            self.write("shared.txt", "one\ntask change and tip change\nthree\n")
            git(m, "add", "shared.txt")
            git(m, "commit", "-q", "--no-edit")
        h2 = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return h2

    def history(self, conflict: bool = True) -> tuple[str, str]:
        return self.start(), self.move_tip(conflict)

    def to_merge_round(self, conflict: bool = True, approve: bool = False) -> tuple[str, str]:
        h1 = self.start()
        self.review(h1)  # reviewed while the tip is still behind it
        if approve:
            self.verify_round(h1, "approve")
        h2 = self.move_tip(conflict)
        self.run_phase("merge", h1, f"PR: #7\nHead: {h2}")
        return h1, h2

    def resolution(self, head: str, *extra: str):
        return self.ccp("prompt", "review", "0002", "--pr", "7", "--head", head, "--mode", "resolution", *extra)

    def open_resolution(self, head: str) -> dict:
        code, body, out, err = self.resolution(head)
        self.assertEqual(code, 0, out + err)
        return body

    def resolution_report(self, run_id: str, lines: str):
        return self.report(run_id, "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n"
                                   f"{lines}\n## Spec beyond intent\nnone\n## Friction\nnone\n")

    def contained(self, head: str, affected: str = "cmd-01") -> str:
        run_id = self.open_resolution(head)["run_id"]
        code, _, out, err = self.resolution_report(run_id, f"Resolution: contained\nAffected checks: {affected}")
        self.assertEqual(code, 0, out + err)
        return run_id

    def verify_head(self, head: str, *extra: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head,
                        "--note", "conflicted merge, resolution review", *extra)

    def record(self, head: str, checks: list[dict], verdict: str = "approve"):
        rec = json.loads((PLANE_ROOT / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head, verdict=verdict, checks=checks)
        rec.pop("checked_at", None)
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        return self.ccp("verify", "record", str(f))

    def ran(self, check_id: str) -> dict:
        return {"dod_check_id": check_id, "pass": True, "evidence": "ran it at the head", "produced_by": "verifier"}

    def rests(self, check_id: str, old: str) -> dict:
        return {"dod_check_id": check_id, "ran": False, "pass": None, "rests_on": f"approve at {old}",
                "evidence": "carried", "produced_by": "verifier"}

    # ------------------------------------------------------------------ opening it

    def test_a_conflicted_merge_opens_a_resolution_review(self):
        _, h2 = self.to_merge_round()
        code, body, out, err = self.resolution(h2)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["mode"], "resolution")
        run = json.loads((self.q / "runs/0002-second/review-2.json").read_text())
        self.assertEqual((run["phase"], run["mode"], run["head"]), ("review", "resolution", h2))
        text = Path(body["prompt_path"]).read_text()
        self.assertIn(f"git show --remerge-diff {h2}", text)
        self.assertNotIn(" pr diff ", text)  # not the full diff

    def test_the_report_contract_lists_the_two_lines_in_this_mode_only(self):
        from ccp import config, prompt
        cfg = config.load(self.runner)
        plain = prompt.report_lines(cfg, "review", runner="r")
        self.assertNotIn("Affected checks", plain)
        self.assertIn("Resolution:", prompt.report_lines(cfg, "review", "resolution", runner="r"))
        self.assertIn("Affected checks:", prompt.report_lines(cfg, "review", "resolution", runner="r"))
        self.assertEqual(prompt.report_lines(cfg, "verify", "resolution", runner="r"),
                         prompt.report_lines(cfg, "verify", runner="r"))

    def test_a_full_review_renders_as_before(self):
        _, h2 = self.to_merge_round()
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", h2)
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        from ccp import config, prompt
        self.assertIn(f"`{prompt.ccp_command(config.load(self.runner))} pr diff 7`", text)
        self.assertNotIn("remerge-diff", text)
        self.assertNotIn("mode", json.loads((self.q / "runs/0002-second/review-2.json").read_text()))

    def test_a_clean_merge_needs_no_resolution_review(self):
        _, h2 = self.to_merge_round(conflict=False)
        code, _, out, err = self.resolution(h2)
        self.assertEqual(code, 2, out + err)
        self.assertIn("no conflict was resolved: a clean merge needs no resolution review", err)
        self.assertIn("empty remerge diff", err)
        self.assertFalse((self.q / "runs/0002-second/review-2.json").exists())  # nothing opened

    def test_a_resolution_review_never_stands_in_for_the_first_review(self):
        h1, h2 = self.history()
        self.run_phase("merge", h1, f"PR: #7\nHead: {h2}")
        code, _, out, err = self.resolution(h2)
        self.assertEqual(code, 2, out + err)
        self.assertIn("no review that reported done", err)
        self.assertFalse((self.q / "runs/0002-second/review.json").exists())  # nothing opened

    def test_it_covers_merge_rounds_only(self):
        h1 = self.start()
        self.review(h1)
        h2 = self.move_tip()
        self.run_phase("fix", h1, f"PR: #7\nHead: {h1}")
        self.run_phase("merge", h1, f"PR: #7\nHead: {h2}")
        code, _, out, err = self.resolution(h2)
        self.assertEqual(code, 2, out + err)
        self.assertIn("fix round 0002-second/fix is newer than the last review 0002-second/review", err)
        self.assertIn("merge rounds only", err)
        self.assertFalse((self.q / "runs/0002-second/review-2.json").exists())

    def test_the_head_must_be_a_merge_commit(self):
        h1, _ = self.to_merge_round()
        code, _, out, err = self.resolution(h1)
        self.assertEqual(code, 2, out + err)
        self.assertIn("is not a merge commit", err)
        self.assertFalse((self.q / "runs/0002-second/review-2.json").exists())

    def test_an_unreadable_head_is_refused(self):
        self.to_merge_round()
        code, _, out, err = self.resolution("c" * 40)
        self.assertEqual(code, 2, out + err)
        self.assertIn("could not be read", err)

    def test_the_mode_belongs_to_review(self):
        _, h2 = self.to_merge_round()
        for phase in ("verify", "fix"):
            code, _, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", h2, "--mode", "resolution")
            self.assertEqual(code, 2, out + err)
            self.assertIn("--mode resolution is for `ccp prompt review` only", err)
        with self.assertRaises(SystemExit) as cm, mock.patch("sys.stderr"):  # argparse: not a mode
            self.ccp("prompt", "review", "0002", "--pr", "7", "--head", h2, "--mode", "other")
        self.assertEqual(cm.exception.code, 2)
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())

    # ------------------------------------------------------------------ its report

    def test_the_report_says_how_far_it_reaches_and_which_checks(self):
        _, h2 = self.to_merge_round()
        run_id = self.open_resolution(h2)["run_id"]
        path = runs.path(self.q, run_id)
        for lines, want in (("Resolution: contained", "Affected checks"),
                            ("Resolution: contained\nAffected checks: cmd-01, cmd-09", "cmd-09"),
                            ("Affected checks: cmd-01", "Resolution")):
            code, _, out, err = self.resolution_report(run_id, lines)
            self.assertEqual(code, 1, out + err)
            self.assertIn("report refused, nothing written", err)
            self.assertIn(want, err)
            self.assertIsNone(json.loads(path.read_text())["outcome"])
            self.assertFalse(runs.report_path(self.q, run_id).exists())
        code, _, out, err = self.resolution_report(run_id, "Resolution: contained\nAffected checks: cmd-01")
        self.assertEqual(code, 0, out + err)
        rec = json.loads(path.read_text())
        self.assertEqual((rec["resolution"], rec["affected_checks"], rec["outcome"]), ("contained", ["cmd-01"], "done"))

    def test_none_and_beyond_are_stored(self):
        _, h2 = self.to_merge_round()
        run_id = self.open_resolution(h2)["run_id"]
        code, body, out, err = self.resolution_report(
            run_id, "Resolution: beyond the fix renames a function the task adds\nAffected checks: none")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["resolution"], body["affected_checks"]), ("beyond", []))
        rec = json.loads(runs.path(self.q, run_id).read_text())
        self.assertEqual((rec["resolution"], rec["affected_checks"]), ("beyond", []))

    def test_the_lines_are_read_exactly(self):
        checks = ["cmd-01", "cmd-02"]

        def parse(lines: str, **kw):
            return report.parse("review", f"Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n{lines}\n"
                                          "## Spec beyond intent\nnone\n## Friction\nnone\n", mode="resolution",
                                checks=checks, **kw)
        got, errs = parse("**Resolution:** contained\n- Affected checks: `cmd-02`, `cmd-01`, cmd-02")
        self.assertEqual((errs, got["resolution"], got["affected_checks"]), ([], "contained", ["cmd-02", "cmd-01"]))
        _, errs = parse("Resolution: contained|beyond <why>\nAffected checks: none")
        self.assertTrue(any("`Resolution:`" in e and "exactly one" in e for e in errs), errs)
        _, errs = parse("Resolution: probably fine\nAffected checks: none")
        self.assertTrue(any("probably fine" in e for e in errs), errs)
        _, errs = parse("Resolution: contained\nResolution: beyond x\nAffected checks: none")
        self.assertTrue(any("stated on 2 lines" in e for e in errs), errs)
        _, errs = parse("Resolution: contained\nAffected checks: none, cmd-01")
        self.assertTrue(any("`none`" in e and "not a dod_check" in e for e in errs), errs)
        _, errs = parse("Resolution: contained\nAffected checks:")
        self.assertTrue(any("is empty" in e for e in errs), errs)
        # only a done resolution review is held to them
        _, errs = report.parse("review", "Outcome: blocked\n## Friction\nnone\n", mode="resolution", checks=checks)
        self.assertEqual(errs, [])
        _, errs = report.parse("review", "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n"
                                         "## Spec beyond intent\nnone\n## Friction\nnone\n", checks=checks)
        self.assertEqual(errs, [])

    def test_a_corrected_report_replaces_the_resolution(self):
        _, h2 = self.to_merge_round()
        run_id = self.contained(h2)
        code, _, out, err = self.resolution_report(run_id, "Resolution: beyond it reaches the task's logic\n"
                                                           "Affected checks: cmd-02")
        self.assertEqual(code, 0, out + err)
        rec = json.loads(runs.path(self.q, run_id).read_text())
        self.assertEqual((rec["resolution"], rec["affected_checks"]), ("beyond", ["cmd-02"]))

    def test_a_correction_with_no_resolution_line_drops_the_earlier_one(self):
        _, h2 = self.to_merge_round()
        run_id = self.contained(h2)
        code, _, out, err = self.report(run_id, "Outcome: blocked\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        rec = json.loads(runs.path(self.q, run_id).read_text())
        self.assertEqual((rec["outcome"], "resolution" in rec, "affected_checks" in rec), ("blocked", False, False))

    # ------------------------------------------------------------------ verify after it

    def test_a_contained_resolution_lets_verify_open_and_names_what_to_rerun(self):
        h1, h2 = self.to_merge_round(approve=True)
        self.contained(h2)
        code, body, out, err = self.verify_head(h2)
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn("cmd-01", text.split("This head follows a resolution review", 1)[1].split("Rerun ", 1)[1].split("\n", 1)[0])
        self.assertIn(f'rests_on: "approve at {h1}"', text)

    def test_with_no_earlier_approve_every_check_runs(self):
        _, h2 = self.to_merge_round()
        resolution_run = self.contained(h2, "none")
        code, body, out, err = self.verify_head(h2)
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn(resolution_run, text)  # the section is there ...
        self.assertNotIn('rests_on: "approve at', text)  # ... and has no approve to rest the other checks on

    def test_a_beyond_resolution_goes_back_to_a_full_review(self):
        _, h2 = self.to_merge_round()
        run_id = self.open_resolution(h2)["run_id"]
        code, _, out, err = self.resolution_report(
            run_id, "Resolution: beyond the fix renames a function the task adds\nAffected checks: cmd-01")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.verify_head(h2)
        self.assertEqual(code, 4, out + err)
        self.assertIn(f"{run_id}: the resolution review judged it beyond the conflict hunks: run a full "
                      "`ccp prompt review`", err)
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())  # nothing opened
        self.review(h2)  # a full review of the same head settles it
        code, _, out, err = self.verify_head(h2)
        self.assertEqual(code, 0, out + err)

    def test_after_a_beyond_resolution_a_resolution_review_is_refused(self):
        _, h2 = self.to_merge_round()
        beyond = self.open_resolution(h2)["run_id"]
        self.resolution_report(beyond, "Resolution: beyond the fix renames a function the task adds\n"
                                       "Affected checks: cmd-01")
        m = self.main  # the tip moves again and the branch merges it, with another conflict, as H3
        self.write("shared.txt", "one\ntip change again\nthree\n")
        git(m, "commit", "-q", "-am", "tip change again")
        git(m, "push", "-q", "origin", "main")
        git(m, "checkout", "-q", "feat")
        self.assertEqual(sh(m, "merge", "-q", "--no-edit", "origin/main").returncode, 1)
        self.write("shared.txt", "one\ntask change and tip change again\nthree\n")
        git(m, "add", "shared.txt")
        git(m, "commit", "-q", "--no-edit")
        h3 = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        self.run_phase("merge", h2, f"PR: #7\nHead: {h3}")
        code, _, out, err = self.resolution(h3)
        self.assertEqual(code, 2, out + err)
        self.assertIn(f"{beyond}: the resolution review judged it beyond the conflict hunks: run a full "
                      "`ccp prompt review`", err)
        self.assertFalse((self.q / "runs/0002-second/review-3.json").exists())  # nothing opened

    def test_a_beyond_resolution_is_refused_though_the_change_is_the_same(self):
        h1, h2 = self.to_merge_round()
        run_id = self.open_resolution(h2)["run_id"]
        self.resolution_report(run_id, "Resolution: beyond it does\nAffected checks: none")
        with mock.patch("ccp.runs.same_change", return_value=True):
            self.assertIn("beyond the conflict hunks", runs.unreviewed_fix(self.q, "0002-second", h2) or "")

    def test_without_a_resolution_review_the_conflicted_merge_needs_a_full_one(self):
        _, h2 = self.to_merge_round()
        with mock.patch("ccp.runs.same_change", return_value=False):
            code, _, out, err = self.verify_head(h2)
        self.assertEqual(code, 4, out + err)
        self.assertIn("merge round 0002-second/merge is newer than the last review", err)

    def test_a_head_the_resolution_review_did_not_judge_is_refused(self):
        h1, h2 = self.to_merge_round()
        self.contained(h2)
        with mock.patch("ccp.runs.same_change", return_value=False):
            code, _, out, err = self.verify_head(h1)
        self.assertEqual(code, 4, out + err)
        self.assertIn("the head the last review 0002-second/review-2 judged", err)

    # ------------------------------------------------------------------ recording the verdict

    def test_an_approve_must_rerun_every_affected_check(self):
        h1, h2 = self.to_merge_round(approve=True)
        self.contained(h2)
        code, body, out, err = self.verify_head(h2)
        self.assertEqual(code, 0, out + err)
        path = self.q / "verification/0002-second.json"
        before = path.read_text()
        for checks in ([self.rests("cmd-01", h1), self.rests("cmd-02", h1)],  # recorded `ran: false`
                       [self.rests("cmd-02", h1)]):                          # missing from the record
            code, _, out, err = self.record(h2, checks)
            self.assertEqual(code, 1, out + err)
            self.assertIn("refused, nothing written", err)
            self.assertIn("cmd-01", err)
            self.assertEqual(path.read_text(), before)
        code, _, out, err = self.record(h2, [self.ran("cmd-01"), self.rests("cmd-02", h1)])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(path.read_text())["head_sha"], h2)

    def test_a_reject_is_never_held_back(self):
        h1, h2 = self.to_merge_round(approve=True)
        self.contained(h2)
        self.verify_head(h2)
        failed = {**self.ran("cmd-01"), "pass": False}
        code, _, out, err = self.record(h2, [self.rests("cmd-01", h1)], verdict="reject")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.record(h2, [failed], verdict="reject")
        self.assertEqual(code, 0, out + err)

    def test_an_empty_affected_list_holds_nothing_back(self):
        h1, h2 = self.to_merge_round(approve=True)
        self.contained(h2, "none")
        self.verify_head(h2)
        code, _, out, err = self.record(h2, [self.rests("cmd-01", h1), self.rests("cmd-02", h1)])
        self.assertEqual(code, 0, out + err)

    def test_the_hold_applies_to_the_head_the_review_judged(self):
        h1, h2 = self.to_merge_round(approve=True)
        self.contained(h2)
        rec = {"task_id": "0002-second", "verdict": "approve", "checks": [self.rests("cmd-01", h1)]}
        self.assertEqual(verify.resolution_errors(self.q, {**rec, "head_sha": h1}), [])  # another head
        self.assertEqual(verify.resolution_errors(self.q, {**rec, "head_sha": h2[:12]}) != [], True)  # a short sha
        self.assertEqual(verify.resolution_errors(self.q, {**rec, "head_sha": h2, "verdict": "reject"}), [])
        self.assertEqual(verify.resolution_errors(self.q, {**rec, "head_sha": h2, "task_id": "pr-7"}), [])

    # ------------------------------------------------------------------ the phases are listed once

    def test_the_round_phases_are_listed_once(self):
        self.assertIs(health.ROUND_KINDS, runs.PHASES)
        sub = next(a for a in cli.build_parser()._actions if getattr(a, "choices", None) and "prompt" in a.choices)
        action = next(a for a in sub.choices["prompt"]._actions if a.dest == "phase")
        self.assertEqual(tuple(action.choices), (*runs.PHASES, "env", "render"))
        out = subprocess.run(["git", "grep", "-n", "-e", '"implement", "fix", "merge", "ruling", "review", "verify"',
                              "-e", '"implement", "review", "fix", "merge", "ruling", "verify"', "--", "ccp"],
                             cwd=PLANE_ROOT, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual([x.split(":")[0] for x in out], ["ccp/runs.py"])


if __name__ == "__main__":
    unittest.main()
