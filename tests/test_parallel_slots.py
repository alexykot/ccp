"""SPEC §16.4–§16.5 (step 6 of the parallel-runners build): several runner teammates, one per slot, each holding one task.
The lead's slots (`team.sh runner spawn --count`, `bind --as`, `rotate`/`stop --slot`, `status`), the
claim's `--holder`, one task per runner and the race for one task, the worker prompt naming the
task's holder, a run's `opened_by` and the supersede guard, `tasks_done` per slot at close, and each
runner's own worktree."""
from __future__ import annotations

import json
import time
import unittest

from tests import test_parallel_claims
from tests.test_team_hosting import TeamCase
from tests.test_toolkit import ToolkitFixture, git

SLOTS = {"runner-1": {"bound_name": "runner-1", "tasks_done": 0}, "runner-2": {"bound_name": "runner-2-x", "tasks_done": 0}}


class LeadSlots(TeamCase):
    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        (self.q / "project.yaml").write_text((self.q / "project.yaml").read_text().replace(
            "runner:\n  name: runner\n", "runner:\n  name: runner\n  worktree: /tmp/demo-runner\n"))

    def work(self):
        return json.loads((self.q / "work.json").read_text())

    def test_spawn_count_records_slots_and_one_spawn_each(self):
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a,0002-b", "--count", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(res["slots"], ["runner-1", "runner-2"])
        self.assertEqual([a["name"] for a in res["actions"]], ["runner-1", "runner-2"])
        self.assertIn("--holder runner-2", res["actions"][1]["prompt"])
        r = self.work()["runners"]
        self.assertEqual((r["runner-1"]["worktree"], r["runner-2"]["tasks_done"]), ("/tmp/demo-runner-runner-1", 0))
        self.assertEqual(self.team("runner", "spawn", "--count", "3")[0], 2)  # above max_in_flight
        self.assertEqual(self.team("runner", "spawn", "--count", "2")[0], 2)  # recorded already
        code, res, _ = self.team("runner", "spawn", "--slot", "runner-2")  # a respawn
        self.assertEqual((code, res["slots"]), (0, ["runner-2"]))

    def test_bind_rotate_stop_status_per_slot(self):
        self.team("runner", "spawn", "--scope", "0001-a,0002-b", "--count", "2")
        code, res, err = self.team("runner", "bind", "--name", "runner-2-x", "--as", "runner-2")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.work()["runners"]["runner-2"]["bound_name"], "runner-2-x")
        self.assertEqual(self.team("runner", "bind", "--name", "x", "--as", "runner-9")[0], 2)
        # rotate refuses while the slot's own task has a worker run open
        (self.q / "tasks/0002-b.json").write_text(json.dumps({"task_id": "0002-b", "lease_holder": "runner-2"}))
        w = self.work()
        (self.q / "work.json").write_text(json.dumps({**w, "in_flight": ["0002-b"]}))
        d = self.q / "runs" / "0002-b"
        d.mkdir(parents=True)
        (d / "implement.json").write_text(json.dumps({"run_id": "0002-b/implement", "agent_id": "a1"}))
        self.assertEqual(self.team("runner", "rotate", "--slot", "runner-2")[0], 3)
        code, res, _ = self.team("runner", "rotate", "--slot", "runner-1")  # runner-1 holds nothing open
        self.assertEqual((code, res["actions"][1]["cmd"]), (0, "team.sh runner spawn --slot runner-1"))
        _, res, _ = self.team("runner", "status")
        self.assertEqual(res["runners"]["runner-2"]["tasks"], {"0002-b": None})
        self.assertIn("open_gates", res)
        code, _, err = self.team("runner", "stop", "--slot", "runner-2")  # it holds a task: drain or release
        self.assertEqual(code, 2)
        self.assertIn("--drain", err)
        self.assertEqual(self.team("runner", "stop", "--slot", "runner-1")[0], 0)  # holds nothing
        self.assertEqual(sorted(self.work()["runners"]), ["runner-2"])
        # a teammate name binds to one slot only
        self.team("runner", "spawn", "--count", "2")
        self.assertEqual(self.team("runner", "bind", "--name", "runner-2-x", "--as", "runner-1")[0], 2)

    def test_a_gate_decision_messages_the_tasks_holder(self):
        self.team("runner", "spawn", "--scope", "0001-a,0002-b", "--count", "2")
        self.team("runner", "bind", "--name", "runner-2-x", "--as", "runner-2")
        (self.q / "tasks/0002-b.json").write_text(json.dumps({"task_id": "0002-b", "lease_holder": "runner-2"}))
        _, g, _ = self.team("gate", "open", "--task-id", "0002-b", "--class", "operator", "--brief", "x")
        _, res, _ = self.team("gate", "decide", g["escalation_id"], "--decision", "approved",
                              "--resolution", "ok", "--authority", "SPEC §17.9")
        self.assertEqual(res["actions"][0]["name"], "runner-2-x")

    def test_a_scope_change_messages_every_runner(self):
        self.team("runner", "spawn", "--scope", "0001-a", "--count", "2")
        _, res, _ = self.team("runner", "scope", "--add", "0002-b")
        self.assertEqual(sorted(a["name"] for a in res["actions"]), ["runner-1", "runner-2"])


class Claims(test_parallel_claims.ParallelFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        (self.q / "work.json").write_text(json.dumps({"status": "running", "runners": SLOTS}))

    def claim_as(self, tid, holder):
        return self.ccp("tasks", "claim", tid, "--holder", holder, root=self.main)

    def test_several_runners_claim_as_their_slot_one_task_each(self):
        code, _, _, err = self.claim("0002")  # no --holder
        self.assertEqual(code, 2, err)
        self.assertIn("--holder", err)
        self.assertEqual(self.claim_as("0002", "runner-1")[0], 0)
        code, _, _, err = self.claim_as("0003", "runner-1")  # a second task for runner-1
        self.assertEqual(code, 7, err)
        self.assertIn("one task per runner", err)
        code, _, _, err = self.claim_as("0002", "runner-2")  # lost the race for 0002
        self.assertEqual(code, 3, err)
        self.assertIn("held by runner-1", err)
        self.assertEqual(self.claim_as("0003", "runner-2")[0], 0)
        self.assertEqual(self.claim_as("0002", "runner-1")[0], 0)  # its own: a resume

    def test_a_workers_prompt_names_its_tasks_runner(self):
        self.assertEqual(self.claim_as("0002", "runner-2")[0], 0)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "runner-2",
                                        root=self.main)
        self.assertEqual(code, 0, out + err)
        from pathlib import Path
        self.assertIn("Send the runner teammate, `runner-2-x`", Path(body["prompt_path"]).read_text())
        run = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual(run["opened_by"], "runner-2")

    def test_any_runners_map_needs_a_slot_and_a_removed_slot_names_itself(self):
        (self.q / "work.json").write_text(json.dumps({"status": "running", "runners": {"runner-1": {}}}))
        self.assertEqual(self.claim("0002")[0], 2)  # the default holder is no slot
        self.assertEqual(self.claim_as("0002", "runner-1")[0], 0)
        (self.q / "work.json").write_text(json.dumps({**json.loads((self.q / "work.json").read_text()),
                                                      "runners": {"runner-2": {}}, "runner": "stale"}))
        from ccp.queue import holder_teammate
        self.assertEqual(holder_teammate(self.q, "0002-second"), "runner-1")
        code, body, _, _ = self.ccp("tasks", "release", "0002", "--reason", "t", root=self.main)
        self.assertEqual((code, body["holder"], body["holder_teammate"]), (0, "runner-1", "runner-1"))

    def test_a_failed_worktree_gives_the_lease_back(self):
        from unittest import mock
        from ccp import lifecycle
        with mock.patch.object(lifecycle, "_worktree", side_effect=lifecycle.QueueError("git worktree add: boom", 1)):
            self.assertEqual(self.claim_as("0002", "runner-1")[0], 1)
        self.assertIsNone(json.loads((self.q / "tasks/0002-second.json").read_text())["lease_holder"])
        self.assertEqual(self.claim_as("0002", "runner-2")[0], 0)

    def test_supersede_never_takes_another_runners_fresh_run(self):
        self.assertEqual(self.claim_as("0002", "runner-1")[0], 0)
        self.assertEqual(self.claim_as("0003", "runner-2")[0], 0)
        self.assertEqual(self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "runner-1",
                                  root=self.main)[0], 0)
        code, _, _, err = self.ccp("prompt", "implement", "0003", "--base", "abc1234", "--supersede",
                                   "--holder", "runner-2", root=self.main)
        self.assertEqual(code, 3, err)
        self.assertIn("by runner-1, another runner", err)
        run = self.q / "runs/0002-second/implement.json"  # once it is old, a supersede may abandon it
        r = json.loads(run.read_text())
        r["opened_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
        run.write_text(json.dumps(r))
        self.assertEqual(self.ccp("prompt", "implement", "0003", "--base", "abc1234", "--supersede",
                                  "--holder", "runner-2", root=self.main)[0], 0)

    def _running(self, path):
        r = json.loads(path.read_text())
        r.update({"agent_id": "agent-w", "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        path.write_text(json.dumps(r))

    def test_a_slot_that_lost_the_race_cannot_open_a_round(self):
        self.assertEqual(self.claim_as("0002", "runner-1")[0], 0)
        self.assertEqual(self.claim_as("0002", "runner-2")[0], 3)  # lost the race
        self.assertEqual(self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "runner-1",
                                  root=self.main)[0], 0)
        run = self.q / "runs/0002-second/implement.json"
        self._running(run)
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "runner-2",
                                   root=self.main)
        self.assertEqual(code, 3, err)
        self.assertIn("held by runner-1, not by runner-2", err)
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", root=self.main)  # no slot named
        self.assertEqual(code, 2, err)
        r = json.loads(run.read_text())  # the winner's running worker is untouched
        self.assertEqual((r.get("agent_id"), r.get("outcome")), ("agent-w", None))
        self.assertFalse((self.q / "runs/0002-second/implement-2.json").exists())

    def test_holder_takes_a_teammate_name_through_bound_name(self):
        self.assertEqual(self.claim_as("0002", "runner-2")[0], 0)
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "runner-2-x",
                                     root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads((self.q / "runs/0002-second/implement.json").read_text())["opened_by"], "runner-2")
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "nobody",
                                   "--supersede", root=self.main)
        self.assertEqual(code, 2, err)
        self.assertIn("not a teammate name", err)

    def test_another_slots_running_round_is_kept_unless_the_holder_supersedes(self):
        self.assertEqual(self.claim_as("0002", "runner-1")[0], 0)
        self.assertEqual(self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "runner-1",
                                  root=self.main)[0], 0)
        run = self.q / "runs/0002-second/implement.json"
        self._running(run)
        r = json.loads(run.read_text())  # a round some other slot opened (before this fix, a race loser could)
        r["opened_by"] = "runner-2"
        run.write_text(json.dumps(r))
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "runner-1",
                                   root=self.main)
        self.assertEqual(code, 3, err)
        self.assertIn("opened by runner-2", err)
        self.assertIsNone(json.loads(run.read_text()).get("outcome"))
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--holder", "runner-1",
                                     "--supersede", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.q / "runs/0002-second/implement-2.json").exists())

    def test_each_runner_gets_its_own_worktree(self):
        (self.q / "project.yaml").write_text((self.q / "project.yaml").read_text()
                                             + f"runner:\n  worktree: {self.main / '.rt' / 'runner'}\n")
        code, body, out, err = self.ccp("tasks", "worktree", "--runner", "runner-2", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["made"])
        self.assertTrue(body["worktree"].endswith(".rt/runner-runner-2"))
        self.assertEqual(git(self.main, "-C", body["worktree"], "rev-parse", "HEAD"), git(self.main, "rev-parse", "origin/main"))
        code, body, _, _ = self.ccp("tasks", "worktree", "--runner", "runner-2", root=self.main)
        self.assertEqual((code, body["made"]), (0, False))
        self.assertEqual(self.ccp("tasks", "worktree", "--runner", "runner-9", root=self.main)[0], 2)
        junk = self.main / ".rt" / "runner-runner-1"  # a directory that is no worktree is not taken over
        junk.mkdir(parents=True)
        (junk / "x").write_text("x")
        self.assertEqual(self.ccp("tasks", "worktree", "--runner", "runner-1", root=self.main)[0], 2)


class CloseCounts(ToolkitFixture, unittest.TestCase):
    def test_a_close_counts_on_its_holders_slot(self):
        head = self._to_approved_pr()
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "lease_holder": "runner-2"}))
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "runners": SLOTS}))
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", "--summary", "it is built.")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["head"], head)
        r = json.loads((self.q / "work.json").read_text())["runners"]
        self.assertEqual((r["runner-1"]["tasks_done"], r["runner-2"]["tasks_done"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
