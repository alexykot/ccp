"""§27.2 suite series: `ccp health`'s suite time comes from `ccp suite run` records, cold apart from
warm, part-lane and unverified runs; `ccp health reclassify-suite` re-files the older entries."""
from __future__ import annotations

import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccp import health, quality, report
from tests.helpers import Product

CACHE = {"verify": {"accept_cache": {"max_age_days": 3}}}
LANES = {"suite": {"lanes": {"gate": ["true"], "full": ["true"]}}}  # the full role's own lane (§14.1)
RUN = "0002-second/implement"
TID = "0002-second"


def started(sid, lane, run=RUN, at="2026-10-22T10:00:00Z"):
    return {"op": "started", "suite_id": sid, "at": at, "lane": lane, "run_id": run, "task_id": run.split("/")[0],
            "phase": run.split("/")[1]}


def ended(sid, code=0, seconds=500.0, tests=1100, ran=None, cached=None, at="2026-10-22T10:09:00Z", legacy=True):
    """An ended row; `legacy` writes the counters under their pre-contract names (suite.fold maps them)."""
    names = ("modules_ran", "modules_cached") if legacy else ("ran", "cached")
    return {"op": "ended", "suite_id": sid, "at": at, "exit_code": code, "seconds": seconds, "tests": tests,
            "failed": None, "skipped": None, names[0]: ran, names[1]: cached, "interrupted": None}


class Fixture:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.q = Path(self._tmp.name)
        self.p = Product(LANES)
        self.pc = Product({**CACHE, **LANES})

    def tearDown(self):
        self._tmp.cleanup()
        self.p.cleanup()
        self.pc.cleanup()

    def suites(self, *rows):
        p = self.q / "runs" / "_suites.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def metrics(self):
        p = self.q / "health" / "metrics.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []


class Classify(unittest.TestCase):
    def test_a_cached_gates_tests_ride_beside_its_module_counts(self):
        """An all-cached gate records 0 tests ran; the cached units' tests go beside it."""
        self.assertEqual(health._tally({"ran": 0, "cached": 58, "cached_tests": 1120}, None),
                         {"ran": 0, "cached": 58, "cached_tests": 1120})
        self.assertEqual(health._tally({"ran": 3, "cached": 55}, None), {"ran": 3, "cached": 55})

    def test_kinds(self):
        ok = {"state": "passed", "lane": "full", "tests": 1100, "cached": None}
        self.assertEqual(health.classify(ok, cache=False), "cold")  # no cache, no tally: cold, as before
        self.assertEqual(health.classify(ok, cache=True), "unverified")  # a cache, no evidence
        self.assertEqual(health.classify(ok, cache=True, said="cold"), "cold")
        self.assertEqual(health.classify(ok, cache=False, said="warm"), "warm")
        self.assertEqual(health.classify({**ok, "cached": 0}, cache=True), "cold")
        self.assertEqual(health.classify({**ok, "cached": 3}, cache=True, said="cold"), "warm")  # the record wins
        self.assertEqual(health.classify({**ok, "lane": "gate", "cached": 58, "tests": None}, True), "warm")
        self.assertEqual(health.classify({**ok, "lane": "part"}, cache=False), "part")
        self.assertEqual(health.classify({**ok, "lane": None}, cache=False), "part")
        self.assertEqual(health.classify({**ok, "tests": None}, cache=False), "unverified")  # nothing counted
        for st in ("failed", "killed", "interrupted", "open"):
            self.assertIsNone(health.classify({**ok, "state": st}, cache=False), st)

    def test_lane_roles_decide_which_lanes_can_be_cold(self):
        ok = {"state": "passed", "lane": "ci", "tests": 10, "cached": 0}
        self.assertEqual(health.classify(ok, cache=True), "part")
        self.assertEqual(health.classify(ok, cache=True, lanes=("ci", "gate")), "cold")
        cfg = type("C", (), {"suite": {"roles": {"full": "ci", "gate": "gate", "part": "part"}}})()
        self.assertEqual(set(health.cold_lanes(cfg)), {"ci", "gate"})
        self.assertEqual(set(health.cold_lanes(None)), {"full", "gate"})

    def test_line_kind_and_both_wordings(self):
        self.assertEqual(report.cache_counts("Suite: 40 tests, 12 s, ran 3, cached 90"), (3, 90))
        self.assertEqual(report.cache_counts("Suite: 1130 tests, 3 s (warm gate: 1 module ran, 58 cached; …)"), (1, 58))
        self.assertEqual(report.cache_counts("Suite: 1068 tests, 482 s, mac (57 modules ran, 3 cached)"), (57, 3))
        self.assertIsNone(report.cache_counts("Suite: 1102 tests, 506 s"))
        self.assertEqual(health.line_kind("Suite: 1124 tests, 547 s (58 modules ran, 1 cached; effectively cold)"), "warm")
        self.assertEqual(health.line_kind("Suite: 1108 tests, 546 s, mac (cold)"), "cold")
        self.assertEqual(health.line_kind("Suite: 1111 tests, 3 s, warm gate"), "warm")
        self.assertEqual(health.line_kind("Suite: 1100 tests, 9 s, not cold"), None)
        self.assertIsNone(health.line_kind("Suite: 1102 tests, 506 s"))
        out, errs = report.parse("verify", "Outcome: done\nVerdict: approve\nHead: abcdef1\n"
                                 "Suite: 1068 tests, 482 s (57 modules ran, 3 cached)\n## Friction\nnone\n", accept_cache=True)
        self.assertEqual((errs, out["suite_ran"], out["suite_cached"]), ([], 57, 3))


class FileSuites(Fixture, unittest.TestCase):
    def test_records_decide_and_each_run_is_filed_once(self):
        self.suites(started("st-a", "full"), ended("st-a", seconds=530.3, tests=1110, ran=59, cached=0),
                    started("st-b", "gate"), ended("st-b", seconds=547, tests=1100, ran=58, cached=1),
                    started("st-c", "part"), ended("st-c", seconds=135, tests=374),
                    started("st-c2", "part"), ended("st-c2", seconds=15, tests=26),
                    started("st-d", "full"), ended("st-d", code=1, seconds=40, tests=12),
                    started("st-e", "full", run="0002-second/review"), ended("st-e", seconds=9, tests=9))
        recs = health.file_suites(self.pc.cfg, self.q, RUN, TID, {"suite_tests": 1100, "suite_seconds": 547},
                                  "Suite: 1100 tests, 547 s (58 modules ran, 1 cached; effectively cold)")
        got = {(m["metric"], m["value"], m.get("suite_id")) for m in recs}
        self.assertEqual(got, {("suite_tests", 1110, "st-a"), ("suite_seconds", 530, "st-a"),
                               ("suite_tests_warm", 1100, "st-b"), ("suite_seconds_warm", 547, "st-b"),
                               ("suite_tests_part", 400, None), ("suite_seconds_part", 150, None)})
        warm = next(m for m in recs if m["metric"] == "suite_seconds_warm")
        self.assertEqual((warm["ran"], warm["cached"]), (58, 1))  # any cached unit: warm, shown
        part = next(m for m in recs if m["metric"] == "suite_seconds_part")
        self.assertEqual((part["runs"], part["suite_ids"], part["run_id"]), (2, ["st-c", "st-c2"], RUN))  # one per run
        self.assertEqual(recs, self.metrics())  # the line's own numbers never reach health; the failed run neither
        self.assertEqual(health.file_suites(self.pc.cfg, self.q, RUN, TID, {}, None), [])  # filed once

    def test_no_tally_no_cache_is_cold_but_the_lines_warm_word_marks_its_run(self):
        self.suites(started("st-a", "full"), ended("st-a", seconds=520, tests=1102),
                    started("st-b", "gate"), ended("st-b", seconds=5.2, tests=None))
        recs = health.file_suites(self.p.cfg, self.q, RUN, TID, {"suite_tests": 1130, "suite_seconds": 3},
                                  "Suite: 1130 tests, 3 s (warm gate: 1 module ran, 58 cached)")
        self.assertEqual({(m["metric"], m["suite_id"]) for m in recs},
                         {("suite_tests", "st-a"), ("suite_seconds", "st-a"), ("suite_seconds_warm", "st-b")})

    def test_once_a_cache_is_seen_a_run_without_a_tally_is_unverified(self):
        self.suites(started("st-x", "gate", run="0001-first/verify"), ended("st-x", seconds=6, tests=22, ran=1, cached=58),
                    started("st-a", "full"), ended("st-a", seconds=520, tests=1102))
        recs = health.file_suites(self.p.cfg, self.q, RUN, TID, {}, "Suite: 1102 tests, 520 s")
        self.assertEqual({m["kind"] for m in recs}, {"unverified"})

    def test_fallback_without_records_once_per_line(self):
        line = "Suite: 412 tests, 88 s"
        nums = {"suite_tests": 412, "suite_seconds": 88}
        recs = health.file_suites(self.p.cfg, self.q, RUN, TID, nums, line)
        self.assertEqual([(m["metric"], m["kind"]) for m in recs], [("suite_tests", "cold"), ("suite_seconds", "cold")])
        self.assertEqual(health.file_suites(self.p.cfg, self.q, RUN, TID, nums, line), [])  # same task, run, numbers
        recs = health.file_suites(self.pc.cfg, self.q, "0002-second/fix", TID, nums, line)
        self.assertEqual({m["kind"] for m in recs}, {"unverified"})  # a cache and no cold evidence
        recs = health.file_suites(self.pc.cfg, self.q, "0002-second/fix-2", TID, nums, line + ", ran 59, cached 0")
        self.assertEqual({m["metric"] for m in recs}, {"suite_tests", "suite_seconds"})
        recs = health.file_suites(self.p.cfg, self.q, "0002-second/verify", TID, {"suite_tests": 40, "suite_seconds": 12},
                                  "Suite: 40 tests, 12 s, 3 modules ran, 90 cached")
        self.assertEqual({m["metric"] for m in recs}, {"suite_tests_warm", "suite_seconds_warm"})

    def test_untagged_entries_after_tagging_began_are_unverified(self):
        p = self.q / "health" / "metrics.jsonl"
        p.parent.mkdir(parents=True)
        rows = [{"at": "2026-10-01T00:00:00Z", "task_id": TID, "metric": "suite_seconds", "value": 500},
                {"at": "2026-10-02T00:00:00Z", "task_id": TID, "metric": "suite_seconds", "value": 510, "kind": "cold"},
                {"at": "2026-10-03T00:00:00Z", "task_id": TID, "metric": "suite_seconds", "value": 21}]
        p.write_text("".join(json.dumps(r) + "\n" for r in rows))
        st = health.suite_trend(self.metrics())
        self.assertEqual((st["cold"]["runs"], st["cold"]["latest_s"], st["unverified"]["runs"]), (2, 510, 1))

    def test_readers_see_the_cold_series_only(self):
        self.suites(started("st-a", "full"), ended("st-a", seconds=540, tests=1110),
                    started("st-b", "part"), ended("st-b", seconds=135, tests=374))
        health.file_suites(self.p.cfg, self.q, RUN, TID, {}, None)
        st = health.suite_trend(self.metrics())
        self.assertEqual((st["cold"]["runs"], st["cold"]["latest_s"], st["part"]["latest_s"], st["warm"]["runs"]),
                         (1, 540, 135, 0))
        text = health.summary_text({"trend": health.trend([], 1.5), "tasks": [], "suite": st}, 0)
        self.assertIn("cold (the suite's time) 1 run(s), median of the last 5 540 s", text)
        self.assertIn("part lane 1 run(s)", text)
        qy = {"suite": quality.suite_series(self.q)}
        self.assertEqual(quality.counters(qy), {"suite_cold_s": 540, "suite_warm_s": None, "suite_part_s": 135})
        page = (Path(health.__file__).parent / "board_page.html").read_text()
        for label in ("Cold suite seconds per task", "Warm suite seconds per task", "Part-lane seconds per task",
                      '"suite_cold_s"', '"suite_warm_s"', '"suite_part_s"'):
            self.assertIn(label, page)

    def test_record_accepts_the_new_names(self):
        recs = health.add_metrics(self.p.cfg, self.q, TID, ["suite_seconds_warm=3", "suite_seconds_part=12"])
        self.assertEqual([r["metric"] for r in recs], ["suite_seconds_warm", "suite_seconds_part"])


def mods(*pairs):
    return [{"name": f"tests.test_{n}", "seconds": s, "tests": t} for n, s, t in pairs]


SEVEN = (("a", 4.0, 10), ("b", 80.5, 100), ("c", 12.0, 20), ("d", 45.0, 40), ("e", 1.5, 5), ("f", 30.0, 30),
         ("g", 9.0, 15))


class SlowestModules(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict("os.environ", {"QUEUE_ROOT": str(self.q)})
        env.start()
        self.addCleanup(env.stop)

    def gate(self, sid, seconds, tests, modules=None, lane="gate", code=0, cached=0, day=1):
        row = ended(sid, code=code, seconds=seconds, tests=tests, cached=cached, legacy=False,
                    at=f"2026-11-{day:02d}T10:05:00Z")
        if modules is not None:
            row["modules"] = modules
        self.suites(started(sid, lane, at=f"2026-11-{day:02d}T10:00:00Z"), row)

    def health(self, product=None, *args):
        from ccp import cli  # noqa: PLC0415
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["--root", str((product or self.p).root), "health", *args]), 0)
        return out.getvalue()

    def three_runs(self):
        self.gate("st-1", 300.0, 1000, mods(*SEVEN), day=1)
        self.gate("st-2", 150.0, 1000, mods(*SEVEN), day=2)
        self.gate("st-3", 130.0, 1300, mods(*SEVEN), day=3)

    def test_the_slowest_modules_of_the_latest_run_and_the_time_per_test(self):
        self.three_runs()
        m = json.loads(self.health(None, "--json"))["suite_modules"]
        self.assertEqual((m["runs"], m["latest"]["suite_id"], m["latest"]["seconds"], m["latest"]["tests"]),
                         (3, "st-3", 130, 1300))
        self.assertEqual([(x["name"], x["seconds"], x["tests"]) for x in m["slowest"]],
                         [("tests.test_b", 80, 100), ("tests.test_d", 45, 40), ("tests.test_f", 30, 30),
                          ("tests.test_c", 12, 20), ("tests.test_g", 9, 15)])
        pt = m["per_test"]
        self.assertEqual((pt["runs"], pt["median_s"]), (3, 0.15))
        self.assertEqual((pt["first"]["suite_id"], pt["first"]["seconds_per_test"]), ("st-1", 0.3))
        self.assertEqual((pt["latest"]["suite_id"], pt["latest"]["seconds_per_test"]), ("st-3", 0.1))
        text = self.health()
        slow = [ln for ln in text.splitlines() if ln.startswith("Slowest test modules")]
        self.assertEqual(len(slow), 1)
        for token in ("st-3", "tests.test_b 80 s", "tests.test_g 9 s"):
            self.assertIn(token, slow[0])
        self.assertNotIn("tests.test_a", slow[0])
        trend = [ln for ln in text.splitlines() if ln.startswith("Seconds per test")]
        self.assertEqual(len(trend), 1)
        for token in ("0.15", "0.3 (st-1)", "0.1 (st-3)"):
            self.assertIn(token, trend[0])

    def test_only_cold_gate_runs_that_carry_modules_count(self):
        self.gate("st-1", 300.0, 1000, None, day=1)                       # the serial gate: no modules
        self.gate("st-2", 100.0, 1000, mods(("a", 5.0, 1000)), day=2)
        self.gate("st-3", 50.0, 1000, mods(("x", 50.0, 1000)), cached=4, day=3)          # warm
        self.gate("st-4", 50.0, 1000, mods(("y", 50.0, 1000)), code=1, day=4)            # failed
        self.gate("st-5", 50.0, 1000, mods(("z", 50.0, 1000)), lane="part", day=5)       # another lane
        m = json.loads(self.health(None, "--json"))["suite_modules"]
        self.assertEqual((m["runs"], m["latest"]["suite_id"], [x["name"] for x in m["slowest"]]),
                         (1, "st-2", ["tests.test_a"]))
        self.assertEqual((m["per_test"]["first"]["suite_id"], m["per_test"]["median_s"]), ("st-2", 0.1))

    def test_the_knobs_and_a_renamed_gate_role_are_read(self):
        p = Product({"health": {"slowest_modules": 2, "suite_trend_runs": 2},
                     "suite": {"lanes": {"check": ["true"]}, "roles": {"gate": "check"}}})
        self.addCleanup(p.cleanup)
        self.gate("st-1", 300.0, 1000, mods(*SEVEN), lane="check", day=1)
        self.gate("st-2", 200.0, 1000, mods(*SEVEN), lane="check", day=2)
        self.gate("st-3", 100.0, 1000, mods(*SEVEN), lane="check", day=3)
        m = json.loads(self.health(p, "--json"))["suite_modules"]
        self.assertEqual([x["name"] for x in m["slowest"]], ["tests.test_b", "tests.test_d"])
        self.assertEqual((m["runs"], m["per_test"]["runs"], m["per_test"]["first"]["suite_id"],
                          m["per_test"]["median_s"]), (3, 2, "st-2", 0.15))

    def test_with_no_module_timings_health_says_nothing_of_them(self):
        self.gate("st-1", 300.0, 1000, None)
        m = json.loads(self.health(None, "--json"))["suite_modules"]
        self.assertEqual((m["runs"], m["latest"], m["slowest"], m["per_test"]), (0, None, [], None))
        text = self.health()
        self.assertNotIn("Slowest test modules", text)
        self.assertNotIn("Seconds per test", text)

    def test_the_architects_summary_carries_them(self):
        self.three_runs()
        self.assertIn("tests.test_b", health.summary_text(health.collect(self.p.cfg, self.q)))

    def test_bad_knobs_are_refused(self):
        from ccp import config  # noqa: PLC0415
        for k in ("slowest_modules", "suite_trend_runs"):
            for bad in (0, -1, True, "5", 2.5):
                p = Product({"health": {k: bad}})
                self.addCleanup(p.cleanup)
                with self.subTest(k=k, bad=bad), self.assertRaises(config.ConfigError):
                    config.load(p.root)
        self.assertEqual({k: self.p.cfg.health[k] for k in ("slowest_modules", "suite_trend_runs")},
                         {"slowest_modules": 5, "suite_trend_runs": 10})
