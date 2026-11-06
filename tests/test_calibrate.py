"""SPEC §26.6 phase D: the calibration loop. The bias and width maths on synthetic data, shrinkage,
recency, the too-few-pairs fallback, the rolling-origin check's no-leakage rule, rho, the
calibrated read path, the forecast's use of it, the estimator's prompt input, the cache, the
config block and the board (escaped)."""
from __future__ import annotations

import json
import math
import random
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ccp import calibrate, config, estimate, estimator, forecast
from tests.helpers import Product
from tests.test_board_drill import Fixture
from tests.test_board_quality import HOSTILE

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
INF = {"half_life": 1e9, "min_pairs": 8, "k": None}


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def task_rows(i: int, p50: float, p90: float, actual: float, kind: str = "feature", fam: str = "sf",
              tokens: tuple[float, float, float] | None = None, src: str = "baseline") -> tuple[str, list[dict]]:
    """Task i starts at T0 + i h and merges 30 min later; its estimate stands a minute before the start."""
    tid = f"{i:04d}-{fam}-t"
    start = T0 + timedelta(hours=i)
    est = {"at": iso(start - timedelta(minutes=1)), "as_of": iso(start - timedelta(minutes=1)), "task_id": tid,
           "source": src, "version": 1, "inputs": {"features": {"kind": kind, "family": fam}},
           "total": {"p50_s": p50, "p90_s": p90},
           "tokens": {"p50": tokens[0], "p90": tokens[1]} if tokens else None, "cost_usd": None}
    act = {"at": iso(start + timedelta(minutes=31)), "task_id": tid, "source": "actual", "version": 1,
           "start_at": iso(start), "merged_at": iso(start + timedelta(minutes=30)), "wall_s": actual,
           "tokens": tokens[2] if tokens else None, "cost_usd": None}
    return tid, [est, act]


def synthetic(n: int, bias: float = 1.0, sigma_true: float = 0.4, sigma_est: float = 0.4, seed: int = 7,
              kind: str = "feature", fam: str = "sf", start: int = 0) -> dict[str, list[dict]]:
    """Estimates P50 = 1000 s, P90 = P50 * exp(1.2816 sigma_est); actuals lognormal(bias * P50, sigma_true)."""
    rng = random.Random(seed)
    by = {}
    for i in range(start, start + n):
        p50 = 1000.0
        x = bias * p50 * math.exp(sigma_true * rng.gauss(0, 1))
        tid, rs = task_rows(i, p50, p50 * math.exp(calibrate.Z90 * sigma_est), x, kind, fam)
        by[tid] = rs
    return by


class Maths(unittest.TestCase):
    def test_weighted_quantile(self):
        self.assertEqual(calibrate.wquantile([3, 1, 2], [1, 1, 1], 0.5), 2)
        self.assertAlmostEqual(calibrate.wquantile([1, 2], [1, 1], 0.5), 1.5)
        self.assertAlmostEqual(calibrate.wquantile([1, 2], [1, 3], 0.5), 1.75)  # pulled toward the heavier value
        self.assertIsNone(calibrate.wquantile([], [], 0.5))
        self.assertEqual(calibrate.wquantile([5, 9], [1, 1], 0.0), 5)
        self.assertEqual(calibrate.wquantile([5, 9], [1, 1], 1.0), 9)

    def test_the_bias_is_the_median_actual_over_p50(self):
        m = calibrate.build(synthetic(400, bias=1.5), INF)
        f = m["factors"]["baseline"]["wall"]
        self.assertTrue(f["fitted"])
        self.assertAlmostEqual(f["bias"], 1.5, delta=0.08)
        self.assertEqual(f["n"], 400)

    def test_the_width_makes_p90_cover_nine_in_ten(self):
        by = synthetic(600, bias=1.0, sigma_true=0.8, sigma_est=0.4)
        f = calibrate.build(by, INF)["factors"]["baseline"]["wall"]
        self.assertAlmostEqual(f["width_raw"], 2.0, delta=0.2)
        self.assertGreater(f["width"], 1.8)  # shrunk a little toward 1 (n / (n + K_WIDTH))
        cal = {"factors": calibrate.build(by, INF)["factors"]}
        cov = [rs[1]["wall_s"] <= estimate.latest(rs, "baseline", calibrated=True, cal=cal)["total"]["p90_s"]
               for rs in by.values()]
        raw = [rs[1]["wall_s"] <= rs[0]["total"]["p90_s"] for rs in by.values()]
        self.assertLess(sum(raw) / len(raw), 0.8)
        self.assertAlmostEqual(sum(cov) / len(cov), 0.9, delta=0.03)

    def test_a_p90_already_wide_enough_is_never_narrowed(self):
        f = calibrate.build(synthetic(200, sigma_true=0.2, sigma_est=0.8), INF)["factors"]["baseline"]["wall"]
        self.assertLess(f["width_raw"], 1.0)
        self.assertEqual(f["width"], 1.0)

    def test_too_few_pairs_give_factors_of_one_and_say_so(self):
        m = calibrate.build(synthetic(5, bias=3.0), INF)
        f = m["factors"]["baseline"]["wall"]
        self.assertFalse(f["fitted"])
        self.assertEqual((f["bias"], f["width"]), (1.0, 1.0))
        self.assertIn("too few pairs (5 < 8)", f["note"])
        self.assertFalse(m["factors"]["agent"]["wall"]["fitted"])
        rs = next(iter(synthetic(5, bias=3.0).values()))
        c = estimate.latest(rs, "baseline", calibrated=True, cal=m)
        self.assertEqual(c["total"], {"p50_s": 1000, "p90_s": int(round(rs[0]["total"]["p90_s"]))})
        self.assertIn("too few pairs", calibrate.text(m))

    def test_recent_pairs_weigh_more(self):
        old = synthetic(60, bias=2.0, sigma_true=0.05, seed=1)
        new = synthetic(60, bias=1.0, sigma_true=0.05, seed=2, start=60)
        by = {**old, **new}
        flat = calibrate.build(by, INF)["factors"]["baseline"]["wall"]["bias"]
        recent = calibrate.build(by, {"half_life": 10, "min_pairs": 8, "k": None})["factors"]["baseline"]["wall"]["bias"]
        self.assertGreater(flat, 1.3)
        self.assertLess(recent, 1.1)

    def test_a_small_group_is_shrunk_toward_its_prior_a_large_one_keeps_its_own(self):
        by = {**synthetic(100, bias=1.0, sigma_true=0.3, fam="sf", seed=3),
              **synthetic(2, bias=5.0, sigma_true=0.01, fam="r2", seed=4, start=100),
              **synthetic(100, bias=2.0, sigma_true=0.3, fam="ops", seed=5, start=102)}
        s = {"half_life": 1e9, "min_pairs": 8, "k": 10.0}
        f = calibrate.build(by, s)["factors"]["baseline"]["wall"]
        r2, sf, ops = f["family"]["r2"], f["family"]["sf"], f["family"]["ops"]
        self.assertAlmostEqual(r2["weight"], 2 / 12, places=2)  # n / (n + k) with equal weights
        self.assertAlmostEqual(r2["raw"], 5.0, delta=0.1)
        self.assertLess(r2["bias"], 2.5)
        self.assertGreater(sf["weight"], 0.9)
        self.assertAlmostEqual(ops["bias"] / sf["bias"], 2.0, delta=0.25)
        # the group factor is what a task of that family gets
        b, grp, n = calibrate.factor(f, "feature", "r2")
        self.assertEqual((grp, n), ("family r2", 2))
        self.assertAlmostEqual(b, r2["bias"], places=2)
        self.assertEqual(calibrate.factor(f, "feature", "unknown")[1], "kind feature")
        self.assertEqual(calibrate.factor(f, "chore", "unknown")[1], "overall")

    def test_empirical_bayes_k(self):
        same = {**synthetic(40, fam="a", seed=1), **synthetic(40, fam="b", seed=2, start=40),
                **synthetic(40, fam="c", seed=3, start=80)}
        f = calibrate.build(same, INF)["factors"]["baseline"]["wall"]
        self.assertGreater(f["k"], 30)  # no real difference: groups lean on their prior
        for v in f["family"].values():  # each pulled at least halfway from its raw median to the overall
            self.assertLess(abs(math.log(v["bias"] / f["bias"])), 0.5 * abs(math.log(v["raw"] / f["bias"])) + 1e-3)
        apart = {**synthetic(40, bias=0.5, fam="a", seed=1), **synthetic(40, bias=1.0, fam="b", seed=2, start=40),
                 **synthetic(40, bias=2.0, fam="c", seed=3, start=80)}
        f = calibrate.build(apart, INF)["factors"]["baseline"]["wall"]
        self.assertLess(f["k"], 10)
        self.assertIn("empirical Bayes", f["k_note"])
        two = {**synthetic(40, fam="a", seed=1), **synthetic(40, fam="b", seed=2, start=40)}
        f = calibrate.build(two, INF)["factors"]["baseline"]["wall"]
        self.assertEqual(f["k"], calibrate.K_DEFAULT)
        self.assertIn("default", f["k_note"])

    def test_each_source_and_metric_has_its_own_factors(self):
        by = {}
        rng = random.Random(9)
        for i in range(30):
            tid, rs = task_rows(i, 1000, 2000, 1000 * math.exp(0.2 * rng.gauss(0, 1)), tokens=(1e6, 2e6, 3e6))
            _, ag = task_rows(i, 500, 900, 0, src="agent")
            by[tid] = rs + [ag[0]]
        m = calibrate.build(by, INF)
        self.assertAlmostEqual(m["factors"]["baseline"]["wall"]["bias"], 1.0, delta=0.15)
        self.assertAlmostEqual(m["factors"]["baseline"]["tokens"]["bias"], 3.0, delta=0.01)
        self.assertAlmostEqual(m["factors"]["agent"]["wall"]["bias"], 2.0, delta=0.3)
        self.assertFalse(m["factors"]["baseline"]["cost"]["fitted"])
        self.assertEqual(m["pairs"], {"baseline": 30, "agent": 30})


class Rolling(unittest.TestCase):
    def test_each_task_is_calibrated_only_on_tasks_merged_before_it_started(self):
        by = synthetic(30, bias=1.4)
        ps = calibrate.pairs(by)["baseline"]
        seen = []
        real = calibrate.fit

        def spy(p, s):
            seen.append([t["merged_at"] for t in p["x"]])
            return real(p, s)
        with mock.patch.object(calibrate, "fit", side_effect=spy):
            ev = calibrate.evaluate(ps, INF)
        order = sorted(ps, key=lambda p: p["start_at"])
        self.assertEqual(len(seen), len(order))
        for p, train in zip(order, seen):
            self.assertTrue(all(m < p["start_at"] for m in train))
        self.assertEqual(len(seen[0]), 0)
        self.assertEqual(ev["metrics"]["wall"]["fitted"], 30 - 8)

    def test_a_later_actual_never_changes_an_earlier_tasks_check(self):
        by = synthetic(30, bias=1.4)
        a = calibrate.evaluate(calibrate.pairs(by)["baseline"], INF)
        last = sorted(by)[-1]
        by[last][1]["wall_s"] = 1e7
        b = calibrate.evaluate(calibrate.pairs(by)["baseline"], INF)
        self.assertEqual(a["z_wall"][:-1], b["z_wall"][:-1])
        self.assertNotEqual(a["z_wall"][-1], b["z_wall"][-1])

    def test_calibration_lifts_a_biased_estimates_coverage(self):
        by = synthetic(120, bias=1.6, sigma_true=0.6, sigma_est=0.3)
        ev = calibrate.build(by, INF)["evaluation"]["baseline"]["wall"]
        self.assertLess(ev["raw"]["share_p50"], 0.3)
        self.assertAlmostEqual(ev["calibrated"]["share_p50"], 0.5, delta=0.12)
        self.assertGreater(ev["calibrated"]["share_p90"], ev["raw"]["share_p90"] + 0.15)


class Rho(unittest.TestCase):
    def test_independent_residuals_give_about_zero(self):
        rng = random.Random(1)
        r = calibrate.fit_rho([rng.gauss(0, 1) for _ in range(400)])
        self.assertTrue(r["fitted"])
        self.assertLess(abs(r["raw"]), 0.08)

    def test_a_shared_drift_gives_a_positive_rho(self):
        rng = random.Random(2)
        z = []
        for _ in range(30):  # blocks of 20 with a common part: corr 0.4 within a block
            c = rng.gauss(0, 1)
            z += [math.sqrt(0.4) * c + math.sqrt(0.6) * rng.gauss(0, 1) for _ in range(20)]
        r = calibrate.fit_rho(z)
        self.assertTrue(r["fitted"], r)
        self.assertGreater(r["value"], 0.15)

    def test_too_few_or_too_noisy_keeps_the_default(self):
        r = calibrate.fit_rho([0.1, -0.2] * 10)
        self.assertEqual((r["value"], r["fitted"]), (calibrate.RHO_DEFAULT, False))
        self.assertIn("too few residuals", r["note"])
        rng = random.Random(3)
        with mock.patch.object(calibrate, "RHO_MAX_SE", 0.001):
            r = calibrate.fit_rho([rng.gauss(0, 1) for _ in range(100)])
        self.assertFalse(r["fitted"])
        self.assertIn("too uncertain", r["note"])

    def test_the_backtest_draws_a_wide_band_as_the_forecast_does(self):
        """A P90 over 4 x P50 draws as 4 x, as in the forecast: the backtest's sums match the capped bands'."""
        # actuals at 2.5 x P50: over the capped draws' P50 sums, under the 40x lognormals' (mean 59 x P50)
        bands = [(2500.0, 1000.0, 40000.0) for _ in range(40)]
        capped = calibrate.backtest_sums([(x, c50, 4 * c50) for x, c50, _ in bands], 0.3)
        self.assertEqual(calibrate.backtest_sums(bands, 0.3), capped)
        self.assertEqual(capped["share_p50"], 0.0)

    def test_the_default_stays_unless_the_backtest_favours_the_fitted_rho(self):
        rng = random.Random(5)
        # calibrated bands whose actual sums are drawn independently: a low rho fits them
        bands = [(1000 * math.exp(0.5 * rng.gauss(0, 1)), 1000.0, 1000 * math.exp(calibrate.Z90 * 0.5))
                 for _ in range(200)]
        lo = calibrate.choose_rho({"value": 0.0, "fitted": True, "note": "n"}, bands)
        self.assertEqual(set(lo["backtest"]), {"default", "fitted"})
        self.assertGreater(lo["backtest"]["default"]["windows"], 30)
        better = abs(lo["backtest"]["fitted"]["share_p50"] - 0.5) < abs(lo["backtest"]["default"]["share_p50"] - 0.5)
        self.assertEqual(lo["use_fitted"], better)
        self.assertEqual(lo["value"], 0.0 if better else calibrate.RHO_DEFAULT)
        self.assertEqual(lo["fitted_value"], 0.0)
        with mock.patch.object(calibrate, "backtest_sums", side_effect=lambda b, r: {"rho": r, "windows": 5,
                                                                                    "share_p50": 0.5 if r == 0.3 else 0.6}):
            c = calibrate.choose_rho({"value": 0.07, "fitted": True}, bands)
        self.assertEqual((c["value"], c["use_fitted"], c["fitted_value"]), (0.3, False, 0.07))
        self.assertIn("default 0.3", c["choice"])
        with mock.patch.object(calibrate, "backtest_sums", side_effect=lambda b, r: {"rho": r, "windows": 5,
                                                                                    "share_p50": 0.62 if r == 0.3 else 0.52}):
            c = calibrate.choose_rho({"value": 0.07, "fitted": True}, bands)
        self.assertEqual((c["value"], c["use_fitted"]), (0.07, True))
        c = calibrate.choose_rho({"value": 0.3, "fitted": False, "note": "too few residuals"}, bands)
        self.assertEqual((c["value"], c["use_fitted"], c["fitted_value"]), (0.3, False, None))
        self.assertIn("too few residuals", c["choice"])

    def test_outliers_are_winsorized(self):
        rng = random.Random(4)
        z = [rng.gauss(0, 1) for _ in range(200)]
        z[0:3] = [50.0, 30.0, 20.0]
        r = calibrate.fit_rho(z)
        self.assertLess(abs(r["raw"]), 0.1)
        self.assertLess(r["sd_z"], 1.5)


class ReadPath(unittest.TestCase):
    def test_latest_calibrated_derives_and_keeps_the_raw(self):
        by = synthetic(60, bias=2.0, sigma_true=0.3)
        m = calibrate.build(by, INF)
        f = m["factors"]["baseline"]["wall"]
        rs = by[sorted(by)[0]]
        raw = estimate.latest(rs, "baseline")
        c = estimate.latest(rs, "baseline", calibrated=True, cal=m)
        b, _, _ = calibrate.factor(f, "feature", "sf")
        p50, p90 = raw["total"]["p50_s"], raw["total"]["p90_s"]
        self.assertEqual(c["total"]["p50_s"], int(round(p50 * b)))
        self.assertEqual(c["total"]["p90_s"], int(round(p50 * b * (p90 / p50) ** f["width"])))
        self.assertEqual(c["raw"]["total"], raw["total"])
        self.assertEqual(c["calibration"]["wall"]["group"], "family sf")
        self.assertEqual(raw["total"], rs[0]["total"])  # the stored row is untouched
        self.assertIs(estimate.latest(rs, "actual", calibrated=True, cal=m), estimate.latest(rs, "actual"))
        with self.assertRaises(ValueError):
            estimate.latest(rs, "baseline", calibrated=True)
        self.assertIsNone(estimate.latest(rs, "agent", calibrated=True, cal=m))

    def test_a_p90_at_its_p50_still_widens_a_little(self):
        c = calibrate.apply({"source": "baseline", "total": {"p50_s": 100, "p90_s": 100}},
                            {"baseline": {"wall": {"fitted": True, "n": 9, "bias": 1.0, "width": 2.0, "k": 10}}})
        self.assertGreater(c["total"]["p90_s"], 100)

    def test_show_prints_raw_and_calibrated(self):
        by = synthetic(60, bias=2.0)
        m = calibrate.build(by, INF)
        tid = sorted(by)[0]
        out = estimate.show_text(tid, by[tid], m)
        self.assertIn("baseline raw", out)
        self.assertIn("baseline calibrated", out)
        self.assertIn("family sf, n 60", out)
        self.assertNotIn("calibrated", estimate.show_text(tid, by[tid]))


class Store(unittest.TestCase):
    def setUp(self):
        self.q = Path(tempfile.mkdtemp())
        (self.q / "board").mkdir()
        for tid, rs in synthetic(40, bias=1.5).items():
            for r in rs:
                estimate._append(self.q, r)

    def tearDown(self):
        shutil.rmtree(self.q, ignore_errors=True)

    def test_the_model_is_cached_by_its_inputs(self):
        a = calibrate.model(self.q)
        self.assertFalse(a["cached"])
        b = calibrate.model(self.q)
        self.assertTrue(b["cached"])
        self.assertEqual(calibrate.summary(a)["factors"], calibrate.summary(b)["factors"])
        # the cached copy applies the same as a fresh one
        rs = estimate.rows(self.q, "0000-sf-t")
        self.assertEqual(estimate.latest(rs, "baseline", calibrated=True, cal=a)["total"],
                         estimate.latest(rs, "baseline", calibrated=True, cal=b)["total"])
        tid, rs = task_rows(40, 1000, 2000, 9000)
        for r in rs:
            estimate._append(self.q, r)
        c = calibrate.model(self.q)
        self.assertFalse(c["cached"])
        self.assertEqual(c["pairs"]["baseline"], 41)
        p = Product({"estimate": {"calibration": {"half_life": 10}}})
        try:
            self.assertFalse(calibrate.model(self.q, p.cfg)["cached"])  # the settings are in the key
            self.assertEqual(calibrate.settings(p.cfg)["half_life"], 10)
        finally:
            p.cleanup()

    def test_board_view_carries_calibrated_views_and_the_calibration(self):
        v = estimate.board_view(self.q)
        t = v["tasks"]["0000-sf-t"]
        self.assertEqual(t["baseline"]["total"], {"p50_s": 1000, "p90_s": t["baseline"]["total"]["p90_s"]})
        self.assertGreater(t["baseline"]["cal"]["total"]["p50_s"], 1300)
        self.assertEqual(t["baseline_scored"]["cal"]["factors"]["wall"]["group"], "family sf")
        self.assertIn("rho", v["calibration"])
        self.assertNotIn("_lb", json.dumps(v["calibration"]))
        with mock.patch.object(calibrate, "model", side_effect=RuntimeError("boom")):
            v = estimate.board_view(self.q)
        self.assertIn("boom", v["calibration"]["_error"])
        self.assertIsNone(v["tasks"]["0000-sf-t"]["baseline"]["cal"])

    def test_the_estimator_prompt_carries_the_factors_bounded(self):
        txt = estimator.calibration(self.q)
        self.assertIn("the baseline shown above, wall: P50 runs low by", txt)
        self.assertIn("(n=40)", txt)
        self.assertIn("your own past estimates: too few scored pairs yet", txt)
        self.assertLessEqual(len(txt), estimator.B_CALIB + 40)
        with mock.patch.object(estimator, "B_CALIB", 120):
            self.assertIn("[... cut at 120 characters]", estimator.calibration(self.q))
        empty = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(estimator.calibration(empty), "No task has actuals yet.")
        finally:
            shutil.rmtree(empty)
        self.assertEqual(estimator.PROMPT_V, 2)
        self.assertIn("baseline's factors", estimator.TEMPLATE.read_text())


class Forecast(unittest.TestCase):
    def view(self, p50, p90, cal=None):
        return {"source": "baseline", "total": {"p50_s": p50, "p90_s": p90}, "tokens": {"p50": 10, "p90": 20},
                "cost_usd": None, "cal": cal}

    def test_the_forecast_reads_the_calibrated_bands(self):
        cal = {"total": {"p50_s": 2000, "p90_s": 5000}, "tokens": {"p50": 30, "p90": 90}, "cost_usd": None}
        ests = forecast.estimates_for({"a": {"baseline": self.view(1000, 2000, cal)}, "b": {"baseline": self.view(1000, 2000)}},
                                      ["a", "b"])
        self.assertEqual(ests["a"]["total"], cal["total"])
        self.assertEqual(ests["a"]["tokens"], cal["tokens"])
        self.assertTrue(ests["a"]["calibrated"])
        self.assertEqual(ests["b"]["total"], {"p50_s": 1000, "p90_s": 2000})
        self.assertFalse(ests["b"]["calibrated"])
        raw = forecast.estimates_for({"a": {"baseline": self.view(1000, 2000, cal)}}, ["a"], calibrated=False)
        self.assertEqual(raw["a"]["total"], {"p50_s": 1000, "p90_s": 2000})

    def test_rho_comes_from_the_calibration_only_when_it_chose_the_fitted_one(self):
        self.assertEqual(forecast.rho_from({"rho": {"value": 0.08, "fitted": True, "use_fitted": True}})[0], 0.08)
        r, info = forecast.rho_from({"rho": {"value": 0.3, "fitted_value": 0.08, "fitted": True, "use_fitted": False,
                                             "choice": "default 0.3: closer"}})
        self.assertEqual((r, info["fitted_value"], info["note"]), (forecast.RHO, 0.08, "default 0.3: closer"))
        self.assertEqual(forecast.rho_from(None)[0], forecast.RHO)
        self.assertEqual(forecast.rho_from({"rho": {"value": True, "use_fitted": True}})[0], forecast.RHO)

    def test_collect_passes_the_fitted_rho_to_the_simulation(self):
        p = Product()
        try:
            p.task("0001-sf-a")
            p.task("0002-sf-b")
            cfg = p.cfg
            est_tasks = {t: {"baseline": self.view(1000, 2000, {"total": {"p50_s": 3000, "p90_s": 6000},
                                                                  "tokens": None, "cost_usd": None})}
                         for t in ("0001-sf-a", "0002-sf-b")}
            real = forecast.simulate
            got = {}

            def spy(*a, **k):
                got["rho"] = a[11] if len(a) > 11 else k.get("rho")
                got["dur"] = a[2]
                return real(*a, **k)
            with mock.patch.object(forecast, "simulate", side_effect=spy):
                f = forecast.collect(cfg, None, est_tasks=est_tasks, work={}, now=T0.timestamp(), trials=50,
                                     calibration={"rho": {"value": 0.1, "fitted": True, "use_fitted": True, "note": "fitted"}})
            self.assertEqual(got["rho"], 0.1)
            self.assertAlmostEqual(math.exp(got["dur"]["0001-sf-a"][0]), 3000, delta=1)
            self.assertEqual((f["rho"]["value"], f["calibrated"], f["calibrated_tasks"]), (0.1, True, 2))
            with mock.patch.object(forecast, "simulate", side_effect=spy):
                f = forecast.collect(cfg, None, est_tasks=est_tasks, work={}, now=T0.timestamp(), trials=50,
                                     calibration={"rho": {"value": 0.1, "fitted": True, "use_fitted": True}}, calibrated=False)
            self.assertEqual(got["rho"], forecast.RHO)
            self.assertAlmostEqual(math.exp(got["dur"]["0001-sf-a"][0]), 1000, delta=1)
            self.assertIn("rho 0.3 (default)", forecast.text(f))
        finally:
            p.cleanup()

    def test_simulate_honours_rho(self):
        order = ["a", "b"]
        dur = {"a": (math.log(1000), 0.5), "b": (math.log(1000), 0.5)}
        meas = {"tokens": {"a": (0.0, 0.5), "b": (0.0, 0.5)}}
        lo = forecast.simulate(order, {}, dur, meas, [0.0], 0.0, {}, 2000, 1, {"a": ["a"], "b": ["b"]}, rho=0.0)
        hi = forecast.simulate(order, {}, dur, meas, [0.0], 0.0, {}, 2000, 1, {"a": ["a"], "b": ["b"]}, rho=0.9)

        def corr(r):
            x = [math.log(v) for v in r["targets"]["a"]["tokens"]]
            y = [math.log(v) for v in r["targets"]["b"]["tokens"]]
            mx, my = sum(x) / len(x), sum(y) / len(y)
            c = sum((a - mx) * (b - my) for a, b in zip(x, y))
            return c / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
        self.assertLess(abs(corr(lo)), 0.08)
        self.assertAlmostEqual(corr(hi), 0.9, delta=0.05)


class Config(unittest.TestCase):
    def test_the_calibration_block_is_checked(self):
        for bad, msg in (({"half_life": 0}, "half_life"), ({"min_pairs": 2}, "min_pairs"), ({"k": "x"}, "calibration.k"),
                         ({"other": 1}, "estimate.calibration must be"), ("x", "estimate.calibration must be")):
            p = Product({"estimate": {"calibration": bad}})
            try:
                with self.assertRaises(config.ConfigError) as cm:
                    p.cfg
                self.assertIn(msg, str(cm.exception))
            finally:
                p.cleanup()
        p = Product({"estimate": {"calibration": {"half_life": 25, "min_pairs": 10, "k": 4}}})
        try:
            self.assertEqual(calibrate.settings(p.cfg), {"half_life": 25.0, "min_pairs": 10, "k": 4.0})
        finally:
            p.cleanup()
        self.assertEqual(calibrate.settings(None), {"half_life": 40.0, "min_pairs": 8, "k": None})


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Page(Fixture, unittest.TestCase):
    from tests.test_estimate import Page as _P
    view = _P.view
    render = _P.render

    def calibrated(self):
        h = HOSTILE
        v = self.view("0002-second")
        cal = {"total": {"p50_s": 900, "p90_s": 3000}, "tokens": {"p50": 1.5e6, "p90": 4e6}, "cost_usd": {"p50": 2, "p90": 5},
               "factors": {"wall": {"bias": 1.5, "width": 1.8, "group": "family sf" + h, "n_group": 40, "n": 90, "fitted": True},
                           "tokens": {"bias": 1, "width": 1, "group": "none", "n": 3, "fitted": False}}}
        t = v["tasks"]["0002-second"]
        t["baseline"] = {**t["baseline"], "cal": cal}
        t["baseline_scored"] = t["baseline"]
        v["calibration"] = {
            "settings": {"half_life": 40, "min_pairs": 8},
            "factors": {"baseline": {"wall": {"fitted": True, "bias": 1.5, "width": 1.8, "n": 90, "k": 5,
                                              "kind": {"feature" + h: {"n": 60, "bias": 1.4, "raw": 1.45, "weight": 0.9}},
                                              "family": {"sf" + h: {"n": 40, "bias": 1.5, "raw": 1.6, "weight": 0.8}}},
                                     "tokens": {"fitted": False, "n": 3, "note": "too few pairs (3 < 8)" + h}},
                        "agent": {}},
            "evaluation": {"baseline": {"wall": {"raw": {"n": 90, "share_p50": 0.3, "share_p90": 0.7},
                                                 "calibrated": {"n": 90, "share_p50": 0.52, "share_p90": 0.88}}}},
            "rho": {"value": 0.08, "fitted": True, "use_fitted": True, "fitted_value": 0.08, "n": 90,
                    "choice": "fitted 0.08: closer" + h, "note": "fitted from 90 residuals" + h, "se": 0.03, "lag1": 0.3}}
        return v

    def test_calibrated_values_show_by_default_with_the_raw_on_hover(self):
        self.seed()
        b = self.build()[0]
        self.assertIn("calibration", b["estimates"])
        b["estimates"] = self.calibrated()
        html = self.render(b, "\nout.push(estCell('0002-second')); out.push('|D|' + estDrill('0002-second'));")
        cell, drill = html.split("|D|", 1)
        self.assertIn(">15m–50m", cell)  # calibrated 900 s – 3000 s
        self.assertIn("calibrated (raw 10m–20m", cell)
        for t in ("raw P50–P90", "calibrated", "15m–50m", "10m–20m", "bias ×1.5"):
            self.assertIn(t, drill, t)
        for t in ("Calibration (phase D)", "30% / 70%", "52% / 88%", "×1.50", "×1.80", "own weight", "ρ 0.08 (fitted)", "n 90, standard error 0.03",
                  "Raw estimates, as stored"):
            self.assertIn(t, html, t)
        self.assertNotIn(HOSTILE, html)
        for raw in ("<script", "<img"):
            self.assertNotIn(raw, html)

    def test_the_forecast_card_names_rho_and_the_calibrated_count(self):
        self.seed()
        b = self.build()[0]
        F = {"trials": 10, "sources": {"baseline": 2}, "calibrated_tasks": 2, "order": ["a"], "throughput": {},
             "rho": {"value": "0.08" + HOSTILE, "fitted": True},
             "backlog": {"tasks": 1, "task_ids": ["a"], "eta": {"p50": "2026-10-23T10:00:00Z", "p90": "2026-10-23T12:00:00Z"},
                         "hours": {"p50": 1, "p90": 2}}}
        html = self.render(b, "\nout.push(forecastCard(" + json.dumps(F) + "));")
        self.assertIn("2 calibrated", html)
        self.assertIn("fitted from history", html)
        self.assertNotIn(HOSTILE, html)

    def test_a_broken_calibration_shows_its_banner_and_the_page_renders(self):
        self.seed()
        b = self.build()[0]
        v = self.calibrated()
        v["calibration"] = {"_error": "boom" + HOSTILE}
        b["estimates"] = v
        html = self.render(b, "")
        self.assertIn("Calibration failed", html)
        self.assertNotIn("<script", html)
        v["calibration"] = {"factors": "x", "evaluation": 3, "rho": [], "settings": None}
        v["tasks"]["0002-second"]["baseline"]["cal"] = {"total": 5, "factors": "y"}
        html = self.render(b, "\nout.push(estCell('0002-second')); out.push(estDrill('0002-second'));")
        self.assertIn("Calibration (phase D)", html)
        self.assertIn("10m–20m", html)  # the raw band stands


if __name__ == "__main__":
    unittest.main()
