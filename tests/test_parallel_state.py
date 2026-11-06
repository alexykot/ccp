"""SPEC §16.4 (step 1 of the parallel-runners build): every writer of work.json holds its lock across the read and the
write, and a wait on one task never repoints the runner's current task to it."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import unittest
from pathlib import Path

from unittest import mock

from ccp import queue, usage
from tests.test_toolkit import ToolkitFixture

PLANE = Path(__file__).resolve().parents[1]


class WorkLock(ToolkitFixture, unittest.TestCase):
    def work(self) -> dict:
        return json.loads((self.q / "work.json").read_text())

    def test_concurrent_writers_lose_no_in_flight_entry(self):
        queue.save_work(self.q, {"in_flight": []})

        def add(prefix: str) -> None:
            for i in range(40):
                tid = f"{prefix}{i}"
                queue.save_work(self.q, {}, edit=lambda cur, t=tid: cur.update(in_flight=list(cur.get("in_flight") or []) + [t]))

        threads = [threading.Thread(target=add, args=(p,)) for p in ("a", "b", "c")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.work()["in_flight"]), 120)

    def test_the_shell_writers_take_the_same_lock(self):
        """While ccp holds work.json's lock, set-waiting-on.sh waits for it rather than writing past it."""
        queue.save_work(self.q, {"task_id": "0002-second", "project_id": "demo"})
        env = {**os.environ, "QUEUE_ROOT": str(self.q)}
        with queue.file_lock(self.q / "work.json"):
            p = subprocess.Popen(["bash", str(PLANE / "scripts/observability/set-waiting-on.sh"), "set",
                                  "0002-second", "design_seat", "--project-id", "demo"],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            with self.assertRaises(subprocess.TimeoutExpired):
                p.wait(timeout=1.5)
            # it appends its event before it takes the lock: an event here proves it reached the lock and
            # waits on it, rather than being slow to start
            self.assertTrue(any(e["type"] == "waiting_on" for e in self.events()))
            self.assertIsNone(self.work().get("waiting_on"))
        out, err = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, out + err)
        self.assertEqual(self.work()["waiting_on"], "design_seat")

    def test_a_wait_on_another_task_does_not_repoint_the_current_one(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        queue.save_work(self.q, {"task_id": "0009-other"})  # the runner moved on to another task
        code, _, out, err = self.ccp("tasks", "wait", "0002", "design_seat")
        self.assertEqual(code, 0, out + err)
        w = self.work()
        self.assertEqual((w["task_id"], w.get("waiting_on")), ("0009-other", None))
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertEqual(st["waiting_on"], "design_seat")
        # its own task's wait still lands in work.json
        queue.save_work(self.q, {"task_id": "0002-second"})
        code, _, out, err = self.ccp("tasks", "resume", "0002", "gate_decided")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((self.work()["task_id"], self.work().get("waiting_on")), ("0002-second", None))


    def test_a_drain_set_while_a_claim_runs_is_kept(self):
        """The claim writes `status` from work.json as read under the lock, not from its first read."""
        queue.save_work(self.q, {"status": "running"})
        real = usage.session_step

        def lead_drains_meanwhile(*a, **k):
            queue.save_work(self.q, {"status": "draining"})
            return real(*a, **k)

        with mock.patch.object(usage, "session_step", side_effect=lead_drains_meanwhile):
            code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.work()["status"], "draining")

    def test_the_next_task_takes_its_own_wait_not_the_released_ones(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        (self.q / "tasks/0009-other.json").write_text(json.dumps({"task_id": "0009-other", "status": "leased",
                                                                  "waiting_on": None}))
        queue.save_work(self.q, {"in_flight": ["0002-second", "0009-other"], "waiting_on": "quota",
                                 "quota_class": "session", "planned_resume_at": "2099-01-01T00:00:00Z"})
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual(code, 0, out + err)
        w = self.work()
        self.assertEqual((w["task_id"], w["waiting_on"], w["quota_class"], w["planned_resume_at"]),
                         ("0009-other", None, None, None))


if __name__ == "__main__":
    unittest.main()
