"""SPEC §26.4 phase C: the completion forecast and the allowance fit. The lognormal through P50 and
P90, the replayed order (dependencies, holds, the task in flight), the in-flight remainder, the
throughput model, the allowance fit on synthetic data, the projection and spill maths, the board
(escaped, in the Queue tab and the strip) and the time bound."""
from __future__ import annotations

import io
import json
import math
import os
import random
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccp import board, calibrate, forecast
from tests.helpers import TASK, Product
from tests.test_board_drill import HASH_STUB, Fixture
from tests.test_board_quality import HOSTILE, _hostile

NOW = 1_800_000_000.0


def iso(e: float) -> str:
    return forecast.iso(e)


def est(p50: float, p90: float, tok: tuple[float, float] | None = (1e6, 2e6), cost: tuple[float, float] | None = (1.0, 2.0),
        source: str = "baseline") -> dict:
    return {"source": source, "total": {"p50_s": p50, "p90_s": p90},
            "tokens": {"p50": tok[0], "p90": tok[1]} if tok else None,
            "cost_usd": {"p50": cost[0], "p90": cost[1]} if cost else None}


class Lognormal(unittest.TestCase):
    def test_the_fit_goes_through_p50_and_p90(self):
        mu, s = forecast.lognormal(3600, 7200)
        self.assertAlmostEqual(math.exp(mu), 3600)
        self.assertAlmostEqual(math.exp(mu + forecast.Z90 * s), 7200)
        self.assertEqual(forecast.lognormal(3600, 3000), (math.log(3600), forecast.SIGMA_MIN))
        self.assertEqual(forecast.lognormal(3600, None), (math.log(3600), forecast.SIGMA_MIN))
        for bad in (0, -5, None, "x", True, float("nan")):
            self.assertIsNone(forecast.lognormal(bad, 100))

    def test_a_band_wider_than_4x_draws_as_4x(self):
        """§26.6: the P90 is capped at P90_RATIO_MAX x P50, the calibration's cap, for every band."""
        self.assertEqual(forecast.P90_RATIO_MAX, calibrate.P90_RATIO_MAX)
        mu, s = forecast.lognormal(1000, 37600)
        self.assertAlmostEqual(math.exp(mu), 1000)
        self.assertAlmostEqual(math.exp(mu + forecast.Z90 * s), 4000)
        self.assertEqual(forecast.lognormal(1000, 37600), forecast.lognormal(1000, 4000))
        self.assertAlmostEqual(math.exp(forecast.lognormal(1000, 3900)[0] + forecast.Z90 * forecast.lognormal(1000, 3900)[1]), 3900)

    def test_draws_reproduce_the_quantiles_of_one_task(self):
        dur = {"a": forecast.lognormal(3600, 7200)}
        with mock.patch.object(forecast, "RHO", 0.0):
            r = forecast.simulate(["a"], {}, dur, {}, [0.0], NOW, {}, trials=4000, targets={"t": ["a"]})
        ends = [e - NOW for e in r["targets"]["t"]["end"]]
        self.assertAlmostEqual(forecast.quantile(ends, 0.5) / 3600, 1, delta=0.05)
        self.assertAlmostEqual(forecast.quantile(ends, 0.9) / 7200, 1, delta=0.07)

    def test_the_same_inputs_give_the_same_forecast(self):
        dur = {"a": forecast.lognormal(600, 1200), "b": forecast.lognormal(900, 2000)}
        r1 = forecast.simulate(["a", "b"], {}, dur, {}, [5.0, -30.0], NOW, {}, trials=200, targets={"t": ["a", "b"]})
        r2 = forecast.simulate(["a", "b"], {}, dur, {}, [5.0, -30.0], NOW, {}, trials=200, targets={"t": ["a", "b"]})
        self.assertEqual(r1["targets"]["t"]["end"], r2["targets"]["t"]["end"])

    def test_the_agent_estimate_comes_before_the_baseline_and_a_missing_one_takes_the_median(self):
        views = {"a": {"baseline": est(600, 900), "agent": est(1200, 1800, source="agent")},
                 "b": {"baseline": est(300, 600), "agent": None}, "c": {}}
        e = forecast.estimates_for(views, ["a", "b", "c"])
        self.assertEqual((e["a"]["source"], e["b"]["source"], e["c"]), ("agent", "baseline", None))
        p, missing = forecast._params(e, "total", "p50_s", "p90_s")
        self.assertEqual(missing, 1)
        self.assertAlmostEqual(math.exp(p["c"][0]), 750)  # the median of 1200 and 300


def task_text(tid: str, status: str = "pending", deps: tuple[str, ...] = (), kind: str = "feature", rp: str | None = "R8") -> str:
    t = TASK.format(tid=tid, title="T", status=status, deps=", ".join(f'"{d}"' for d in deps), ver="*Append-only.*")
    extra = f"kind: {kind}\n" + (f"review_point: {rp}\n" if rp else "")
    return t.replace("created: 2026-09-30\n", "created: 2026-09-30\n" + extra, 1)


class Order(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        for tid, st, deps, rp in (("0001-a", "done", (), "R7"), ("0002-b", "pending", ("0004-d",), "R8"),
                                  ("0003-c", "pending", (), "R8"), ("0004-d", "pending", (), "R8"),
                                  ("0005-e", "pending", ("0009-gone",), "R8"), ("0006-f", "pending", (), "R8"),
                                  ("0007-g", "pending", (), "R9"), ("0009-gone", "dropped", (), None)):
            self.p.write(f"docs/delivery/tasks/{tid}.md", task_text(tid, st, deps, rp=rp))
        self.q = Path(tempfile.mkdtemp())
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\n")

    def tearDown(self):
        self.p.cleanup()
        shutil.rmtree(self.q, ignore_errors=True)

    def work(self, **w):
        (self.q / "work.json").write_text(json.dumps(w))

    def test_a_task_joins_once_its_dependencies_merge_and_holds_and_dead_ends_are_left_out(self):
        self.work(held={"0006-f": {"by": "lead"}})
        s = forecast.sequence(self.p.cfg, self.q)
        self.assertEqual(s["order"], ["0003-c", "0004-d", "0002-b", "0007-g"])
        self.assertEqual(s["unreached"], {"0005-e": "waits on 0009-gone", "0006-f": "held"})
        self.assertEqual(s["deps"]["0002-b"], ["0004-d"])

    def test_the_task_in_flight_comes_first_and_the_scope_before_the_rest(self):
        self.work(status="running", task_id="0004-d", in_flight=["0004-d"], scope=["0002", "0003", "0004", "0006"])
        s = forecast.sequence(self.p.cfg, self.q)
        self.assertEqual(s["order"][:3], ["0004-d", "0002-b", "0003-c"])  # 0002 is ready once 0004 (in flight) is
        self.assertEqual(s["order"][3:], ["0006-f", "0007-g"])            # the scope, then the rest of the log
        self.assertEqual(s["in_flight"], ["0004-d"])

    def test_the_lead_preference_goes_first(self):
        self.work(next_task="0007-g", next_task_by="lead")
        self.assertEqual(forecast.sequence(self.p.cfg, self.q)["order"][0], "0007-g")

    def test_the_lead_list_goes_in_order_and_a_waiting_entry_joins_once_ready(self):
        self.work(next_tasks=["0002-b", "0007-g", "0004-d"], next_task_by="lead", held={"0006-f": {"by": "lead"}})
        # 0002 waits on 0004: 0007 first, then 0004, then 0002 (ready now), ahead of the plane's own 0003
        self.assertEqual(forecast.sequence(self.p.cfg, self.q)["order"], ["0007-g", "0004-d", "0002-b", "0003-c"])

    def test_a_dependency_never_starts_before_its_dependency_merges(self):
        dur = {t: forecast.lognormal(1000, 1500) for t in ("a", "b", "c")}
        # a huge negative gap (overlap) would start everything at once but for the dependency
        r = forecast.simulate(["a", "b", "c"], {"c": ["a"]}, dur, {}, [-1e6], NOW, {}, trials=300,
                              targets={"a": ["a"], "c": ["c"]})
        for ea, ec in zip(r["targets"]["a"]["end"], r["targets"]["c"]["end"]):
            self.assertGreater(ec - ea, 0)

    def test_the_forecast_reports_the_review_point_and_the_backlog(self):
        self.work(held={"0006-f": {"by": "lead"}})
        views = {t: {"baseline": est(3600, 7200)} for t in ("0002-b", "0003-c", "0004-d")}
        views["0004-d"]["agent"] = {**est(1800, 3600, source="agent"), "waits": ["the operator rules on the schema"]}
        f = forecast.collect(self.p.cfg, self.q, est_tasks=views, now=NOW, trials=200, point="R8",
                             open_items={"gates": [{"task_id": "0003-c"}]})
        self.assertEqual(f["point"]["task_ids"], ["0003-c", "0004-d", "0002-b"])
        self.assertEqual(f["point"]["done"], 0)
        self.assertEqual(f["point"]["unreached"], {"0005-e": "waits on 0009-gone", "0006-f": "held"})
        self.assertEqual(f["point"]["waits_flagged"], ["0003-c"])
        self.assertEqual(f["point"]["waits_expected"], ["0004-d"])
        self.assertEqual(f["sources"], {"agent": 1, "baseline": 2})
        self.assertEqual(f["backlog"]["unestimated"], 1)  # 0007 took the median
        self.assertFalse(f["backlog"]["same_as_point"])
        self.assertLess(f["point"]["eta"]["p50"], f["point"]["eta"]["p90"])
        self.assertLessEqual(f["point"]["eta"]["p50"], f["backlog"]["eta"]["p50"])
        self.assertGreater(f["point"]["tokens"]["p50"], 2e6)
        self.assertTrue(f["advisory"])

    def test_no_estimate_at_all_says_so(self):
        f = forecast.collect(self.p.cfg, self.q, est_tasks={}, now=NOW, trials=10)
        self.assertIn("ccp tasks estimate --all --baseline", f["note"])
        self.assertIsNone(f["point"])


class InFlight(unittest.TestCase):
    def test_the_remainder_is_drawn_given_the_task_has_not_finished(self):
        mu, s = forecast.lognormal(3600, 7200)
        with mock.patch.object(forecast, "RHO", 0.0):
            r = forecast.simulate(["a"], {}, {"a": (mu, s)}, {"tokens": {"a": forecast.lognormal(1e6, 2e6)}}, [0.0], NOW,
                                  {"a": 3600.0}, trials=4000, targets={"t": ["a"]})
        rem = [e - NOW for e in r["targets"]["t"]["end"]]
        self.assertTrue(all(x >= 0 for x in rem))
        # the median of a draw given it exceeds its own median is its 75th percentile
        want = math.exp(mu + s * forecast._ND.inv_cdf(0.75)) - 3600
        self.assertAlmostEqual(forecast.quantile(rem, 0.5) / want, 1, delta=0.08)
        # tokens: only the part not yet spent
        self.assertLess(forecast.quantile(r["targets"]["t"]["tokens"], 0.5), 1e6)

    def test_a_task_far_past_its_p90_still_has_some_time_left(self):
        mu, s = forecast.lognormal(600, 900)
        r = forecast.simulate(["a"], {}, {"a": (mu, s)}, {}, [0.0], NOW, {"a": 50_000.0}, trials=200, targets={"t": ["a"]})
        self.assertTrue(all(e >= NOW for e in r["targets"]["t"]["end"]))

    def test_a_capped_wide_band_in_flight_far_past_its_p50_is_not_drawn_finished(self):
        """A 10x band draws as 4x; 16x its P50 in, the task still has time left in (almost) every trial."""
        mu, s = forecast.lognormal(1800, 18000)
        r = forecast.simulate(["a"], {}, {"a": (mu, s)}, {}, [0.0], NOW, {"a": 16 * 1800.0}, trials=400, targets={"t": ["a"]})
        left = [e - NOW for e in r["targets"]["t"]["end"]]
        self.assertGreater(sum(x > 0 for x in left) / len(left), 0.99)

    def test_elapsed_comes_from_the_drill_down_then_the_claim(self):
        q = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(forecast._flight_elapsed(q, "x", {"x": {"start_at": iso(NOW - 100)}}, {}, NOW), 100)
            (q / "tasks").mkdir()
            (q / "tasks" / "x.json").write_text(json.dumps({"claimed_at": iso(NOW - 200)}))
            self.assertEqual(forecast._flight_elapsed(q, "x", {}, {}, NOW), 200)
            self.assertEqual(forecast._flight_elapsed(q, "y", {}, {"lease": {"task_id": "y", "since": iso(NOW - 300)}}, NOW), 300)
        finally:
            shutil.rmtree(q, ignore_errors=True)


class Throughput(unittest.TestCase):
    def test_gaps_overlaps_and_stops(self):
        tp = forecast.throughput([(0, 100), (110, 200), (150, 260), (2300, 2400)])
        self.assertEqual((tp["gaps"], tp["stops"], tp["overlap_share"]), ([10, -50], 1, 0.5))
        self.assertIn("one task at a time", tp["text"])
        self.assertIsNone(forecast.throughput([])["median_gap_s"])

    def test_windows_are_the_drill_downs_merged_tasks(self):
        d = {"a": {"start_at": iso(NOW), "merged_at": iso(NOW + 60)}, "b": {"open": True, "start_at": iso(NOW)},
             "c": {"_error": "x"}, "_error": "y", "d": {"start_at": iso(NOW + 100), "merged_at": iso(NOW + 50)}}
        self.assertEqual(forecast.windows(d), [(NOW, NOW + 60)])

    def test_sequential_tasks_add_their_gaps(self):
        dur = {t: forecast.lognormal(1000, 1000) for t in "abc"}
        r = forecast.simulate(list("abc"), {}, dur, {}, [600.0], NOW, {}, trials=50, targets={"t": list("abc")})
        self.assertAlmostEqual(forecast.quantile(r["targets"]["t"]["end"], 0.5) - NOW, 3 * 1600, delta=3 * 1600 * 0.08)


def series_rows(spec: list[tuple[float, str, float, float]]) -> list[dict]:
    return [{"at": iso(t), "model": m, "input_tokens": tok, "output_tokens": 0, "cache_read_tokens": 0,
             "cache_creation_tokens": 0, "cost_usd": c, "request_id": f"r{i}"} for i, (t, m, tok, c) in enumerate(spec)]


class AllowanceFit(unittest.TestCase):
    def synth(self, pct_of, n=12, step=3600, resets="2027-01-05T04:00:00+00:00"):
        rng = random.Random(1)
        rows, samples, pct = [], [], 10.0
        t = NOW
        samples.append({"at": iso(t), "seven_day": pct, "resets_at": resets})
        for _ in range(n):
            spec = []
            for j in range(6):
                spec.append((t + 60 + j * 500, rng.choice(["claude-opus-5-5", "claude-sonnet-5"]), rng.uniform(1e5, 2e6),
                             rng.uniform(0.5, 5)))
            rows += spec
            pct += pct_of(spec)
            t += step
            samples.append({"at": iso(t), "seven_day": pct, "resets_at": resets})
        return series_rows(rows), samples, t

    def test_the_fit_recovers_percent_per_dollar(self):
        rows, samples, end = self.synth(lambda sp: 0.1 * sum(c for *_, c in sp))
        fit = forecast.allowance_fit(samples, forecast.Series(rows[::2]), forecast.Series(rows[1::2]), end)
        self.assertEqual(fit["chosen"], "cost")
        self.assertAlmostEqual(fit["k_plane"], 0.1, places=6)
        self.assertLess(fit["loo_rmse"], 1e-6)
        self.assertEqual(fit["n"], 11)  # the sink's first row comes after the first sample
        self.assertGreater(fit["models"]["tokens"]["loo_rmse"], fit["loo_rmse"])
        # the fit starts when both sources record: a sink that starts half way leaves the first half out
        late = forecast.allowance_fit(samples, forecast.Series(rows[: len(rows) // 2]), forecast.Series(rows[len(rows) // 2:]), end)
        self.assertEqual(late["n"], 5)

    def test_by_family_wins_when_families_cost_differently(self):
        k = {"opus": 2e-6, "sonnet": 0.5e-6}
        rows, samples, end = self.synth(lambda sp: sum(k[forecast.family(m)] * tok for _, m, tok, _ in sp))
        plane = forecast.Series(rows)
        fit = forecast.allowance_fit(samples, plane, forecast.Series([]), end)
        self.assertEqual(fit["chosen"], "tokens_by_family")
        self.assertAlmostEqual(fit["k_map"]["tokens:opus"], 2e-6, places=12)
        self.assertAlmostEqual(fit["k_map"]["tokens:sonnet"], 0.5e-6, places=12)
        self.assertIn("no system sink", fit.get("note") or "")  # an empty sink: use outside the plane unknown

    def test_whole_percent_samples_still_fit_with_an_error(self):
        rows, samples, end = self.synth(lambda sp: 0.1 * sum(c for *_, c in sp))
        for s in samples:
            s["seven_day"] = float(round(s["seven_day"]))
        fit = forecast.allowance_fit(samples, forecast.Series(rows), forecast.Series(rows[:1]), end)
        self.assertAlmostEqual(fit["k_plane"], 0.1, delta=0.02)
        self.assertGreater(fit["loo_rmse"], 0)
        self.assertLess(fit["loo_rmse"], 1)

    def test_intervals_skip_a_reset_a_fall_and_join_short_samples(self):
        r = "2027-01-05T04:00:00+00:00"
        s = [{"at": iso(NOW), "seven_day": 10, "resets_at": r}, {"at": iso(NOW + 600), "seven_day": 11, "resets_at": r},
             {"at": iso(NOW + 2400), "seven_day": 12, "resets_at": r},          # joined: 0 → 2400 s
             {"at": iso(NOW + 4800), "seven_day": 0, "resets_at": r},           # fell: restart
             {"at": iso(NOW + 8400), "seven_day": 3, "resets_at": r},
             {"at": iso(NOW + 12000), "seven_day": 5, "resets_at": "2027-01-12T04:00:00+00:00"},  # another window
             {"at": iso(NOW + 15600), "seven_day": None, "resets_at": r}]
        iv = forecast.intervals(s)
        self.assertEqual([(x["a"] - NOW, x["b"] - NOW, x["d"]) for x in iv], [(0, 2400, 2), (4800, 8400, 3)])

    def test_too_few_intervals_is_no_fit(self):
        fit = forecast.allowance_fit([{"at": iso(NOW), "seven_day": 1, "resets_at": "x"}], forecast.Series([]), None, NOW)
        self.assertIsNone(fit["chosen"])
        self.assertIn("needs", fit["note"])


class Projection(unittest.TestCase):
    burn = {"k": 1.0, "per_s": 1 / 3600, "pct_now": 50.0, "reset": NOW + 5400, "levels": [60.0, 80.0]}
    traj = [(NOW + 3600, 10.0), (NOW + 7200, 10.0)]

    def test_the_weekly_percent_rises_with_the_work_and_the_baseline(self):
        self.assertAlmostEqual(forecast._pct_at(self.traj, NOW, self.burn, NOW + 3600), 61)
        self.assertAlmostEqual(forecast._pct_at(self.traj, NOW, self.burn, NOW + 7200), 72)
        self.assertAlmostEqual(forecast._pct_at(self.traj, NOW, self.burn, NOW + 5400), 50 + 1.5 + 15)
        self.assertAlmostEqual(forecast._pct_at(self.traj, NOW, self.burn, NOW + 10800), 73)  # baseline only after
        self.assertEqual(forecast._pct_at(self.traj, NOW, self.burn, NOW - 5), 50)

    def test_checkpoint_crossings(self):
        self.assertAlmostEqual(forecast._crossing(self.traj, NOW, self.burn, 60) - NOW, 3600 * 10 / 11)
        self.assertIsNone(forecast._crossing(self.traj, NOW, self.burn, 80))  # 72% at the end, 1%/h: after the reset
        self.assertEqual(forecast._crossing(self.traj, NOW, self.burn, 40), NOW)  # already past
        far = {**self.burn, "reset": NOW + 1e6}
        self.assertAlmostEqual(forecast._crossing(self.traj, NOW, far, 80) - NOW, 7200 + 8 * 3600)

    def test_spill_past_the_reset(self):
        dur = {"a": forecast.lognormal(3600, 3600), "b": forecast.lognormal(3600, 3600)}
        x = {"cost": {"a": forecast.lognormal(10, 10), "b": forecast.lognormal(10, 10)}}
        burn = {**self.burn, "measure": "cost"}
        r = forecast.simulate(["a", "b"], {}, dur, x, [0.0], NOW, {}, trials=100, targets={"t": ["a", "b"]}, burn=burn)
        t = r["targets"]["t"]
        self.assertAlmostEqual(forecast.quantile(t["pct"], 0.5), 72, delta=2)
        self.assertAlmostEqual(forecast.quantile(t["spill"], 0.5), 5.5, delta=1)
        self.assertAlmostEqual(forecast.quantile(t["burn"], 0.5), 22, delta=2)
        self.assertEqual(len(r["crossings"]["60.0"]), 100)
        self.assertTrue(all(c is None for c in r["crossings"]["80.0"]))
        # all before the reset: no spill
        early = {**burn, "reset": NOW + 1e6}
        r = forecast.simulate(["a", "b"], {}, dur, x, [0.0], NOW, {}, trials=50, targets={"t": ["a", "b"]}, burn=early)
        self.assertEqual(set(r["targets"]["t"]["spill"]), {0.0})


class Performance(unittest.TestCase):
    def test_a_board_sized_simulation_is_cheap(self):
        order = [f"{i:04d}-t" for i in range(30)]
        dur = {t: forecast.lognormal(3600, 7200) for t in order}
        x = {"tokens": {t: forecast.lognormal(3e7, 5e7) for t in order}, "cost": {t: forecast.lognormal(15, 20) for t in order}}
        deps = {order[i]: [order[i - 1]] for i in range(1, 30, 3)}
        burn = {"k": 0.1, "per_s": 1 / 3600, "pct_now": 30.0, "reset": NOW + 3 * 86400, "levels": [80.0, 95.0], "measure": "cost"}
        t0 = time.perf_counter()
        forecast.simulate(order, deps, dur, x, [10.0, 20.0, -600.0], NOW, {order[0]: 600.0}, forecast.TRIALS, forecast.SEED,
                          {"point": order[:20], "backlog": order}, burn)
        self.assertLess(time.perf_counter() - t0, 0.6)  # about 0.1 s on the Mac (19 tasks: 0.07 s)


class Cli(unittest.TestCase):
    def test_ccp_forecast(self):
        from ccp import cli
        p = Product()
        q = Path(tempfile.mkdtemp())
        try:
            p.write("docs/delivery/tasks/0001-a.md", task_text("0001-a"))
            (q / "estimates").mkdir()
            (q / "estimates" / "0001-a.jsonl").write_text(json.dumps({"at": "2026-10-22T10:00:00Z", "task_id": "0001-a",
                                                                       "version": 1, **est(600, 900)}) + "\n")
            with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(q)}):
                o, e = io.StringIO(), io.StringIO()
                with redirect_stdout(o), redirect_stderr(e):
                    c = cli.main(["--root", str(p.root), "forecast", "--json", "--point", "R8"])
                self.assertEqual(c, 0, e.getvalue())
                f = json.loads(o.getvalue())
                self.assertEqual(f["point"]["task_ids"], ["0001-a"])
                self.assertTrue(f["backlog"]["same_as_point"])
                o = io.StringIO()
                with redirect_stdout(o), redirect_stderr(io.StringIO()):
                    cli.main(["--root", str(p.root), "forecast"])
                self.assertIn("ETA", o.getvalue())
                self.assertIn("advisory", o.getvalue())
        finally:
            p.cleanup()
            shutil.rmtree(q, ignore_errors=True)


class Page(Fixture, unittest.TestCase):
    env2 = None

    def tearDown(self):
        if self.env2 is not None:  # before the fixture's own patch: each restores the environment it saw
            self.env2.stop()
        super().tearDown()

    def seed_forecast(self):
        self.seed()
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "telemetry": {"allowance_stop_weekly": 80}}))
        (self.q / "estimates").mkdir(exist_ok=True)
        (self.q / "estimates" / "0002-second.jsonl").write_text(json.dumps(
            {"at": "2026-10-20T09:00:00Z", "task_id": "0002-second", "version": 1, **est(3600, 7200, (3e7, 5e7), (10, 20))}) + "\n")
        sink = Path(self._tmp.name) / "sink"
        sink.mkdir()
        self.env2 = mock.patch.dict(os.environ, {"CCP_TELEMETRY_DIR": str(sink)})
        self.env2.start()
        # hourly samples, each interval's rise 0.1% per dollar of usage, half in the plane, half outside
        t0 = time.time() - 12 * 3600
        resets = iso(time.time() + 3 * 86400)
        b = self.q / "board"
        b.mkdir(exist_ok=True)
        pct, samples, plane, out = 20.0, [], [], []
        for i in range(10):
            samples.append({"at": iso(t0 + i * 3600), "five_hour": 5, "seven_day": round(pct, 3), "resets_at": resets})
            for j, dst in ((1, plane), (2, out)):
                dst.append({"at": iso(t0 + i * 3600 + 60 * j), "model": "claude-opus-5-5", "input_tokens": 1000, "output_tokens": 0,
                            "cache_read_tokens": 0, "cache_creation_tokens": 0, "cost_usd": 5.0 + i, "request_id": f"x{i}-{j}"})
            pct += 0.1 * 2 * (5.0 + i)
        with (b / "allowance.jsonl").open("w") as fh:
            fh.writelines(json.dumps(s) + "\n" for s in samples)
        with (b / "usage-requests.jsonl").open("a") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in plane)
        (sink / f"usage-requests-{iso(t0)[:10]}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in out))

    def render(self, b, h="#tab=queue"):
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        loc = "globalThis.location = {hash: %s, pathname: '/b', search: ''};\n" % json.dumps(h)
        r = subprocess.run(["node", "-e", HASH_STUB + loc + js + "\nprocess.stdout.write(JSON.stringify(out.join('')));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_the_build_carries_the_forecast_and_the_fit(self):
        self.seed_forecast()
        b = self.build()[0]
        f = b["forecast"]
        self.assertNotIn("_error", f)
        self.assertEqual(f["in_flight"], ["0002-second"])
        self.assertEqual(f["backlog"]["task_ids"], ["0002-second"])
        self.assertTrue(f["advisory"])
        a = f["allowance"]
        self.assertEqual(a["fit"]["chosen"], "cost", a)
        self.assertAlmostEqual(a["fit"]["baseline_pct_per_h"] or 0, 0, delta=5)
        self.assertGreater(a["pct_now"], 20)
        self.assertIn("80.0", a["crossings"])
        self.assertTrue((self.q / "board" / "forecast-fit.json").is_file())  # the cache, keyed by the samples
        self.assertEqual(b["forecast"]["allowance"]["fit"], self.build()[0]["forecast"]["allowance"]["fit"])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_page_shows_the_forecast_in_the_queue_tab_and_the_strip_escaped(self):
        self.seed_forecast()
        b = self.build()[0]
        html = self.render(b)
        head, rest = html.split('<div class="pane grid"', 1)
        self.assertIn("P50: +", head)                 # the strip's projection
        self.assertIn("<h2>Forecast</h2>", html)
        self.assertIn("ETA P50 / P90", html)
        self.assertIn("leave-one-out error", html)   # Plane health's Allowance card
        self.assertIn("Estimates, not commitments", html)
        h = self.render(_hostile(b))
        for raw in ("<!--", "<script", "<img", "</script"):
            self.assertNotIn(raw, h)
        self.assertIn("&lt;!--&lt;script&gt;", h)
        self.assertNotIn(HOSTILE, h)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_a_broken_or_empty_forecast_keeps_the_page(self):
        self.seed()
        b = self.build()[0]
        for f in ({"_error": "boom" + HOSTILE}, {"note": "n" + HOSTILE}, {"point": {"eta": 3, "allowance": "x"}, "allowance": 5},
                  {"backlog": {"allowance": {"burn": {}, "pct": None}}, "allowance": {"fit": {"chosen": "cost", "models": 3}}}):
            b["forecast"] = f
            html = self.render(b)
            self.assertIn("Now, in detail", html)
            self.assertNotIn("<script", html)
        b["forecast"] = {"_error": "boom"}
        self.assertIn("Forecast failed", self.render(b))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_forecast_card_shows_the_pauses_escaped(self):
        self.seed_forecast()
        b = self.build()[0]
        f = b["forecast"]
        f["session"] = {"modelled": True, "r5": 6.1, "n": 26, "park_pct": 95, "pct_now": 40}
        f["backlog"]["session"] = {"pauses": {"p50": 2, "p90": 3}, "paused_h": {"p50": 1.6, "p90": 2.4}, "share": 1.0}
        html = self.render(b)
        self.assertIn("5-hour limit", html)
        self.assertIn("pauses P50 2 (1.6 h) / P90 3 (2.4 h)", html)
        self.assertIn("r5 6.1", html)
        h = self.render(_hostile(b))
        self.assertNotIn("<script", h)
        self.assertNotIn(HOSTILE, h)


class ReviewFixes(unittest.TestCase):
    def test_two_tasks_deviates_correlate_at_rho(self):
        order = ["a", "b"]
        dur = {t: forecast.lognormal(1000, 2000) for t in order}
        s = dur["a"][1]
        r = forecast.simulate(order, {}, dur, {}, [0.0], NOW, {}, trials=6000,
                              targets={"a": ["a"], "b": ["b"]})
        ea, eb = r["targets"]["a"]["end"], r["targets"]["b"]["end"]
        za = [(math.log(e - NOW) - math.log(1000)) / s for e in ea]
        zb = [(math.log(b - a) - math.log(1000)) / s for a, b in zip(ea, eb)]
        ma, mb = sum(za) / len(za), sum(zb) / len(zb)
        cov = sum((x - ma) * (y - mb) for x, y in zip(za, zb)) / len(za)
        va = sum((x - ma) ** 2 for x in za) / len(za)
        vb = sum((y - mb) ** 2 for y in zb) / len(zb)
        self.assertAlmostEqual(cov / math.sqrt(va * vb), forecast.RHO, delta=0.05)

    def test_the_task_in_flight_shares_the_common_shock(self):
        dur = {t: forecast.lognormal(1000, 3000) for t in ("a", "b")}
        r = forecast.simulate(["a", "b"], {}, dur, {}, [0.0], NOW, {"a": 10.0}, trials=4000,
                              targets={"a": ["a"], "b": ["b"]})
        ea, eb = r["targets"]["a"]["end"], r["targets"]["b"]["end"]
        la = [math.log(e - NOW + 10) for e in ea]
        lb = [math.log(b - a) for a, b in zip(ea, eb)]
        ma, mb = sum(la) / len(la), sum(lb) / len(lb)
        cov = sum((x - ma) * (y - mb) for x, y in zip(la, lb)) / len(la)
        corr = cov / math.sqrt(sum((x - ma) ** 2 for x in la) / len(la) * sum((y - mb) ** 2 for y in lb) / len(lb))
        self.assertGreater(corr, 0.15)
        self.assertTrue(all(e >= NOW for e in ea))

    def test_past_100_percent_never_fits_and_says_it_runs_out(self):
        dur = {t: forecast.lognormal(3600, 3600) for t in ("a", "b")}
        x = {"cost": {"a": forecast.lognormal(10, 10), "b": forecast.lognormal(10, 10)}}
        burn = {"k": 1.0, "per_s": 0.0, "pct_now": 90.0, "reset": NOW + 1e6, "levels": [95.0, 100.0], "measure": "cost"}
        r = forecast.simulate(["a", "b"], {}, dur, x, [0.0], NOW, {}, trials=100, targets={"t": ["a", "b"]}, burn=burn)
        t = r["targets"]["t"]
        self.assertTrue(all(p > 100 for p in t["pct"]))
        self.assertTrue(all(e is not None and NOW + 3000 < e <= NOW + 7200 * 1.2 for e in t["exhaust"]))
        self.assertIn("exhausts the weekly allowance", forecast.exhaust_text({"exhausts": {"p50": iso(NOW), "p90_early": iso(NOW)}}))
        self.assertIn("may exhaust", forecast.exhaust_text({"exhausts": {"share": 0.2, "p50": None, "p90_early": iso(NOW)}}))

    def test_after_compares_times_not_strings(self):
        d = Path(tempfile.mkdtemp())
        try:
            f = d / "r.jsonl"
            f.write_text("".join(json.dumps(r) + "\n" for r in [
                {"request_id": "early", "at": "2027-01-15T10:00:00+01:00"},       # 09:00Z: before; as a string, after
                {"request_id": "late", "at": "2027-01-15T09:45:00.5Z"},
                {"request_id": "short", "at": "2027-01-15T09:31Z"}]))
            after = forecast._ep("2027-01-15T09:30:00Z")
            self.assertEqual(sorted(r["request_id"] for r in forecast._rows([f], after=after)), ["late", "short"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class FitCache(unittest.TestCase):
    def setUp(self):
        self.q = Path(tempfile.mkdtemp())
        self.sink = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"CCP_TELEMETRY_DIR": str(self.sink)})
        self.env.start()
        (self.q / "board").mkdir()
        rows, samples, self.end = AllowanceFit().synth(lambda sp: 0.1 * sum(c for *_, c in sp))
        self.p = self.q / "board" / "usage-requests.jsonl"
        self.p.write_text("".join(json.dumps(r) + "\n" for r in rows))
        (self.q / "board" / "allowance.jsonl").write_text("".join(json.dumps(s) + "\n" for s in samples))
        self.fits = 0
        real = forecast.allowance_fit

        def counting(*a, **k):
            self.fits += 1
            return real(*a, **k)
        self.stub = mock.patch.object(forecast, "allowance_fit", counting)
        self.stub.start()

    def tearDown(self):
        self.stub.stop()
        self.env.stop()
        shutil.rmtree(self.q, ignore_errors=True)
        shutil.rmtree(self.sink, ignore_errors=True)

    def append(self, at):
        with self.p.open("a") as fh:
            fh.write(json.dumps({"request_id": f"x{at}", "at": iso(at), "model": "claude-opus-5-5", "cost_usd": 3,
                                 "input_tokens": 5}) + "\n")

    def test_the_key_follows_the_telemetry_files(self):
        forecast.cached_fit(self.q, self.end)
        forecast.cached_fit(self.q, self.end)
        self.assertEqual(self.fits, 1)
        self.append(self.end + 600)          # after the fitted span: the fit stands
        forecast.cached_fit(self.q, self.end + 700)
        self.assertEqual(self.fits, 1)
        self.append(self.end - 600)          # a late row inside the span: re-fit
        forecast.cached_fit(self.q, self.end + 700)
        self.assertEqual(self.fits, 2)
        text = self.p.read_text()
        self.p.unlink()
        self.p.write_text(text[: len(text) // 2])  # replaced and shorter: re-fit
        forecast.cached_fit(self.q, self.end + 700)
        self.assertEqual(self.fits, 3)
        (self.sink / "usage-requests-2027-01-15.jsonl").write_text("")  # a new file: re-fit
        forecast.cached_fit(self.q, self.end + 700)
        self.assertEqual(self.fits, 4)


if __name__ == "__main__":
    unittest.main()


class SessionWindow(unittest.TestCase):
    """SPEC §26 (2026-10-23): the 5-hour window as pauses, its r5 fit, and the non-plane burn's floor."""

    def samples(self, pairs, step=1800, five_resets=None):
        out = []
        for i, (five, seven) in enumerate(pairs):
            out.append({"at": iso(NOW + i * step), "five_hour": five, "seven_day": seven, "resets_at": "2027-01-05T04:00:00+00:00",
                        **({"five_hour_resets_at": five_resets[i]} if five_resets else {})})
        return out

    def test_r5_is_the_ratio_of_the_rises_within_one_window(self):
        # five rises 6 per weekly point, then a 5-hour reset (a fall) and another window at 7 per point
        s = self.samples([(5, 10), (11, 11), (23, 13), (1, 13), (8, 14), (22, 16), (23, 16.5), (30, 17.5)])
        f = forecast.session_fit(s)
        self.assertEqual(f["n"], 5)  # the fall starts afresh; a rise under 1 point carries forward
        self.assertAlmostEqual(f["r5"], (6 + 12 + 7 + 14 + 8) / (1 + 2 + 1 + 2 + 1.5), places=3)

    def test_too_few_intervals_and_different_windows(self):
        self.assertIsNone(forecast.session_fit(self.samples([(5, 10), (11, 11), (23, 13)]))["r5"])
        self.assertIn("needs 3", forecast.session_fit(self.samples([(5, 10), (11, 11)]))["note"])
        # rows that name different 5-hour resets are not one window, even when five did not fall
        r = [iso(NOW + 3600), iso(NOW + 3600), iso(NOW + 3600 + 5 * 3600), iso(NOW + 3600 + 5 * 3600)]
        self.assertEqual(forecast.session_fit(self.samples([(5, 10), (11, 11), (12, 12), (20, 13)], five_resets=r))["n"], 2)
        # more than 5 h apart is never one window
        self.assertEqual(forecast.session_fit(self.samples([(5, 10), (11, 11), (12, 12)], step=6 * 3600))["n"], 0)

    def test_a_real_sample_gives_about_six(self):
        # a copy of a product's board/allowance.jsonl (numbers and times only), never the live
        # queue (tests/__init__.py); it holds two pairs of samples taken in the same second
        p = Path(__file__).parent / "data" / "allowance-sample.jsonl"
        f = forecast.session_fit([json.loads(x) for x in p.read_text().splitlines() if x.strip()])
        self.assertTrue(5.5 <= f["r5"] <= 7.5, f)

    def tied(self):
        """Samples as in that file: a pair in the same second, differing only in its resets_at jitter, so the
        (time, row) tuples are not equal and sorting them compared the dicts (a TypeError)."""
        rows = self.samples([(5, 10), (11, 11), (12, 12), (20, 13)])
        rows.insert(2, {**rows[1], "resets_at": "2027-01-05T04:00:00.5+00:00"})
        return rows

    def test_no_five_hour_figure_models_no_pauses(self):
        """§25.1: a weekly-only latest sample means no 5-hour limit to pause on."""
        from types import SimpleNamespace
        cfg = SimpleNamespace(telemetry={})
        sess, info = forecast._session(cfg, {"session": {"r5": 6.0, "n": 10}}, {"pct_now": 40.0},
                                       {"five_hour": None, "seven_day": 43.0}, NOW)
        self.assertIsNone(sess)
        self.assertIn("no 5-hour limit", info["note"])

    def test_a_tie_in_the_session_fit(self):
        self.assertIsNotNone(forecast.session_fit(self.tied())["n"])

    def test_a_tie_in_the_allowance_intervals(self):
        self.assertIsInstance(forecast.intervals(self.tied()), list)
        p = Path(__file__).parent / "data" / "allowance-sample.jsonl"
        self.assertTrue(forecast.intervals([json.loads(x) for x in p.read_text().splitlines() if x.strip()]))

    def test_a_tie_in_the_request_series(self):
        reqs = [{"at": iso(NOW), "model": "claude-opus-5-5", "output_tokens": n, "cost_usd": 0.1} for n in (1, 2)]
        self.assertEqual(forecast.Series(reqs).t, [NOW, NOW])

    def setup(self, n=12):
        order = [f"{i:04d}-t" for i in range(n)]
        dur = {t: forecast.lognormal(3600, 5400) for t in order}
        x = {"cost": {t: forecast.lognormal(20, 30) for t in order}}
        burn = {"k": 0.1, "per_s": 0.2 / 3600, "pct_now": 20.0, "reset": NOW + 5 * 86400, "levels": [80.0], "measure": "cost"}
        return order, dur, x, burn

    def test_a_backlog_that_needs_more_than_one_window_pauses_and_ends_later(self):
        order, dur, x, burn = self.setup()
        # per task about 2 weekly % an hour, so 12 %/h of the 5-hour window: the park comes within the hour
        sess = {"r5": 6.0, "park": 95.0, "margin": 180.0, "w_end": NOW + 40 * 60, "pct_now": 91.0}
        off = forecast.simulate(order, {}, dur, x, [0.0], NOW, {}, trials=200, targets={"t": order}, burn=burn)
        on = forecast.simulate(order, {}, dur, x, [0.0], NOW, {}, trials=200, targets={"t": order}, burn=burn, session=sess)
        a, b = off["targets"]["t"], on["targets"]["t"]
        self.assertTrue(all(p >= 1 for p in b["pauses"]))
        self.assertTrue(all(e1 > e0 for e0, e1 in zip(a["end"], b["end"])))
        self.assertTrue(all(abs((e1 - e0) - s) < 1e-6 for e0, e1, s in zip(a["end"], b["end"], b["paused_s"])))
        # the first pause runs from the park to the reset + margin: never before the reset
        self.assertGreater(forecast.quantile(b["paused_s"], 0.5), 0)
        self.assertEqual(a["pauses"], [])  # not modelled without a session
        # with the window just reset and a small backlog, no pause
        small = forecast.simulate(order[:1], {}, dur, x, [0.0], NOW, {}, trials=50, targets={"t": order[:1]}, burn=burn,
                                  session={**sess, "w_end": NOW + 5 * 3600, "pct_now": 0.0})
        self.assertEqual(set(small["targets"]["t"]["pauses"]), {0})

    def test_a_pause_waits_for_the_windows_end_and_the_next_window_starts_at_the_resume(self):
        # one task of 3 h burning 10 weekly % (r5 1: 10 five-%/3 h); the window is at 90 and ends in 2 h
        pts = forecast._pauses([NOW], [NOW + 3 * 3600], [10.0], 0.0, NOW,
                               {"r5": 1.0, "park": 95.0, "margin": 180.0, "w_end": NOW + 7200, "pct_now": 90.0})
        self.assertEqual(len(pts), 1)
        t_park, shift = pts[0]
        self.assertAlmostEqual(t_park - NOW, 5 / (10 / 3 / 3600))  # 1.5 h to the park
        self.assertAlmostEqual(t_park + shift, NOW + 7200 + 180)   # resumes at the window's end + margin
        # the park % already reached: work stops at once
        pts = forecast._pauses([NOW], [NOW + 3600], [1.0], 0.0, NOW,
                               {"r5": 1.0, "park": 95.0, "margin": 0.0, "w_end": NOW + 600, "pct_now": 96.0})
        self.assertEqual(pts, [(NOW, 600.0)])

    def test_collect_with_the_park_off_is_the_old_forecast(self):
        order, dur, x, burn = self.setup(6)
        r1 = forecast.simulate(order, {}, dur, x, [0.0], NOW, {}, trials=100, targets={"t": order}, burn=burn)
        r2 = forecast.simulate(order, {}, dur, x, [0.0], NOW, {}, trials=100, targets={"t": order}, burn=burn, session=None)
        self.assertEqual(r1["targets"]["t"]["end"], r2["targets"]["t"]["end"])
        cfg = SimpleNamespace(telemetry={"session_park_pct": None})
        sess, info = forecast._session(cfg, {"session": {"r5": 6.0, "n": 9}}, burn, {}, NOW)
        self.assertIsNone(sess)
        self.assertIn("null", info["note"])
        sess, info = forecast._session(SimpleNamespace(telemetry={}), {"session": {"r5": None, "n": 1, "note": "too few"}}, burn, {}, NOW)
        self.assertIsNone(sess)
        sess, info = forecast._session(SimpleNamespace(telemetry={}), {"session": {"r5": 6.0, "n": 9}}, burn,
                                       {"five_hour": 80.0, "seven_day": 18.0, "five_hour_resets_at": iso(NOW + 1200)}, NOW)
        self.assertEqual((sess["w_end"], sess["pct_now"]), (NOW + 1200, 80.0 + 6.0 * 2.0))  # + r5 x the weekly since
        sess, _ = forecast._session(SimpleNamespace(telemetry={}), {"session": {"r5": 6.0, "n": 9}}, burn,
                                    {"five_hour": 80.0, "seven_day": 18.0}, NOW)
        self.assertEqual((sess["w_end"], sess["pct_now"]), (NOW + forecast.SESSION_S, 0.0))  # unknown end: a fresh window

    def test_the_text_names_the_pauses(self):
        line = forecast.session_text({"pauses": {"p50": 2.0, "p90": 3.0}, "paused_h": {"p50": 1.6, "p90": 2.4}},
                                     {"r5": 6.4, "n": 9})
        self.assertEqual(line, "5-hour limit: pauses P50 2 (1.6 h) / P90 3 (2.4 h), r5 6.4 (n 9)")

    def test_a_short_sink_history_is_averaged_over_72_hours(self):
        # 26 h of sink at $10/h, 0.1% per dollar: 1%/h over 26 h, floored to 26/72 of that
        rows, samples = [], []
        pct = 10.0
        for i in range(8):
            samples.append({"at": iso(NOW + i * 3600), "seven_day": pct, "resets_at": "2027-01-05T04:00:00+00:00"})
            pct += 0.1 * 10
        rng = random.Random(3)
        sink = [{"at": iso(NOW - 26 * 3600 + 60 + h * 3600), "model": "claude-opus-5-5", "input_tokens": rng.randint(1, 10 ** 6), "output_tokens": 0,
                 "cache_read_tokens": 0, "cache_creation_tokens": 0, "cost_usd": 10.0, "request_id": f"s{h}"} for h in range(26 + 7)]
        fit = forecast.allowance_fit(samples, forecast.Series([]), forecast.Series(sink), NOW + 7 * 3600)
        self.assertEqual(fit["chosen"], "cost")
        self.assertTrue(fit["baseline_floored"])
        self.assertEqual(fit["baseline_span_h"], 72)
        self.assertAlmostEqual(fit["baseline_hours"], 33, delta=0.1)
        self.assertAlmostEqual(fit["baseline_pct_per_h"], 0.1 * 10 * 33 / 72, delta=0.02)

    def test_the_simulation_with_pauses_stays_fast(self):
        order = [f"{i:04d}-t" for i in range(20)]
        dur = {t: forecast.lognormal(3600, 7200) for t in order}
        x = {"tokens": {t: forecast.lognormal(3e7, 5e7) for t in order}, "cost": {t: forecast.lognormal(30, 40) for t in order}}
        burn = {"k": 0.1, "per_s": 0.3 / 3600, "pct_now": 30.0, "reset": NOW + 3 * 86400, "levels": [80.0, 95.0], "measure": "cost"}
        sess = {"r5": 6.1, "park": 95.0, "margin": 180.0, "w_end": NOW + 2400, "pct_now": 91.0}
        t0 = time.perf_counter()
        r = forecast.simulate(order, {}, dur, x, [10.0, 20.0, -600.0], NOW, {order[0]: 600.0}, forecast.TRIALS, forecast.SEED,
                              {"point": order[:12], "backlog": order}, burn, None, sess)
        took = time.perf_counter() - t0
        self.assertGreater(forecast.quantile([float(p) for p in r["targets"]["backlog"]["pauses"]], 0.5), 1)
        self.assertLess(took, 1.0)  # about 0.06 s on the Mac (0.03 s without the pauses)



class SessionReviewFixes(unittest.TestCase):
    def test_no_sink_is_not_floored_and_a_null_park_prints_as_before(self):
        rows, samples = [], []
        for i in range(8):
            samples.append({"at": iso(NOW + i * 3600), "seven_day": 10.0 + i, "resets_at": "2027-01-05T04:00:00+00:00"})
            rows.append({"at": iso(NOW + i * 3600 + 60), "model": "claude-opus-5-5", "input_tokens": 1000 + i * 7, "output_tokens": 0,
                         "cache_read_tokens": 0, "cache_creation_tokens": 0, "cost_usd": 10.0, "request_id": f"p{i}"})
        fit = forecast.allowance_fit(samples, forecast.Series(rows), None, NOW + 8 * 3600)
        self.assertIsNone(fit["baseline_pct_per_h"])
        self.assertFalse(fit["baseline_floored"])
        alw = {"pct_now": 20.0, "pct_sample": 18.0, "sample_at": iso(NOW), "added_since_sample": 2.0, "resets_at": iso(NOW + 86400),
               "crossings": {}, "fit": {**{k: fit.get(k) for k in ("chosen", "per_unit_text", "loo_rmse", "n", "mean_interval_h",
                                                                   "mean_delta", "baseline_pct_per_h", "baseline_floored")},
                                        "models": {}}}
        f = {"trials": 10, "allowance": alw, "throughput": {}, "session": {"park_pct": None, "note": "null park"}}
        out = forecast.text(f)
        self.assertNotIn("averaged as", out)
        self.assertNotIn("5-hour", out)
        f["session"] = {"park_pct": 95.0, "note": "2 usable interval(s)"}
        self.assertIn("5-hour window not modelled", forecast.text(f))
