"""SPEC §25.1 the shared allowance reader's rules on plain values: what a good reading is, the backoff and
when the account went unread (from the cache and from a product's own samples), what the reader does under
its lock, which sample each rule judges (§16.3 rule 5, §25.3), and the reader without its cache."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ccp import parallel, usage
from tests.helpers import Product, machine_file

T0 = float(int(time.time()))


def utc(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def ok(at: float, five: float | None = 20.0, seven: float | None = 50.0, **extra) -> dict:
    return {"at": utc(at), "five_hour": five, "seven_day": seven, "resets_at": utc(T0 + 86400),
            "five_hour_resets_at": utc(T0 + 3600), **extra,
            "windows": [{"name": "five_hour", "pct": five, "resets_at": utc(T0 + 3600)},
                        {"name": "seven_day", "pct": seven, "resets_at": utc(T0 + 86400)}]}


def failed(at: float, **extra) -> dict:
    return {"at": utc(at), "five_hour": None, "seven_day": None, "windows": [], "failed": True, "exit": 1, **extra}


class Good(unittest.TestCase):
    def test_a_good_reading_has_a_figure(self):
        self.assertTrue(usage.good([{"name": "w", "pct": 0.0}]))
        self.assertFalse(usage.good([{"name": "w", "pct": None, "resets_at": utc(T0)}]))
        self.assertFalse(usage.good([]))
        self.assertFalse(usage.good(None))

    def test_a_good_sample(self):
        self.assertTrue(usage.good_row(ok(T0)))
        self.assertFalse(usage.good_row(ok(T0, failed=True)))
        # a sample written before the shared reader is judged by its own windows
        self.assertFalse(usage.good_row({"at": utc(T0), "five_hour": None, "seven_day": None, "windows": []}))
        # one written before the usage windows, by its legacy figures
        self.assertTrue(usage.good_row({"at": utc(T0), "five_hour": None, "seven_day": 40}))
        self.assertFalse(usage.good_row({"at": utc(T0), "five_hour": None, "seven_day": None}))


class Backoff(unittest.TestCase):
    def test_it_doubles_up_to_the_cap(self):
        self.assertEqual([usage.next_backoff(x) for x in (None, 0, 60, 120, 600, 900)], [60, 60, 120, 240, 900, 900])

    def test_retry_after_lengthens_it_up_to_an_hour(self):
        self.assertEqual(usage.backoff_end(T0, 60, None), T0 + 60)
        self.assertEqual(usage.backoff_end(T0, 60, 300), T0 + 300)
        self.assertEqual(usage.backoff_end(T0, 240, 30), T0 + 240)
        self.assertEqual(usage.backoff_end(T0, 60, 99999), T0 + usage.RETRY_AFTER_MAX_S)

    def test_from_a_products_own_samples(self):
        self.assertIsNone(usage.backoff_from_log([]))
        self.assertIsNone(usage.backoff_from_log([failed(T0 - 50), ok(T0 - 10)]))
        self.assertEqual(usage.backoff_from_log([ok(T0 - 900), failed(T0 - 10)]), T0 - 10 + 60)
        three = [ok(T0 - 900), failed(T0 - 300), failed(T0 - 200), failed(T0 - 10)]
        self.assertEqual(usage.backoff_from_log(three), T0 - 10 + 240)
        self.assertEqual(usage.backoff_from_log([failed(T0 - 10 - i) for i in range(10)]), T0 - 19 + 900)
        self.assertEqual(usage.backoff_from_log([failed(T0 - 10, retry_after_s=1000)]), T0 - 10 + 1000)

    def test_unread_since_from_a_products_own_samples(self):
        self.assertIsNone(usage.unread_since_log([failed(T0 - 50), ok(T0 - 10)]))
        self.assertEqual(usage.unread_since_log([ok(T0 - 900), failed(T0 - 300), failed(T0 - 10)]), T0 - 300)
        self.assertEqual(usage.unread_since_log([failed(T0 - 700), failed(T0 - 10)]), T0 - 700)
        self.assertIsNone(usage.unread_since_log([]))


class UnderTheLock(unittest.TestCase):
    def test_backoff_then_reuse_then_run(self):
        good = {"windows": [{"name": "seven_day", "pct": 10}], "at": utc(T0 - 30)}
        self.assertEqual(usage.plan_read({"good": good, "backoff_until": utc(T0 + 5)}, T0), "backoff")
        self.assertEqual(usage.plan_read({"good": good, "backoff_until": utc(T0 - 5)}, T0), "reuse")
        self.assertEqual(usage.plan_read({"good": good}, T0 + 31), "run")
        self.assertEqual(usage.plan_read({}, T0), "run")

    def test_failing_since_is_set_on_the_first_failure_only(self):
        first = usage.after_read({"good": None}, T0, None, None)
        self.assertEqual((first["failing_since"], first["backoff_s"], first["backoff_until"]),
                         (utc(T0), 60, utc(T0 + 60)))
        second = usage.after_read(first, T0 + 61, None, 300)
        self.assertEqual((second["failing_since"], second["backoff_s"], second["backoff_until"]),
                         (utc(T0), 120, utc(T0 + 61 + 300)))
        wins = [{"name": "seven_day", "pct": 10}]
        cleared = usage.after_read(second, T0 + 400, wins, None)
        self.assertEqual(cleared, {"good": {"windows": wins, "at": utc(T0 + 400)}, "failing_since": None,
                                   "backoff_s": None, "backoff_until": None})


class Judged(unittest.TestCase):
    def setUp(self):
        self.p = Product({})
        self.addCleanup(self.p.cleanup)
        machine_file(self, allowance_cmd="true")
        self.q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.q, True)
        clock = mock.patch.object(usage, "now", lambda: T0)
        clock.start()
        self.addCleanup(clock.stop)

    def log(self, *rows: dict) -> None:
        (self.q / "board").mkdir(exist_ok=True)
        (self.q / "board/allowance.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_the_latest_good_sample_and_the_reading_in_force(self):
        self.log(ok(T0 - 600, five=30), failed(T0 - 10))
        self.assertEqual(usage.latest_good(self.q)["five_hour"], 30)
        self.assertEqual(usage.in_force(self.q)["five_hour"], 30)
        self.log(ok(T0 - usage.IN_FORCE_S - 1), failed(T0 - 10))
        self.assertIsNotNone(usage.latest_good(self.q))
        self.assertIsNone(usage.in_force(self.q))

    def test_a_weekly_window_is_judged_while_its_reset_is_ahead(self):
        cfg = self.p.cfg
        row = ok(T0 - 2400, seven=95)
        self.assertEqual(usage.weekly_over(cfg, self.q, row, T0)[0]["name"], "seven_day")
        row["windows"][1]["resets_at"] = utc(T0 - 60)  # the window has reset since
        self.assertIsNone(usage.weekly_over(cfg, self.q, row, T0))
        row["windows"][1]["resets_at"] = None  # no reset time: only while the sample is in force
        self.assertIsNone(usage.weekly_over(cfg, self.q, row, T0))
        self.assertIsNotNone(usage.weekly_over(cfg, self.q, {**row, "at": utc(T0 - 60)}, T0))

    def test_rule_5_with_no_reading_in_force_refuses_a_second_claim(self):
        cfg = self.p.cfg
        cand = {"task_id": "0003-c", "parallel": True}
        busy = [{"task_id": "0002-b", "parallel": True}]
        with mock.patch.object(parallel, "settings", return_value={"max_in_flight": 2, "exclusive": [], "schedule": "clashes"}):
            self.assertIn("no good usage reading in the last 15 minutes", parallel.join_refusal(cfg, cand, busy, None))
            self.assertIsNone(parallel.join_refusal(cfg, cand, busy, None, five_known=False))

    def test_the_unread_stop_waits_an_hour_and_a_reading_in_force_lifts_it(self):
        cfg = self.p.cfg
        self.log(ok(T0 - 70 * 60))
        stop = usage.checkpoint_stop(cfg, self.q, {"unread_since": T0 - usage.UNREAD_STOP_S})
        self.assertEqual((stop.code, stop.reason), (5, "usage unread"))
        self.assertIsNone(usage.checkpoint_stop(cfg, self.q, {"unread_since": T0 - usage.UNREAD_STOP_S + 60}))
        self.log(ok(T0 - 60))
        self.assertIsNone(usage.checkpoint_stop(cfg, self.q, {"unread_since": T0 - 2 * usage.UNREAD_STOP_S}))

    def test_a_decision_and_the_status_read_the_latest_good_sample(self):
        cfg = self.p.cfg
        self.log(ok(T0 - 600, seven=85), failed(T0 - 10))
        st = usage.status(cfg, self.q, False)
        self.assertTrue(st["latest"]["failed"])
        self.assertEqual((st["latest_good"]["seven_day"], st["in_force"]), (85, True))
        self.assertEqual(usage.continue_(cfg, self.q, 95, "the operator's words")["seven_day_then"], 85)


class WithoutTheCache(unittest.TestCase):
    """The machine file's directory cannot hold the reader's lock: the reader works from the product's samples."""

    def setUp(self):
        self.p = Product({})
        self.addCleanup(self.p.cleanup)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(usage.UNSHARED_ENV, None)
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        self.counter = d / "counter"
        self.code = d / "code"
        self.code.write_text("0")
        reading = json.dumps({"seven_day": {"utilization": 10, "resets_at": utc(T0 + 86400)}})
        machine = machine_file(self, allowance_cmd=f"echo x >> '{self.counter}'; echo '{reading}'; exit \"$(cat '{self.code}')\"")
        machine.parent.chmod(0o500)
        self.addCleanup(machine.parent.chmod, 0o700)
        self.q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.q, True)
        self.t = T0
        clock = mock.patch.object(usage, "now", lambda: self.t)
        clock.start()
        self.addCleanup(clock.stop)

    def runs(self) -> int:
        return len(self.counter.read_text().splitlines()) if self.counter.is_file() else 0

    def test_it_reuses_and_backs_off_from_its_own_samples_and_says_so(self):
        if os.geteuid() == 0:
            self.skipTest("root writes a read-only directory")
        cfg = self.p.cfg
        read = usage.reading(cfg, self.q)
        self.assertIn("usage reads are not shared", read["warnings"][0])
        self.assertEqual(self.runs(), 1)
        self.t = T0 + 30
        self.assertFalse(usage.reading(cfg, self.q)["ran"])  # a good sample younger than READ_TTL_S
        self.assertIn("usage reads are not shared", usage.reading_warnings(cfg, self.q, read)[0])
        self.code.write_text("1")
        self.t = T0 + 61
        self.assertTrue(usage.reading(cfg, self.q)["ran"])
        self.t = T0 + 100
        self.assertFalse(usage.reading(cfg, self.q)["ran"])  # inside the backoff its failed sample gives
        self.t = T0 + 122
        self.assertTrue(usage.reading(cfg, self.q)["ran"])
        self.assertEqual(self.runs(), 3)


class Reused(unittest.TestCase):
    def test_a_reading_newer_than_the_products_is_appended_inside_a_backoff(self):
        p = Product({})
        self.addCleanup(p.cleanup)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(usage.UNSHARED_ENV, None)
        machine_file(self, allowance_cmd="exit 1")
        q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, q, True)
        wins = [{"name": "seven_day", "pct": 33.0, "resets_at": utc(T0 + 86400)}]
        usage.cache_path("exit 1").write_text(json.dumps({"good": {"windows": wins, "at": utc(T0 - 300)},
                                                          "failing_since": utc(T0 - 200), "backoff_s": 120,
                                                          "backoff_until": utc(T0 + 100)}))
        with mock.patch.object(usage, "now", lambda: T0):
            read = usage.reading(p.cfg, q)
            self.assertFalse(read["ran"])
            self.assertEqual((read["row"]["seven_day"], read["row"]["reused"], read["row"]["at"]), (33.0, True, utc(T0 - 300)))
            self.assertEqual(read["unread_since"], T0 - 200)
            self.assertIsNone(usage.reading(p.cfg, q)["row"])  # not newer than the product's own any more


if __name__ == "__main__":
    unittest.main()
