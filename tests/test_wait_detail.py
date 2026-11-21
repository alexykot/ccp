"""SPEC §10.1, §16.4: work.json's `waiting_on_detail` belongs to the wait it was set with. A clear, or a
later set without `--detail`, leaves none, a close or release, which give work.json the next task's
wait, leave none from the task that left, and a claim leaves none of the wait before it."""
from __future__ import annotations

import json
import unittest

from ccp.lifecycle import WAIT_KEYS
from tests.test_toolkit import ToolkitFixture


class WaitDetail(ToolkitFixture, unittest.TestCase):
    def work(self) -> dict:
        return json.loads((self.q / "work.json").read_text())

    def run_ok(self, *args: str):
        code, body, out, err = self.ccp(*args)
        self.assertEqual(code, 0, out + err)
        return body

    def test_a_cleared_wait_leaves_no_detail(self):
        self.run_ok("tasks", "claim", "0002")
        self.run_ok("tasks", "wait", "0002", "spec_maintainer", "--detail", "Q1")
        self.assertEqual((self.work()["waiting_on"], self.work()["waiting_on_detail"]), ("spec_maintainer", "Q1"))
        self.run_ok("tasks", "resume", "0002", "spec_maintainer")
        self.assertEqual((self.work()["waiting_on"], self.work()["waiting_on_detail"]), (None, None))
        self.run_ok("tasks", "wait", "0002", "spec_maintainer", "--detail", "Q1")
        self.run_ok("tasks", "resume", "0002", "spec_maintainer", "--detail", "answered")  # on the event only
        self.assertEqual((self.work()["waiting_on"], self.work()["waiting_on_detail"]), (None, None))

    def test_a_set_without_a_detail_leaves_none_from_the_wait_before(self):
        self.run_ok("tasks", "claim", "0002")
        self.run_ok("tasks", "wait", "0002", "spec_maintainer", "--detail", "Q2")
        self.run_ok("tasks", "wait", "0002", "runner")
        self.assertEqual((self.work()["waiting_on"], self.work()["waiting_on_detail"]), ("runner", None))

    def test_a_release_leaves_no_detail(self):
        self.run_ok("tasks", "claim", "0002")
        self.run_ok("tasks", "wait", "0002", "design_seat", "--detail", "G1")
        self.run_ok("tasks", "release", "0002", "--reason", "claimed too early")
        self.assertEqual((self.work()["task_id"], self.work()["waiting_on_detail"]), (None, None))

    def test_a_claim_leaves_none_of_the_wait_before_it(self):
        self.run_ok("tasks", "claim", "0002")
        self.run_ok("tasks", "wait", "0002", "design_seat", "--until", "2030-01-01T00:00:00Z", "--detail", "G2")
        (self.q / "work.json").write_text(json.dumps({**self.work(), "quota_class": "session"}))  # the wrapper sets none
        before = {k: self.work().get(k) for k in WAIT_KEYS}
        self.assertTrue(all(before.values()), before)
        self.run_ok("tasks", "claim", "0002")
        self.assertEqual({k: self.work().get(k) for k in WAIT_KEYS}, dict.fromkeys(WAIT_KEYS))

    def test_a_close_leaves_no_detail(self):
        self._to_approved_pr()
        w = self.work()  # a detail the close finds on its task, however it got there
        (self.q / "work.json").write_text(json.dumps({**w, "waiting_on_detail": "Q3"}))
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR, "--summary", "it is built.")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((self.work()["task_id"], self.work()["waiting_on_detail"]), (None, None))


if __name__ == "__main__":
    unittest.main()
