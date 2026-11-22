"""SPEC §2 Claude team: team.sh (runner + gates), the team-lead question channel, the
TeammateIdle hook, the triage hand-off and the managed copies sync installs."""
from __future__ import annotations

import json
import re
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from ccp.queue import lib
from tests.helpers import Product, binding
from tests.team_hosting_fixture import HOOK, PLANE, TEAM, TeamCase

ASK = PLANE / "scripts" / "spec-maintainer-ask.sh"


class TestRunner(TeamCase):
    def test_spawn_records_scope_audit_and_event(self):
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a,0002-b", "--review-point", "R2")
        self.assertEqual(code, 0, err)
        act = res["actions"][0]
        # §9.1: the test product has no runner copy of its own, so the spawn names the plugin type
        self.assertEqual((act["action"], act["name"], act["subagent_type"]), ("spawn_teammate", "runner", "ccp:delivery-runner"))
        self.assertIn("Scope: 0001-a, 0002-b (review point R2)", act["prompt"])
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual((w["status"], w["scope"], w["runner_tasks_done"]), ("running", ["0001-a", "0002-b"], 0))
        self.assertTrue((self.q / res["prompt_ref"]).is_file())
        ev = [e for e in self.events() if e["type"] == "runner"]
        self.assertEqual((ev[-1]["op"], ev[-1]["actor"]), ("spawn", lib.LEAD))

    def test_spawn_warns_when_close_will_not_stamp_the_review_point(self):
        """§22.1: `ccp tasks close` stamps only a review point that matches ids.review_point.pattern."""
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a", "--review-point", "R2")
        self.assertEqual((code, "warnings" in res), (0, False), err)
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a", "--review-point", "PM")
        self.assertEqual(code, 0, err)
        self.assertIn("review point 'PM' does not match ids.review_point.pattern", res["warnings"][0])
        self.assertIn("warning: review point 'PM'", err)

    def test_the_lead_audits_follow_keep_body(self):
        """§23.8: the runner-spawn and runner-scope audits keep the text only when the product opts in."""
        def audits():
            return [json.loads(f.read_text()) for f in sorted((self.q / "prompts" / "_runner").glob("*.json"))]
        self.team("runner", "spawn", "--scope", "0001-a")
        self.team("runner", "scope", "--add", "0002-b")
        self.assertEqual([("prompt_body" in a) for a in audits()], [False, False])
        self.team("runner", "stop")
        self.prod.write("docs/delivery/plane.json", json.dumps(
            {"project_id": "demo", "prompts": {"keep_body": True}, "parallel": {"max_in_flight": 2}}))
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertIn("Scope: 0001-a", json.loads((self.q / res["prompt_ref"]).read_text())["prompt_body"])
        code, res, err = self.team("runner", "scope", "--add", "0002-b")
        self.assertEqual(code, 0, err)
        self.assertIn("now 0001-a, 0002-b", json.loads((self.q / res["prompt_ref"]).read_text())["prompt_body"])
        self.team("runner", "stop")
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a", "--count", "2")
        self.assertEqual(code, 0, err)
        ref = [e for e in self.events() if e["type"] == "runner"][-1]["payload"]["prompt_ref"]
        self.assertIn("Your runner slot is runner-", json.loads((self.q / ref).read_text())["prompt_body"])

    def test_scope_add_remove(self):
        self.team("runner", "spawn", "--scope", "0001-a")
        code, res, err = self.team("runner", "scope", "--add", "0002-b,0003-c")
        self.assertEqual(code, 0, err)
        self.assertEqual((res["scope"], res["added"]), (["0001-a", "0002-b", "0003-c"], ["0002-b", "0003-c"]))
        act = res["actions"][0]
        self.assertEqual((act["action"], act["name"]), ("message_teammate", "runner"))
        self.assertIn("now 0001-a, 0002-b, 0003-c", act["message"])
        self.assertTrue((self.q / res["prompt_ref"]).is_file())
        self.assertEqual(json.loads((self.q / "work.json").read_text())["scope"], ["0001-a", "0002-b", "0003-c"])
        ev = [e for e in self.events() if e["type"] == "runner"]
        self.assertEqual((ev[-1]["op"], ev[-1]["actor"], ev[-1]["payload"]["added"]),
                         ("scope", lib.LEAD, ["0002-b", "0003-c"]))
        code, res, _ = self.team("runner", "scope", "--remove", "0003-c")
        self.assertEqual((code, res["scope"], res["removed"]), (0, ["0001-a", "0002-b"], ["0003-c"]))
        # refusals: not an id; empty scope; nothing to change; no running runner
        self.assertEqual(self.team("runner", "scope", "--add", "0004-d, which can run.")[0], 2)
        self.assertEqual(self.team("runner", "scope", "--remove", "0001-a,0002-b")[0], 2)
        self.assertEqual(self.team("runner", "scope")[0], 2)
        self.team("runner", "stop")
        self.assertEqual(self.team("runner", "scope", "--add", "0004-d")[0], 2)

    def test_scope_remove_refuses_any_task_in_flight(self):
        """§16.4: not only work.json's task_id, every task in in_flight."""
        self.team("runner", "spawn", "--scope", "0001-a,0002-b")
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "task_id": "0001-a", "phase": "implementing",
                                                      "in_flight": ["0001-a", "0002-b"]}))
        code, _, err = self.team("runner", "scope", "--remove", "0002-b", "--add", "0003-c")
        self.assertEqual(code, 2)
        self.assertIn("0002-b: in flight", err)

    def test_a_new_review_point_starts_with_the_waiting_refactors(self):
        # §20.4 "deps" (the default): refactors no scope task depends on go to the top of the next review point.
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "architect": {"shape_from_task": "0001"}}))
        for tid, status, deps in (("0001-a", "pending", []), ("0002-b", "pending", ["0004-needed"]),
                                  ("0003-waiting", "pending", []), ("0004-needed", "pending", []),
                                  ("0005-old", "done", []), ("0006-blocked", "pending", ["0001-a"])):
            f = self.prod.task(tid, status, deps)
            if tid not in ("0001-a", "0002-b"):
                f.write_text(f.read_text().replace('spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E1"]'))
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle", "review_point": "R7"}))
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a,0002-b", "--review-point", "R8")
        self.assertEqual(code, 0, err)
        # outstanding = pending, ready or not; 0004 joins through 0002-b's dependency, so it is not added
        self.assertEqual(res["refactors_added"], ["0003-waiting", "0006-blocked"])
        self.assertEqual(res["scope"], ["0003-waiting", "0006-blocked", "0001-a", "0002-b"])
        act = res["actions"][0]
        self.assertIn("Scope: 0003-waiting, 0006-blocked, 0001-a, 0002-b (review point R8)", act["prompt"])
        self.assertIn("placed first in the scope (SPEC §20.4): 0003-waiting, 0006-blocked", act["prompt"])
        self.assertIn("runner scope --remove", act["detail"])
        self.assertEqual(json.loads((self.q / "work.json").read_text())["scope"][:2], ["0003-waiting", "0006-blocked"])
        ev = [e for e in self.events() if e["type"] == "runner"][-1]
        self.assertEqual((ev["op"], ev["payload"]["refactors_added"]), ("spawn", ["0003-waiting", "0006-blocked"]))
        self.assertEqual(json.loads((self.q / "work.json").read_text())["review_point_refactors"], ["0003-waiting", "0006-blocked"])
        # a respawn of the same review point (rotate, restart) keeps them and looks for no new ones:
        # 0007, filed during R8, waits for R9
        f = self.prod.task("0007-filed-mid-cycle")
        f.write_text(f.read_text().replace('spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E1"]'))
        code, res, err = self.team("runner", "spawn")
        self.assertEqual((code, res["refactors_added"], res["scope"][:2]), (0, [], ["0003-waiting", "0006-blocked"]), err)
        self.assertIn("1 refactor(s) wait outside this scope", err)
        # the lead naming the scope again does not drop them: the ones still pending go back on top
        f = self.prod.root / "docs/delivery/tasks/0006-blocked.md"
        f.write_text(f.read_text().replace("status: pending", "status: done"))
        code, res, _ = self.team("runner", "spawn", "--scope", "0001-a", "--review-point", "R8")
        self.assertEqual((res["refactors_added"], res["scope"]), (["0003-waiting"], ["0003-waiting", "0001-a"]))
        # a refactor the lead removes stays out
        self.team("runner", "scope", "--remove", "0003-waiting", "--add", "0002-b")
        self.assertEqual(json.loads((self.q / "work.json").read_text())["review_point_refactors"], ["0006-blocked"])
        code, res, _ = self.team("runner", "spawn", "--scope", "0001-a", "--review-point", "R8")
        self.assertEqual((res["refactors_added"], res["scope"]), ([], ["0001-a"]))
        # true and false add nothing: true already reaches every refactor, false never does
        for mode in (True, False):
            self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "architect": {"shape_from_task": "0001", "refactor_in_scope": mode}}))
            code, res, _ = self.team("runner", "spawn", "--scope", "0001-a", "--review-point", f"R9{mode}")
            self.assertEqual((code, res["refactors_added"]), (0, []))

    def test_spawn_refuses_an_unreadable_task_log_and_writes_nothing(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "architect": {"shape_from_task": "0001"}}))
        self.prod.write("docs/delivery/tasks/0001-a.md", "not a task file")
        (self.prod.root / "docs/delivery/tasks/0001-a.md").write_bytes(b"---\n\xff\xfe\n---\n")
        before = (self.q / "work.json").read_text()
        code, _, err = self.team("runner", "spawn", "--scope", "0001-a", "--review-point", "R8")
        self.assertEqual(code, 2)
        self.assertIn("cannot read the product's task log", err)
        self.assertEqual((self.q / "work.json").read_text(), before)
        self.assertEqual([e for e in self.events() if e["type"] == "runner"], [])

    def test_a_rotation_binds_the_suffixed_name_and_every_action_follows_it(self):
        """§10.2: the harness names a fresh runner `runner-2` while the old one holds `runner`."""
        self.team("runner", "spawn", "--scope", "0001-a")
        code, res, err = self.team("runner", "rotate", "--reason", "4 done")
        self.assertEqual(code, 0, err)
        shut = res["actions"][0]
        self.assertEqual((shut["action"], shut["name"]), ("shutdown_teammate", "runner"))
        self.assertIn("TaskStop", shut["detail"])
        code, res, err = self.team("runner", "spawn")
        self.assertIn("runner bind --name", res["actions"][0]["detail"])
        code, res, err = self.team("runner", "bind", "--name", "runner-2")
        self.assertEqual(code, 0, err)
        self.assertEqual((res["name"], res["previous"]), ("runner-2", "runner"))
        self.assertEqual((res["actions"][0]["action"], res["actions"][0]["name"]), ("stop_teammate", "runner"))
        self.assertEqual(json.loads((self.q / "work.json").read_text())["runner"], "runner-2")
        ev = [e for e in self.events() if e["type"] == "runner"][-1]
        self.assertEqual((ev["op"], ev["payload"]), ("bound", {"name": "runner-2", "previous": "runner"}))
        # scope, gate decisions, rotate and stop now address runner-2
        _, res, _ = self.team("runner", "scope", "--add", "0002-b")
        self.assertEqual(res["actions"][0]["name"], "runner-2")
        _, g, _ = self.team("gate", "open", "--task-id", "0001-a", "--class", "operator", "--brief", "x")
        _, res, _ = self.team("gate", "decide", g["escalation_id"], "--decision", "approved",
                              "--resolution", "ok", "--authority", "SPEC §17.9")
        self.assertEqual(res["actions"][0]["name"], "runner-2")
        _, res, _ = self.team("runner", "rotate")
        self.assertEqual(res["actions"][0]["name"], "runner-2")
        self.assertEqual([e for e in self.events() if e["type"] == "runner"][-1]["payload"]["name"], "runner-2")
        # binding the same name again asks for no stop; a spawn resets the bound name to the asked-for one
        _, res, _ = self.team("runner", "bind", "--name", "runner-2")
        self.assertEqual(res["actions"], [])
        self.team("runner", "spawn")
        self.assertEqual(json.loads((self.q / "work.json").read_text())["runner"], "runner")
        _, res, _ = self.team("runner", "stop", "--drain")
        self.assertEqual(res["actions"][0]["name"], "runner")

    def test_a_spawn_over_a_live_runner_stops_it_first(self):
        """§16.5: one runner at a time; the old one's shutdown comes before the new spawn."""
        self.team("runner", "spawn", "--scope", "0001-a")
        self.team("runner", "bind", "--name", "runner-old")
        for status in ("running", "draining"):
            with self.subTest(status=status):
                if status == "draining":
                    self.team("runner", "stop", "--drain")
                    self.team("runner", "bind", "--name", "runner-old")
                code, res, err = self.team("runner", "spawn")
                self.assertEqual(code, 0, err)
                self.assertEqual([(a["action"], a["name"]) for a in res["actions"]],
                                 [("shutdown_teammate", "runner-old"), ("spawn_teammate", "runner")])
                self.assertEqual(res["stopped"], "runner-old")
                ops = [(e["op"], e["payload"].get("name"), e["payload"].get("reason"))
                       for e in self.events() if e["type"] == "runner"][-2:]
                self.assertEqual(ops, [("stop", "runner-old", "respawn"), ("spawn", "runner", None)])
                w = json.loads((self.q / "work.json").read_text())
                self.assertEqual((w["status"], w["runner"]), ("running", "runner"))
                self.assertNotIn("runners", w)
        # nothing live: a stopped runner, or one a rotation shut down already, gets no second stop
        for before in (("runner", "stop"), ("runner", "rotate")):
            with self.subTest(before=before):
                self.team(*before)
                n = len(self.events())
                _, res, _ = self.team("runner", "spawn", "--scope", "0001-a")
                self.assertEqual([a["action"] for a in res["actions"]], ["spawn_teammate"])
                self.assertNotIn("stopped", res)
                self.assertEqual([e["op"] for e in self.events()[n:] if e["type"] == "runner"], ["spawn"])

    def test_a_spawn_after_a_rotation_waits_for_the_bind(self):
        """§10.2: until the lead binds the fresh runner, the hook keeps no teammate working."""
        self.team("runner", "spawn", "--scope", "0001-a")
        self.assertFalse(json.loads((self.q / "work.json").read_text())["runner_bind_pending"])
        self.team("runner", "rotate")
        _, res, _ = self.team("runner", "spawn")
        self.assertTrue(json.loads((self.q / "work.json").read_text())["runner_bind_pending"])
        self.assertIn("the bind is required", res["actions"][0]["detail"])
        self.team("runner", "bind", "--name", "runner")
        self.assertFalse(json.loads((self.q / "work.json").read_text())["runner_bind_pending"])

    def test_bind_refusals(self):
        self.assertEqual(self.team("runner", "bind", "--name", "runner-2")[0], 2)  # no running runner
        self.team("runner", "spawn", "--scope", "0001-a")
        self.assertEqual(self.team("runner", "bind")[0], 2)
        self.assertEqual(self.team("runner", "bind", "--name", "runner 2")[0], 2)
        self.assertEqual(json.loads((self.q / "work.json").read_text())["runner"], "runner")
        self.team("runner", "stop", "--drain")  # a draining runner can still be bound; a stopped one cannot
        self.assertEqual(self.team("runner", "bind", "--name", "runner-2")[0], 0)
        self.team("runner", "stop")
        self.assertEqual(self.team("runner", "bind", "--name", "runner-3")[0], 2)


class TestGates(TeamCase):
    def test_open_decide_status(self):
        code, res, err = self.team("gate", "open", "--task-id", "0001-a", "--class", "operator",
                                   "--brief", "apply the schema", "--ask", "app db init")
        self.assertEqual(code, 0, err)
        eid = res["escalation_id"]
        self.assertEqual(eid, "0001-a-1")
        self.assertEqual(self.task_wait("0001-a"), "design_seat")
        self.assertEqual(self.team("gate", "status", eid)[0], 3)
        # decide needs an authority
        self.assertEqual(self.team("gate", "decide", eid, "--decision", "approved", "--resolution", "ok")[0], 2)
        code, res, err = self.team("gate", "decide", eid, "--decision", "approved", "--resolution", "backup taken",
                                   "--authority", "SPEC §17.9")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.team("gate", "status", eid)[0], 0)
        self.assertIsNone(self.task_wait("0001-a"))
        g = json.loads((self.q / "escalations" / "0001-a" / "1.json").read_text())
        self.assertEqual((g["status"], g["decided_by"], g["to"]), ("closed", "design_seat", "design_seat"))

    def test_ask_operator_then_decide_marks_the_operator(self):
        eid = self.team("gate", "open", "--task-id", "0001-a", "--class", "spend", "--brief", "a paid cycle")[1]["escalation_id"]
        self.assertEqual(self.team("gate", "ask-operator", eid)[0], 0)
        self.assertEqual(self.task_wait("0001-a"), "operator_decision")
        self.assertEqual(self.team("gate", "status", eid)[0], 3)
        self.team("gate", "decide", eid, "--decision", "refused", "--resolution", "not this week", "--authority", "the operator, in session")
        g = json.loads((self.q / "escalations" / "0001-a" / "1.json").read_text())
        self.assertEqual((g["decision"], g["decided_by"]), ("refused", "operator_via_design_seat"))
        self.assertEqual(self.team("gate", "status", eid)[0], 4)

    def test_the_pre_rename_ask_verb_is_gone(self):
        """Only `gate ask-operator` asks the operator; the verb's pre-rename name is refused."""
        eid = self.team("gate", "open", "--task-id", "0001-a", "--class", "spend", "--brief", "a paid cycle")[1]["escalation_id"]
        self.assertNotEqual(self.team("gate", "ask-" + "a" + "lex", eid)[0], 0)
        self.assertEqual(self.task_wait("0001-a"), "design_seat")  # still waiting on the gate, not the operator

    def test_standing_approval_closes_at_once(self):
        code, res, _ = self.team("gate", "open", "--task-id", "0002-b", "--class", "operator", "--brief", "db init",
                                 "--standing", "docs/BUILD.md#review-point-r2")
        self.assertEqual(res["outcome"], "approved_standing")
        self.assertEqual(self.team("gate", "status", res["escalation_id"])[0], 0)
        self.assertIsNone(self.task_wait("0002-b"))


class TestTeamLeadQuestions(TeamCase):
    def raise_q(self):
        r = self.run_cmd("bash", ASK, "raise", "--raised-by", lib.RUNNER, "--task-id", "0001-a", "--text", "Which?",
                         "--inconsistency", "task vs SPEC", "--spec-refs", "S1", "--tried", "read both")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_raise_sends_to_lead_without_lock_or_launch(self):
        res = self.raise_q()
        self.assertEqual(res["outcome"], "sent_to_lead")
        self.assertEqual(res["actions"][0]["action"], "send_message_to_lead")
        self.assertFalse((self.q / "spec-maintainer.lock").exists())
        self.assertFalse((self.q / "prompts").exists())

    def test_a_binding_without_a_spec_maintainer_block_still_sends_to_the_lead(self):
        # §17 (2026-11-05): the lead is every project's maintainer; there is no steerer route.
        y = self.q / "project.yaml"
        text = y.read_text()
        y.write_text(re.sub(r"^spec_maintainer:\n(?:[ \t]+.*\n)*", "", text, flags=re.M))
        self.assertNotIn("spec_maintainer:", y.read_text())
        res = self.raise_q()
        self.assertEqual((res["outcome"], res["route"]), ("sent_to_lead", "spec_maintainer"))
        q = json.loads((self.q / "questions" / f"{res['question_id']}.json").read_text())
        self.assertEqual(q["route"], "spec_maintainer")
        self.assertEqual(self.task_wait("0001-a"), "spec_maintainer")
        # No answer yet: process waits on the lead.
        r = self.run_cmd("bash", ASK, "process", res["question_id"])
        self.assertEqual(json.loads(r.stdout)["outcome"], "waiting_on_lead")

    def test_lead_answer_is_applied(self):
        qid = self.raise_q()["question_id"]
        (self.q / "questions" / f"{qid}.answer.json").write_text(json.dumps({
            "schema_version": 1, "question_id": qid, "project_id": "demo", "verdict": "resolved",
            "ruling": "Do A.", "reasoning": "SPEC S1 says A.", "commit_sha": "abc1234",
            "files_changed": ["docs/SPEC.md"], "question_for_operator": None, "guidance": None,
            "answered_by": "spec_maintainer", "session_id": "lead", "answered_at": "2026-09-30T20:00:00Z",
            "supersedes": None}))
        r = self.run_cmd("bash", ASK, "process", qid)
        self.assertEqual(json.loads(r.stdout)["outcome"], "answered", r.stderr)
        self.assertIsNone(self.task_wait("0001-a"))

    def test_needs_operator_sends_no_email(self):
        qid = self.raise_q()["question_id"]
        (self.q / "questions" / f"{qid}.answer.json").write_text(json.dumps({
            "schema_version": 1, "question_id": qid, "project_id": "demo", "verdict": "needs_operator",
            "ruling": None, "reasoning": "product call", "commit_sha": None, "files_changed": [],
            "question_for_operator": "A or B? I recommend A.", "guidance": None, "answered_by": "spec_maintainer",
            "session_id": "lead", "answered_at": "2026-09-30T20:00:00Z", "supersedes": None}))
        res = json.loads(self.run_cmd("bash", ASK, "process", qid).stdout)
        self.assertNotIn("email", res)
        self.assertEqual(res["actions"][-1]["action"], "wait_for_lead")
        self.assertEqual(self.task_wait("0001-a"), "operator_decision")

    def test_blocks_must_be_task_ids(self):
        r = self.run_cmd("bash", ASK, "raise", "--raised-by", lib.RUNNER, "--task-id", "0001-a", "--text", "Which?",
                         "--inconsistency", "x", "--spec-refs", "S1", "--tried", "y",
                         "--blocks", "0002-b, Merge of 0008 (after the fix), which can run.")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not task ids", r.stderr)
        self.assertFalse((self.q / "questions").exists())
        self.assertIsNone(self.task_wait("0001-a"))
        self.assertFalse(list((self.q / "tasks").glob("*which*")))
        # With a task log present, the ids must exist; whitespace around real ids is fine.
        self.prod.task("0001-a")
        self.prod.task("0002-b")
        bad = self.run_cmd("bash", ASK, "raise", "--raised-by", lib.RUNNER, "--task-id", "0001-a", "--text", "Q",
                           "--inconsistency", "x", "--spec-refs", "S1", "--tried", "y", "--blocks", "0009-nope")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("no such task: 0009-nope", bad.stderr)
        ok = self.run_cmd("bash", ASK, "raise", "--raised-by", lib.RUNNER, "--task-id", "0001-a", "--text", "Q",
                          "--inconsistency", "x", "--spec-refs", "S1", "--tried", "y", "--blocks", " 0002-b , 0001-a")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["blocks"], ["0002-b", "0001-a"])
        self.assertEqual(self.task_wait("0002-b"), "spec_maintainer")


class TestIdleHook(TeamCase):
    def hook(self, name="runner", **extra):
        r = self.run_cmd("bash", HOOK, "--queue-root", self.q, "--ccp", PLANE / "bin" / "ccp",
                         stdin=json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": name,
                                           "cwd": str(self.prod.root), **extra}))
        self.stderr = r.stderr
        return r.returncode

    def setUp(self):
        super().setUp()
        self.prod.task("0001-a", status="done")
        self.prod.task("0002-b", deps=["0001-a"])
        self.prod.index()
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-a", "0002-b"],
                                                      "runner_tasks_done": 1, "waiting_on": None}))

    def test_keeps_runner_working_then_lets_go(self):
        self.assertEqual(self.hook(), 2)
        self.assertEqual(self.hook(), 2)
        self.assertEqual(self.hook(), 2)
        self.assertEqual(self.hook(), 0)  # the idle limit, 3, on the same ready set

    def test_a_session_park_lets_the_runner_idle_until_its_resume(self):
        # SPEC §25.4: the 5-hour window is the account's, so a park in work.json is a scope-wide stop
        w = json.loads((self.q / "work.json").read_text())
        future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
        (self.q / "work.json").write_text(json.dumps({**w, "waiting_on": "quota", "quota_class": "session",
                                                      "planned_resume_at": future, "task_id": "0002-b"}))
        self.assertEqual(self.hook(), 0)
        past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
        (self.q / "work.json").write_text(json.dumps({**w, "waiting_on": "quota", "quota_class": "session",
                                                      "planned_resume_at": past, "task_id": "0002-b"}))
        self.assertEqual(self.hook(), 2)  # past its resume: no longer a stop

    def test_an_expired_park_on_the_task_file_no_longer_holds_the_task(self):
        # the wake was lost (the lead restarted): past its planned resume the park holds nothing back
        future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
        past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
        park = {"task_id": "0002-b", "waiting_on": "quota", "quota_class": "session"}
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-b.json").write_text(json.dumps({**park, "planned_resume_at": future}))
        self.assertEqual(self.hook(), 0)  # a live park on any task file: the runner idles
        (self.q / "tasks" / "0002-b.json").write_text(json.dumps({**park, "planned_resume_at": past}))
        self.assertEqual(self.hook(), 2)  # expired: 0002-b is ready again, the runner is nudged on
        (self.q / "tasks" / "0002-b.json").write_text(json.dumps({"waiting_on": "quota", "planned_resume_at": past}))
        self.assertEqual(self.hook(), 0)  # another quota wait (not the 5-hour park) still holds it

    def test_ignores_other_teammates_and_waits(self):
        self.assertEqual(self.hook("reviewer"), 0)
        (self.q / "tasks" / "0002-b.json").write_text(json.dumps({"waiting_on": "design_seat"}))
        self.assertEqual(self.hook(), 0)

    def test_open_gate_holds_task_even_if_work_json_waits_elsewhere(self):
        self.team("gate", "open", "--task-id", "0002-b", "--class", "operator", "--brief", "x")
        self.assertEqual(self.hook(), 0)
        w = json.loads((self.q / "work.json").read_text())
        w["scope"] = ["0002-b", "0003-c"]
        self.prod.task("0003-c")
        (self.q / "work.json").write_text(json.dumps(w))
        self.assertEqual(self.hook(), 2)  # 0003-c is ready although work.json.waiting_on is design_seat

    def test_a_plugin_teammate_reports_its_name_as_its_type(self):
        # SPEC docs/design/plugin.md: for a teammate, agent_type is the teammate's name; its workers carry scoped types.
        self.assertEqual(self.hook(agent_id="arunner-1", agent_type="ccp:delivery-implementer"), 0)
        self.assertEqual(self.hook(agent_id="arunner-1", agent_type="runner"), 2)

    def test_ignores_the_runners_subagents_and_logs_inputs(self):
        # Inside a subagent the harness adds agent_id/agent_type; the teammate_name is still the runner's.
        self.assertEqual(self.hook(agent_id="a1", agent_type="general-purpose"), 0)
        self.assertEqual(self.hook(agent_id="a2"), 0)
        self.assertFalse((self.q / "observability" / "runner-idle.json").exists())  # no block counted
        self.assertEqual(self.hook(agent_id="a3", agent_type="delivery-runner"), 2)  # the runner itself
        self.assertEqual(self.hook(), 2)
        log = [json.loads(l) for l in (self.q / "observability" / "runner-idle-inputs.jsonl").read_text().splitlines()]
        self.assertEqual(len(log), 4)
        self.assertEqual((log[0]["teammate_name"], log[0]["agent_id"], log[0]["agent_type"]),
                         ("runner", "a1", "general-purpose"))
        self.assertIn("hook_event_name", log[0]["keys"])

    def test_architect_triage_block_waits_on_the_lead(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "architect": {"shape_from_task": "0001", "triage_grace_tasks": 1}}))
        st = {"schema_version": 1, "seen": {}, "reviews": {"ar-20261014T000000Z-abcd": {
            "status": "reported", "mode": "pass", "done": [], "done_at_report": [], "started_at": "2026-10-14T00:00:00Z"}}}
        (self.q / "architect.json").write_text(json.dumps(st))
        self.assertEqual(self.hook(), 0)  # 0001-a merged since the report: next exits 4, triage waits on the lead
        st["reviews"]["ar-20261014T000000Z-abcd"]["status"] = "triaged"
        (self.q / "architect.json").write_text(json.dumps(st))
        self.assertEqual(self.hook(), 2)

    def architect_waiting(self, *, wait="operator_step", held=True, holder="runner", every_n_tasks=1, reviews=None,
                          **work):
        """Two tasks in flight at most, the architect adopted, 0001-a and 0003-c merged since the adoption point
        (a pass due at `every_n_tasks` 1), and 0002-b, the scope's one open task, waiting on `wait`; `holder`
        holds it (claimed) when `held`. `work` adds keys to work.json."""
        self.prod.task("0003-c", status="done")
        self.prod.index()
        self.prod.write("docs/delivery/plane.json", json.dumps({
            "project_id": "demo", "parallel": {"max_in_flight": 2},
            "architect": {"shape_from_task": "0001", "every_n_tasks": every_n_tasks}}))
        (self.q / "architect.json").write_text(json.dumps({"schema_version": 1, "seen": {}, "reviews": reviews or {}}))
        (self.q / "tasks" / "0002-b.json").write_text(json.dumps(
            {"task_id": "0002-b", "waiting_on": wait, **({"lease_holder": holder} if held else {})}))
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "in_flight": ["0002-b"] if held else [], **work}))

    def test_a_due_pass_keeps_a_runner_whose_held_tasks_wait_working(self):
        self.architect_waiting()
        self.assertEqual(self.hook(), 2)
        self.assertIn("ccp architect run --detach", self.stderr)

    def test_a_triage_overdue_lets_a_runner_whose_held_tasks_wait_idle(self):
        self.architect_waiting(reviews={"ar-20261014T000000Z-abcd": {
            "status": "reported", "mode": "pass", "done": [], "done_at_report": [], "started_at": "2026-10-14T00:00:00Z"}})
        self.assertEqual(self.hook(), 0)

    def test_no_pass_due_lets_a_runner_whose_held_tasks_wait_idle(self):
        self.architect_waiting(every_n_tasks=4)
        self.assertEqual(self.hook(), 0)

    def test_a_due_pass_leaves_a_runner_holding_nothing_idle(self):
        self.architect_waiting(held=False)
        self.prod.task("0004-d")
        self.prod.task("0002-b", deps=["0004-d"])  # `next` names no task either: a due pass blocks it at once
        self.prod.index()
        self.assertEqual(self.hook(), 0)

    def test_a_due_pass_keeps_only_the_slot_whose_held_tasks_wait_working(self):
        """With several slots, the waiting task runner-1 holds is not runner-2's: runner-2 holds nothing."""
        self.architect_waiting(holder="runner-1", runners={"runner-1": {}, "runner-2": {}})
        self.assertEqual(self.hook("runner-2"), 0)
        self.assertEqual(self.hook("runner-1"), 2)
        self.assertIn("ccp architect run --detach", self.stderr)

    def test_a_held_quota_wait_lets_the_runner_idle_with_a_pass_due(self):
        self.architect_waiting(wait="quota")
        self.assertEqual(self.hook(), 0)

    def test_after_a_rotation_only_the_bound_runner_is_kept_working(self):
        """§10.2: the old runner, idling under the binding's name, is no longer nudged."""
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "runner": "runner-2"}))
        self.assertEqual(self.hook("runner", agent_id="arunner-old", agent_type="runner"), 0)
        self.assertFalse((self.q / "observability" / "runner-idle.json").exists())  # no block counted
        self.assertEqual(self.hook("runner-2", agent_id="arunner-2", agent_type="runner-2"), 2)
        self.assertEqual(self.hook("runner-2"), 2)
        self.assertEqual(self.hook("runner-2", agent_id="a9", agent_type="ccp:delivery-implementer"), 0)

    def test_unbound_after_a_rotation_nudges_no_one(self):
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "runner_bind_pending": True}))
        self.assertEqual(self.hook("runner"), 0)
        self.assertEqual(self.hook("runner-2"), 0)
        (self.q / "work.json").write_text(json.dumps([]))  # not an object: every teammate idles, no traceback
        self.assertEqual(self.hook("reviewer"), 0)

    def test_the_queue_settles_a_task_a_stale_worktree_still_shows_open(self):
        """The hook reads task files in a runner's worktree, maybe behind master."""
        (self.q / "tasks" / "0002-b.json").write_text(json.dumps({"task_id": "0002-b", "status": "done"}))
        self.assertEqual(self.hook(), 0)  # merged per the queue: never nudged toward it
        (self.q / "tasks" / "0002-b.json").write_text(json.dumps({"task_id": "0002-b", "status": "pending"}))
        f = self.prod.root / "docs/delivery/tasks/0001-a.md"
        f.write_text(f.read_text().replace("status: done", "status: pending"))  # the worktree lags on 0001-a
        self.prod.index()
        (self.q / "tasks" / "0001-a.json").write_text(json.dumps({"task_id": "0001-a", "status": "done"}))
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "scope": ["0001-a", "0002-b"]}))
        self.assertEqual(self.hook(), 2)  # 0002-b's dependency is done per the queue: ready
        (self.q / "tasks" / "0001-a.json").write_text(json.dumps({"task_id": "0001-a", "status": "dropped"}))
        self.assertEqual(self.hook(), 0)  # a dropped dependency meets nothing, as `ccp tasks next` judges it

    def test_rotation_due_lets_go(self):
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-b"], "runner_tasks_done": 4}))
        self.assertEqual(self.hook(), 0)


AGENT_MODELS = {  # SPEC §2.4 *Models and effort*: (model, effort); every seat pinned (operator, 2026-10-21)
    "delivery-runner": ("claude-sonnet-5-5", "high"),
    "delivery-implementer": ("claude-opus-5-5", "high"),
    "delivery-reviewer": ("claude-opus-5-5", "high"),
    "delivery-verifier": ("claude-sonnet-5-5", "high"),
}


class TestQueueFromTheBinding(unittest.TestCase):
    """SPEC §9.2: with QUEUE_ROOT unset, the seat scripts take the queue `ccp where` prints for the product
    (CLAUDE_PROJECT_DIR, else the working directory); with no binding naming it they stop and say what to do."""

    def setUp(self):
        from tests.sandbox_fixture import SandboxCase
        case = SandboxCase()
        case.setUp()
        self.addCleanup(case.tearDown)
        self.sandbox = json.loads(case.ccp("sandbox", "create", str(case.base / "S")).stdout)
        self.env = {**case.env, "PROJECT_YAML": self.sandbox["binding"], "CCP_NO_BINDING_QUEUE": ""}
        self.env.pop("CLAUDE_PROJECT_DIR", None)
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.scratch)], check=True, capture_output=True)

    def run_in(self, cwd, script, *argv, **env):
        return subprocess.run(["bash", str(script), *argv], cwd=cwd, capture_output=True, text=True,
                              env={**self.env, **env})

    def test_team_sh_finds_the_queue_of_the_product_it_runs_in(self):
        r = self.run_in(self.sandbox["root"], TEAM, "runner", "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("work", json.loads(r.stdout))
        self.assertNotIn("set QUEUE_ROOT", r.stderr)

    def test_claude_project_dir_names_the_product_ahead_of_the_working_directory(self):
        r = self.run_in(self.scratch, TEAM, "runner", "status", CLAUDE_PROJECT_DIR=self.sandbox["root"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("work", json.loads(r.stdout))

    def test_where_no_binding_names_the_product_it_says_to_init_or_set_queue_root(self):
        for script, argv in ((TEAM, ("runner", "status")), (ASK, ("blocked",))):
            r = self.run_in(self.scratch, script, *argv)
            self.assertNotEqual(r.returncode, 0, script)
            self.assertIn("ccp init", r.stderr, script)
            self.assertIn("QUEUE_ROOT", r.stderr, script)
            self.assertEqual(r.stdout, "", script)

    def test_queue_root_when_set_wins_over_the_binding(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        (Path(other.name) / "work.json").write_text(json.dumps({"status": "idle", "scope": ["0042-elsewhere"]}))
        r = self.run_in(self.sandbox["root"], TEAM, "runner", "status", QUEUE_ROOT=other.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["work"]["scope"], ["0042-elsewhere"])


class TestKeepBodyImport(unittest.TestCase):
    """§23.8: `keep_body` reads the product's plane.json through ccp's config, which it puts on the import
    path once, not on every audit write."""

    def test_repeated_calls_leave_the_import_path_as_the_first_left_it(self):
        import importlib.util
        import sys
        from unittest import mock
        prod = Product({"prompts": {"keep_body": True}})
        self.addCleanup(prod.cleanup)
        q = tempfile.TemporaryDirectory()
        self.addCleanup(q.cleanup)
        (Path(q.name) / "project.yaml").write_text(binding(product_root=prod.root))
        with mock.patch.object(sys, "path", list(sys.path)):
            spec = importlib.util.spec_from_file_location("team_keep_body", PLANE / "scripts/observability/team.py")
            team = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(team)
            self.assertEqual(team.keep_body(Path(q.name)), ["--keep-body"])
            after_one = list(sys.path)
            for _ in range(3):
                self.assertEqual(team.keep_body(Path(q.name)), ["--keep-body"])
            self.assertEqual(sys.path, after_one)
            self.assertIn(str(PLANE), sys.path)


class TestAgentModels(unittest.TestCase):
    """Every Claude team agent pins a full model id (an alias would take the lead's [1m] suffix) and
    its effort, so nothing depends on the lead session's settings."""

    def front(self, name):
        text = (PLANE / "plugin" / "agents" / f"{name}.md").read_text()
        self.assertTrue(text.startswith("---\n"), name)
        from ccp import runs  # noqa: PLC0415
        return runs.agent_frontmatter(text)

    def test_models_and_effort_pinned(self):
        for name, (model, effort) in AGENT_MODELS.items():
            f = self.front(name)
            self.assertEqual((f["name"], f["model"], f.get("effort")), (name, model, effort), name)

    def test_runner_launches_workers_by_type_with_a_model_only_as_printed(self):
        brief = (PLANE / "plugin" / "agents" / "delivery-runner.md").read_text()
        for worker in ("delivery-implementer", "delivery-reviewer", "delivery-verifier"):
            self.assertIn(f"`{worker}` subagent", brief)
        self.assertIn("Pass `model` in the Agent call\nonly when `ccp prompt` prints it", brief)  # §2.4

    def test_a_single_runner_is_told_to_make_its_missing_worktree_with_ccp(self):
        brief = (PLANE / "plugin" / "agents" / "delivery-runner.md").read_text()
        single = brief.split("## Several runners", 1)[0]  # §12.1: the part a runner with no slot follows
        self.assertIn("`ccp tasks worktree`", single)


class TestArchitectInTemplates(unittest.TestCase):
    """SPEC docs/design/architect.md #7 and §19.9: the runner handles `next`'s exit 4, records friction and
    metrics, and gives implementers the house rules; every worker reports friction."""

    def brief(self, name):
        return " ".join((PLANE / "plugin" / "agents" / f"{name}.md").read_text().split())

    def test_acceptance_7_runner_handles_exit_4(self):
        b = self.brief("delivery-runner")
        self.assertIn("**Exit 4: the architect blocks `next`**", b)
        self.assertIn("exits 4 with \"architect pass due: …\":** run `ccp architect run --detach`", b)
        self.assertIn("exits 4 with \"… awaits triage\":** run `ccp architect triage <id>` and send the lead", b)
        self.assertIn("then ask `next` again", b)
        # §10.3: the worker's `ccp report` records what the runner used to copy (§13.4),
        # and `ccp prompt` gives every worker the house rules.
        self.assertIn("`ccp report <run_id> <report path>`", b)
        self.assertIn("(SPEC §13.4)", b)
        common = (PLANE / "templates" / "prompts" / "_common.md").read_text()
        self.assertIn("{{#rules_doc}}- Read the house rules, {{rules_doc}}", common)

    def test_workers_read_the_rules(self):
        for w in ("delivery-implementer", "delivery-reviewer", "delivery-verifier"):
            self.assertIn("architect.rules_doc", self.brief(w), w)


class TheRunnerSpawnFollowsCcpsDefault(TeamCase):
    """SPEC §16.2: `runner spawn` asks ccp's loaded configuration for parallel.max_in_flight, so a product
    with no `parallel` block gets the default `ccp` has, not one of the spawn's own."""

    def setUp(self):
        super().setUp()
        # The subject is a missing `parallel` block: the plane.json `Product(bare=True)` writes.
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo"}))

    def test_a_product_with_no_parallel_block_gets_the_slots_ccps_default_gives(self):
        self.patch_default("PARALLEL_DEFAULTS", "max_in_flight", 1)
        code, _, err = self.team("runner", "spawn", "--scope", "0001-a,0002-b", "--count", "2")
        self.assertEqual(code, 2, err)  # ccp's default, set to one slot here
        self.assertIn("max_in_flight", err)
        self.patch_default("PARALLEL_DEFAULTS", "max_in_flight", 2)
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a,0002-b", "--count", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(res["slots"], ["runner-1", "runner-2"])


class TestSync(TeamCase):
    def test_installs_agent_and_executable_hook(self):
        yml = self.q / "project.yaml"
        r = subprocess.run(["bash", str(PLANE / "scripts" / "sync-product-docs.sh"), "demo", "--project-yaml", str(yml),
                            "--allow-dirty"], capture_output=True, text=True)
        if "is not committed" in r.stderr:
            self.skipTest("templates not committed yet")
        self.assertEqual(r.returncode, 0, r.stderr)
        for name, (model, _) in AGENT_MODELS.items():
            agent = (self.prod.root / f".claude/agents/{name}.md").read_text()
            self.assertTrue(agent.startswith(f"---\nname: {name}\n"), name)
            self.assertIn(f"\nmodel: {model}\n", agent)
        hook = self.prod.root / ".claude/hooks/runner-idle.sh"
        lines = hook.read_text().splitlines()
        self.assertEqual(lines[0], "#!/usr/bin/env bash")
        self.assertTrue(lines[1].startswith("# Managed copy of control-plane `plugin/hooks/runner-idle.sh`"))
        self.assertTrue(os.access(hook, os.X_OK))
        chk = subprocess.run(["bash", str(PLANE / "scripts" / "sync-product-docs.sh"), "demo", "--project-yaml", str(yml),
                              "--check"], capture_output=True, text=True)
        self.assertNotIn("DRIFT .claude/hooks", chk.stdout)

    def test_the_rules_doc_note_names_the_path_ccps_default_gives(self):
        """The note on a missing `architect.rules_doc` takes the path from ccp's loaded configuration."""
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "architect": {"shape_from_task": "0001"}}))
        self.patch_default("ARCHITECT_DEFAULTS", "rules_doc", "docs/HOUSE-RULES.md")
        yml = self.q / "project.yaml"
        chk = subprocess.run(["bash", str(PLANE / "scripts" / "sync-product-docs.sh"), "demo", "--project-yaml", str(yml),
                              "--check"], capture_output=True, text=True, env=self.env)
        if "is not committed" in chk.stderr:
            self.skipTest("templates not committed yet")
        self.assertIn("plane.json architect.rules_doc docs/HOUSE-RULES.md does not exist", chk.stdout)

    def test_architect_skill_replaces_the_two_old_ones(self):
        yml = self.q / "project.yaml"
        sync = ["bash", str(PLANE / "scripts" / "sync-product-docs.sh"), "demo", "--project-yaml", str(yml), "--allow-dirty"]
        header = "> Managed copy of control-plane `plugin/skills/docs-audit/SKILL.md` at abc1234. Edit it.\n"
        self.prod.write(".claude/skills/docs-audit/SKILL.md", "---\nname: docs-audit\n---\n\n" + header)
        self.prod.write(".claude/skills/architecture-review/SKILL.md", "---\nname: architecture-review\n---\nmine\n")
        chk = subprocess.run(sync[:-1] + ["--check"], capture_output=True, text=True)
        if "is not committed" in chk.stderr:
            self.skipTest("templates not committed yet")
        self.assertIn("DRIFT .claude/skills/docs-audit/SKILL.md: retired", chk.stdout)
        r = subprocess.run(sync, capture_output=True, text=True)
        if "is not committed" in r.stderr:
            self.skipTest("templates not committed yet")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.prod.root / ".claude/skills/architect/SKILL.md").read_text().startswith("---\nname: architect\n"))
        self.assertFalse((self.prod.root / ".claude/skills/docs-audit").exists())
        # a copy without the managed header is the product's own: left alone, with a note
        self.assertTrue((self.prod.root / ".claude/skills/architecture-review/SKILL.md").is_file())
        self.assertIn("no managed-copy header; left alone", r.stdout)


if __name__ == "__main__":
    unittest.main()
