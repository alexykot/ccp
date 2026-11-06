"""SPEC §16.5 (step 3 of the parallel-runners build, the verify slot removed in step 7: git and the head check decide): the
session park parks every task held, rotation waits for open worker runs, and the idle hook waits
on a working worker. With `parallel.max_in_flight` 1 none of it applies."""
from __future__ import annotations

import json
import subprocess
import time
import unittest

from tests import test_parallel_claims
from tests.test_team_hosting import HOOK, PLANE, TeamCase


class Runner(test_parallel_claims.ParallelFixture, unittest.TestCase):
    def two(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self.assertEqual(self.claim("0003")[0], 0)

    def verify(self, tid):
        return self.ccp("prompt", "verify", tid, "--pr", "7", "--head", "abc1234", root=self.main)

    def open_run(self, tid, phase, **extra):
        d = self.q / "runs" / tid
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{phase}.json").write_text(json.dumps({"run_id": f"{tid}/{phase}", "task_id": tid, "phase": phase,
                                                     "opened_at": "2026-10-28T10:00:00Z", **extra}))

    def test_the_session_park_parks_every_task_held(self):
        self.two()
        self.five(96)
        code, _, _, err = self.claim("0002")  # a resume, at the park
        self.assertEqual(code, 6, err)
        for tid in ("0002-second", "0003-third"):
            st = json.loads((self.q / f"tasks/{tid}.json").read_text())
            self.assertEqual((st["waiting_on"], st["quota_class"]), ("quota", "session"), tid)
        self.five(10)  # the window frees: the resume lifts every held park, not only its own
        code, _, out, err = self.claim("0002")
        self.assertEqual(code, 0, out + err)
        for tid in ("0002-second", "0003-third"):
            self.assertIsNone(json.loads((self.q / f"tasks/{tid}.json").read_text())["waiting_on"], tid)

    def test_the_park_keeps_another_wait(self):
        self.two()
        self.assertEqual(self.ccp("tasks", "wait", "0003", "design_seat", root=self.main)[0], 0)
        self.five(96)
        self.assertEqual(self.claim("0002")[0], 6)
        st = json.loads((self.q / "tasks/0003-third.json").read_text())
        self.assertEqual(st["waiting_on"], "design_seat")


class Rotation(TeamCase):
    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))

    def test_one_task_at_a_time_rotation_is_as_before(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo"}))
        self.team("runner", "spawn", "--scope", "0001-a")
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "in_flight": ["0001-a"], "task_id": "0001-a"}))
        d = self.q / "runs" / "0001-a"
        d.mkdir(parents=True)
        (d / "implement.json").write_text(json.dumps({"run_id": "0001-a/implement"}))  # opened, never launched
        self.assertEqual(self.team("runner", "rotate")[0], 0)

    def test_rotate_waits_for_open_worker_runs(self):
        self.team("runner", "spawn", "--scope", "0001-a,0002-b")
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "in_flight": ["0001-a", "0002-b"]}))
        d = self.q / "runs" / "0002-b"
        d.mkdir(parents=True)
        (d / "implement.json").write_text(json.dumps({"run_id": "0002-b/implement", "agent_id": "a1"}))
        code, _, err = self.team("runner", "rotate")
        self.assertEqual(code, 3)
        self.assertIn("0002-b/implement", err)
        self.assertEqual(self.team("runner", "rotate", "--force")[0], 2)  # --force needs a reason
        self.assertEqual(self.team("runner", "rotate", "--force", "--reason", "its worker died")[0], 0)
        (d / "implement.json").write_text(json.dumps({"run_id": "0002-b/implement", "agent_id": "a1",
                                                      "reported_at": "2026-10-28T11:00:00Z"}))
        self.assertEqual(self.team("runner", "rotate")[0], 0)


class Hook(TeamCase):
    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        self.prod.task("0001-a")
        self.prod.task("0002-b")
        self.prod.index()
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-a", "0002-b"],
                                                      "in_flight": ["0001-a"], "runner_tasks_done": 0}))
        (self.q / "tasks/0001-a.json").write_text(json.dumps({"task_id": "0001-a", "status": "leased",
                                                              "lease_holder": "runner", "waiting_on": None}))

    def hook(self):
        r = subprocess.run(["bash", HOOK, "--queue-root", self.q, "--ccp", PLANE / "bin" / "ccp"], capture_output=True,
                           text=True, input=json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": "runner",
                                                        "cwd": str(self.prod.root)}), env=self.env)
        return r.returncode, r.stderr

    def test_a_task_whose_worker_works_is_not_ready(self):
        d = self.q / "runs" / "0001-a"
        d.mkdir(parents=True)
        (d / "implement.json").write_text(json.dumps({"run_id": "0001-a/implement", "agent_id": "a1"}))
        # 0002-b cannot join (no paths in the test task, no parallel: true): nothing to do but wait
        self.assertEqual(self.hook()[0], 0)
        (d / "implement.json").write_text(json.dumps({"run_id": "0001-a/implement", "agent_id": "a1",
                                                      "reported_at": "2026-10-28T11:00:00Z"}))
        code, err = self.hook()  # the worker reported: 0001-a is the runner's to act on
        self.assertEqual(code, 2, err)
        self.assertIn("0001-a", err)

    def test_a_free_slot_nudges_toward_the_task_next_hands_out(self):
        self.prod.write("docs/delivery/tasks/0001-a.md", (self.prod.root / "docs/delivery/tasks/0001-a.md").read_text()
                        .replace("- **In:** it", "- **In:** `a.py`"))
        self.prod.write("docs/delivery/tasks/0002-b.md", (self.prod.root / "docs/delivery/tasks/0002-b.md").read_text()
                        .replace("- **In:** it", "- **In:** `b.py`"))
        self.prod.index()
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (self.q / "board").mkdir(exist_ok=True)
        (self.q / "board/allowance.jsonl").write_text(json.dumps({"at": stamp, "five_hour": 10, "seven_day": 5}) + "\n")
        d = self.q / "runs" / "0001-a"
        d.mkdir(parents=True)
        (d / "implement.json").write_text(json.dumps({"run_id": "0001-a/implement", "agent_id": "a1"}))
        code, err = self.hook()  # 0001-a's worker works; a slot is free and 0002-b may join it
        self.assertEqual(code, 2, err)
        self.assertIn("0002-b", err)


if __name__ == "__main__":
    unittest.main()
