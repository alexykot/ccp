"""SPEC §10.5 `ccp tasks check --lease`: a claimed task's file is edited only in its PR, so an edit to it
on the integration branch after the claim is caught, naming the task and the lease holder."""
from __future__ import annotations

import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import TASK
from tests.test_toolkit import GIT_ENV, PLANE, ToolkitFixture, git

FILE = "docs/delivery/tasks/0002-second.md"


class LeaseEdits(ToolkitFixture, unittest.TestCase):
    def claim(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def commit_on_main(self, msg: str, status: str = "pending", stage_only: bool = False, later: int = 5) -> str:
        """The lead edits task 0002's file in the main checkout, on main; committed a little after the claim."""
        self.write(FILE, TASK.format(tid="0002-second", title=f"Second, amended: {msg}", status=status, deps='"0001-first"',
                                     ver="*Append-only.*"))
        git(self.main, "add", FILE)
        if stage_only:
            return ""
        with mock.patch.dict(os.environ, {"GIT_COMMITTER_DATE": f"@{int(time.time()) + later} +0000"}):
            git(self.main, "commit", "-qm", msg)
        return git(self.main, "rev-parse", "HEAD")

    def check(self, *extra: str):
        code, _, out, err = self.ccp("tasks", "check", "--lease", *extra, root=self.main)
        return code, out + err

    def test_an_edit_to_a_leased_task_file_on_main_fails_naming_the_task_and_holder(self):
        self.claim()
        sha = self.commit_on_main("Amend 0002")
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("0002-second", out)
        self.assertIn("runner", out)  # the lease holder, one runner's slot
        self.assertIn(sha[:7], out)

    def test_the_same_edit_with_no_lease_passes(self):
        self.commit_on_main("Amend 0002")
        code, out = self.check()
        self.assertEqual(code, 0, out)

    def test_an_edit_before_the_claim_and_a_released_lease_pass(self):
        self.commit_on_main("Amend 0002", later=-60)
        self.claim()
        self.assertEqual(self.check()[0], 0)
        self.commit_on_main("Amend 0002 again")
        self.assertEqual(self.check()[0], 1)
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.check()[0], 0)

    def test_the_holder_named_is_the_slot_holding_the_lease(self):
        self.claim()
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "lease_holder": "runner-2"}))
        self.commit_on_main("Amend 0002")
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("runner-2", out)

    def test_the_tasks_own_squash_merge_and_reconcile_are_not_edits(self):
        self.claim()
        sq = self.commit_on_main("Task 0002: the second thing (#7)")
        self.write(FILE, (self.main / FILE).read_text() + "\n- verified\n")
        git(self.main, "add", FILE)
        with mock.patch.dict(os.environ, {"GIT_COMMITTER_DATE": f"@{int(time.time()) + 6} +0000"}):
            git(self.main, "commit", "-qm", f"Reconcile 0002: done (PR #7, squash {sq[:7]})")
        code, out = self.check()
        self.assertEqual(code, 0, out)

    def test_another_tasks_merge_editing_the_file_is_an_edit(self):
        self.claim()
        self.commit_on_main("Task 0001: something else (#8)")
        self.assertEqual(self.check()[0], 1)

    def test_the_leads_drop_is_not_an_edit(self):
        self.claim()
        self.commit_on_main("Drop 0002", status="dropped")
        code, out = self.check()
        self.assertEqual(code, 0, out)

    def test_a_pushed_edit_is_seen_from_a_checkout_whose_local_main_lacks_it(self):
        self.claim()
        self.commit_on_main("Amend 0002")
        git(self.main, "push", "-q", "origin", "main")
        git(self.main, "reset", "-q", "--hard", "HEAD~1")
        self.assertEqual(self.check()[0], 1)

    def test_a_lease_of_a_task_done_in_the_queue_is_not_live(self):
        self.claim()
        self.commit_on_main("Amend 0002")
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "status": "done"}))
        self.assertEqual(self.check()[0], 0)

    def test_staged_judges_the_index_only_on_the_integration_branch(self):
        self.claim()
        self.commit_on_main("", stage_only=True)
        code, out = self.check("--staged")
        self.assertEqual(code, 1, out)
        self.assertIn("0002-second", out)
        self.assertIn("runner", out)
        git(self.main, "checkout", "-q", "-b", "lead-branch")
        self.assertEqual(self.check("--staged")[0], 0)

    def test_staged_ignores_history_and_passes_a_staged_drop(self):
        self.claim()
        self.commit_on_main("Amend 0002")
        self.assertEqual(self.check("--staged")[0], 0)  # nothing staged: a past edit does not block every commit
        self.commit_on_main("", status="dropped", stage_only=True)
        self.assertEqual(self.check("--staged")[0], 0)

    def test_without_a_queue_it_is_a_usage_error(self):
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": ""}):
            self.assertEqual(self.check()[0], 2)

    def test_staged_without_lease_is_a_usage_error(self):
        code, _, out, err = self.ccp("tasks", "check", "--staged", root=self.main)
        self.assertEqual(code, 2, out + err)


    def test_the_commit_hook_refuses_a_commit_on_main_editing_a_leased_task_file(self):
        """scripts/git-hooks/pre-commit, with the plane's own main override set so only the lease rule speaks."""
        shim = Path(self._tmp.name) / "bin"
        shim.mkdir()
        (shim / "ccp").symlink_to(PLANE / "bin/ccp")
        git(self.main, "config", "core.hooksPath", str(PLANE / "scripts/git-hooks"))
        env = {**os.environ, **GIT_ENV, "PATH": f"{shim}:{os.environ['PATH']}", "CCP_ALLOW_MAIN_COMMIT": "1"}

        def commit(msg: str) -> int:
            return subprocess.run(["git", "-C", str(self.main), "commit", "-qm", msg], env=env,
                                  capture_output=True, text=True).returncode

        self.commit_on_main("Amend 0002 before the claim", stage_only=True)
        self.assertEqual(commit("Amend 0002 before the claim"), 0)
        self.claim()
        self.commit_on_main("Amend 0002", stage_only=True)
        self.assertNotEqual(commit("Amend 0002"), 0)
        git(self.main, "checkout", "-q", "-b", "lead-branch")
        self.assertEqual(commit("Amend 0002 on a branch"), 0)


if __name__ == "__main__":
    unittest.main()
