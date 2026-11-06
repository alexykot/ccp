"""Task estimation, phase D (SPEC §26.6): the calibration loop. Advisory.

  ccp estimate calibration [--json]      the factors, their sample sizes, the rolling-origin check and rho

**The pairs.** Each task with an actual is scored on the estimate it had before it started (phase A's
`estimate._pair`: the latest row of the source made before the start, a live one ahead of a backfilled
one). Per source (baseline, agent) and per metric (wall, tokens, cost) a pair is (actual, P50, P90),
with the estimate's kind and family; oldest merge first. Each pair weighs 0.5 ** (age / half_life),
its age counted in merges among the source's pairs (`estimate.calibration.half_life`, default 40):
recent tasks weigh more, and a process change shows within a few dozen merges.

**The bias** (`bias`): the weighted median of actual/P50, overall and by kind and by family. A group's
log factor is shrunk toward its prior by n/(n+k) (n: the group's effective sample size, Kish's
(sum w)^2 / sum w^2): a kind toward the overall factor, a family toward its kind's. k comes from the
data (empirical Bayes, `_k`): the sampling variance of a group median of n log ratios is about
(pi/2) sigma^2 / n, sigma^2 the pooled within-group variance; the variance of the true family
factors, tau^2, is DerSimonian-Laird's method-of-moments estimate over the families (precision
weighted, so two small outlying families do not outweigh a large one near the centre); then
n/(n+k) with k = (pi/2) sigma^2 / tau^2 is the posterior weight of a group's own median. With too
few groups (3 with 2 or more pairs) k is K_DEFAULT (10); it is kept within K_BOUNDS (5 to 100: a
group of 5 pairs carries at most half its own weight), and with no between-group variance beyond
noise (tau^2 <= 0) it is the upper bound: every group takes its prior. `estimate.calibration.k`
fixes it instead.

**The width** (`width`): after the bias, the share of actuals at or under P50'·(P90/P50)^s should be
0.9. Each pair needs s_i = log(actual/P50') / log(P90/P50) (a P90 at or under its P50 counts as the
spread SPREAD_MIN); s is the weighted 0.9 quantile of s_i, shrunk toward 1 by n/(n+K_WIDTH) (a 90th
percentile from n pairs rests on about n/10 of them), and never under 1: calibration widens a P90,
it never narrows one. One width per source and metric; groups are too small for a 90th percentile.
The widening stops at P90 = P90_RATIO_MAX (4) x P50 (on real data: the 95th percentile of the raw bands is
4.2x), so a band that is already wide is not raised to a power into a lognormal whose mean is many
times its median; on real data the cap leaves the rolling P90 coverage unchanged.

**Too few pairs.** A source and metric with fewer than `min_pairs` (default 8) pairs gets factors 1.0
and says so (`fitted: false`).

**Applied at read time** (`apply`): no row is rewritten. P50' = P50·bias and
P90' = P50'·(P90/P50)^width, with the task's group factor (its family's when the family has pairs,
else its kind's, else the overall). `estimate.latest(rs, src, calibrated=True, cal=model)`, the
board's views (`cal` beside the raw bands), `ccp tasks estimate show` and the forecast read them.
Phases stay raw: the factors are fitted on totals.

**The rolling-origin check** (`evaluate`): for each task in start order, the calibration is fitted
on the pairs of tasks merged before it started (no leakage: the backfill's rule) and applied to its
estimate; the shares at or under P50 and P90, raw and calibrated, are reported per metric.

**Rho** (`fit_rho`): the forecast's correlation of any two tasks' deviates in one trial. From the
rolling check's out-of-sample wall residuals z = log(actual/P50') / (log(P90'/P50') / 1.2816), in
start order, only where the calibration had enough pairs to fit, winsorized at +-3 (a task estimated
from one or two earlier ones is not the error model): in windows of W consecutive tasks (a backlog's size), the variance of the window means
is sigma_z^2 (1 + (W - 1) rho) / W, so rho = (W Var(means) / Var(z) - 1) / (W - 1), averaged over
every window offset. With fewer than RHO_MIN_PAIRS residuals, or a standard error (a block bootstrap)
over RHO_MAX_SE, there is no fitted rho. The forecast uses 0.3 by default; the fitted rho replaces it
only when a backtest on the same history (`backtest_sums`: windows of 19 consecutive tasks, their
calibrated bands drawn as the forecast draws them) puts the actual sums closer to 50% at or under P50
with the fitted rho than with 0.3 (`choose_rho`). Both are computed here, and cached.

The model is cached in `QUEUE_ROOT/board/estimate-calibration.json`, keyed by a hash of the pairs
and the settings, so a board build re-fits only when an actual or an estimate arrives.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

from ccp import estimate as est

CALIB_V = 4
METRICS = ("wall", "tokens", "cost")
HALF_LIFE = 40          # merges: a pair this many merges older weighs half
MIN_PAIRS = 8           # fewer scored pairs for a source and metric: factors 1.0
GROUP_MIN = 2           # a kind or family with fewer pairs takes its prior
K_DEFAULT = 10.0        # the shrinkage strength when too few groups to fit it
K_BOUNDS = (5.0, 100.0)  # a group of 5 pairs carries at most half its own weight
K_WIDTH = 20.0          # the width's shrinkage toward 1: a 90th percentile from n pairs rests on ~n/10
WIDTH_MAX = 4.0
P90_RATIO_MAX = 4.0     # the widening stops at P90 = 4 x P50 (a raw band already wider keeps its own; the forecast's draws cap it)
Z90 = 1.2815515655446004
SPREAD_MIN = 0.05 * Z90  # log(P90/P50) floor, the forecast's SIGMA_MIN
RHO_DEFAULT = 0.3
RHO_WINDOW = 20         # consecutive tasks: about a review point's backlog
RHO_MIN_PAIRS = 40
Z_CLIP = 3.0           # residuals are winsorized here before rho
RHO_MAX_SE = 0.15
RHO_BOUNDS = (0.0, 0.8)
BT_WINDOW = 19          # the backtest's backlog: consecutive tasks (R8's size)
BT_STEP = 3
BT_TRIALS = 400
CACHE = "estimate-calibration.json"
KEYS = {"wall": ("wall_s", "p50_s", "p90_s"), "tokens": ("tokens", "p50", "p90"), "cost": ("cost_usd", "p50", "p90")}
ROW_KEY = {"wall": "total", "tokens": "tokens", "cost": "cost_usd"}


def settings(cfg: Any = None) -> dict[str, Any]:
    c = ((getattr(cfg, "estimate", None) or {}).get("calibration") or {}) if cfg is not None else {}
    return {"half_life": float(c.get("half_life") or HALF_LIFE), "min_pairs": int(c.get("min_pairs") or MIN_PAIRS),
            "k": float(c["k"]) if c.get("k") is not None else None}


# ------------------------------------------------------------------------------------ maths

def _pos(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 and math.isfinite(v) else None


def wquantile(vals: list[float], ws: list[float], p: float) -> float | None:
    """The weighted quantile: values at the midpoints of their cumulative weight, linear between
    (equal weights: the type-5 sample quantile)."""
    pts = sorted((v, w) for v, w in zip(vals, ws) if w > 0)
    if not pts:
        return None
    tot = sum(w for _, w in pts)
    c, xs = 0.0, []
    for v, w in pts:
        xs.append(((c + w / 2) / tot, v))
        c += w
    if p <= xs[0][0]:
        return xs[0][1]
    for (pa, va), (pb, vb) in zip(xs, xs[1:]):
        if p <= pb:
            return va + (vb - va) * ((p - pa) / (pb - pa) if pb > pa else 0.0)
    return xs[-1][1]


def neff(ws: list[float]) -> float:
    s2 = sum(w * w for w in ws)
    return (sum(ws) ** 2) / s2 if s2 else 0.0


def weights(n: int, half_life: float) -> list[float]:
    """Oldest first: the newest weighs 1, one `half_life` merges older 0.5."""
    return [0.5 ** ((n - 1 - i) / half_life) for i in range(n)]


def _shrink(log_b: float, n_eff: float, prior: float, k: float) -> tuple[float, float]:
    w = n_eff / (n_eff + k) if n_eff + k > 0 else 0.0
    return w * log_b + (1 - w) * prior, w


def _k(groups: dict[str, list[tuple[float, float]]]) -> tuple[float, str]:
    """Empirical-Bayes shrinkage strength from groups of (log ratio, weight): DerSimonian-Laird's
    method of moments, so a large group near the centre counts for more than two small outliers."""
    big = {g: xs for g, xs in groups.items() if len(xs) >= GROUP_MIN}
    if len(big) < 3:
        return K_DEFAULT, f"default ({len(big)} group(s) with {GROUP_MIN}+ pairs, need 3)"
    ss, dof = 0.0, 0
    for xs in big.values():
        v = [x for x, _ in xs]
        m = sum(v) / len(v)
        ss += sum((x - m) ** 2 for x in v)
        dof += len(v) - 1
    s2 = ss / dof if dof else 0.0
    if s2 <= 0:
        return K_BOUNDS[0], "fitted (no within-group spread)"
    meds, prec = [], []
    for xs in big.values():
        meds.append(wquantile([x for x, _ in xs], [w for _, w in xs], 0.5))
        prec.append(max(neff([w for _, w in xs]), 1.0) / (math.pi / 2 * s2))  # 1 / the median's variance
    sw = sum(prec)
    mbar = sum(w * m for w, m in zip(prec, meds)) / sw
    qstat = sum(w * (m - mbar) ** 2 for w, m in zip(prec, meds))
    tau2 = (qstat - (len(meds) - 1)) / (sw - sum(w * w for w in prec) / sw)
    if tau2 <= 0:
        return K_BOUNDS[1], "fitted: no between-group variance beyond noise (groups take their prior)"
    k = math.pi / 2 * s2 / tau2
    return min(K_BOUNDS[1], max(K_BOUNDS[0], k)), "fitted (empirical Bayes)" + (" at its bound" if not K_BOUNDS[0] < k < K_BOUNDS[1] else "")


def _spread(p50: float, p90: float) -> float:
    return max(math.log(p90 / p50), SPREAD_MIN) if p90 > 0 and p50 > 0 else SPREAD_MIN


def fit_metric(items: list[dict[str, Any]], s: dict[str, Any]) -> dict[str, Any]:
    """One source and metric. `items`: {x, p50, p90, kind, family}, oldest merge first."""
    n = len(items)
    if n < s["min_pairs"]:
        return {"n": n, "fitted": False, "bias": 1.0, "width": 1.0, "note": f"too few pairs ({n} < {s['min_pairs']}): factors 1.0",
                "kind": {}, "family": {}}
    ws = weights(n, s["half_life"])
    lr = [math.log(it["x"] / it["p50"]) for it in items]
    lb0 = wquantile(lr, ws, 0.5)
    by: dict[str, dict[str, list[tuple[float, float]]]] = {"kind": {}, "family": {}}
    fam_kind: dict[str, dict[str, float]] = {}
    for it, x, w in zip(items, lr, ws):
        by["kind"].setdefault(it["kind"], []).append((x, w))
        by["family"].setdefault(it["family"], []).append((x, w))
        fam_kind.setdefault(it["family"], {}).setdefault(it["kind"], 0.0)
        fam_kind[it["family"]][it["kind"]] += w
    if s.get("k") is not None:
        k, k_note = float(s["k"]), "set in plane.json"
    else:
        k, k_note = _k(by["family"])
    kinds = {}
    for g, xs in sorted(by["kind"].items()):
        med = wquantile([x for x, _ in xs], [w for _, w in xs], 0.5)
        ne = neff([w for _, w in xs])
        lf, wt = _shrink(med, ne, lb0, k) if len(xs) >= GROUP_MIN else (lb0, 0.0)
        kinds[g] = {"n": len(xs), "n_eff": round(ne, 1), "raw": round(math.exp(med), 3), "weight": round(wt, 2),
                    "bias": round(math.exp(lf), 3), "_lf": lf}
    fams = {}
    for g, xs in sorted(by["family"].items()):
        med = wquantile([x for x, _ in xs], [w for _, w in xs], 0.5)
        ne = neff([w for _, w in xs])
        kd = max(fam_kind[g].items(), key=lambda kv: kv[1])[0]
        prior = kinds.get(kd, {}).get("_lf", lb0)
        lf, wt = _shrink(med, ne, prior, k) if len(xs) >= GROUP_MIN else (prior, 0.0)
        fams[g] = {"n": len(xs), "n_eff": round(ne, 1), "raw": round(math.exp(med), 3), "weight": round(wt, 2),
                   "bias": round(math.exp(lf), 3), "kind": kd, "_lw": (med, ne, len(xs))}
    model = {"n": n, "n_eff": round(neff(ws), 1), "fitted": True, "bias": round(math.exp(lb0), 3), "_lb": lb0,
             "k": round(k, 1), "k_note": k_note, "kind": kinds, "family": fams}
    # the width, after each pair's own bias factor
    need = []
    for it in items:
        b = factor(model, it["kind"], it["family"])[0]
        a = math.log(it["x"] / (it["p50"] * b))
        need.append(a / _spread(it["p50"], it["p90"]))
    raw = wquantile(need, ws, 0.9)
    ne = neff(ws)
    width = 1 + ne / (ne + K_WIDTH) * (raw - 1)
    model.update({"width_raw": round(raw, 3), "width": round(min(WIDTH_MAX, max(1.0, width)), 3),
                  "width_weight": round(ne / (ne + K_WIDTH), 2)})
    return model


def factor(m: dict[str, Any], kind: Any, family: Any) -> tuple[float, str, int]:
    """(bias, the group it came from, that group's pairs) for a task of `kind` and `family`."""
    if not m.get("fitted"):
        return 1.0, "none", int(m.get("n") or 0)
    lb0 = m.get("_lb", math.log(m["bias"]))
    kd = (m.get("kind") or {}).get(str(kind))
    kprior = kd["_lf"] if kd and "_lf" in kd else (math.log(kd["bias"]) if kd else lb0)
    fm = (m.get("family") or {}).get(str(family))
    if fm and fm.get("n", 0) >= GROUP_MIN:
        med, ne, _ = fm["_lw"] if "_lw" in fm else (math.log(fm["raw"]), fm["n_eff"], fm["n"])
        return math.exp(_shrink(med, ne, kprior, m["k"])[0]), f"family {family}", int(fm["n"])
    if kd and kd.get("n", 0) >= GROUP_MIN:
        return math.exp(kprior), f"kind {kind}", int(kd["n"])
    return math.exp(lb0), "overall", int(m.get("n") or 0)


# ------------------------------------------------------------------------------------ pairs

def _items(e: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    f = (e.get("inputs") or {}).get("features") or {}
    b = est._bands(e)
    out = {}
    for metric, (akey, _, _) in KEYS.items():
        band = b.get(metric) or {}
        x, p50, p90 = _pos(a.get(akey)), _pos(band.get("p50")), _pos(band.get("p90"))
        if x is not None and p50 is not None and p90 is not None and p90 >= p50:
            out[metric] = {"x": x, "p50": p50, "p90": p90}
    return {"kind": str(f.get("kind") or "?"), "family": str(f.get("family") or "?"), "m": out}


def pairs(by: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Per source, the scored pairs, oldest merge first."""
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in est.SOURCES}
    for tid, rs in by.items():
        for src in est.SOURCES:
            p = est._pair(rs, src)
            if not p:
                continue
            e, a = p
            it = _items(e, a)
            if not it["m"]:
                continue
            merged = str(a.get("merged_at") or "")
            out[src].append({"task_id": tid, "merged_at": merged, "start_at": str(a.get("start_at") or merged), **it})
    for src in out:
        out[src].sort(key=lambda p: (p["merged_at"], p["task_id"]))
    return out


def fit(ps: dict[str, list[dict[str, Any]]], s: dict[str, Any]) -> dict[str, Any]:
    """Per source and metric, the factors."""
    out: dict[str, Any] = {}
    for src, lst in ps.items():
        out[src] = {}
        for metric in METRICS:
            items = [{**p["m"][metric], "kind": p["kind"], "family": p["family"]} for p in lst if metric in p["m"]]
            out[src][metric] = fit_metric(items, s)
    return out


# ------------------------------------------------------------------------------------ apply

BIAS_MIN, BIAS_MAX = 0.25, 4.0  # a fitted bias outside this is a data problem, not a correction


def _band_cal(p50: float, p90: float, bias: float, width: float) -> tuple[float, float]:
    c50 = p50 * min(max(bias, BIAS_MIN), BIAS_MAX)
    sp = _spread(p50, p90)
    return c50, c50 * math.exp(min(width * sp, max(sp, math.log(P90_RATIO_MAX))))


def apply(row: dict[str, Any] | None, factors: dict[str, Any] | None, source: str | None = None) -> dict[str, Any] | None:
    """The calibrated bands of an estimate row (or a board view, with `kind`, `family`): {total,
    tokens, cost_usd, factors}. None without a row; factors 1.0 where none were fitted."""
    if not row:
        return None
    src = source or row.get("source")
    f = (row.get("inputs") or {}).get("features") or {}
    kind, fam = row.get("kind") or f.get("kind") or "?", row.get("family") or f.get("family") or "?"
    out: dict[str, Any] = {"factors": {}}
    for metric in METRICS:
        key, (_, lo, hi) = ROW_KEY[metric], KEYS[metric]
        band = row.get(key) or {}
        m = ((factors or {}).get(src) or {}).get(metric) or {}
        b, grp, gn = factor(m, kind, fam)
        w = float(m.get("width") or 1.0) if m.get("fitted") else 1.0
        out["factors"][metric] = {"bias": round(b, 3), "width": round(w, 3), "group": grp, "n_group": gn,
                                  "n": m.get("n", 0), "fitted": bool(m.get("fitted"))}
        p50, p90 = _pos(band.get(lo)), _pos(band.get(hi))
        if p50 is None or p90 is None:
            out[key] = None
            continue
        c50, c90 = _band_cal(p50, max(p90, p50), b, w)
        nd = 2 if metric == "cost" else None
        out[key] = {lo: round(c50, nd) if nd else int(round(c50)), hi: round(c90, nd) if nd else int(round(c90))}
    return out


# ------------------------------------------------------------------------------------ the check

def _cover(rows: list[tuple[float, float, float]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    n = len(rows)
    ratios = sorted(x / p50 for x, p50, _ in rows)
    return {"n": n, "share_p50": round(sum(1 for x, a, _ in rows if x <= a) / n, 3),
            "share_p90": round(sum(1 for x, _, b in rows if x <= b) / n, 3),
            "median_ratio": round(ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2, 2)}


def evaluate(ps: list[dict[str, Any]], s: dict[str, Any]) -> dict[str, Any]:
    """Rolling origin over one source's pairs: each task's calibration is fitted only on the tasks
    merged before it started, then applied to it. Returns per metric the coverage raw and calibrated,
    and the wall residuals in start order (for rho)."""
    order = sorted(ps, key=lambda p: (p["start_at"], p["task_id"]))
    raw: dict[str, list[tuple[float, float, float]]] = {m: [] for m in METRICS}
    cal: dict[str, list[tuple[float, float, float]]] = {m: [] for m in METRICS}
    fitted = {m: 0 for m in METRICS}
    z: list[float] = []
    bands: list[tuple[float, float, float]] = []
    for p in order:
        train = [t for t in ps if t["merged_at"] < p["start_at"] and t["task_id"] != p["task_id"]]
        f = fit({"x": train}, s)["x"]
        for metric, v in p["m"].items():
            m = f[metric]
            b = factor(m, p["kind"], p["family"])[0]
            w = float(m.get("width") or 1.0) if m.get("fitted") else 1.0
            fitted[metric] += 1 if m.get("fitted") else 0
            c50, c90 = _band_cal(v["p50"], v["p90"], b, w)
            raw[metric].append((v["x"], v["p50"], v["p90"]))
            cal[metric].append((v["x"], c50, c90))
            if metric == "wall" and m.get("fitted"):
                bands.append((v["x"], c50, c90))
                # the deviate as the forecast draws it: sigma floored and capped as in backtest_sums
                z.append(math.log(v["x"] / c50) / _sigma(c50, c90))
    return {"metrics": {m: {"raw": _cover(raw[m]), "calibrated": _cover(cal[m]), "fitted": fitted[m]} for m in METRICS},
            "z_wall": z, "wall_bands": bands}


def _rho_windows(z: list[float], w: int) -> float | None:
    n = len(z)
    if n < 2 * w:
        return None
    mu = sum(z) / n
    var = sum((x - mu) ** 2 for x in z) / (n - 1)
    if var <= 0:
        return None
    means = [sum(z[i:i + w]) / w for i in range(n - w + 1)]
    vm = sum((m - mu) ** 2 for m in means) / len(means)
    return (w * vm / var - 1) / (w - 1)


def fit_rho(z: list[float], w: int = RHO_WINDOW, seed: int = 2828, boots: int = 200) -> dict[str, Any]:
    """The between-task correlation of the out-of-sample wall residuals (see the module doc)."""
    z = [max(-Z_CLIP, min(Z_CLIP, x)) for x in z]  # a task estimated from one or two others is not an error model
    n = len(z)
    base = {"value": RHO_DEFAULT, "fitted": False, "n": n, "window": w, "method": "window means of the rolling residuals"}
    if n < RHO_MIN_PAIRS:
        return {**base, "note": f"too few residuals ({n} < {RHO_MIN_PAIRS}): kept {RHO_DEFAULT}"}
    est_ = _rho_windows(z, w)
    if est_ is None:
        return {**base, "note": f"residuals have no spread: kept {RHO_DEFAULT}"}
    lag1 = None
    mu = sum(z) / n
    var = sum((x - mu) ** 2 for x in z)
    if var > 0:
        lag1 = sum((z[i] - mu) * (z[i + 1] - mu) for i in range(n - 1)) / var
    # a moving-block bootstrap (blocks of w) for its standard error
    rng = random.Random(seed)
    vals = []
    nb = max(1, n // w)
    for _ in range(boots):
        zz: list[float] = []
        for _ in range(nb):
            i = rng.randrange(0, n - w + 1)
            zz += z[i:i + w]
        r = _rho_windows(zz, w)
        if r is not None:
            vals.append(r)
    se = (sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / max(1, len(vals) - 1)) ** 0.5 if len(vals) > 1 else None
    out = {**base, "raw": round(est_, 3), "se": round(se, 3) if se is not None else None,
           "lag1": round(lag1, 3) if lag1 is not None else None, "mean_z": round(mu, 3),
           "sd_z": round((var / (n - 1)) ** 0.5, 3)}
    if se is None or se > RHO_MAX_SE:
        return {**out, "note": f"too uncertain (standard error {out['se']} > {RHO_MAX_SE}): kept {RHO_DEFAULT}"}
    v = min(RHO_BOUNDS[1], max(RHO_BOUNDS[0], est_))
    return {**out, "value": round(v, 3), "fitted": True,
            "note": f"fitted from {n} residuals in windows of {w}" + (" (clamped)" if v != est_ else "")}


# ------------------------------------------------------------------------------------ the model

def _strip(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if not str(k).startswith("_")}
    return d


def _sigma(c50: float, c90: float) -> float:
    """The forecast's sigma for a band (forecast.lognormal): at least 0.05, P90 capped at P90_RATIO_MAX x P50."""
    return min(max(math.log(c90 / c50) / Z90, 0.05), math.log(P90_RATIO_MAX) / Z90)


def backtest_sums(bands: list[tuple[float, float, float]], rho: float, w: int = BT_WINDOW, step: int = BT_STEP,
                  trials: int = BT_TRIALS, seed: int = 2828) -> dict[str, Any]:
    """The forecast's sum, checked on history: for windows of `w` consecutive tasks (start order, every
    `step`), the out-of-sample calibrated bands are drawn as the forecast draws them (lognormals whose
    deviates correlate at `rho`, seeded, the P90 capped at P90_RATIO_MAX x P50), and the actual sum is
    compared with the draws' P50 and P90."""
    rng = random.Random(seed)
    gauss = rng.gauss
    le50 = le90 = n = 0
    rc, ri = math.sqrt(rho), math.sqrt(1 - rho)
    for st in range(0, len(bands) - w + 1, step):
        win = bands[st:st + w]
        par = [(math.log(c50), _sigma(c50, c90)) for _, c50, c90 in win]
        sums = []
        for _ in range(trials):
            cm = rc * gauss(0.0, 1.0)
            sums.append(sum(math.exp(mu + sg * (cm + ri * gauss(0.0, 1.0))) for mu, sg in par))
        sums.sort()
        a = sum(x for x, _, _ in win)
        le50 += a <= sums[len(sums) // 2]
        le90 += a <= sums[int(0.9 * (len(sums) - 1))]
        n += 1
    return {"rho": round(rho, 3), "windows": n, "share_p50": round(le50 / n, 3) if n else None,
            "share_p90": round(le90 / n, 3) if n else None}


def choose_rho(fitted: dict[str, Any], bands: list[tuple[float, float, float]]) -> dict[str, Any]:
    """The forecast keeps RHO_DEFAULT unless the fitted rho's backtest (`backtest_sums`) puts the
    actual backlog sums closer to 50% at or under P50 than the default's does."""
    out = {**fitted, "fitted_value": fitted["value"] if fitted.get("fitted") else None, "value": RHO_DEFAULT,
           "use_fitted": False}
    if not fitted.get("fitted"):
        return {**out, "choice": f"default {RHO_DEFAULT}: {fitted.get('note')}"}
    d = backtest_sums(bands, RHO_DEFAULT)
    f = backtest_sums(bands, fitted["value"])
    out["backtest"] = {"default": d, "fitted": f}
    if not d["windows"]:
        return {**out, "choice": f"default {RHO_DEFAULT}: too few tasks for a backtest of {BT_WINDOW}-task sums"}
    if abs(f["share_p50"] - 0.5) < abs(d["share_p50"] - 0.5):
        return {**out, "value": fitted["value"], "use_fitted": True,
                "choice": f"fitted {fitted['value']}: backlog sums at or under P50 in {f['share_p50']:.0%} of "
                          f"{f['windows']} windows, against {d['share_p50']:.0%} with {RHO_DEFAULT}"}
    return {**out, "choice": f"default {RHO_DEFAULT}: backlog sums at or under P50 in {d['share_p50']:.0%} of "
                             f"{d['windows']} windows, against {f['share_p50']:.0%} with the fitted {fitted['value']}"}


def build(by: dict[str, list[dict[str, Any]]], s: dict[str, Any]) -> dict[str, Any]:
    ps = pairs(by)
    factors = fit(ps, s)
    ev = {src: evaluate(lst, s) for src, lst in ps.items()}
    z = ev.get("baseline", {}).get("z_wall") or []
    rho = choose_rho(fit_rho(z), ev.get("baseline", {}).get("wall_bands") or [])
    rho["source"] = "baseline"
    return {"v": CALIB_V, "settings": s, "pairs": {src: len(v) for src, v in ps.items()}, "factors": factors,
            "evaluation": {src: e["metrics"] for src, e in ev.items()}, "rho": rho, "advisory": True}


def _key(by: dict[str, list[dict[str, Any]]], s: dict[str, Any]) -> str:
    ps = pairs(by)
    blob = json.dumps([CALIB_V, s, {src: [(p["task_id"], p["merged_at"], p["start_at"], p["kind"], p["family"], p["m"])
                                          for p in v] for src, v in ps.items()}], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def model(q: Path | None, cfg: Any = None, by: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """The calibration, cached in board/estimate-calibration.json by the hash of its inputs. The
    cached copy keeps the private fields `apply` reads; `summary` drops them for the board."""
    s = settings(cfg)
    by = by if by is not None else (est.all_rows(q) if q is not None else {})
    key = _key(by, s)
    p = q / "board" / CACHE if q is not None else None
    if p is not None:
        try:
            c = json.loads(p.read_text())
            if isinstance(c, dict) and c.get("key") == key and isinstance(c.get("model"), dict):
                return {**c["model"], "cached": True}
        except (OSError, ValueError):
            pass
    m = build(by, s)
    if p is not None and p.parent.is_dir():
        try:
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps({"key": key, "model": m}, default=str))
            tmp.replace(p)
        except OSError:
            pass
    return {**m, "cached": False}


def summary(m: dict[str, Any]) -> dict[str, Any]:
    return _strip(m)


# ------------------------------------------------------------------------------------ text

def _pct(f: float) -> str:
    return f"{abs(f - 1) * 100:.0f}%"


def prompt_text(m: dict[str, Any], limit: int = 1500) -> str:
    """The estimator seat's calibration input: the factors and their sample sizes, bounded."""
    lines = ["Calibration factors (P50' = P50 x bias; P90' = P50' x (P90/P50)^width), fitted on estimates made "
             "before each task started, recent tasks weighted more:"]
    for src, who in (("agent", "your own past estimates"), ("baseline", "the baseline shown above")):
        fs = ((m.get("factors") or {}).get(src) or {})
        if not any((fs.get(x) or {}).get("fitted") for x in METRICS):
            lines.append(f"- {who}: too few scored pairs yet (n={max([(fs.get(x) or {}).get('n', 0) for x in METRICS] or [0])}); no factor")
            continue
        for metric in METRICS:
            f = fs.get(metric) or {}
            if not f.get("fitted"):
                lines.append(f"- {who}, {metric}: {f.get('note') or 'no pairs'}")
                continue
            b = f["bias"]
            lines.append(f"- {who}, {metric}: P50 runs {'low' if b > 1 else 'high'} by {_pct(b)} overall (n={f['n']}); "
                         + (f"widen P90: (P90/P50)^{f['width']:.2f}, so a P90 1.6x its P50 becomes {1.6 ** f['width']:.1f}x"
                            if f["width"] > 1.0 else "P90 width holds"))
            groups = [(f"{g} {k}", v) for g in ("family", "kind") for k, v in (f.get(g) or {}).items()
                      if v.get("n", 0) >= GROUP_MIN and abs(v["bias"] - 1) >= 0.1]
            groups.sort(key=lambda kv: -kv[1]["n"])
            for name, v in groups[:4]:
                lines.append(f"    {name}: P50 runs {'low' if v['bias'] > 1 else 'high'} by {_pct(v['bias'])} (n={v['n']}, shrunk)")
    r = m.get("rho") or {}
    lines.append(f"Estimates err together: rho {r.get('value')} ({'fitted' if r.get('use_fitted') else 'default'}).")
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit].rstrip() + f"\n[... cut at {limit} characters]"


def text(m: dict[str, Any]) -> str:
    lines = [f"Calibration (advisory, SPEC §26.6 phase D): half-life {m['settings']['half_life']:.0f} merges, "
             f"at least {m['settings']['min_pairs']} pairs; pairs {m.get('pairs')}"]
    for src in est.SOURCES:
        lines.append(f"{src}:")
        for metric in METRICS:
            f = (m["factors"].get(src) or {}).get(metric) or {}
            ev = ((m.get("evaluation") or {}).get(src) or {}).get(metric) or {}
            r, c = ev.get("raw") or {}, ev.get("calibrated") or {}
            cov = (f"; rolling check (n {r.get('n')}): <=P50 {r.get('share_p50', 0):.0%} -> {c.get('share_p50', 0):.0%}, "
                   f"<=P90 {r.get('share_p90', 0):.0%} -> {c.get('share_p90', 0):.0%}") if r.get("n") else ""
            if not f.get("fitted"):
                lines.append(f"  {metric}: {f.get('note')}{cov}")
                continue
            lines.append(f"  {metric}: bias x{f['bias']} (n {f['n']}, effective {f['n_eff']}), width x{f['width']} "
                         f"(raw {f['width_raw']}), shrinkage k {f['k']} ({f['k_note']}){cov}")
            for g in ("kind", "family"):
                for k, v in (f.get(g) or {}).items():
                    if v.get("n", 0) >= GROUP_MIN:
                        lines.append(f"    {g} {k}: x{v['bias']} (raw x{v['raw']}, n {v['n']}, own weight {v['weight']})")
    r = m.get("rho") or {}
    lines.append(f"rho for the forecast: {r.get('value')} ({r.get('choice')})")
    lines.append(f"  fit: {r.get('note')}"
                 + (f"; raw {r.get('raw')}, se {r.get('se')}, n {r.get('n')}, lag-1 {r.get('lag1')}" if r.get("raw") is not None else ""))
    return "\n".join(lines)
