"""SPEC §10.4 `ccp tasks drop`: a task the lead dropped while it was in
flight (its file on the integration tip says dropped, its PR not merged) is settled in one step: its
runs abandoned, its wait and lease cleared, out of work.json, its runner's slot free."""
from __future__ import annotations

import json
import unittest

from tests.helpers import TASK
from tests.test_toolkit import ToolkitFixture, git


class Drop(ToolkitFixture, unittest.TestCase):
    def in_flight(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)

    def lead_drops_it(self):
        """The lead marks it dropped in the main checkout and pushes; the runner's worktree stays behind."""
        self.write("docs/delivery/tasks/0002-second.md", TASK.format(
            tid="0002-second", title="Second", status="dropped", deps='"0001-first"', ver="*Append-only.*"))
        git(self.main, "commit", "-qam", "Drop 0002")
        git(self.main, "push", "-q", "origin", "HEAD:main")

    def test_a_task_dropped_in_flight_is_settled_and_its_slot_freed(self):
        self.in_flight()
        self.lead_drops_it()
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "runners": {"runner": {}, "runner-2": {"bound_name": "r2"}}}))
        code, body, out, err = self.ccp("tasks", "drop", "0002", "--reason", "superseded by 0005")
        self.assertEqual(code, 0, out + err)
        self.assertIn("abandoned run 0002-second/implement (task dropped)", body["changed"])
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertEqual((st["status"], st["lease_holder"]), ("dropped", None))
        run = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertTrue(run["abandoned_at"])
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual(w["in_flight"], [])
        self.assertEqual(body["idle_runners"], ["r2"])  # not the runner whose task it was: it goes on itself
        notes = [e for e in self.events() if (e["type"], e["op"]) == ("note", "set")]
        self.assertIn("superseded by 0005", notes[-1]["payload"]["message"])
        code, body, _, _ = self.ccp("tasks", "drop", "0002", "--reason", "again")  # a second run changes nothing
        self.assertEqual((code, body["changed"]), (0, []))

    def test_only_a_task_its_file_on_the_tip_marks_dropped(self):
        self.in_flight()
        code, _, _, err = self.ccp("tasks", "drop", "0002", "--reason", "x")
        self.assertEqual(code, 3, err)
        self.assertIn("pending in its task file on origin/main", err)
        # dropped only in a local checkout, not committed to the tip: still refused
        (self.runner / "docs/delivery/tasks/0002-second.md").write_text(TASK.format(
            tid="0002-second", title="Second", status="dropped", deps='"0001-first"', ver="*Append-only.*"))
        self.assertEqual(self.ccp("tasks", "drop", "0002", "--reason", "x")[0], 3)

    def test_a_merged_task_is_closed_not_dropped(self):
        self.in_flight()
        self.lead_drops_it()
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "merge_sha": "a" * 40}))
        code, _, _, err = self.ccp("tasks", "drop", "0002", "--reason", "x")
        self.assertEqual(code, 3, err)
        self.assertIn("closed, not dropped", err)


    def test_a_waiting_task_and_a_late_report_after_the_drop(self):
        self.in_flight()
        self.assertEqual(self.ccp("tasks", "wait", "0002", "design_seat")[0], 0)
        self.lead_drops_it()
        code, body, out, err = self.ccp("tasks", "drop", "0002", "--reason", "x")
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(json.loads((self.q / "tasks/0002-second.json").read_text())["waiting_on"])
        drop = [e for e in self.events() if (e["type"], e["op"]) == ("durable", "reconcile")][-1]
        self.assertIn("ccp tasks drop", drop["payload"]["note"])
        code, _, _, err = self.report("0002-second/implement", "Outcome: done\n## Friction\nnone\n")
        self.assertEqual(code, 1, err)  # its worker's report comes too late: the run was abandoned

    def test_a_pr_that_merged_outside_close_is_closed_not_dropped(self):
        self.in_flight()
        self.lead_drops_it()
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "merged_by_close": "7"}))
        (self.ghstate / "pr.json").write_text(json.dumps({"state": "MERGED", "head": "a" * 40, "merge": "b" * 40}))
        code, _, _, err = self.ccp("tasks", "drop", "0002", "--reason", "x")
        self.assertEqual(code, 3, err)
        self.assertIn("PR 7 merged", err)


if __name__ == "__main__":
    unittest.main()
