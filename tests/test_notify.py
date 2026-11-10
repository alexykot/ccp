"""Notifying the operator (SPEC §3.6, §17.10): the plane's triggers, and the product's `notify` command
that `ccp` runs on each with the trigger and ids only; with none, nothing runs."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, tasklog
from tests.helpers import Product
from tests.test_toolkit import ToolkitFixture, git

# One line per run: the trigger, project, task, id, reason, and the line ccp composes, `|`-separated
APPEND = ('printf \'%s|%s|%s|%s|%s|%s\\n\' "$CCP_NOTIFY_TRIGGER" "$CCP_PROJECT_ID" "$CCP_TASK_ID" '
          '"$CCP_NOTIFY_ID" "$CCP_NOTIFY_REASON" "$CCP_NOTIFY_LINE" >> "$NOTIFY_OUT"')
TASK_FILE = "docs/delivery/tasks/0002-second.md"


def sent(out: Path) -> list[list[str]]:
    return [x.split("|") for x in out.read_text().splitlines()] if out.is_file() else []


class Channel(ToolkitFixture, unittest.TestCase):
    """A scratch product whose notify command appends a line to a file."""

    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "notify": {"command": APPEND}}

    def setUp(self):
        super().setUp()
        self.out = Path(self._tmp.name) / "notified.txt"
        self.out_env = mock.patch.dict(os.environ, {"NOTIFY_OUT": str(self.out)})
        self.out_env.start()
        self.addCleanup(self.out_env.stop)

    def set_plane(self, **blocks) -> None:
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg.update(blocks)
        self.write("docs/delivery/plane.json", json.dumps(cfg))

    # ------------------------------------------------------------------ blocker and decision

    def test_a_blocker_reaches_the_channel_once(self):
        self.assertEqual(self.ccp("tasks", "claim", "0002", root=self.main)[0], 0)
        code, body, out, err = self.ccp("tasks", "wait", "0002", "operator_step", "--detail", "a live upgrade",
                                        root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(sent(self.out), [["blocker", "demo", "0002-second", "", "operator_step",
                                           "blocker project=demo task=0002-second reason=operator_step"]])
        self.assertEqual((body["notified"]["trigger"], body["notified"]["exit"]), ("blocker", 0))

    def test_reauth_is_a_blocker_and_operator_decision_a_decision(self):
        self.ccp("tasks", "wait", "0002", "reauth", root=self.main)
        self.ccp("tasks", "wait", "0002", "operator_decision", "--detail", "free text, never sent", root=self.main)
        self.assertEqual([(r[0], r[2], r[4]) for r in sent(self.out)],
                         [("blocker", "0002-second", "reauth"), ("decision", "0002-second", "operator_decision")])
        self.assertNotIn("free text", self.out.read_text())

    def test_the_lead_s_waits_quota_and_a_resume_are_not_triggers(self):
        for reason in ("design_seat", "spec_maintainer", "quota", "runner"):
            code, body, out, err = self.ccp("tasks", "wait", "0002", reason, root=self.main)
            self.assertEqual(code, 0, out + err)
            self.assertNotIn("notified", body)
        self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        self.ccp("tasks", "resume", "0002", "done by hand", root=self.main)
        self.assertEqual([r[0] for r in sent(self.out)], ["blocker"])

    def test_a_failing_command_warns_and_the_wait_stands(self):
        self.set_plane(notify={"command": "exit 3"})
        self.assertEqual(self.ccp("tasks", "claim", "0002", root=self.main)[0], 0)
        code, body, out, err = self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["notified"]["exit"], 3)
        self.assertTrue(body["warnings"][0].startswith("notify:"), body["warnings"])
        state = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertEqual(state["waiting_on"], "operator_step")

    def test_a_command_past_its_timeout_is_killed_and_warns(self):
        self.set_plane(notify={"command": "sleep 20", "timeout_seconds": 1})
        code, body, out, err = self.ccp("tasks", "wait", "0002", "reauth", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["notified"]["exit"], 124)
        self.assertIn("timed out", body["warnings"][0])

    def test_a_command_that_reads_stdin_gets_an_empty_one_not_ccp_s(self):
        # ccp's own stdin is a pipe nobody closes: a command reading it would wait out its timeout
        self.set_plane(notify={"command": f"cat >/dev/null && {APPEND}", "timeout_seconds": 10})
        r, w = os.pipe()
        saved = os.dup(0)
        os.dup2(r, 0)
        try:
            started = time.monotonic()
            code, body, out, err = self.ccp("tasks", "wait", "0002", "reauth", root=self.main)
            took = time.monotonic() - started
        finally:
            os.dup2(saved, 0)
            for fd in (saved, r, w):
                os.close(fd)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["notified"]["exit"], 0)
        self.assertLess(took, 5)
        self.assertEqual([r[0] for r in sent(self.out)], ["blocker"])

    # ------------------------------------------------------------------ allowance checkpoint

    def test_a_claim_refused_at_the_weekly_checkpoint_notifies(self):
        reading = Path(self._tmp.name) / "reading.json"
        reading.write_text(json.dumps({"five_hour": {"utilization": 10}, "seven_day": {"utilization": 90}}))
        self.set_plane(telemetry={"allowance_cmd": f"cat '{reading}'", "allowance_stop_weekly": 80})
        code, _, _, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 5, err)
        self.assertEqual([(r[0], r[2]) for r in sent(self.out)], [("allowance_checkpoint", "0002-second")])

    def test_a_failing_command_at_the_checkpoint_adds_its_warning_to_the_refusal(self):
        reading = Path(self._tmp.name) / "reading.json"
        reading.write_text(json.dumps({"five_hour": {"utilization": 10}, "seven_day": {"utilization": 90}}))
        self.set_plane(telemetry={"allowance_cmd": f"cat '{reading}'", "allowance_stop_weekly": 80},
                       notify={"command": "exit 3"})
        code, _, _, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 5, err)
        self.assertIn("notify:", err)

    def test_a_claim_under_the_checkpoint_notifies_nothing(self):
        reading = Path(self._tmp.name) / "reading.json"
        reading.write_text(json.dumps({"five_hour": {"utilization": 10}, "seven_day": {"utilization": 20}}))
        self.set_plane(telemetry={"allowance_cmd": f"cat '{reading}'", "allowance_stop_weekly": 80})
        self.assertEqual(self.ccp("tasks", "claim", "0002", root=self.main)[0], 0)
        self.assertEqual(sent(self.out), [])

    # ------------------------------------------------------------------ review point done

    def tag(self, *tids: str) -> None:
        """Give each task `review_point: R1`, commit and push it, and bring the runner worktree along."""
        for tid in tids:
            p = next((self.main / "docs/delivery/tasks").glob(f"{tid}-*.md"))
            p.write_text(p.read_text().replace("depends_on:", "review_point: R1\ndepends_on:", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", "-A", "docs/delivery")
        git(self.main, "commit", "-q", "-m", "tag R1")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def test_the_close_that_finishes_a_review_point_notifies_once(self):
        self.tag("0001", "0002")
        self._to_approved_pr()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([(r[0], r[2], r[3]) for r in sent(self.out)], [("review_point_done", "0002-second", "R1")])
        self.assertEqual(body["notified"]["trigger"], "review_point_done")
        self.ccp("tasks", "close", "0002", "--pr", "7")  # a re-run finds the reconcile done: nothing more
        self.assertEqual(len(sent(self.out)), 1)

    def test_the_retry_of_a_close_that_crashed_after_its_reconcile_notifies_once(self):
        self.tag("0001", "0002")
        self._to_approved_pr()
        with mock.patch("ccp.lifecycle._cleanup", side_effect=RuntimeError("crashed")):
            code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("status: done", git(self.main, "show", "origin/main:" + TASK_FILE))  # the reconcile landed
        self.assertNotEqual(json.loads((self.q / "tasks/0002-second.json").read_text())["status"], "done")
        self.assertEqual(sent(self.out), [])
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["reconciled_now"])
        self.assertEqual([(r[0], r[3]) for r in sent(self.out)], [("review_point_done", "R1")])
        self.ccp("tasks", "close", "0002", "--pr", "7")  # the queue says done now: nothing more
        self.assertEqual(len(sent(self.out)), 1)

    def test_a_close_that_leaves_its_review_point_open_notifies_nothing(self):
        self.write("docs/delivery/tasks/0003-third.md",
                   (self.main / TASK_FILE).read_text().replace("0002-second", "0003-third"))
        self.tag("0002", "0003")
        self._to_approved_pr()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("notified", body)
        self.assertEqual(sent(self.out), [])


class NoChannel(ToolkitFixture, unittest.TestCase):
    """No notify block: the lead's session, as before; no command runs."""

    def test_a_blocker_is_raised_as_today_and_nothing_runs(self):
        out = Path(self._tmp.name) / "notified.txt"
        with mock.patch.dict(os.environ, {"NOTIFY_OUT": str(out)}), \
                mock.patch("ccp.wt.run_cmd", side_effect=AssertionError("a command ran")):
            self.assertEqual(self.ccp("tasks", "claim", "0002", root=self.main)[0], 0)
            code, body, o, err = self.ccp("tasks", "wait", "0002", "operator_step", root=self.main)
        self.assertEqual(code, 0, o + err)
        self.assertNotIn("notified", body)
        self.assertNotIn("warnings", body)
        self.assertEqual(json.loads((self.q / "tasks/0002-second.json").read_text())["waiting_on"], "operator_step")
        self.assertFalse(out.exists())


    def test_a_claim_refused_at_the_checkpoint_is_refused_as_today_and_nothing_runs(self):
        reading = Path(self._tmp.name) / "reading.json"
        reading.write_text(json.dumps({"five_hour": {"utilization": 10}, "seven_day": {"utilization": 90}}))
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["telemetry"] = {"allowance_cmd": f"cat '{reading}'", "allowance_stop_weekly": 80}
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        with mock.patch("ccp.wt.run_cmd", side_effect=AssertionError("a command ran")):
            code, _, _, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 5, err)
        self.assertIn("allowance checkpoint", err)
        self.assertNotIn("notify:", err)


class Config(unittest.TestCase):
    def load(self, notify):
        p = Product({"notify": notify})
        self.addCleanup(p.cleanup)
        return config.load(p.root)

    def test_the_block_defaults_to_no_command(self):
        p = Product()
        self.addCleanup(p.cleanup)
        self.assertEqual(config.load(p.root).notify, {"command": None, "timeout_seconds": 30})

    def test_an_unknown_trigger_is_a_programming_error(self):
        from ccp import notify
        with self.assertRaises(ValueError):
            notify.send(self.load({"command": "true"}), "lunch")

    def test_a_bad_block_is_refused(self):
        for bad in ({"command": ""}, {"command": 3}, {"timeout_seconds": 0}, {"timeout_seconds": True},
                    {"channel": "mail"}, "mail"):
            with self.subTest(bad=bad), self.assertRaises(config.ConfigError):
                self.load(bad)
        self.assertEqual(self.load({"command": "notify-me", "timeout_seconds": 5}).notify["timeout_seconds"], 5)


PLANE = Path(__file__).resolve().parents[1]


class Gates(unittest.TestCase):
    """A decision taken to the operator: `team.sh gate ask-operator` and a `needs_operator` answer."""

    def setUp(self):
        self.prod = Product({"notify": {"command": APPEND}})
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

    def run_script(self, script: str, *argv: str) -> dict:
        r = subprocess.run(["bash", str(PLANE / "scripts" / script), *argv], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_a_gate_taken_to_the_operator_notifies_a_decision(self):
        eid = self.run_script("team.sh", "gate", "open", "--task-id", "0001-a", "--class", "spend",
                              "--brief", "a paid cycle")["escalation_id"]
        self.assertEqual(sent(self.out), [])  # a gate for the lead is not the operator's
        self.run_script("team.sh", "gate", "ask-operator", eid)
        self.assertEqual([(r[0], r[2], r[3]) for r in sent(self.out)], [("decision", "0001-a", eid)])
        self.assertNotIn("paid cycle", self.out.read_text())

    def test_a_binding_with_no_product_root_sends_nothing(self):
        (self.q / "project.yaml").write_text("project_id: demo\n")
        eid = self.run_script("team.sh", "gate", "open", "--task-id", "0001-a", "--class", "spend",
                              "--brief", "a paid cycle")["escalation_id"]
        res = self.run_script("team.sh", "gate", "ask-operator", eid)
        self.assertNotIn("warnings", res)
        self.assertEqual(sent(self.out), [])

    def test_an_unreadable_plane_json_warns_and_the_gate_still_goes_to_the_operator(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "notify": {"command": 3}}))
        eid = self.run_script("team.sh", "gate", "open", "--task-id", "0001-a", "--class", "spend",
                              "--brief", "a paid cycle")["escalation_id"]
        res = self.run_script("team.sh", "gate", "ask-operator", eid)
        self.assertEqual(res["outcome"], "waiting_operator")
        self.assertTrue(res["warnings"][0].startswith("notify:"), res)
        self.assertEqual(sent(self.out), [])

    def test_a_needs_operator_answer_notifies_once(self):
        res = self.run_script("spec-maintainer-ask.sh", "raise", "--raised-by", "task-runner", "--task-id", "0001-a",
                              "--text", "Which?", "--inconsistency", "task vs SPEC", "--spec-refs", "S1", "--tried", "x")
        qid = res["question_id"]
        self.assertEqual(sent(self.out), [])  # a question for the lead is not the operator's
        (self.q / "questions" / f"{qid}.answer.json").write_text(json.dumps({
            "schema_version": 1, "question_id": qid, "project_id": "demo", "verdict": "needs_operator",
            "ruling": None, "reasoning": "product call", "commit_sha": None, "files_changed": [],
            "question_for_operator": "A or B?", "guidance": None, "answered_by": "spec_maintainer",
            "session_id": "lead", "answered_at": "2026-09-30T20:00:00Z", "supersedes": None}))
        self.run_script("spec-maintainer-ask.sh", "process", qid)
        self.run_script("spec-maintainer-ask.sh", "process", qid)
        self.assertEqual([(r[0], r[2], r[3]) for r in sent(self.out)], [("decision", "0001-a", qid)])
        self.assertNotIn("A or B", self.out.read_text())


if __name__ == "__main__":
    unittest.main()
