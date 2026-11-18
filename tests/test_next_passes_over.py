"""SPEC §16.3: with tasks in flight, `ccp tasks next` passes over a ready task that only a path in flight
keeps out (rule 3), and one whose path meets a task it passed over, naming each on stderr and in
`--json` `passed_over`; a task any other rule keeps out still holds the line."""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from ccp import config, plan, tasklog
from tests.test_parallel_claims import task
from tests.test_toolkit import ToolkitFixture


class PassesOver(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["parallel"] = {"max_in_flight": 2, "shared": ["docs/notes.md"]}
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        self.tasks({"0002-second": "`src/a.py`"})
        (self.q / "work.json").write_text(json.dumps({"status": "running"}))
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)  # A, in flight
        self.assertEqual(code, 0, out + err)

    def tasks(self, scopes: dict[str, str], extra: dict[str, str] | None = None):
        for tid, scope_in in scopes.items():
            self.write(f"docs/delivery/tasks/{tid}.md", task(tid, scope_in, extra=(extra or {}).get(tid, "")))

    def next(self):
        return self.ccp("tasks", "next", "--json", root=self.main)

    def test_a_task_meeting_nothing_in_flight_is_offered_past_one_that_clashes(self):
        self.tasks({"0003-third": "`src/c.py`", "0004-fourth": "`src/a.py`"})
        with mock.patch.dict(os.environ, {"ACTOR": "design-seat"}):
            self.assertEqual(self.ccp("tasks", "prefer", "0004", root=self.main)[0], 0)
        code, body, out, err = self.next()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["task_id"], "0003-third")
        self.assertEqual([p["task_id"] for p in body["passed_over"]], ["0004-fourth"])
        why = body["passed_over"][0]["why"]
        self.assertIn("`src/a.py`", why)
        self.assertIn("0002-second", why)
        self.assertIn("ccp tasks next: passed over 0004-fourth:", err)
        cfg = config.load(self.main)  # the board takes the same choice
        self.assertEqual(plan.ready_queue(cfg, self.q, tasklog.load(cfg))["next"], "0003-third")

    def test_a_task_passed_over_is_not_starved_by_one_that_meets_it(self):
        self.tasks({"0003-third": "`src/a.py`, `src/b.py`", "0004-fourth": "`src/b.py`", "0005-fifth": "`src/c.py`"})
        code, body, out, err = self.next()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["task_id"], "0005-fifth")
        self.assertEqual([p["task_id"] for p in body["passed_over"]], ["0003-third", "0004-fourth"])
        self.assertIn("0003-third", body["passed_over"][1]["why"])  # 0004 waits behind 0003, not behind 0002
        self.assertIn("ccp tasks next: passed over 0004-fourth:", err)

    def test_a_task_that_runs_alone_still_holds_the_line(self):
        self.tasks({"0003-third": "`src/e.py`", "0004-fourth": "`src/c.py`"}, extra={"0003-third": "parallel: false\n"})
        code, body, out, err = self.next()
        self.assertEqual(code, 7, out + err)
        self.assertEqual((body["slots_full"], body["head"], body["passed_over"]), (True, "0003-third", []))

    def test_a_clash_behind_the_line_ends_with_the_tasks_passed_over_named(self):
        self.tasks({"0003-third": "`src/a.py`", "0004-fourth": "`src/e.py`"}, extra={"0004-fourth": "parallel: false\n"})
        code, body, out, err = self.next()
        self.assertEqual(code, 7, out + err)
        self.assertEqual((body["head"], [p["task_id"] for p in body["passed_over"]]), ("0003-third", ["0003-third"]))
        self.assertIn("rule 3", body["reason"])
        self.assertIn("ccp tasks next: passed over 0003-third:", err)

    def test_meeting_a_passed_over_task_only_in_a_shared_file_holds_nothing_back(self):
        self.tasks({"0003-third": "`src/a.py`, `docs/notes.md`", "0004-fourth": "`docs/notes.md`, `src/d.py`"})
        code, body, out, err = self.next()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["task_id"], [p["task_id"] for p in body["passed_over"]]), ("0004-fourth", ["0003-third"]))


if __name__ == "__main__":
    unittest.main()
