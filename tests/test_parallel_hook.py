"""SPEC §16.5 (step 8 of the parallel-runners build): the TeammateIdle hook with several runners. It acts on each slot's
bound name only, keeps a slot's runner working on the task it holds, points an idle slot at the task
`ccp tasks next` hands out, counts blocks and rotations per slot, and leaves an unbound slot alone."""
from __future__ import annotations

import json
import subprocess
import time
import unittest

from tests.test_team_hosting import HOOK, PLANE, TeamCase


class SlotHook(TeamCase):
    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        for tid, path in (("0001-a", "a.py"), ("0002-b", "b.py")):
            self.prod.task(tid)
            f = self.prod.root / f"docs/delivery/tasks/{tid}.md"
            f.write_text(f.read_text().replace("- **In:** it", f"- **In:** `{path}`"))
        self.prod.index()
        self.slots = {"runner-1": {"bound_name": "runner-1"}, "runner-2": {"bound_name": "runner-2-x"}}
        self.work_({})
        (self.q / "tasks/0001-a.json").write_text(json.dumps({"task_id": "0001-a", "status": "leased",
                                                              "lease_holder": "runner-1", "waiting_on": None}))
        (self.q / "board").mkdir(exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (self.q / "board/allowance.jsonl").write_text(json.dumps({"at": stamp, "five_hour": 10, "seven_day": 5}) + "\n")

    def work_(self, slots_extra):
        slots = {k: {**v, **slots_extra.get(k, {})} for k, v in self.slots.items()}
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-a", "0002-b"],
                                                      "in_flight": ["0001-a"], "runners": slots}))

    def hook(self, name):
        r = subprocess.run(["bash", HOOK, "--queue-root", self.q, "--ccp", PLANE / "bin" / "ccp"], capture_output=True,
                           text=True, input=json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": name,
                                                        "cwd": str(self.prod.root)}), env=self.env)
        return r.returncode, r.stderr

    def test_a_slots_runner_is_kept_on_the_task_it_holds(self):
        code, err = self.hook("runner-1")
        self.assertEqual(code, 2, err)
        self.assertIn("0001-a", err)
        self.assertTrue((self.q / "observability/runner-idle-runner-1.json").is_file())  # per-slot counter

    def test_an_idle_slot_is_pointed_at_the_task_next_hands_out(self):
        code, err = self.hook("runner-2-x")
        self.assertEqual(code, 2, err)
        self.assertIn("ccp tasks claim 0002-b --holder runner-2", err)

    def test_other_names_an_unbound_slot_and_a_rotation_due_are_left_alone(self):
        self.assertEqual(self.hook("runner")[0], 0)  # the single runner's name is no slot's
        self.assertEqual(self.hook("runner-2")[0], 0)  # runner-2's bound name is runner-2-x
        self.work_({"runner-1": {"bind_pending": True}})
        self.assertEqual(self.hook("runner-1")[0], 0)
        self.work_({"runner-1": {"tasks_done": 4}})
        self.assertEqual(self.hook("runner-1")[0], 0)
        self.assertEqual(self.hook("runner-2-x")[0], 2)  # its own counter is 0


    def test_a_slots_subagent_a_waiting_task_and_full_slots_leave_it_idle(self):
        self.assertEqual(self.hook_with("runner-1", agent_id="a9", agent_type="ccp:delivery-implementer")[0], 0)
        (self.q / "tasks/0001-a.json").write_text(json.dumps({"task_id": "0001-a", "status": "leased",
                                                              "lease_holder": "runner-1", "waiting_on": "design_seat"}))
        self.assertEqual(self.hook("runner-1")[0], 0)  # its one task waits on the lead
        (self.q / "tasks/0002-b.json").write_text(json.dumps({"task_id": "0002-b", "status": "leased",
                                                              "lease_holder": "runner-1", "waiting_on": None}))
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "in_flight": ["0001-a", "0002-b"]}))
        self.assertEqual(self.hook("runner-2-x")[0], 0)  # nothing left for runner-2: next exits 7

    def hook_with(self, name, **extra):
        r = subprocess.run(["bash", HOOK, "--queue-root", self.q, "--ccp", PLANE / "bin" / "ccp"], capture_output=True,
                           text=True, input=json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": name,
                                                        "cwd": str(self.prod.root), **extra}), env=self.env)
        return r.returncode, r.stderr


class SlotSpawn(TeamCase):
    def test_spawning_slots_refuses_while_the_single_runner_holds_a_task(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        self.team("runner", "spawn", "--scope", "0001-a,0002-b")
        (self.q / "tasks/0001-a.json").write_text(json.dumps({"task_id": "0001-a", "lease_holder": "runner"}))
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "in_flight": ["0001-a"]}))
        code, _, err = self.team("runner", "spawn", "--count", "2")
        self.assertEqual(code, 2)
        self.assertIn("0001-a (held by runner)", err)


if __name__ == "__main__":
    unittest.main()
