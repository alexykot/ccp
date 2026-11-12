"""SPEC §10.3: `ccp tasks next` never offers a task already done or dropped: a task whose queue status
is terminal is passed over whatever the checkout's task file says, and a checkout that lags the remote
integration branch reads the task statuses from that branch's tip."""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from ccp import config, tasklog
from tests.helpers import TASK
from tests.test_toolkit import ToolkitFixture, git


class NextReadsTheTip(ToolkitFixture, unittest.TestCase):
    """The runner worktree sits at the first commit; the main checkout moves the integration branch on."""

    def setUp(self):
        super().setUp()
        self.write("docs/delivery/tasks/0003-third.md", TASK.format(tid="0003-third", title="Third", status="pending",
                                                                    deps="", ver="*Append-only.*"))
        self.commit_and_push("add 0003")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def commit_and_push(self, msg: str, push: bool = True):
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", "docs/delivery")
        git(self.main, "commit", "-q", "-m", msg)
        if push:
            git(self.main, "push", "-q", "origin", "main")

    def set_status(self, tid: str, status: str):
        p = self.main / "docs/delivery/tasks" / f"{tid}.md"
        text = p.read_text()
        for s in ("pending", "done", "dropped"):
            text = text.replace(f"status: {s}   #", f"status: {status}   #", 1)
        p.write_text(text)

    def next_id(self, root=None):
        code, body, out, err = self.ccp("tasks", "next", "--json", root=root)
        return code, (body or {}).get("task_id"), out + err

    def test_a_lagging_worktree_is_not_offered_a_task_done_on_the_tip(self):
        self.assertEqual(self.next_id()[1], "0002-second")  # before the merge: the worktree offers it
        self.set_status("0002-second", "done")
        self.commit_and_push("Task 0002: done (#1)")
        self.assertIn("status: pending", (self.runner / "docs/delivery/tasks/0002-second.md").read_text())
        code, tid, msg = self.next_id()
        self.assertEqual((code, tid), (0, "0003-third"), msg)

    def test_a_task_dropped_on_the_tip_is_not_offered_and_its_dependants_stay_waiting(self):
        self.write("docs/delivery/tasks/0004-fourth.md", TASK.format(tid="0004-fourth", title="Fourth", status="pending",
                                                                     deps='"0003-third"', ver="*Append-only.*"))
        self.commit_and_push("add 0004")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        self.set_status("0002-second", "dropped")
        self.set_status("0003-third", "done")
        self.commit_and_push("drop 0002, finish 0003")
        code, tid, msg = self.next_id()
        self.assertEqual((code, tid), (0, "0004-fourth"), msg)  # 0003's done on the tip readies its dependant

    def test_without_a_queue_the_tip_is_origin_main(self):
        self.set_status("0002-second", "done")
        self.commit_and_push("Task 0002: done (#1)")
        with mock.patch.dict(os.environ):
            os.environ.pop("QUEUE_ROOT")
            code, tid, msg = self.next_id()
        self.assertEqual((code, tid), (0, "0003-third"), msg)

    def test_the_tip_is_the_bindings_integration_branch(self):
        git(self.main, "push", "-q", "origin", "main:trunk")
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\nintegration_branch: trunk\n")
        self.set_status("0002-second", "done")
        self.commit_and_push("Task 0002: done (#1)")  # on main only: origin/trunk still holds the worktree's commit
        self.assertEqual(self.next_id()[1], "0002-second")
        git(self.main, "push", "-q", "origin", "main:trunk")
        self.assertEqual(self.next_id()[1], "0003-third")

    def test_a_checkout_that_does_not_lag_keeps_its_own_statuses(self):
        self.set_status("0002-second", "done")
        self.commit_and_push("Task 0002: done (#1)")
        self.set_status("0002-second", "pending")
        self.commit_and_push("reopen 0002 locally", push=False)  # ahead of origin/main, not behind it
        code, tid, msg = self.next_id(root=self.main)
        self.assertEqual((code, tid), (0, "0002-second"), msg)

    def test_a_task_done_or_dropped_in_the_queue_is_passed_over(self):
        (self.q / "tasks").mkdir()
        for status in ("done", "dropped"):
            (self.q / "tasks" / "0002-second.json").write_text(json.dumps({"task_id": "0002-second", "status": status}))
            code, tid, msg = self.next_id()
            self.assertEqual((code, tid), (0, "0003-third"), f"{status}: {msg}")
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps({"task_id": "0002-second", "status": "implementing"}))
        self.assertEqual(self.next_id()[1], "0002-second")

    def test_a_queue_done_task_is_skipped_but_does_not_ready_its_dependants(self):
        (self.q / "tasks").mkdir()
        for tid in ("0002-second", "0003-third"):
            (self.q / "tasks" / f"{tid}.json").write_text(json.dumps({"task_id": tid, "status": "done"}))
        self.write("docs/delivery/tasks/0004-fourth.md", TASK.format(tid="0004-fourth", title="Fourth", status="pending",
                                                                     deps='"0003-third"', ver="*Append-only.*"))
        self.commit_and_push("add 0004")
        code, tid, _ = self.next_id(root=self.main)
        self.assertEqual((code, tid), (3, None))

    def test_a_lead_preference_for_a_task_done_on_the_tip_is_ignored(self):
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002", "0003"],
                                                      "next_tasks": ["0002-second"]}))
        self.set_status("0002-second", "done")
        self.commit_and_push("Task 0002: done (#1)")
        code, _, out, err = self.ccp("tasks", "next", "--json")
        self.assertEqual((code, json.loads(out)["task_id"]), (0, "0003-third"), err)
        self.assertIn("preferred 0002-second is done", err)


class TipStatuses(ToolkitFixture, unittest.TestCase):
    def test_statuses_at_a_ref_and_the_lag(self):
        cfg = config.load(self.runner)
        self.assertEqual(tasklog.statuses_at(cfg, "origin/main", ["0001-first", "0002-second", "0009-absent"]),
                         {"0001-first": "done", "0002-second": "pending"})
        self.assertEqual(tasklog.statuses_at(cfg, "origin/no-such-branch", ["0001-first"]), {})
        self.assertFalse(tasklog.lags(cfg, "origin/main"))
        self.assertFalse(tasklog.lags(cfg, "origin/no-such-branch"))
        self.write("x.txt", "x")
        git(self.main, "add", "x.txt")
        git(self.main, "commit", "-q", "-m", "x")
        git(self.main, "push", "-q", "origin", "main")
        self.assertTrue(tasklog.lags(cfg, "origin/main"))
        self.assertFalse(tasklog.lags(config.load(self.main), "origin/main"))

    def test_a_legacy_status_on_the_tip_reads_as_its_canonical_state(self):
        p = self.main / "docs/delivery/tasks/0002-second.md"
        p.write_text(p.read_text().replace("status: pending", "status: in_progress", 1))
        git(self.main, "add", str(p))
        git(self.main, "commit", "-q", "-m", "legacy")
        git(self.main, "push", "-q", "origin", "main")
        self.assertEqual(tasklog.statuses_at(config.load(self.runner), "origin/main", ["0002-second"]),
                         {"0002-second": "pending"})


if __name__ == "__main__":
    unittest.main()
