"""SPEC §25.4 the session park and the session wake (2026-10-23): the config keys, the 5-hour reset in
each sample, claim and prompt parking a task at the 5-hour park % (exit 6) and lifting it after, the
no-wake warning, `ccp allowance session-wake` (arm, --armed, --fire) and the wake time taken from the
reading's reset, never from now + 5 h."""
from __future__ import annotations

import json
import os
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccp import config, usage
from tests.test_toolkit import ToolkitFixture


def utc(t: float, frac: str = "") -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + frac + "+00:00"


class SessionFixture(ToolkitFixture):
    """The allowance command reads a file the test rewrites (`reading`)."""

    def setUp(self):
        super().setUp()
        self.reading_file = Path(self._tmp.name) / "reading.json"
        self.reading(10)

    def reading(self, five, reset_in=3600.0, seven=20.0, frac="", tel=None):
        five_hour = {"utilization": five, **({"resets_at": utc(time.time() + reset_in, frac)} if reset_in is not None else {})}
        self.reading_file.write_text(json.dumps({"five_hour": five_hour, "seven_day": {
            "utilization": seven, "resets_at": "2026-10-27T04:00:00Z"}}))
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["telemetry"] = {"allowance_cmd": f"cat '{self.reading_file}'", **(tel or {})}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))

    def rows(self):
        return [json.loads(x) for x in (self.q / "board/allowance.jsonl").read_text().splitlines()]

    def work(self):
        return json.loads((self.q / "work.json").read_text())

    def task_state(self, tid="0002-second"):
        p = self.q / "tasks" / f"{tid}.json"
        return json.loads(p.read_text()) if p.is_file() else {}

    def wake(self, *flags):
        with mock.patch.dict(os.environ, {"ACTOR": "design-seat"}):
            return self.ccp("allowance", "session-wake", *flags)


class Config(ToolkitFixture, unittest.TestCase):
    def plane(self, tel):
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["telemetry"] = tel
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        return config.load(self.runner)

    def test_defaults_and_validation(self):
        tel = config.load(self.runner).telemetry
        self.assertEqual((tel["session_park_pct"], tel["session_wake_arm_pct"], tel["session_wake_margin_s"]), (95, 50, 180))
        self.assertIsNone(self.plane({"session_park_pct": None}).telemetry["session_park_pct"])
        for bad in ({"session_park_pct": 0}, {"session_park_pct": 101}, {"session_park_pct": True},
                    {"session_wake_arm_pct": None}, {"session_wake_arm_pct": "50"},
                    {"session_wake_margin_s": -1}, {"session_wake_margin_s": 1.5}, {"session_wake_margin_s": 7200}):
            with self.assertRaises(config.ConfigError, msg=bad):
                self.plane(bad)

    def test_settings_fill_defaults_for_a_bare_telemetry_block(self):
        self.assertEqual(usage.session_settings(SimpleNamespace(telemetry={})), (95.0, 50.0, 180))
        self.assertEqual(usage.session_settings(SimpleNamespace(telemetry={"session_park_pct": None}))[0], None)


class Sampling(SessionFixture, unittest.TestCase):
    def test_a_sample_records_the_five_hour_reset_and_unknown_is_null(self):
        self.reading(40, reset_in=1200)
        self.ccp("allowance", "status", "--sample")
        row = self.rows()[-1]
        self.assertEqual(row["five_hour"], 40.0)
        self.assertAlmostEqual(usage._iso_ts(row["five_hour_resets_at"]), time.time() + 1200, delta=5)
        self.reading(40, reset_in=None)
        self.ccp("allowance", "status", "--sample")
        self.assertIsNone(self.rows()[-1]["five_hour_resets_at"])
        self.reading_file.write_text(json.dumps({"five_hour": {"utilization": 1, "resets_at": "not a time"}}))
        self.ccp("allowance", "status", "--sample")
        self.assertIsNone(self.rows()[-1]["five_hour_resets_at"])
        ev = [e for e in self.events() if (e["type"], e["op"]) == ("allowance", "sample")]
        self.assertIn("five_hour_resets_at", ev[-1]["payload"])

    def test_old_rows_without_the_reset_are_read_as_unknown(self):
        (self.q / "board").mkdir(exist_ok=True)
        (self.q / "board/allowance.jsonl").write_text(json.dumps({"at": "2026-10-22T22:38:54Z", "five_hour": 91.0,
                                                                  "seven_day": 48.0, "resets_at": "x"}) + "\n")
        code, body, out, err = self.wake()
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["arm"])
        self.assertIn("reset time is unknown", body["reason"])


class Park(SessionFixture, unittest.TestCase):
    def test_a_new_claim_at_the_park_is_refused_parked_and_lifted_later(self):
        self.reading(96, reset_in=40 * 60)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 6, out + err)
        self.assertIn("session park", err)
        self.assertIn("96%", err)
        self.assertIn("ccp allowance session-wake", err)
        self.assertRegex(err, r"resets \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ \(")  # UTC, then local time
        self.assertIn("Runner:", err)
        st = self.task_state()  # a queue file of its own carries the wait; nothing is claimed
        self.assertEqual((st["waiting_on"], st["quota_class"], st["status"], st["lease_holder"]),
                         ("quota", "session", "pending", None))
        reset = usage._iso_ts(self.rows()[-1]["five_hour_resets_at"])
        self.assertEqual(usage._iso_ts(st["planned_resume_at"]), usage.wake_time(reset, 180))
        self.assertFalse((self.q / "work.json").exists())  # work.json is not the refused task's
        self.assertIn(("waiting_on", "set"), self.ops())
        # the window resets: the claim goes through and lifts the park
        self.reading(3, reset_in=5 * 3600)
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(self.work()["waiting_on"])
        self.assertIsNone(self.task_state()["waiting_on"])
        self.assertEqual(self.task_state()["lease_holder"], "runner")
        self.assertIn(("waiting_on", "clear"), self.ops())
        self.assertTrue(any("park is lifted" in x for x in body["warnings"]))

    def test_a_weekly_only_reading_lifts_a_park_and_parks_nothing(self):
        """§25.4: no 5-hour figure since 2026-10-31 means no 5-hour limit, not an unknown read."""
        self.reading(96, reset_in=40 * 60)
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 6)  # parked under the old limit
        self.reading_file.write_text(json.dumps({"seven_day": {"utilization": 20, "resets_at": "2026-10-27T04:00:00Z"}}))
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(self.task_state()["waiting_on"])  # the old park is lifted
        self.assertTrue(any("park is lifted" in x for x in body["warnings"]))
        self.assertFalse(any("session wake" in x for x in body.get("warnings") or []))

    def test_the_wake_lifts_parks_on_a_weekly_only_reading(self):
        """--fire (§25.4): with no 5-hour figure there is no window to wait for: every park lifts."""
        self.reading(96, reset_in=40 * 60)
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 6)
        self.reading_file.write_text(json.dumps({"seven_day": {"utilization": 20, "resets_at": "2026-10-27T04:00:00Z"}}))
        with mock.patch.dict(os.environ, {"ACTOR": "design-seat"}):
            code, body, out, err = self.ccp("allowance", "session-wake", "--fire")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["reset"])
        self.assertEqual([p["task_id"] for p in body["unparked"]], ["0002-second"])
        self.assertIsNone(self.task_state()["waiting_on"])

    def test_a_resumed_claim_and_a_prompt_are_parked_too_and_the_prompt_lifts_it(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.reading(95, reset_in=600)
        code, _, out, err = self.ccp("tasks", "claim", "0002")  # resumed: the weekly gate spares it, the park does not
        self.assertEqual(code, 6, out + err)
        st = self.task_state()
        self.assertEqual((st["waiting_on"], st["quota_class"]), ("quota", "session"))
        self.assertEqual(st["status"], "leased")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "HEAD")
        self.assertEqual(code, 6, out + err)
        self.assertFalse(list((self.q / "runs").glob("*.json")) if (self.q / "runs").is_dir() else [])  # no run opened
        self.assertEqual(self.task_state()["status"], "leased")
        sets = [e for e in self.events() if (e["type"], e["op"]) == ("waiting_on", "set")]
        self.assertEqual(len(sets), 1)  # parked once, not again for the same window
        self.reading(4, reset_in=5 * 3600)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "HEAD")
        self.assertEqual(code, 0, out + err)
        st = self.task_state()
        self.assertIsNone(st["waiting_on"])
        self.assertEqual(st["status"], "implementing")
        self.assertIn("park is lifted", err)

    def test_no_gate_when_the_reading_is_unknown_or_absent_or_off(self):
        self.reading_file.write_text("not json")
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.reading(99, reset_in=600, tel={"session_park_pct": None})
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "HEAD")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("session wake", err)
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["telemetry"] = {}  # no allowance_cmd at all
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_a_reset_already_past_gates_nothing(self):
        self.reading(99, reset_in=-60)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_the_weekly_gate_is_unchanged_and_comes_first(self):
        self.reading(99, reset_in=600, seven=85, tel={"allowance_stop_weekly": 80})
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 5)
        self.assertIn("allowance checkpoint", err)

    def test_the_no_wake_warning_until_one_is_armed(self):
        self.reading(60, reset_in=1800)
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIn("warning: 5-hour window at 60%: no session wake armed", err)
        code, _, out, err = self.wake("--armed")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "HEAD")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("no session wake armed", err)
        self.reading(40, reset_in=1800)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertNotIn("no session wake armed", err)  # under the arm %


class Wake(SessionFixture, unittest.TestCase):
    def test_the_wake_is_the_readings_reset_plus_the_margin_not_five_hours(self):
        # e.g. 91% with the reset 40 minutes away; the wake is 43 minutes away, not 5 h
        self.reading(91, reset_in=40 * 60)
        t0 = time.time()
        code, body, out, err = self.wake("--sample")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["arm"], body)
        wake = usage._iso_ts(body["wake_at"])
        self.assertGreaterEqual(wake - t0, 43 * 60 - 2)
        self.assertLess(wake - t0, 44 * 60 + 2)  # up to the next whole minute
        self.assertEqual(wake % 60, 0)
        d = datetime.fromtimestamp(wake)
        self.assertEqual(body["cron"], f"{d.minute} {d.hour} {d.day} {d.month} *")
        self.assertIn("session-wake --fire", body["prompt"])
        self.assertIn("CronCreate", body["instruction"])

    def test_arm_logic(self):
        self.reading(30, reset_in=3600)
        _, body, _, _ = self.wake("--sample")
        self.assertFalse(body["arm"])
        self.assertIn("under 50%", body["reason"])
        self.reading(55, reset_in=3600, frac=".120000")
        _, body, _, _ = self.wake("--sample")
        self.assertTrue(body["arm"])
        code, armed, out, err = self.wake("--armed")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(armed["already"])
        rec = [json.loads(x) for x in (self.q / "board/session-wakes.jsonl").read_text().splitlines()]
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["wake_at"], body["wake_at"])
        self.assertIn(("allowance", "armed"), self.ops())
        # the next reading of the same window jitters by milliseconds: still armed, no second record
        self.reading(80, reset_in=3600, frac=".870000")
        _, body, _, _ = self.wake("--sample")
        self.assertFalse(body["arm"])
        self.assertIn("already armed", body["reason"])
        self.assertEqual(body["armed"]["wake_at"], rec[0]["wake_at"])
        _, again, _, _ = self.wake("--armed")
        self.assertTrue(again["already"])
        self.assertEqual(len((self.q / "board/session-wakes.jsonl").read_text().splitlines()), 1)
        # a new window (reset 5 h on) is not armed by the old record
        self.reading(70, reset_in=5 * 3600)
        _, body, _, _ = self.wake("--sample")
        self.assertTrue(body["arm"])
        # a reset already past: nothing to arm
        self.reading(70, reset_in=-30)
        _, body, _, _ = self.wake("--sample")
        self.assertFalse(body["arm"])
        self.assertIn("already reset", body["reason"])
        code, _, _, err = self.wake("--armed")
        self.assertEqual(code, 3)

    def test_a_parked_task_arms_under_the_threshold(self):
        self.reading(97, reset_in=1200)
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 6)
        self.reading(20, reset_in=1200, tel={"session_wake_arm_pct": 50})
        _, body, _, _ = self.wake("--sample")
        self.assertTrue(body["arm"], body)
        self.assertEqual([p["task_id"] for p in body["parked"]], ["0002-second"])
        self.assertIn("parked", body["reason"])

    def test_flags_are_for_session_wake_and_one_at_a_time(self):
        self.assertEqual(self.ccp("allowance", "status", "--armed")[0], 2)
        self.assertEqual(self.wake("--armed", "--fire")[0], 2)
        self.assertEqual(self.wake("--fire", "--sample")[0], 2)

    def test_park_off_never_arms(self):
        self.reading(99, reset_in=600, tel={"session_park_pct": None})
        _, body, _, _ = self.wake("--sample")
        self.assertFalse(body["arm"])
        self.assertIn("null", body["reason"])
        self.assertEqual(self.wake("--armed")[0], 2)


class Fire(SessionFixture, unittest.TestCase):
    def park(self):
        self.ccp("tasks", "claim", "0002")
        self.reading(96, reset_in=60, tel={"session_wake_margin_s": 0})
        self.assertEqual(self.ccp("prompt", "implement", "0002", "--base", "HEAD")[0], 6)
        return usage._iso_ts(self.task_state()["planned_resume_at"])

    def later(self, t):
        return mock.patch.object(usage, "time", SimpleNamespace(time=lambda: t))

    def test_fire_before_the_reset_unparks_nothing_and_gives_the_next_wake(self):
        self.park()
        code, body, out, err = self.wake("--fire")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["reset"])
        self.assertEqual(body["unparked"], [])
        self.assertIn("not reset yet", body["instruction"])
        self.assertIn("wake", body)
        self.assertEqual(self.task_state()["waiting_on"], "quota")

    def test_fire_after_the_reset_unparks_and_says_how_to_resume(self):
        planned = self.park()
        self.reading(2, reset_in=5 * 3600, tel={"session_wake_margin_s": 0})
        with self.later(planned + 5):
            code, body, out, err = self.wake("--fire")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["reset"])
        self.assertEqual([p["task_id"] for p in body["unparked"]], ["0002-second"])
        self.assertIn("resume 0002-second at its recorded phase", body["instruction"])
        self.assertIn("§10.2", body["instruction"])
        self.assertIsNone(self.task_state()["waiting_on"])
        self.assertIn(("allowance", "fired"), self.ops())

    def test_a_park_whose_resume_is_ahead_stays(self):
        planned = self.park()
        self.reading(2, reset_in=5 * 3600)
        with self.later(planned - 300):
            _, body, _, _ = self.wake("--fire")
        self.assertEqual(body["unparked"], [])
        self.assertEqual([p["task_id"] for p in body["still_parked"]], ["0002-second"])

    def test_nothing_parked_still_names_the_runners_task(self):
        self.ccp("tasks", "claim", "0002")
        self.reading(1, reset_in=5 * 3600)
        _, body, _, _ = self.wake("--fire")
        self.assertTrue(body["reset"])
        self.assertIn("nothing was parked", body["instruction"])
        self.assertIn("0002-second", body["instruction"])



class ReviewFixes(SessionFixture, unittest.TestCase):
    """The review of 382c85b: expiry, the unknown reset, lifting on every path, jitter, an early wake,
    work.json kept, best effort."""

    def add_task(self, tid="0003-third"):
        from tests.helpers import TASK
        p = self.runner / "docs/delivery/tasks" / f"{tid}.md"
        p.write_text(TASK.format(tid=tid, title="Third", status="pending", deps='"0001-first"',
                                 ver="*Append-only, per check id: pass or fail, with evidence.*"))

    def test_a_refused_new_claim_keeps_work_json_on_the_task_in_flight(self):
        self.add_task()
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        before = self.work()
        self.reading(97, reset_in=900)
        code, _, out, err = self.ccp("tasks", "claim", "0003")
        self.assertEqual(code, 6, out + err)
        w = self.work()
        self.assertEqual((w["task_id"], w.get("waiting_on")), (before["task_id"], before.get("waiting_on")))
        st = self.task_state("0003-third")
        self.assertEqual((st["waiting_on"], st["quota_class"]), ("quota", "session"))
        _, body, _, _ = self.wake()
        self.assertEqual([p["task_id"] for p in body["parked"]], ["0003-third"])

    def test_an_unknown_reset_parks_with_a_retry_and_the_wake_is_that_retry(self):
        self.reading(98, reset_in=None)
        t0 = time.time()
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 6)
        due = usage._iso_ts(self.task_state()["planned_resume_at"])
        self.assertAlmostEqual(due - t0, usage.PARK_RETRY_S, delta=5)
        _, body, _, _ = self.wake()
        self.assertTrue(body["arm"], body)
        self.assertIn("retry", body["reason"])
        self.assertEqual(usage._iso_ts(body["wake_at"]), usage.wake_time(due, 0))
        self.assertEqual(self.wake("--armed")[0], 0)
        _, body, _, _ = self.wake()
        self.assertFalse(body["arm"])
        self.assertIn("already armed", body["reason"])
        # a second refusal keeps the live retry's time: not pushed out, not written again
        sets = len([e for e in self.events() if (e["type"], e["op"]) == ("waiting_on", "set")])
        with mock.patch.object(usage, "time", SimpleNamespace(time=lambda: t0 + 600)):
            self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 6)
        self.assertEqual(usage._iso_ts(self.task_state()["planned_resume_at"]), due)
        self.assertEqual(len([e for e in self.events() if (e["type"], e["op"]) == ("waiting_on", "set")]), sets)
        # once it has expired, a refusal sets a new retry
        with mock.patch.object(usage, "time", SimpleNamespace(time=lambda: due + 5)):
            self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 6)
        self.assertAlmostEqual(usage._iso_ts(self.task_state()["planned_resume_at"]), due + 5 + usage.PARK_RETRY_S, delta=2)
        st = self.task_state()
        due2 = usage._iso_ts(st["planned_resume_at"])
        self.assertFalse(usage.expired(st, now=due2 - 1))
        self.assertTrue(usage.expired(st, now=due2 + 1))

    def test_an_unknown_reading_proceeds_but_keeps_the_park_and_a_past_reset_lifts_it(self):
        self.ccp("tasks", "claim", "0002")
        self.reading(96, reset_in=600)
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 6)
        self.reading_file.write_text("garbage")
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)  # best effort: the call goes on
        self.assertEqual(self.task_state()["waiting_on"], "quota")  # but an unknown reading lifts nothing
        self.assertNotIn(("waiting_on", "clear"), self.ops())
        self.reading(99, reset_in=-30)  # the endpoint still shows the old window's %
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "HEAD")
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(self.task_state()["waiting_on"])

    def test_fire_counts_a_past_reset_as_reset_and_unparks_a_task_due_within_two_minutes(self):
        self.ccp("tasks", "claim", "0002")
        self.reading(96, reset_in=600, tel={"session_wake_margin_s": 0})
        self.assertEqual(self.ccp("prompt", "implement", "0002", "--base", "HEAD")[0], 6)
        planned = usage._iso_ts(self.task_state()["planned_resume_at"])
        self.reading(97, reset_in=-10, tel={"session_wake_margin_s": 0})  # past reset, old % still shown
        with mock.patch.object(usage, "time", SimpleNamespace(time=lambda: planned - 60)):
            _, body, _, _ = self.wake("--fire")
        self.assertTrue(body["reset"], body)
        self.assertEqual([p["task_id"] for p in body["unparked"]], ["0002-second"])

    def test_the_wake_does_not_move_with_millisecond_jitter(self):
        base = usage._iso_ts("2026-10-27T04:00:00Z")
        for jit in (-0.3, -0.001, 0.0, 0.2, 0.49):
            self.assertEqual(usage.wake_time(base + jit, 180), base + 180)
        self.assertEqual(usage.wake_time(base + 10, 180), base + 240)

    def test_fire_before_the_reset_offers_the_armed_wake_again(self):
        # a clock change fired the one-shot cron an hour early: the same wake is offered for re-arming
        self.reading(97, reset_in=3600)
        self.assertEqual(self.wake("--sample")[1]["arm"], True)
        self.assertEqual(self.wake("--armed")[0], 0)
        code, body, out, err = self.wake("--fire")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["reset"])
        self.assertTrue(body["wake"]["arm"], body["wake"])
        self.assertIn("again", body["wake"]["reason"])
        self.assertEqual(body["wake"]["wake_at"], body["wake"]["armed"]["wake_at"])

    def test_prompt_and_claim_stay_best_effort(self):
        self.ccp("tasks", "claim", "0002")
        with mock.patch.object(usage, "sample_allowance", side_effect=OSError("disk full")):
            code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "HEAD")
        self.assertEqual(code, 0, out + err)
        self.assertIn("session park was not checked", err)
        with mock.patch.object(usage, "clear_park", side_effect=usage.QueueError("set-waiting-on: boom", 1)):
            code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIn("session park was not checked", err)
        # a wait that cannot be written still parks (the limit is near), and says so
        self.reading(99, reset_in=600)
        with mock.patch.object(usage, "_set_wait", side_effect=OSError("no space")):
            code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 6)
        self.assertIn("could not be recorded", err)


if __name__ == "__main__":
    unittest.main()
