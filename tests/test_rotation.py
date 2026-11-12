"""SPEC §10.2 step 4: rotation is due at `runner.rotate_after_tasks` tasks done, or at
`runner.rotate_at_context_tokens` of the runner teammate's latest request context (§24); `ccp tasks claim`
refuses the due slot a new task (exit 7) until `team.sh runner rotate` records the rotation, never a
resume; `ccp health` reports the due slot and the rotations against tasks done."""
from __future__ import annotations

import json
import subprocess
import time
import unittest

from tests.test_toolkit import PLANE, ToolkitFixture

TEAM = PLANE / "scripts" / "team.sh"


def iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class Rotation(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.binding()

    def binding(self, **runner):
        lines = "".join(f"  {k}: {v}\n" for k, v in runner.items())
        (self.q / "project.yaml").write_text(f"project_id: demo\nintegration_branch: main\nproduct_root: {self.main}\n"
                                             f"runner:\n  name: runner\n{lines}")

    def slots(self, **rec):
        spawned = iso(time.time() - 3600)
        slot = {"bound_name": "runner-1", "spawned_at": spawned, "tasks_done": 0, "rotated_at": None, **rec}
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-second"],
                                                      "runners": {"runner-1": slot}}))

    def work(self):
        return json.loads((self.q / "work.json").read_text())

    def claim(self, holder="runner-1"):
        return self.ccp("tasks", "claim", "0002", "--holder", holder, root=self.main)

    def team(self, *argv):
        r = subprocess.run(["bash", str(TEAM), *argv], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def span(self, name, tokens, at):
        (self.q / "board").mkdir(exist_ok=True)
        with (self.q / "board" / "usage-spans.jsonl").open("a") as fh:
            fh.write(json.dumps({"request_id": f"r{at}", "agent_id": f"{name}@session-abc", "at": iso(at),
                                 "input_tokens": 10, "cache_read_tokens": tokens - 110, "cache_creation_tokens": 100,
                                 "output_tokens": 999}) + "\n")

    def health(self):
        code, body, out, err = self.ccp("health", "--json", root=self.main)
        self.assertEqual(code, 0, out + err)
        return body["rotation"]

    def test_a_slot_at_its_threshold_takes_no_task_until_rotated(self):
        self.binding(rotate_after_tasks=2)
        self.slots(tasks_done=2)
        code, _, out, err = self.claim()
        self.assertEqual(code, 7, out + err)
        self.assertIn("team.sh runner rotate --slot runner-1", err)
        self.assertIn("rotate_after_tasks", err)
        self.assertIsNone(json.loads((self.q / "tasks/0002-second.json").read_text()).get("lease_holder")
                          if (self.q / "tasks/0002-second.json").is_file() else None)
        due = self.health()["due"]
        self.assertEqual([(d["slot"], d["trigger"]) for d in due], [("runner-1", "tasks")])
        code, _, out, err = self.ccp("health", root=self.main)  # the text view names the rotation to run
        self.assertEqual(code, 0, err)
        self.assertIn("team.sh runner rotate --slot runner-1", out)
        code, out, err = self.team("runner", "rotate", "--slot", "runner-1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.health()["due"], [])  # recorded: no longer reported as due
        code, out, err = self.team("runner", "spawn", "--slot", "runner-1")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.claim()
        self.assertEqual(code, 0, out + err)

    def test_below_the_threshold_and_the_default_of_four(self):
        self.slots(tasks_done=3)  # no knob: 4
        code, _, out, err = self.claim()
        self.assertEqual(code, 0, out + err)
        self.ccp("tasks", "release", "0002", "--reason", "t", root=self.main)
        self.slots(tasks_done=4)
        self.assertEqual(self.claim()[0], 7)

    def test_a_resume_is_never_refused(self):
        self.binding(rotate_after_tasks=2)
        self.slots(tasks_done=0)
        self.assertEqual(self.claim()[0], 0)
        w = self.work()
        w["runners"]["runner-1"]["tasks_done"] = 2
        (self.q / "work.json").write_text(json.dumps(w))
        code, body, out, err = self.claim()
        self.assertEqual((code, body["resumed"]), (0, True), out + err)

    def test_one_runner_is_held_to_it_too(self):
        self.binding(rotate_after_tasks=2)
        spawned = iso(time.time() - 3600)
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-second"], "runner": "runner",
                                                      "runner_spawned_at": spawned, "runner_tasks_done": 2}))
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 7, out + err)
        self.assertIn("`team.sh runner rotate`", err)
        code, out, err = self.team("runner", "rotate")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 0, out + err)

    def test_a_large_context_makes_rotation_due(self):
        self.binding(rotate_at_context_tokens=100000)
        self.slots(tasks_done=0)
        self.span("runner-1", 120000, time.time() - 60)
        code, _, out, err = self.claim()
        self.assertEqual(code, 7, out + err)
        self.assertIn("rotate_at_context_tokens", err)
        due = self.health()["due"]
        self.assertEqual([(d["slot"], d["trigger"], d["context_tokens"]) for d in due], [("runner-1", "context", 120000)])

    def test_a_context_due_slot_takes_a_task_once_rotated_and_respawned(self):
        self.binding(rotate_at_context_tokens=100000)
        self.slots(tasks_done=0)
        self.span("runner-1", 120000, time.time() - 60)
        self.assertEqual(self.claim()[0], 7)
        code, out, err = self.team("runner", "rotate", "--slot", "runner-1")
        self.assertEqual(code, 0, out + err)
        code, out, err = self.team("runner", "spawn", "--slot", "runner-1")
        self.assertEqual(code, 0, out + err)
        # the fresh runner has made no request yet: the old incarnation's large one predates its spawn
        self.assertEqual(self.health()["due"], [])
        code, _, out, err = self.claim()
        self.assertEqual(code, 0, out + err)

    def test_a_request_before_the_spawn_does_not_count(self):
        self.binding(rotate_at_context_tokens=100000)
        self.slots(tasks_done=0, spawned_at=iso(time.time() - 600))
        self.span("runner-1", 500000, time.time() - 3600)  # the slot's only request, made before this spawn
        self.assertEqual(self.health()["due"], [])
        self.assertEqual(self.claim()[0], 0)

    def test_another_runners_request_does_not_count(self):
        self.binding(rotate_at_context_tokens=100000)
        self.slots(tasks_done=0, spawned_at=iso(time.time() - 600))
        self.span("runner-1", 90000, time.time() - 120)  # the slot's latest: below
        self.span("runner-2", 500000, time.time() - 30)  # later, and above, but another runner's
        self.assertEqual(self.health()["due"], [])
        self.assertEqual(self.claim()[0], 0)

    def test_the_slots_latest_request_decides_not_its_largest(self):
        self.binding(rotate_at_context_tokens=100000)
        self.slots(tasks_done=0, spawned_at=iso(time.time() - 600))
        self.span("runner-1", 150000, time.time() - 120)
        self.span("runner-1", 90000, time.time() - 60)  # the latest: below
        self.assertEqual(self.health()["due"], [])
        self.assertEqual(self.claim()[0], 0)

    def test_the_context_trigger_is_off_by_default(self):
        self.binding(rotate_at_context_tokens="null")
        self.slots(tasks_done=0)
        self.span("runner-1", 900000, time.time() - 60)
        self.assertEqual(self.claim()[0], 0)

    def test_health_counts_rotations_against_tasks_done(self):
        self.slots(tasks_done=1)
        evs = [{"type": "runner", "op": "rotate", "payload": {"name": "runner-1"}},
               {"type": "phase", "op": "transition", "task_id": "0001-first", "payload": {"from": "merging", "to": "done"}},
               {"type": "phase", "op": "transition", "task_id": "0003-x", "payload": {"from": "merging", "to": "done"}},
               {"type": "phase", "op": "transition", "task_id": "0003-x", "payload": {"from": "merging", "to": "done"}},
               {"type": "phase", "op": "transition", "task_id": "0004-y", "payload": {"from": "leased", "to": "implementing"}}]
        (self.q / "observability").mkdir(exist_ok=True)
        (self.q / "observability" / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))
        r = self.health()
        self.assertEqual((r["rotations"], r["tasks_done"], r["due"]), (1, 2, []))


if __name__ == "__main__":
    unittest.main()
