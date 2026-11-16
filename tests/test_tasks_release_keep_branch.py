"""SPEC §10.4, §10.5 `ccp tasks release --keep-branch`: a claimed task whose runs are all closed goes back
to pending with its branch and PR kept, and a later claim resumes on that branch; a task with an open
run, one merging and one merged are refused."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.test_toolkit import ToolkitFixture, git


class ReleaseKeepingBranch(ToolkitFixture, unittest.TestCase):
    def state(self) -> dict:
        return json.loads((self.q / "tasks/0002-second.json").read_text())

    def set_state(self, **fields) -> None:
        p = self.q / "tasks/0002-second.json"
        p.write_text(json.dumps({**json.loads(p.read_text()), **fields}))

    def implemented(self) -> str:
        """Claim 0002, commit and push work on its branch, and report its implement run: the pushed head."""
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        wt = self.main / ".rt" / "impl-0002"
        (wt / "feature.txt").write_text("built\n")
        git(wt, "add", "feature.txt")
        git(wt, "commit", "-q", "-m", "Task 0002: build it")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        head = git(wt, "rev-parse", "HEAD")
        code, _, out, err = self.report("0002-second/implement", f"Outcome: done\nPR: #7\nHead: {head}\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        return head

    def test_a_task_with_its_runs_closed_is_released_and_reclaimed_on_its_branch(self):
        head = self.implemented()
        self.set_state(pr="7")
        code, _, out, err = self.ccp("tasks", "wait", "0002", "design_seat")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("tasks", "release", "0002", "--keep-branch", "--reason", "fix-check")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["kept_branch"], "task/0002-second")
        st = self.state()
        self.assertEqual((st["status"], st["lease_holder"], st["waiting_on"], st["lease_since"]), ("pending", None, None, None))
        self.assertTrue((self.q / "queue/pending/0002-second").exists())
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual((w["in_flight"], w["task_id"]), ([], None))
        clear = [e for e in self.events() if (e["type"], e["op"]) == ("lease", "clear")]
        self.assertTrue(clear[-1]["payload"]["released"])
        # the branch stays, here and on origin, and so does the worktree on it
        wt = self.main / ".rt" / "impl-0002"
        self.assertEqual(git(self.main, "rev-parse", "refs/heads/task/0002-second"), head)
        self.assertEqual(git(self.main, "ls-remote", "origin", "refs/heads/task/0002-second").split()[0], head)
        self.assertTrue(wt.is_dir())
        # the lead amends the file unleased; a later claim takes it under the same id and resumes on the branch
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(Path(body["worktree"]["path"]), wt)
        self.assertEqual((git(wt, "rev-parse", "--abbrev-ref", "HEAD"), git(wt, "rev-parse", "HEAD")),
                         ("task/0002-second", head))
        st = self.state()
        self.assertEqual((st["status"], st["lease_holder"], st["branch"]), ("leased", "runner", "task/0002-second"))

    def test_a_task_with_its_runs_closed_is_still_refused_without_the_flag(self):
        self.implemented()
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "fix-check")
        self.assertEqual(code, 3, out + err)
        self.assertIn("--keep-branch", err)
        self.set_state(status="blocked")  # a releasable phase, but runs behind it
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "fix-check")
        self.assertEqual(code, 3, out + err)
        self.assertIn("--keep-branch", err)
        self.assertEqual(self.state()["lease_holder"], "runner")

    def test_a_task_with_an_open_run_is_refused(self):
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        before = len(self.events())
        code, _, out, err = self.ccp("tasks", "release", "0002", "--keep-branch", "--reason", "fix-check")
        self.assertEqual(code, 3, out + err)
        self.assertIn("0002-second/implement", err)
        st = self.state()
        self.assertEqual((st["status"], st["lease_holder"]), ("implementing", "runner"))
        self.assertEqual(len(self.events()), before)

    def test_a_later_round_open_is_refused_though_an_earlier_one_closed(self):
        self.implemented()
        code, _, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "release", "0002", "--keep-branch", "--reason", "fix-check")
        self.assertEqual(code, 3, out + err)
        self.assertIn("0002-second/review", err)
        self.assertNotIn("0002-second/implement", err)

    def test_a_task_merging_or_merged_is_refused(self):
        self.implemented()
        for fields in ({"status": "merging"}, {"status": "submitted", "merged_by_close": "7"}):
            self.set_state(**fields)
            code, _, out, err = self.ccp("tasks", "release", "0002", "--keep-branch", "--reason", "fix-check")
            self.assertEqual(code, 3, f"{fields}: {out}{err}")
            self.assertEqual(self.state()["lease_holder"], "runner")

    def test_an_unclaimed_task_is_refused(self):
        code, _, out, err = self.ccp("tasks", "release", "0002", "--keep-branch", "--reason", "fix-check")
        self.assertEqual(code, 3, out + err)
        self.assertIn("only a claimed task", err)

    def test_a_claim_with_no_run_is_released_with_the_flag_too(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("tasks", "release", "0002", "--keep-branch", "--reason", "too early")
        self.assertEqual((code, body["released_from"]), (0, "leased"), out + err)
        self.assertIsNone(self.state()["lease_holder"])


if __name__ == "__main__":
    unittest.main()
