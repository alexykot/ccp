"""SPEC §10.4 `ccp tasks release`: a claim taken too early is undone. The task goes back to pending,
its lease and wait cleared and each recorded, and it leaves work.json; a task with a PR or an open
run is refused."""
from __future__ import annotations

import json
import time
import unittest

from ccp import backfill, cli, drill, health
from tests.test_toolkit import ToolkitFixture


class Release(ToolkitFixture, unittest.TestCase):
    def state(self) -> dict:
        return json.loads((self.q / "tasks/0002-second.json").read_text())

    def work(self) -> dict:
        return json.loads((self.q / "work.json").read_text())

    def claimed_and_waiting(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "wait", "0002", "design_seat")
        self.assertEqual(code, 0, out + err)

    def test_a_claimed_task_goes_back_to_pending(self):
        self.claimed_and_waiting()
        code, body, out, err = self.ccp("tasks", "release", "0002", "--reason", "claimed before its precondition")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["task_id"], body["released_from"]), ("0002-second", "leased"))
        st = self.state()
        self.assertEqual((st["status"], st["lease_holder"], st["waiting_on"], st["claimed_at"]), ("pending", None, None, None))
        self.assertTrue((self.q / "queue/pending/0002-second").exists())
        self.assertFalse((self.q / "queue/leased/0002-second").exists())
        w = self.work()
        self.assertEqual((w["in_flight"], w["task_id"], w.get("lease"), w.get("waiting_on")), ([], None, None, None))
        evs = self.events()
        clear = [e for e in evs if (e["type"], e["op"]) == ("lease", "clear")]
        self.assertEqual(len(clear), 1)
        self.assertEqual(clear[0]["payload"]["holder"], "runner")
        self.assertTrue(clear[0]["payload"]["released"])
        self.assertIn(("waiting_on", "clear"), self.ops())
        moves = [e["payload"] for e in evs if (e["type"], e["op"]) == ("phase", "transition")]
        self.assertEqual((moves[-1]["from"], moves[-1]["to"]), ("leased", "pending"))
        self.assertIn("claimed before its precondition", moves[-1]["note"])
        self.assertTrue(any("worktree" in x and "kept" in x for x in body["warnings"]), body)
        self.assertIsNone(st["lease_since"])
        self.assertEqual(w["runtime_status"], "idle")
        code, body, out, err = self.ccp("tasks", "next", "--json")
        self.assertEqual((code, body["task_id"]), (0, "0002-second"), out + err)
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual((code, body["resumed"]), (0, False), out + err)  # a fresh claim, in the kept worktree
        self.assertTrue(self.state()["claimed_at"])

    def test_the_runners_current_task_hands_over_to_the_next_in_flight(self):
        self.claimed_and_waiting()
        w = self.work()
        w["in_flight"] = ["0009-other", "0002-second"]
        (self.q / "work.json").write_text(json.dumps(w))
        (self.q / "tasks/0009-other.json").write_text(json.dumps({"task_id": "0009-other", "status": "reviewing",
                                                                  "phase_since": "2026-10-23T10:00:00Z"}))
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual(code, 0, out + err)
        w = self.work()
        self.assertEqual((w["in_flight"], w["task_id"], w["phase"]), (["0009-other"], "0009-other", "reviewing"))

    def test_a_claim_that_has_done_work_is_refused(self):
        self.claimed_and_waiting()
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual(code, 3, out + err)
        self.assertIn("implementing", err)
        self.assertEqual(self.state()["status"], "implementing")
        code, _, out, err = self.ccp("tasks", "phase", "0002", "blocked")  # blocked, but a run is behind it
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual(code, 3, out + err)
        self.assertIn("0002-second/implement", err)
        self.assertEqual(self.state()["lease_holder"], "runner")
        self.assertNotIn(("lease", "clear"), self.ops())

    def test_a_blocked_claim_and_a_stopped_release_are_released(self):
        self.claimed_and_waiting()
        self.ccp("tasks", "phase", "0002", "blocked")
        code, body, out, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual((code, body["released_from"]), (0, "blocked"), out + err)
        self.ccp("tasks", "claim", "0002")
        self.ccp("tasks", "phase", "0002", "pending")  # as a release that stopped after its phase move leaves it
        code, body, out, err = self.ccp("tasks", "release", "0002", "--reason", "again")
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(self.state()["lease_holder"])

    def test_a_claim_with_prompt_audits_from_before_run_records_is_refused(self):
        self.claimed_and_waiting()
        d = self.q / "prompts/0002-second"
        d.mkdir(parents=True)
        (d / "20261001T000000Z-implement.json").write_text("{}")
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual(code, 3, out + err)
        self.assertIn("prompts/0002-second/", err)

    def test_a_reason_the_ledger_refuses_writes_nothing(self):
        self.claimed_and_waiting()
        before = len(self.events())
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "ANTHROPIC_API_KEY=abc123")
        self.assertEqual(code, 2, out + err)
        st = self.state()
        self.assertEqual((st["status"], st["lease_holder"], st["waiting_on"]), ("leased", "runner", "design_seat"))
        self.assertEqual(len(self.events()), before)

    def test_an_unclaimed_task_and_a_missing_reason_are_refused(self):
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual(code, 3, out + err)
        self.assertIn("only a claimed task", err)
        self.claimed_and_waiting()
        code, _, out, err = self.ccp("tasks", "release", "0002", "--reason", "  ")
        self.assertEqual(code, 2, out + err)
        self.assertEqual(self.state()["status"], "leased")

    def backdate_first_claim(self):
        """The claim, wait and release an hour back, in the ledger and progress/."""
        evs = self.events()
        p = self.q / "observability/events.jsonl"
        p.write_text("".join(json.dumps({**e, "at": "2026-10-23T08:00:00Z"} if e["type"] in ("lease", "phase", "waiting_on")
                                        else e) + "\n" for e in evs))
        f = self.q / "progress/0002-second.json"
        prog = json.loads(f.read_text())
        prog["events"] = [{**x, "at": "2026-10-23T08:00:00Z"} for x in prog["events"]]
        f.write_text(json.dumps(prog))

    def test_the_task_starts_at_the_claim_after_a_release(self):
        self.claimed_and_waiting()
        self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.backdate_first_claim()
        self.ccp("tasks", "claim", "0002")
        second = [e for e in self.events() if (e["type"], e["op"]) == ("lease", "set")][-1]["at"]
        rec = drill.collect(self.q, [], {}, only="0002-second", now=time.time())["0002-second"]
        self.assertEqual(rec["start_at"], second)
        # health's start, which a merged task's drill and estimate actuals take their wall time from
        view = health._queue_view(self.q)["0002-second"]
        self.assertEqual(health._task_queue(self.q, "0002-second", view)["start"], health._epoch(second))
        claim, _, _ = backfill._times(self.events(), self.q, "0002-second")
        self.assertEqual(claim, second)

    def test_an_event_between_the_release_and_the_next_claim_is_no_start(self):
        self.claimed_and_waiting()
        self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.backdate_first_claim()
        p = self.q / "observability/events.jsonl"
        gap = {**self.events()[-1], "at": "2026-10-23T08:30:00Z", "type": "claude", "op": "exit", "payload": {"phase": "spec-maintainer"}}
        p.write_text(p.read_text() + json.dumps(gap) + "\n")
        self.ccp("tasks", "claim", "0002")
        second = [e for e in self.events() if (e["type"], e["op"]) == ("lease", "set")][-1]["at"]
        self.assertEqual(health._queue_view(self.q)["0002-second"]["first"], health._epoch(second))

    def test_a_release_and_claim_in_the_same_second_keep_the_new_claim(self):
        self.claimed_and_waiting()
        self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.ccp("tasks", "claim", "0002")
        second = [e for e in self.events() if (e["type"], e["op"]) == ("lease", "set")][-1]["at"]
        rec = drill.collect(self.q, [], {}, only="0002-second", now=time.time())["0002-second"]
        self.assertEqual(rec["start_at"], second)

    def test_a_release_rebuilds_the_board(self):
        self.assertIn(("tasks", "release"), cli.REFRESHES)

if __name__ == "__main__":
    unittest.main()
