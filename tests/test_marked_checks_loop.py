"""A check only the operator's machine can run, in the runner's loop (SPEC §10.2, §13.2, §14.4; ADR-0045 D2): the
runner runs it as a recorded suite run in a checkout of the head, the run records that head, the implement and
verify prompts list it as not the worker's, and `ccp prompt verify` opens nothing while it has no passed run at the
head, unless it rests on an earlier approve or a ruling waives it. The history is real git: a task branch, an
integration tip that moves, and a merge of it."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from ccp import prompt
from tests.review_flow import ReviewFlow
from tests.suite_fixture import ccp_proc
from tests.toolkit_fixture import ToolkitFixture, git
from tests.helpers import MARKED_CHECK_ID as CHECK, MARKED_BLOCK as MARKED, MARKED_TASK_ID as TASK, as_lead


def started(head: str, lane: str = CHECK, task: str = TASK, state: str = "passed", sid: str = "st-1") -> dict:
    """A suite run as `suite.fold` gives it: its started row's fields and its end's state."""
    return {"suite_id": sid, "lane": lane, "task_id": task, "head": head, "state": state}


class CheckRun(unittest.TestCase):
    """`prompt.check_run` on plain values: only a passed run of the check's lane, bound to the task, at the head."""

    H, OTHER = "1" * 40, "2" * 40

    def test_a_passed_run_at_the_head_is_found(self):
        self.assertEqual(prompt.check_run([started(self.H)], CHECK, TASK, self.H), ("st-1", ""))
        self.assertEqual(prompt.check_run([started(self.H)], CHECK, TASK, self.H[:12])[0], "st-1")  # a short sha

    def test_the_latest_passed_run_at_the_head_wins(self):
        runs = [started(self.H, sid="st-1"), started(self.H, state="failed", sid="st-2"), started(self.H, sid="st-3")]
        self.assertEqual(prompt.check_run(runs, CHECK, TASK, self.H)[0], "st-3")

    def test_none_is_found_otherwise(self):
        for runs in ([], [started(self.H, state="failed")], [started(self.H, state="interrupted")],
                     [started(self.H, state="open")], [started(self.OTHER)], [started("")],
                     [started(self.H, lane="gate")], [started(self.H, task="0001-first")]):
            sid, why = prompt.check_run(runs, CHECK, TASK, self.H)
            self.assertIsNone(sid, runs)
            self.assertTrue(why, runs)


class CarriedBy(unittest.TestCase):
    """`prompt.carried_by` on plain values (§15.6 rule 3): an approve to rest on, then the resolution review's
    `Affected checks` when one judged the head, else the PR's own change unchanged."""

    def test_no_approve_carries_nothing(self):
        self.assertFalse(prompt.carried_by(CHECK, "", True, None))
        self.assertFalse(prompt.carried_by(CHECK, "", False, []))

    def test_an_unchanged_change_carries(self):
        self.assertTrue(prompt.carried_by(CHECK, "a" * 40, True, None))
        self.assertFalse(prompt.carried_by(CHECK, "a" * 40, False, None))

    def test_a_resolution_review_decides_by_its_affected_checks(self):
        self.assertTrue(prompt.carried_by(CHECK, "a" * 40, False, ["cmd-01"]))
        self.assertFalse(prompt.carried_by(CHECK, "a" * 40, True, [CHECK]))


class MarkedLoop(ReviewFlow, ToolkitFixture, unittest.TestCase):

    def setUp(self):
        super().setUp()
        # runs open a minute apart: `opened_at` has one-second resolution, and the gates order by it
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")
        self.mark()
        self.checkouts = 0

    def mark(self) -> None:
        """The claimed task gets the check `CHECK`, marked `runs_on: operator-machine`."""
        task = self.runner / "docs/delivery/tasks/0002-second.md"
        task.write_text(task.read_text().replace("## Implementation notes", MARKED, 1))

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

    def another(self) -> str:
        """A second commit on the task branch, after H1."""
        m = self.main
        git(m, "checkout", "-q", "feat")
        self.write("feature.txt", "more\n")
        git(m, "add", "feature.txt")
        git(m, "commit", "-q", "-m", "more")
        head = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return head

    def move_tip(self, conflict: bool = False) -> str:
        """The integration tip moves and the task branch merges it, as H2: with `conflict`, both changed one line
        and the merge commit holds a hand resolution, else the merge was clean."""
        m = self.main
        if conflict:
            self.write("shared.txt", "one\ntip change\nthree\n")
        else:
            self.write("other.txt", "alpha\nbeta\n")
        git(m, "commit", "-q", "-am", "tip change")
        git(m, "push", "-q", "origin", "main")
        git(m, "checkout", "-q", "feat")
        merged = subprocess.run(["git", "-C", str(m), "merge", "-q", "--no-edit", "origin/main"], capture_output=True,
                                text=True)
        self.assertEqual(merged.returncode, 1 if conflict else 0, merged.stdout + merged.stderr)
        if conflict:
            self.write("shared.txt", "one\ntask change and tip change\nthree\n")
            git(m, "add", "shared.txt")
            git(m, "commit", "-q", "--no-edit")
        h2 = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return h2

    def checkout(self, head: str) -> Path:
        """A clean checkout detached at `head`, as `ccp wt create --kind mac` makes one."""
        self.checkouts += 1
        wt = Path(self._tmp.name) / f"mac-{self.checkouts}"
        git(self.main, "worktree", "add", "-q", "--detach", str(wt), head)
        return wt

    def run_check(self, head: str, code: int = 0, wt: Path | None = None) -> str:
        """The runner's run of `CHECK` in a checkout of `head`: `ccp suite run --lane <check> --task <task> --
        <command>`, exiting `code`. Its suite id."""
        r = ccp_proc(wt or self.checkout(head), "suite", "run", "--lane", CHECK, "--task", TASK, "--",
                     "sh", "-c", f"exit {code}")
        self.assertEqual(r.returncode, code, r.stderr)
        return self.suite_rows()[-1]["suite_id"]

    def suite_rows(self) -> list[dict]:
        p = self.q / "runs" / "_suites.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines() if '"started"' in x] if p.is_file() else []

    def verify(self, head: str, *extra: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head, *extra)

    def assert_refused(self, got: tuple, *names: str) -> None:
        code, _, out, err = got
        self.assertEqual(code, 1, out + err)
        for name in (CHECK, *names):
            self.assertIn(name, err)
        self.assertFalse(any(p.name.startswith("verify") for p in (self.q / "runs" / TASK).glob("*.json")),
                         "nothing opened")

    def approved(self, conflict: bool = False) -> tuple[str, str]:
        """H1 reviewed, its check run and approved; then the tip moves and a merge round merges it, as H2."""
        h1 = self.start()
        self.review(h1)
        self.run_check(h1)
        self.verify_round(h1, "approve")
        h2 = self.move_tip(conflict)
        self.run_phase("merge", h1, f"PR: #7\nHead: {h2}")
        return h1, h2

    def contained(self, head: str, affected: str) -> None:
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", head, "--mode", "resolution")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(body["run_id"], "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n"
                                                        f"Resolution: contained\nAffected checks: {affected}\n"
                                                        "## Spec beyond intent\nnone\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)

    # ------------------------------------------------------------------ the suite row

    def test_a_clean_checkout_records_its_head_and_a_dirty_one_none(self):
        h1 = self.start()
        wt = self.checkout(h1)
        self.run_check(h1, wt=wt)
        row = self.suite_rows()[-1]
        self.assertEqual((row["head"], row["tree"], row["task_id"], row["lane"]),
                         (h1, git(wt, "rev-parse", "HEAD^{tree}"), TASK, CHECK))
        (wt / "untracked.txt").write_text("x")
        self.run_check(h1, wt=wt)
        self.assertNotIn("head", self.suite_rows()[-1])

    # ------------------------------------------------------------------ the prompts

    def test_the_implement_and_verify_prompts_list_a_marked_check(self):
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertIn(f"`{CHECK}`", Path(body["prompt_path"]).read_text())
        h1 = self.start()
        sid = self.run_check(h1)
        code, body, out, err = self.verify(h1)
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn(f"`{CHECK}`", text)
        self.assertIn(sid, text)  # the run the verifier cites

    def test_an_unmarked_check_is_in_neither_prompt(self):
        task = self.runner / "docs/delivery/tasks/0002-second.md"
        task.write_text(task.read_text().replace("  runs_on: operator-machine\n", ""))
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn(CHECK, Path(body["prompt_path"]).read_text())
        code, body, out, err = self.verify(self.start())  # and verify needs no run of it
        self.assertEqual(code, 0, out + err)
        self.assertNotIn(CHECK, Path(body["prompt_path"]).read_text())

    # ------------------------------------------------------------------ the launch refusal

    def test_verify_is_refused_with_no_run(self):
        self.assert_refused(self.verify(self.start()))

    def test_verify_is_refused_with_a_failed_run(self):
        h1 = self.start()
        sid = self.run_check(h1, code=3)
        self.assert_refused(self.verify(h1), sid)

    def test_verify_is_refused_with_a_run_at_another_head(self):
        h1 = self.start()
        sid = self.run_check(h1)
        self.assert_refused(self.verify(self.another()), sid)

    def test_verify_launches_with_a_passed_run_at_the_head(self):
        h1 = self.start()
        self.run_check(h1, code=3)
        self.run_check(h1)
        code, body, out, err = self.verify(h1)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], f"{TASK}/verify")

    # ------------------------------------------------------------------ what needs no run at the head

    def test_an_integration_merge_alone_needs_no_new_run(self):
        h1, h2 = self.approved()
        code, body, out, err = self.verify(h2, "--note", f"head moved by an integration merge; prior approve at {h1}")
        self.assertEqual(code, 0, out + err)
        self.assertIn(h1, Path(body["prompt_path"]).read_text())  # what the check rests on

    def test_a_resolution_review_that_does_not_list_the_check_needs_no_new_run(self):
        h1, h2 = self.approved(conflict=True)
        self.contained(h2, "cmd-01")
        code, _, out, err = self.verify(h2, "--note", "conflicted merge, resolution review")
        self.assertEqual(code, 0, out + err)

    def test_a_resolution_review_that_lists_the_check_needs_a_new_run(self):
        _, h2 = self.approved(conflict=True)
        self.contained(h2, f"cmd-01, {CHECK}")
        code, _, out, err = self.verify(h2, "--note", "conflicted merge, resolution review")
        self.assertEqual(code, 1, out + err)
        self.assertIn(CHECK, err)
        sid = self.run_check(h2)
        code, body, out, err = self.verify(h2, "--note", "conflicted merge, resolution review")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn("Rerun the checks that review names in `Affected checks`: cmd-01 (the checks it names that are "
                      f"marked `runs_on: operator-machine`, `{CHECK}`, are not yours to rerun", text)
        self.assertIn(sid, text)  # the runner's run is its evidence

    def test_a_waiver_names_an_approved_ruling(self):
        h1 = self.start()
        with as_lead():
            code, _, out, err = self.ccp("tasks", "ruling", "0002", "--words", "the operator waives the live check")
        self.assertEqual(code, 0, out + err)
        ruling = json.loads(out)["id"]
        for bad in ("mac-01=no ruling here", f"mac-01={TASK}-r9"):
            self.assert_refused(self.verify(h1, "--waived", bad), bad.split("=", 1)[1])
        code, _, out, err = self.verify(h1, "--waived", "cmd-01=" + ruling)  # not a marked check
        self.assertEqual(code, 2, out + err)
        code, _, out, err = self.verify(h1, "--waived", CHECK)  # not in its form
        self.assertEqual(code, 2, out + err)
        code, body, out, err = self.verify(h1, "--waived", f"{CHECK}={ruling}")
        self.assertEqual(code, 0, out + err)
        self.assertIn(ruling, Path(body["prompt_path"]).read_text())

    def test_the_waiver_belongs_to_verify(self):
        h1 = self.start()
        code, _, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", h1, "--waived", f"{CHECK}=x")
        self.assertEqual(code, 2, out + err)
        self.assertIn("--waived", err)


if __name__ == "__main__":
    unittest.main()
