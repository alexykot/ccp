"""SPEC §18.2, §10.2 step 4: the `TeammateIdle` hook lets a runner idle when its rotation is due under
either trigger, `runner.rotate_after_tasks` or `runner.rotate_at_context_tokens`, by the rule
`ccp tasks claim` enforces (asked of `ccp tasks rotation-due`), and keeps driving it below both."""
from __future__ import annotations

import json
import time

from tests.test_team_hosting import HOOK, PLANE, TeamCase


def iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class IdleHookRotation(TeamCase):
    def setUp(self):
        super().setUp()
        self.prod.task("0001-a", status="done")
        self.prod.task("0002-b", deps=["0001-a"])
        self.prod.index()
        yaml = (self.q / "project.yaml").read_text()
        (self.q / "project.yaml").write_text(yaml.replace("  rotate_after_tasks: 4\n",
                                                          "  rotate_after_tasks: 4\n  rotate_at_context_tokens: 100000\n"))

    def hook(self, name):
        r = self.run_cmd("bash", HOOK, "--queue-root", self.q, "--ccp", PLANE / "bin" / "ccp",
                         stdin=json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": name,
                                           "cwd": str(self.prod.root)}))
        return r.returncode, r.stderr

    def span(self, name, tokens, at):
        (self.q / "board").mkdir(exist_ok=True)
        with (self.q / "board" / "usage-spans.jsonl").open("a") as fh:
            fh.write(json.dumps({"request_id": f"r{at}", "agent_id": f"{name}@session-abc", "at": iso(at),
                                 "input_tokens": 10, "cache_read_tokens": tokens - 110,
                                 "cache_creation_tokens": 100}) + "\n")

    def slot(self, tasks_done=1):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        (self.q / "work.json").write_text(json.dumps({
            "status": "running", "scope": ["0001-a", "0002-b"],
            "runners": {"runner-1": {"bound_name": "runner-1", "spawned_at": iso(time.time() - 3600),
                                     "tasks_done": tasks_done, "rotated_at": None}}}))

    def one_runner(self, tasks_done=1):
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-a", "0002-b"],
                                                      "runner": "runner", "runner_spawned_at": iso(time.time() - 3600),
                                                      "runner_tasks_done": tasks_done}))

    def test_a_slot_below_both_triggers_is_driven(self):
        self.slot()
        self.span("runner-1", 90000, time.time() - 60)
        code, err = self.hook("runner-1")
        self.assertEqual(code, 2, err)
        self.assertIn("ccp tasks claim 0002-b --holder runner-1", err)

    def test_a_slot_past_its_context_trigger_is_let_idle(self):
        self.slot()
        self.span("runner-1", 120000, time.time() - 60)
        code, err = self.hook("runner-1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("ccp tasks claim", err)
        self.assertFalse((self.q / "observability" / "runner-idle-runner-1.json").exists())  # no block counted

    def test_a_slot_at_its_task_count_is_let_idle(self):
        self.slot(tasks_done=4)
        code, err = self.hook("runner-1")
        self.assertEqual(code, 0, err)

    def test_one_runner_past_its_context_trigger_is_let_idle(self):
        self.one_runner()
        self.span("runner", 90000, time.time() - 60)
        self.assertEqual(self.hook("runner")[0], 2)
        self.span("runner", 120000, time.time() - 30)
        self.assertEqual(self.hook("runner")[0], 0)

    def test_a_rotated_slot_respawned_and_bound_is_driven_again(self):
        self.slot()
        self.span("runner-1", 120000, time.time() - 600)
        w = json.loads((self.q / "work.json").read_text())
        w["runners"]["runner-1"]["spawned_at"] = iso(time.time() - 60)  # the old incarnation's request predates it
        (self.q / "work.json").write_text(json.dumps(w))
        self.assertEqual(self.hook("runner-1")[0], 2)

    def test_an_unreadable_answer_reads_as_not_due(self):
        self.one_runner()
        self.span("runner", 120000, time.time() - 60)
        stub = self.prod.root / "ccp-stub.sh"  # a ccp that knows no rotation-due: the hook drives as before
        stub.write_text(f"#!/usr/bin/env bash\nif [ \"$3 $4\" = \"tasks rotation-due\" ]; then exit 2; fi\n"
                        f"exec \"{PLANE / 'bin' / 'ccp'}\" \"$@\"\n")
        stub.chmod(0o755)
        r = self.run_cmd("bash", HOOK, "--queue-root", self.q, "--ccp", stub,
                         stdin=json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": "runner",
                                           "cwd": str(self.prod.root)}))
        self.assertEqual(r.returncode, 2, r.stderr)


class IdleHookHeldTask(TeamCase):
    """SPEC §18.2, §16.3: one runner holding a task (work.json `in_flight`) is kept working only on what it
    holds; while that waits (on a gate, its wait, a question) it is let idle, never sent to another task."""

    def setUp(self):
        super().setUp()
        self.prod.task("0001-a")
        self.prod.task("0002-b")
        self.prod.index()
        self.work(["0001-a"])

    def work(self, in_flight):
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-a", "0002-b"],
                                                      "runner": "runner", "runner_tasks_done": 1,
                                                      "in_flight": in_flight}))

    def hook(self):
        r = self.run_cmd("bash", HOOK, "--queue-root", self.q, "--ccp", PLANE / "bin" / "ccp",
                         stdin=json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": "runner",
                                           "cwd": str(self.prod.root)}))
        return r.returncode, r.stderr

    def counter(self):
        return json.loads((self.q / "observability" / "runner-idle.json").read_text())

    def test_a_held_task_on_a_gate_lets_the_runner_idle_until_the_gate_closes(self):
        code, res, err = self.team("gate", "open", "--task-id", "0001-a", "--class", "operator", "--brief", "x")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.task_wait("0001-a"), "design_seat")
        code, err = self.hook()
        self.assertEqual(code, 0, err)
        self.assertNotIn("0002-b", err)
        self.assertEqual(self.counter(), {"key": "", "count": 0})
        code, _, err = self.team("gate", "decide", res["escalation_id"], "--decision", "approved",
                                 "--resolution", "done", "--authority", "SPEC §17.9")
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.task_wait("0001-a"))
        code, err = self.hook()
        self.assertEqual(code, 2, err)
        self.assertIn("0001-a", err)
        self.assertNotIn("0002-b", err)

    def test_a_held_task_listed_last_in_scope_is_the_one_named(self):
        self.work(["0002-b"])
        code, err = self.hook()
        self.assertEqual(code, 2, err)
        self.assertIn("0002-b", err)
        self.assertNotIn("0001-a", err)

    def test_a_held_task_already_done_or_dropped_holds_nothing_back(self):
        for status in ("done", "dropped"):
            (self.q / "tasks" / "0001-a.json").write_text(json.dumps({"task_id": "0001-a", "status": status}))
            code, err = self.hook()
            self.assertEqual(code, 2, (status, err))
            self.assertIn("0002-b", err, status)
