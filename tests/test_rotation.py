"""SPEC §10.2 step 4: rotation is due at `runner.rotate_after_tasks` tasks done, or at
`runner.rotate_at_context_tokens` of the runner teammate's latest request context (§24); `ccp tasks claim`
refuses the due slot a new task (exit 7) until `team.sh runner rotate` records the rotation, and from the
rotation until the lead binds the fresh runner, never a resume; `ccp health` reports the due slot and the
rotations against tasks done."""
from __future__ import annotations

import json
import time
import unittest
from tests.rotation_fixture import RotationFixture, iso



class Rotation(RotationFixture, unittest.TestCase):
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
        code, out, err = self.team("runner", "bind", "--name", "runner-1", "--as", "runner-1")
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
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)  # rotated: held until the bind
        self.assertEqual(code, 7, out + err)
        self.assertIn("`team.sh runner spawn`", err)

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
        self.assertEqual(self.team("runner", "bind", "--name", "runner-1-b", "--as", "runner-1")[0], 0)
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


class RotationReadsItsRecordSafely(RotationFixture, unittest.TestCase):
    """A `tasks_done` that is no whole number reads as 0, warned; a record with no spawn time counts the
    requests since the slot's latest spawn event in the ledger, and none when there is none."""

    def spawn_event(self, at, slot=None):
        (self.q / "observability").mkdir(exist_ok=True)
        payload = {"name": slot or "runner", **({"slot": slot} if slot else {})}
        with (self.q / "observability" / "events.jsonl").open("a") as fh:
            fh.write(json.dumps({"at": iso(at), "type": "runner", "op": "spawn", "payload": payload}) + "\n")

    def test_a_tasks_done_that_is_no_number_reads_as_zero_with_a_warning(self):
        self.binding(rotate_after_tasks=1)
        self.slots(tasks_done="x")
        code, _, out, err = self.claim()
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("warning:", err)
        self.assertIn("runners.runner-1.tasks_done", err)

    def test_one_runners_tasks_done_that_is_no_number_reads_as_zero_too(self):
        self.binding(rotate_after_tasks=1)
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-second"], "runner": "runner",
                                                      "runner_spawned_at": iso(time.time() - 60),
                                                      "runner_tasks_done": [3]}))
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertIn("runner_tasks_done", err)

    def test_a_whole_number_written_as_text_still_counts(self):
        self.binding(rotate_after_tasks=2)
        self.slots(tasks_done="2")
        code, _, out, err = self.claim()
        self.assertEqual(code, 7, out + err)
        self.assertNotIn("not a whole number", err)

    def test_no_spawn_time_counts_from_the_slots_latest_spawn_event(self):
        self.binding(rotate_at_context_tokens=100000)
        self.slots(tasks_done=0, spawned_at=None)
        self.spawn_event(time.time() - 7200, "runner-1")
        self.spawn_event(time.time() - 600, "runner-1")  # the latest of this slot's spawns
        self.spawn_event(time.time() - 30, "runner-2")  # another slot's, later: not this slot's
        self.span("runner-1", 500000, time.time() - 3600)  # before its latest spawn: does not count
        self.assertEqual(self.health()["due"], [])
        self.span("runner-1", 120000, time.time() - 60)  # since its latest spawn, before runner-2's
        self.assertEqual([(d["slot"], d["trigger"]) for d in self.health()["due"]], [("runner-1", "context")])
        self.assertEqual(self.claim()[0], 7)

    def test_no_spawn_time_and_no_spawn_event_counts_no_request(self):
        self.binding(rotate_at_context_tokens=100000)
        self.slots(tasks_done=0, spawned_at=None)
        self.span("runner-1", 500000, time.time() - 60)
        self.assertEqual(self.health()["due"], [])
        self.assertEqual(self.claim()[0], 0)

    def test_one_runner_with_no_spawn_time_counts_from_its_own_spawn_event(self):
        self.binding(rotate_at_context_tokens=100000)
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-second"], "runner": "runner",
                                                      "runner_tasks_done": 0}))
        self.spawn_event(time.time() - 600)
        self.spawn_event(time.time() - 30, "runner-1")  # a slot's spawn is not the one runner's
        self.span("runner", 500000, time.time() - 3600)
        self.assertEqual(self.health()["due"], [])
        self.span("runner", 120000, time.time() - 60)
        self.assertEqual([d["trigger"] for d in self.health()["due"]], ["context"])


class RotationDueCommand(RotationFixture, unittest.TestCase):
    """`ccp tasks rotation-due`: the rule claim enforces, asked without claiming."""

    def due(self, *holder):
        code, body, out, err = self.ccp("tasks", "rotation-due", *holder, root=self.main)
        return code, body, out + err

    def test_it_answers_both_triggers_and_not_due(self):
        self.binding(rotate_after_tasks=2, rotate_at_context_tokens=100000)
        self.slots(tasks_done=1)
        code, body, out = self.due("--holder", "runner-1")
        self.assertEqual((code, body["due"], body["slot"]), (0, False, "runner-1"), out)
        self.span("runner-1", 120000, time.time() - 60)
        code, body, out = self.due("--holder", "runner-1")
        self.assertEqual((code, body["due"], body["trigger"]), (0, True, "context"), out)
        self.assertEqual(body["rotate"], "team.sh runner rotate --slot runner-1")
        self.slots(tasks_done=2)
        code, body, out = self.due("--holder", "runner-1")
        self.assertEqual((code, body["due"], body["trigger"]), (0, True, "tasks"), out)

    def test_a_rotated_slot_is_not_due(self):
        self.binding(rotate_after_tasks=2)
        self.slots(tasks_done=2, rotated_at=iso(time.time()))
        code, body, out = self.due("--holder", "runner-1")
        self.assertEqual((code, body["due"]), (0, False), out)

    def test_one_runner_needs_no_holder(self):
        self.binding(rotate_after_tasks=2)
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-second"], "runner": "runner",
                                                      "runner_spawned_at": iso(time.time() - 60), "runner_tasks_done": 2}))
        code, body, out = self.due()
        self.assertEqual((code, body["due"], body["trigger"]), (0, True, "tasks"), out)

    def test_a_holder_that_is_no_slot_is_refused(self):
        self.slots(tasks_done=0)
        code, body, out = self.due("--holder", "runner-9")
        self.assertEqual((code, body), (2, None), out)
        self.assertIn("runner-1", out)


if __name__ == "__main__":
    unittest.main()
