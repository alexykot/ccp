"""The operator's notices (SPEC §3.6): the plane renders and records them, the lead dispatches over a
configured channel. `ccp notify render | sent | pending`, the `pending` record a trigger writes, and
plane.json `notify.lead`."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ccp import cli, config
from tests.helpers import Product
from tests.test_notify import PLANE, ChannelFixture, sent
from tests.test_toolkit import ToolkitFixture

LEAD = {"tool": "mail-send", "to": "operator@example.invalid"}


class LeadChannel(ToolkitFixture, unittest.TestCase):
    """A scratch product whose plane.json declares a `lead` channel and no command."""

    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "notify": {"lead": LEAD}}

    def notify(self, *args: str, actor: str | None = None):
        env = {"ACTOR": actor} if actor else {}
        with mock.patch.dict(os.environ, env):
            if actor is None:
                os.environ.pop("ACTOR", None)
            return self.ccp("notify", *args, root=self.main)

    def notices(self, op: str) -> list[dict]:
        return [e for e in self.events() if e["type"] == "notify" and e["op"] == op]

    # ------------------------------------------------------------------ render

    def test_render_prints_the_subject_and_one_line_per_id_and_nothing_else(self):
        code, _, out, err = self.notify("render", "decision", "--task", "0001-x", "--id", "0001-x-1")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "[demo] decision: 0001-x\n\nproject: demo\ntrigger: decision\ntask: 0001-x\nid: 0001-x-1\n")

    def test_render_json_gives_the_same_keys(self):
        code, body, out, err = self.notify("render", "decision", "--task", "0001-x", "--id", "0001-x-1", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(body, {"subject": "[demo] decision: 0001-x",
                                "body": "project: demo\ntrigger: decision\ntask: 0001-x\nid: 0001-x-1",
                                "project": "demo", "trigger": "decision", "task": "0001-x", "id": "0001-x-1"})

    def test_render_names_the_id_when_there_is_no_task_and_carries_a_reason(self):
        code, body, _, err = self.notify("render", "review_point_done", "--id", "R1", "--json")
        self.assertEqual((code, body["subject"]), (0, "[demo] review_point_done: R1"), err)
        code, body, _, err = self.notify("render", "other", "--reason", "outage", "--json")
        self.assertEqual((code, body["subject"], body["reason"]), (0, "[demo] other", "outage"), err)

    def test_render_refuses_an_unknown_trigger_and_a_field_of_more_than_one_line(self):
        with self.assertRaises(SystemExit):
            self.notify("render", "lunch")
        code, _, out, err = self.notify("render", "other", "--reason", "one\ntwo")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("one line", err)

    # ------------------------------------------------------------------ sent

    def test_sent_records_the_trigger_ids_channel_and_the_seat(self):
        code, _, _, err = self.notify("sent", "decision", "--task", "0001-x", "--id", "0001-x-1", "--via", "lead")
        self.assertEqual(code, 0, err)
        code, _, _, err = self.notify("sent", "other", "--via", "lead", "--note", "unexpected outage")
        self.assertEqual(code, 0, err)
        got = [e["payload"] for e in self.notices("sent")]
        self.assertEqual(got, [
            {"trigger": "decision", "project": "demo", "task": "0001-x", "id": "0001-x-1", "via": "lead",
             "by": "design-seat", "ok": True},
            {"trigger": "other", "project": "demo", "task": "", "id": "", "via": "lead", "by": "design-seat",
             "ok": True, "note": "unexpected outage"}])

    def test_sent_records_the_seat_it_was_run_as(self):
        code, _, _, err = self.notify("sent", "blocker", "--task", "0002-second", "--via", "lead", actor="task-runner")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.notices("sent")[0]["payload"]["by"], "task-runner")
        self.assertEqual(self.notices("sent")[0]["actor"], "task-runner")

    def test_sent_refuses_other_without_a_note_and_a_note_of_more_than_one_line(self):
        for extra in ([], ["--note", " "], ["--note", "a\nb"], ["--note", "x" * 4001]):
            with self.subTest(extra=extra):
                code, _, _, err = self.notify("sent", "other", "--via", "lead", *extra)
                self.assertEqual(code, 2, err)
        self.assertEqual(self.notices("sent"), [])
        with self.assertRaises(SystemExit):
            self.notify("sent", "decision", "--task", "0002-second")  # --via is required
        with self.assertRaises(SystemExit):
            self.notify("sent", "decision", "--via", "email")

    # ------------------------------------------------------------------ firing and pending

    def test_a_trigger_records_a_pending_notice_and_prints_it_with_the_lead_s_channel(self):
        code, body, out, err = self.ccp("tasks", "wait", "0002", "operator_decision", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("notified", body)  # no command ran
        self.assertEqual([e["payload"] for e in self.notices("pending")],
                         [{"trigger": "decision", "project": "demo", "task": "0002-second", "id": "",
                           "reason": "operator_decision"}])
        self.assertIn("[demo] decision: 0002-second", err)
        self.assertIn("mail-send", err)
        self.assertIn("operator@example.invalid", err)
        self.assertIn("ccp notify sent decision --task 0002-second --via lead", err)

    def test_a_notice_that_cannot_be_recorded_warns_and_the_wait_stands(self):
        from ccp.queue import QueueError
        with mock.patch("ccp.notify.record_pending", side_effect=QueueError("ledger locked", 1)):
            code, body, out, err = self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["warnings"][0].startswith("notify:"), body)
        state = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertEqual(state["waiting_on"], "operator_step")

    def test_pending_lists_a_fired_notice_until_it_is_sent(self):
        self.ccp("tasks", "wait", "0002", "operator_decision", root=self.main)
        code, body, out, err = self.notify("pending")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([(n["trigger"], n["task"], n["id"]) for n in body["pending"]],
                         [("decision", "0002-second", "")])
        self.assertEqual(body["pending"][0]["subject"], "[demo] decision: 0002-second")
        self.assertEqual(self.notify("sent", "decision", "--task", "0002-second", "--via", "lead")[0], 0)
        self.assertEqual(self.notify("pending")[1]["pending"], [])

    def test_a_notice_that_fires_again_is_listed_once_and_again_after_a_send(self):
        self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        rows = self.notify("pending")[1]["pending"]
        self.assertEqual([(n["trigger"], n["fired"]) for n in rows], [("blocker", 2)])
        self.notify("sent", "blocker", "--task", "0002-second", "--via", "lead")
        self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        self.assertEqual([n["fired"] for n in self.notify("pending")[1]["pending"]], [1])

    def test_a_send_clears_only_the_notice_with_its_trigger_task_and_id(self):
        self.ccp("tasks", "wait", "0002", "operator_decision", root=self.main)
        self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        for args in (["blocker", "--task", "0002-second", "--id", "G-1"], ["decision", "--task", "0001-first"]):
            self.notify("sent", *args, "--via", "lead")
        self.assertEqual(sorted(n["trigger"] for n in self.notify("pending")[1]["pending"]), ["blocker", "decision"])

    def test_pending_needs_the_queue(self):
        with mock.patch.dict(os.environ, {"CCP_NO_BINDING_QUEUE": "1"}):
            os.environ.pop("QUEUE_ROOT", None)
            code, _, _, err = self.notify("pending")
        self.assertEqual(code, 2, err)


class CommandChannel(ChannelFixture, unittest.TestCase):
    """With a notify command, `ccp` sends and records the send itself."""

    def notices(self, op: str) -> list[dict]:
        return [e for e in self.events() if e["type"] == "notify" and e["op"] == op]

    def test_a_command_send_is_recorded_by_ccp_and_clears_the_notice(self):
        code, _, out, err = self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual([e["payload"] for e in self.notices("sent")],
                         [{"trigger": "blocker", "project": "demo", "task": "0002-second", "id": "", "via": "command",
                           "by": "task-runner", "ok": True}])
        self.assertEqual(self.ccp("notify", "pending", root=self.main)[1]["pending"], [])
        self.assertIn("sent by the product's notify command", err)

    def test_a_failed_command_send_is_recorded_not_ok_and_the_notice_stays_pending(self):
        self.set_plane(notify={"command": "exit 3"})
        code, body, out, err = self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["warnings"][0].startswith("notify:"))
        self.assertEqual([e["payload"]["ok"] for e in self.notices("sent")], [False])
        self.assertEqual([n["trigger"] for n in self.ccp("notify", "pending", root=self.main)[1]["pending"]],
                         ["blocker"])

    def test_the_review_point_close_records_its_notice(self):
        self.tag("0001", "0002")
        self._to_approved_pr()
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([(e["payload"]["trigger"], e["payload"]["id"]) for e in self.notices("pending")],
                         [("review_point_done", "R1")])


class NoCommand(ChannelFixture, unittest.TestCase):
    """No channel at all: the notice is still on record and printed for the lead's session."""

    PLANE_JSON = {k: v for k, v in ChannelFixture.PLANE_JSON.items() if k != "notify"}

    def triggers(self) -> list[str]:
        return [e["payload"]["trigger"] for e in self.events() if e["type"] == "notify" and e["op"] == "pending"]

    def test_a_close_that_finishes_its_review_point_records_a_notice_with_no_channel(self):
        self.tag("0001", "0002")
        self._to_approved_pr()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("notified", body)
        self.assertEqual(self.triggers(), ["review_point_done"])
        self.ccp("tasks", "close", "0002", "--pr", "7")  # a re-run records nothing more
        self.assertEqual(self.triggers(), ["review_point_done"])

    def test_a_claim_refused_at_the_checkpoint_records_a_notice_for_the_lead_s_session(self):
        reading = Path(self._tmp.name) / "reading.json"
        reading.write_text(json.dumps({"five_hour": {"utilization": 10}, "seven_day": {"utilization": 90}}))
        self.set_plane(telemetry={"allowance_cmd": f"cat '{reading}'", "allowance_stop_weekly": 80})
        code, _, _, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 5, err)
        self.assertEqual(self.triggers(), ["allowance_checkpoint"])
        self.assertIn("channel: the lead's session", err)


class LeadConfig(unittest.TestCase):
    def load(self, notify):
        p = Product({"notify": notify})
        self.addCleanup(p.cleanup)
        return config.load(p.root)

    def test_a_lead_channel_needs_exactly_a_tool_and_a_to(self):
        for bad in ({"tool": "x"}, {"to": "y"}, {"tool": "x", "to": "y", "cc": "z"}, {"tool": "", "to": "y"},
                    {"tool": "x", "to": " "}, {"tool": 3, "to": "y"}, {"tool": "x", "to": "a\nb"}, "mail", []):
            with self.subTest(bad=bad), self.assertRaisesRegex(config.ConfigError, r"notify\.lead"):
                self.load({"lead": bad})
        self.assertEqual(self.load({"lead": {"tool": "x", "to": "y"}}).notify["lead"], {"tool": "x", "to": "y"})
        self.assertIsNone(self.load({"command": "notify-me"}).notify["lead"])

    def test_tasks_check_refuses_a_malformed_lead_channel_by_name(self):
        for bad in ({"tool": "x"}, {"tool": "x", "to": "y", "channel": "z"}):
            p = Product({"notify": {"lead": bad}})
            self.addCleanup(p.cleanup)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = cli.main(["--root", str(p.root), "tasks", "check"])
            self.assertEqual(code, 2, out.getvalue())
            self.assertIn("notify.lead", err.getvalue())


class Contract(unittest.TestCase):
    def test_the_ledger_contract_and_its_validator_accept_the_notify_events(self):
        from ccp import queue
        schema = json.loads((PLANE / "contracts/observability_event.schema.json").read_text())
        self.assertIn("notify", schema["properties"]["type"]["enum"])
        self.assertTrue({"pending", "sent"} <= set(schema["properties"]["op"]["enum"]))
        ev = {"at": "2026-11-11T00:00:00Z", "project_id": "demo", "task_id": "", "actor": "design-seat",
              "type": "notify", "op": "sent", "payload": {"trigger": "other"}}
        self.assertTrue(any("payload missing" in e for e in queue.lib.validate_event(ev)))
        ev["payload"] = {"trigger": "other", "project": "demo", "task": "", "id": "", "via": "lead",
                         "by": "design-seat", "ok": True}
        self.assertEqual(queue.lib.validate_event(ev), [])


class Gates(unittest.TestCase):
    """A decision taken to the operator from the team scripts records its notice, as the lead."""

    def setUp(self):
        self.prod = Product({"notify": {"lead": LEAD}})
        self.addCleanup(self.prod.cleanup)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.q = Path(tmp.name) / "queue"
        (self.q / "tasks").mkdir(parents=True)
        (self.q / "project.yaml").write_text(f"project_id: demo\nproduct_root: {self.prod.root}\n")
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle"}))
        (self.q / "tasks/0001-a.json").write_text(json.dumps({"task_id": "0001-a", "waiting_on": None}))
        self.out = Path(tmp.name) / "notified.txt"
        self.env = {**os.environ, "QUEUE_ROOT": str(self.q), "NOTIFY_OUT": str(self.out)}
        self.env.pop("PROJECT_YAML", None)

    def run_script(self, *argv: str) -> subprocess.CompletedProcess:
        r = subprocess.run(["bash", str(PLANE / "scripts/team.sh"), *argv], capture_output=True, text=True,
                           env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_ask_operator_records_a_pending_decision_and_prints_it(self):
        eid = json.loads(self.run_script("gate", "open", "--task-id", "0001-a", "--class", "spend",
                                         "--brief", "a paid cycle").stdout)["escalation_id"]
        r = self.run_script("gate", "ask-operator", eid)
        evs = [json.loads(x) for x in (self.q / "observability/events.jsonl").read_text().splitlines()]
        got = [(e["actor"], e["payload"]) for e in evs if e["type"] == "notify"]
        self.assertEqual(got, [("design-seat", {"trigger": "decision", "project": "demo", "task": "0001-a",
                                                "id": eid, "reason": ""})])
        self.assertIn("[demo] decision: 0001-a", r.stderr)
        self.assertNotIn("paid cycle", r.stderr)
        self.assertEqual(sent(self.out), [])  # no command: nothing ran

    def test_a_needs_operator_answer_records_one_pending_decision(self):
        r = subprocess.run(["bash", str(PLANE / "scripts/spec-maintainer-ask.sh"), "raise", "--raised-by", "task-runner",
                            "--task-id", "0001-a", "--text", "Which?", "--inconsistency", "task vs SPEC",
                            "--spec-refs", "S1", "--tried", "x"], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        qid = json.loads(r.stdout)["question_id"]
        (self.q / "questions" / f"{qid}.answer.json").write_text(json.dumps({
            "schema_version": 1, "question_id": qid, "project_id": "demo", "verdict": "needs_operator",
            "ruling": None, "reasoning": "product call", "commit_sha": None, "files_changed": [],
            "question_for_operator": "A or B?", "guidance": None, "answered_by": "spec_maintainer",
            "session_id": "lead", "answered_at": "2026-09-30T20:00:00Z", "supersedes": None}))
        for _ in range(2):
            r = subprocess.run(["bash", str(PLANE / "scripts/spec-maintainer-ask.sh"), "process", qid],
                               capture_output=True, text=True, env=self.env)
            self.assertEqual(r.returncode, 0, r.stderr)
        evs = [json.loads(x) for x in (self.q / "observability/events.jsonl").read_text().splitlines()]
        got = [(e["payload"]["trigger"], e["payload"]["task"], e["payload"]["id"]) for e in evs if e["type"] == "notify"]
        self.assertEqual(got, [("decision", "0001-a", qid)])
        self.assertNotIn("A or B", (self.q / "observability/events.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
