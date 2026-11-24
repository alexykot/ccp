"""SPEC §10.2 step 4, §16.5 rule 7, §18.2: from the rotation until the lead binds the fresh runner, the slot
takes no new task (`ccp tasks claim` exit 7, naming the lead's step left) and the idle hook keeps none of its
teammates working; a slot rotated and not respawned is left out of `idle_runners` and named in `vacant_slots`
by close, release and drop, `team.sh runner status` marks it `vacant`, and rotate's respawn action says it
holds no runner until that spawn runs."""
from __future__ import annotations

import json
import time
import unittest

from tests.helpers import TASK, PLANE_ROOT
from tests.rotation_fixture import RotationFixture, iso
from tests.team_hosting_fixture import HOOK, TeamCase
from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture


class ClaimMidRotation(RotationFixture, unittest.TestCase):
    def two_slots(self, **one):
        spawned = iso(time.time() - 3600)
        rec = {"spawned_at": spawned, "tasks_done": 0, "rotated_at": None}
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-second"], "runners": {
            "runner-1": {**rec, "bound_name": "runner-1", **one}, "runner-2": {**rec, "bound_name": "runner-2"}}}))

    def leased(self):
        f = self.q / "tasks/0002-second.json"
        return json.loads(f.read_text()).get("lease_holder") if f.is_file() else None

    def test_a_rotated_slot_takes_no_task_until_its_fresh_runner_is_bound(self):
        self.binding(rotate_after_tasks=2)
        self.two_slots(tasks_done=2)
        code, out, err = self.team("runner", "rotate", "--slot", "runner-1")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.claim()  # the outgoing runner
        self.assertEqual(code, 7, out + err)
        self.assertIn("`team.sh runner spawn --slot runner-1`", err)
        self.assertIsNone(self.leased())
        code, out, err = self.team("runner", "spawn", "--slot", "runner-1")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.claim()  # respawned, not bound
        self.assertEqual(code, 7, out + err)
        self.assertIn("`team.sh runner bind --name <name> --as runner-1`", err)
        self.assertIsNone(self.leased())
        code, out, err = self.team("runner", "bind", "--name", "runner-1-b", "--as", "runner-1")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.claim()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.leased(), "runner-1")

    def test_a_resume_mid_rotation_is_not_refused(self):
        self.two_slots()
        self.assertEqual(self.claim()[0], 0)
        self.two_slots(rotated_at=iso(time.time()))
        code, body, out, err = self.claim()
        self.assertEqual((code, body["resumed"]), (0, True), out + err)

    def test_one_runner_is_held_from_the_rotation_to_the_bind(self):
        self.binding(rotate_after_tasks=2)
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-second"], "runner": "runner",
                                                      "runner_spawned_at": iso(time.time() - 3600),
                                                      "runner_tasks_done": 2}))
        code, out, err = self.team("runner", "rotate")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 7, out + err)
        self.assertIn("`team.sh runner spawn`", err)
        self.assertIsNone(self.leased())
        w = self.work()  # the lead waited for the shutdown: the rotation is a minute older than the respawn
        (self.q / "work.json").write_text(json.dumps({**w, "runner_rotated_at": iso(time.time() - 60)}))
        code, out, err = self.team("runner", "spawn")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 7, out + err)
        self.assertIn("`team.sh runner bind --name <name>`", err)
        self.assertIsNone(self.leased())
        code, out, err = self.team("runner", "bind", "--name", "runner-b")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 0, out + err)

    def test_rotates_respawn_action_says_the_slot_stays_empty_until_the_spawn(self):
        self.two_slots()
        code, out, err = self.team("runner", "rotate", "--slot", "runner-1")
        self.assertEqual(code, 0, out + err)
        act = json.loads(out)["actions"][1]
        self.assertEqual((act["action"], act["cmd"]), ("respawn", "team.sh runner spawn --slot runner-1"))
        self.assertIn("`team.sh runner stop --slot runner-1`", act["detail"])


class IdleHookMidRotation(TeamCase):
    def setUp(self):
        super().setUp()
        self.prod.task("0001-a", status="done")
        self.prod.task("0002-b", deps=["0001-a"])
        self.prod.index()

    def hook(self, name):
        r = self.run_cmd("bash", HOOK, "--queue-root", self.q, "--ccp", PLANE_ROOT / "bin" / "ccp",
                         stdin=json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": name,
                                           "cwd": str(self.prod.root)}))
        return r.returncode, r.stderr

    def slots(self, rotated_at):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        rec = {"spawned_at": iso(time.time() - 3600), "tasks_done": 2}
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-a", "0002-b"], "runners": {
            "runner-1": {**rec, "bound_name": "runner-1", "rotated_at": rotated_at},
            "runner-2": {**rec, "bound_name": "runner-2", "rotated_at": None}}}))

    def test_the_slot_being_rotated_out_is_let_go(self):
        self.slots(rotated_at=None)
        self.assertEqual(self.hook("runner-1")[0], 2)  # below the threshold: kept on the ready task
        self.slots(rotated_at=iso(time.time()))
        code, err = self.hook("runner-1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("ccp tasks claim", err)
        self.assertEqual(self.hook("runner-2")[0], 2)  # the other slot is still driven

    def test_one_runner_rotated_since_its_spawn_is_let_go(self):
        w = {"status": "running", "scope": ["0001-a", "0002-b"], "runner": "runner",
             "runner_spawned_at": iso(time.time() - 3600), "runner_tasks_done": 1}
        (self.q / "work.json").write_text(json.dumps(w))
        self.assertEqual(self.hook("runner")[0], 2)
        (self.q / "work.json").write_text(json.dumps({**w, "runner_rotated_at": iso(time.time() - 60)}))
        self.assertEqual(self.hook("runner")[0], 0)


class VacantSlots(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "parallel": {"max_in_flight": 2}}

    def runners(self, **extra):
        f = self.q / "work.json"
        w = json.loads(f.read_text()) if f.is_file() else {"status": "running", "scope": ["0002-second"]}
        rec = {"spawned_at": "2026-11-18T00:00:00Z", "tasks_done": 0, "rotated_at": None}
        (self.q / "work.json").write_text(json.dumps({**w, "runners": {
            "runner-1": {**rec, "bound_name": "runner-1", "tasks_done": 2, "rotated_at": "2026-11-18T01:00:00Z"},
            "runner-2": {**rec, "bound_name": "r2"}, **extra}}))

    def hold(self, slot):
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "lease_holder": slot}))

    def test_close_names_the_vacant_slot_and_status_marks_it(self):
        self._to_approved_pr()
        self.hold("runner-2")
        self.runners()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR, "--summary", "done.")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["vacant_slots"], ["runner-1"])
        self.assertNotIn("runner-1", body.get("idle_runners", []))
        import subprocess  # noqa: PLC0415
        r = subprocess.run(["bash", str(PLANE_ROOT / "scripts" / "team.sh"), "runner", "status"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        runners = json.loads(r.stdout)["runners"]
        self.assertEqual((runners["runner-1"]["vacant"], runners["runner-2"]["vacant"]), (True, False))

    def test_release_names_it_and_still_wakes_the_idle(self):
        self.runners(**{"runner-3": {"bound_name": "r3", "tasks_done": 0, "rotated_at": None}})
        code, _, out, err = self.ccp("tasks", "claim", "0002", "--holder", "runner-2")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("tasks", "release", "0002", "--reason", "the lead takes it back")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["idle_runners"], body["vacant_slots"]), (["r2", "r3"], ["runner-1"]))

    def test_no_rotation_no_vacant_slots(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("tasks", "release", "0002", "--reason", "back")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("vacant_slots", body)

    def test_drop_names_it(self):
        self.runners()
        code, _, out, err = self.ccp("tasks", "claim", "0002", "--holder", "runner-2")
        self.assertEqual(code, 0, out + err)
        self.write("docs/delivery/tasks/0002-second.md", TASK.format(
            tid="0002-second", title="Second", status="dropped", deps='"0001-first"', ver="*Append-only.*"))
        git(self.main, "commit", "-qam", "Drop 0002")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        code, body, out, err = self.ccp("tasks", "drop", "0002", "--reason", "superseded")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["vacant_slots"], ["runner-1"])
        self.assertNotIn("idle_runners", body)  # runner-2 freed it and goes on; runner-1 is gone


if __name__ == "__main__":
    unittest.main()
