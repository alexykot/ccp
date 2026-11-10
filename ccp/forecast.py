"""Task estimation, phase C (SPEC §26.4): completion forecasts and the allowance fit. Advisory.

  ccp forecast [--point R<n> | --backlog] [--json]

**The order.** The open tasks are replayed in the order `ccp tasks next` would take them
(`selection.pick`, `tasklog.ranked`: the lead's preference list, the holds, the review point's refactors,
`refactor_every`, the dependencies): the task in flight first, then `ranked`'s first row, marked
merged, then `ranked` again, so a task joins once its dependencies have merged. When the runner's
scope runs out the replay goes on over the whole log (no scope). A held task, one whose dependency
is dropped or missing, and one that is not pending are left out and listed (`unreached`).

**The durations.** Each task's estimate is its latest agent row, else its latest baseline row
(ccp/estimate.py), calibrated (phase D, ccp/calibrate.py: the board view's `cal` bands; the stored
bands where it has none, or with `calibrated=False`). Its wall time is a lognormal through the estimate's P50 and P90
(mu = ln P50, sigma = ln(P90/P50) / 1.2816, the P90 capped at P90_RATIO_MAX = 4 x P50: a lognormal
through a wider band has a mean many times its median, and summed means overshoot); tokens and cost the same, drawn with the same normal
deviate as the wall time (a long task is also an expensive one). The deviates of one trial share a
common part, so any two tasks' deviates correlate at rho (z = sqrt(rho) Z + sqrt(1 - rho) e, the task
in flight included): RHO = 0.3, or the calibration's fitted rho when its backtest favours it (`rho_from`), since estimates made the same way tend to err the same
way; independent tasks would make a backlog's P90 implausibly close to its P50. The task in flight is drawn
conditioned on not having finished yet: its total is at least the time since it started, and its
remaining time and tokens are what is left of that draw. A task with no estimate takes the median
P50 and P90 of the ones that have one, and is counted (`unestimated`).

**The throughput** (`throughput`). The runner takes one task at a time (with SPEC §16's
`parallel.max_in_flight` above 1, that many slots: a task starts at the earliest free slot, and one
that runs alone takes them all; a gap is measured only where the task that starts was held alone, though
every merge moves the frontier; tasks whose paths meet, and the 5-hour ceiling, are not modelled): the next task starts at the
latest merge so far plus a gap drawn from the gaps observed between consecutive tasks (the drill-down's
windows, first recorded event to the merge, for the recent merged tasks). A negative gap is an observed
overlap: the next task started before the previous one merged. A gap of GAP_STOP_S or more is a stop
(the runner was down, or waited on the operator) and is left out, and counted. A task never starts before its
dependencies merge, nor before the task ahead of it started.

**Waits on the operator** are not modelled: no calendar time is added for gates, questions or the allowance
checkpoint. The remaining tasks with a wait, gate or question open now are reported
(`waits_flagged`), and those whose agent estimate expects a wait (`waits_expected`), and the estimates' own wall times include whatever waits their reference tasks had.

**The allowance fit** (`allowance_fit`). From `board/allowance.jsonl`: consecutive samples in the
same weekly window (`usage.same_window`) whose weekly % did not fall are joined into intervals of at
least FIT_MIN_INTERVAL_S. For each interval the Claude usage is summed from the telemetry: every
bound project's `board/usage-requests.jsonl` (the plane's rows) and the system sink (§24.1, the use
outside every project), one row per request id, only from when both sources were recording. Four
models are fitted through the origin, weekly % per token, % per dollar of cost, and either of those
by model family (when two or more families each have usage in 3 intervals or more), and the one
with the lowest leave-one-out error (RMSE in percentage points per interval) is used; within 5% of
the lowest, the simpler one. The non-plane
burn is the system sink's usage over the last 7 days, per hour, times the fit; a history shorter than
BASELINE_MIN_SPAN_H (72 h) is averaged over 72 h (`baseline_floored`).

**The 5-hour window** (§25.4 the session park, 2026-10-23). `r5`, the 5-hour % per weekly %, is fitted
from the samples (`session_fit`). In each trial the 5-hour % rises at r5 times the weekly % rate (the
non-plane burn plus the running task's burn spread over its run); the current window ends at the
latest sample's `five_hour_resets_at`. When it would reach `telemetry.session_park_pct` first, work
pauses until the window's end plus the wake margin, and every later start and end moves by the pause
(`_pauses`). Each target reports its pauses and paused hours (P50, P90). A null park % models none.

**The projection.** In each trial the weekly % rises from the latest sample (plus the fitted % of the
usage recorded since) by the non-plane burn per hour and by each task's tokens or cost, spread
evenly between task completions. It reports the % at the review point's and the backlog's completion,
when the project's checkpoint and the checkpoint in force would be crossed (P50, and "P90" as the
early side: 90% of trials cross later), and whether the work ends before `resets_at` or how much %
it spills into the next week.

The fit is cached in `board/forecast-fit.json`, keyed by the allowance samples and the telemetry
files' sizes, mtimes and inodes: a file that grew is re-fitted only when what it appended holds a
row inside the fitted span, so a board build usually re-fits only when a new sample arrives. Everything here is advisory: no claim, order or check reads it.
"""
from __future__ import annotations

import bisect
import json
import math
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any

from ccp import tasklog
from ccp.config import Config

FORECAST_V = 3         # 2: the 5-hour limit's pauses; 3: the P90_RATIO_MAX draw cap (2026-10-23)
TRIALS = 1000           # seeded: the same inputs give the same forecast
SEED = 2828
Z90 = 1.2815515655446004
SIGMA_MIN = 0.05        # a P90 at or under its P50 still gets a little spread
P90_RATIO_MAX = 4.0     # draws use a P90 of at most 4 x P50 (calibrate.P90_RATIO_MAX): a wider band's mean overshoots
SIGMA_MAX = math.log(P90_RATIO_MAX) / Z90
U0_MAX = 1 - 1e-12      # the in-flight task's conditioning: 0.999 drew one task at 16 x its P50 in as finished (4x cap)
RHO = 0.3               # the correlation of any two tasks' deviates in one trial: estimates err together
GAP_STOP_S = 1800       # a gap between tasks this long is a stop (runner down, a wait on the operator), not throughput
GAP_HISTORY = 40        # the latest gaps kept
FIT_V = 2              # 2: the non-plane burn's 72 h floor and the 5-hour fit (2026-10-23)
FIT_MIN_INTERVAL_S = 1800   # samples are whole percents: shorter intervals are mostly rounding
FIT_MAX_INTERVAL_S = 12 * 3600
FIT_MIN_N = 4
FIT_FAMILY_MIN = 3
BASELINE_DAYS = 7
# The non-plane burn is averaged over at least this many hours: a short history (a sink that began 26 h
# before, on one heavy interactive day) is spread as if it covered 3 days, so one busy day does not
# set a round-the-clock rate (it ran 0.91%/h for four days to "100% crossed in 100% of trials" while
# the weekly % rose 3 points overnight, 2026-10-23).
BASELINE_MIN_SPAN_H = 72
SESSION_S = 5 * 3600    # the 5-hour window
R5_MIN_N = 3            # intervals the 5-hour fit needs
WEEK_S = 7 * 86400
FAMILY_RE = re.compile(r"(opus|sonnet|haiku|fable)", re.I)
_ND = NormalDist()


# ------------------------------------------------------------------------------------ helpers

def _ep(s: Any) -> float | None:
    """An ISO time as epoch seconds, UTC when it carries no offset."""
    if not s:
        return None
    try:  # Python 3.11+ reads "Z" and any fraction directly
        d = datetime.fromisoformat(str(s))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except (TypeError, ValueError):
        pass
    try:
        t = re.sub(r"\.(\d{1,6})\d*", lambda m: "." + m.group(1).ljust(6, "0"), str(s).replace("Z", "+00:00"), count=1)
        d = datetime.fromisoformat(t)
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except (TypeError, ValueError):
        return None


def iso(e: float | None) -> str | None:
    return None if e is None else datetime.fromtimestamp(e, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def quantile(xs: list[float], p: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    pos = (len(xs) - 1) * p
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def lognormal(p50: Any, p90: Any) -> tuple[float, float] | None:
    """(mu, sigma) of the lognormal whose median is `p50` and 90th percentile `p90`, the P90 capped at
    P90_RATIO_MAX x P50."""
    a, b = _num(p50), _num(p90)
    if a is None or a <= 0:
        return None
    if b is None or b <= a:
        return math.log(a), SIGMA_MIN
    return math.log(a), min(SIGMA_MAX, max(SIGMA_MIN, math.log(b / a) / Z90))


def family(model: Any) -> str:
    m = FAMILY_RE.search(str(model or ""))
    return m.group(1).lower() if m else "other"


# ------------------------------------------------------------------------------------ the order

def since_refactor(kinds: dict[str, str], merged: list[str]) -> int:
    """Features merged since the last refactor, from task ids in merge order."""
    n = 0
    for tid in merged:
        n = 0 if kinds.get(tid) == "refactor" else n + 1
    return n


def sequence(cfg: Config, q: Path | None, tasks: list[dict[str, Any]] | None = None,
             merged: list[str] | None = None) -> dict[str, Any]:
    """The open tasks in the order the runner would take them, merge by merge (see the module doc).
    `merged` (task ids in merge order, e.g. the board's merged tasks) replaces git's count of the
    features merged since the last refactor."""
    from ccp import selection  # noqa: PLC0415
    tasks = tasks if tasks is not None else tasklog.load(cfg)
    sel = selection.inputs(cfg, q, None, tasks)
    held = set(selection.holds(q))
    status = {str(t.get("task_id")): t.get("status") for t in tasks}
    open_ = [t for t in tasks if t.get("status") not in ("done", "dropped")]
    # `ranked` reads only the open tasks and the state of their dependencies: done and dropped tasks
    # stand in as stubs, so each replay step is cheap
    live = [dict(t) for t in open_]
    by_id = {str(t.get("task_id")): t for t in live}
    refd = {d for t in open_ for d in tasklog._as_list(t.get("depends_on"))} - set(by_id)
    live += [{"task_id": d, "status": status[d]} for d in sorted(refd) if d in status]
    flight = [x for x in sel.get("in_flight") or [] if x in by_id]
    order: list[str] = []
    for tid in flight:
        order.append(tid)
        by_id[tid]["status"] = "done"
    for tid in held:
        if tid in by_id and by_id[tid].get("status") == "pending":
            by_id[tid]["status"] = "held"
    a = cfg.architect
    every = a["refactor_every"] if a else 0
    since = 0
    if every and any(tasklog.kind_of(t) == "refactor" and t.get("status") == "pending" for t in open_):
        since = since_refactor({str(t.get("task_id")): tasklog.kind_of(t) for t in tasks}, merged) \
            if merged is not None else tasklog.features_since_refactor(cfg, tasks)
    for tid in flight:
        since = 0 if tasklog.kind_of(by_id[tid]) == "refactor" else since + 1
    # the lead's list: each entry goes first once it is ready, in the lead's order, until it is taken
    pref = [(pid, why) for t, why in sel.get("prefer") or []
            if (pid := str(t.get("task_id"))) in by_id and pid not in held and pid not in flight]
    first = [x for x in (sel.get("first") or []) if x not in held]
    scope = sel.get("scope")
    for sc in ([scope, None] if scope else [None]):
        while True:
            r = tasklog.ranked(cfg, sc, first, [(by_id[x], why) for x, why in pref], live, sel.get("review_point"), since=since)
            if not r:
                break
            t = r[0][0]
            tid = str(t.get("task_id"))
            order.append(tid)
            t["status"] = "done"
            first = [x for x in first if x != tid]
            pref = [(x, why) for x, why in pref if x != tid]
            since = 0 if tasklog.kind_of(t) == "refactor" else since + 1
    seen = set(order)
    unreached = {}
    for t in open_:
        tid = str(t.get("task_id"))
        if tid in seen:
            continue
        if tid in held:
            unreached[tid] = "held"
        elif t.get("status") != "pending":
            unreached[tid] = f"status {t.get('status')}"
        else:
            miss = [d for d in tasklog._as_list(t.get("depends_on")) if status.get(d) != "done" and d not in seen]
            unreached[tid] = ("waits on " + ", ".join(miss)) if miss else "not reached"
    deps = {tid: [d for d in tasklog._as_list(by_id[tid].get("depends_on")) if d in seen] for tid in order}
    return {"order": order, "in_flight": flight, "unreached": unreached, "deps": deps, "scope": scope,
            "review_point": sel.get("review_point"),
            "tags": {str(t.get("task_id")): t.get("review_point") for t in tasks}, "status": status}


# ------------------------------------------------------------------------------------ the throughput

def windows(drill: dict[str, Any] | None, alone: dict[str, bool] | None = None) -> list[tuple[float, ...]]:
    """(start, merge) of each merged task the drill-down measured; with `alone` (§16.7), (start, merge,
    1.0 when the runner held it alone else 0.0)."""
    out = []
    for tid, v in (drill or {}).items():
        if not isinstance(v, dict) or v.get("open") or v.get("_error"):
            continue
        s, m = _ep(v.get("start_at")), _ep(v.get("merged_at"))
        if s is not None and m is not None and m >= s:
            out.append((s, m) if alone is None else (s, m, 1.0 if alone.get(tid, True) else 0.0))
    return sorted(out)


def _held_alone(q: Path | None, drill: dict[str, Any] | None) -> dict[str, bool]:
    """Per drilled task: whether the runner held it alone (`peak_in_flight` 1 or unset, §16.7)."""
    if q is None or not drill:
        return {}
    from ccp.queue import load_task_state  # noqa: PLC0415
    out = {}
    for tid in drill:
        try:
            out[tid] = int(load_task_state(q, tid).get("peak_in_flight") or 1) <= 1
        except Exception:  # noqa: BLE001  (an unreadable state: serial, as before §16)
            out[tid] = True
    return out


def throughput(wins: list[tuple[float, float]]) -> dict[str, Any]:
    """The gaps between consecutive tasks: each task's start less the latest merge before it."""
    gaps, stops = [], 0
    frontier = None
    for w in sorted(wins):
        s, m = w[0], w[1]
        # §16.7: a task held beside others still moves the frontier, but its start is no serial gap
        if frontier is not None and (len(w) < 3 or w[2]):
            g = s - frontier
            if g >= GAP_STOP_S:
                stops += 1
            else:
                gaps.append(round(g, 1))
        frontier = m if frontier is None else max(frontier, m)
    gaps = gaps[-GAP_HISTORY:]
    over = [g for g in gaps if g < 0]
    return {"model": "sequential", "gaps": gaps, "pairs": len(gaps), "stops": stops, "stop_s": GAP_STOP_S,
            "median_gap_s": quantile(gaps, 0.5), "mean_gap_s": round(sum(gaps) / len(gaps), 1) if gaps else None,
            "overlap_share": round(len(over) / len(gaps), 2) if gaps else None,
            "median_overlap_s": quantile([-g for g in over], 0.5),
            "text": ("one task at a time; the next starts at the latest merge plus a gap drawn from the "
                     f"{len(gaps)} latest observed gaps (negative: an overlap); gaps of {GAP_STOP_S // 60} min or "
                     "more are stops, left out" if gaps else "one task at a time, back to back: no observed gaps yet")}


# ------------------------------------------------------------------------------------ the estimates

def _est(view: dict[str, Any] | None, calibrated: bool = True) -> dict[str, Any] | None:
    """A view's bands: the calibrated ones (phase D, `cal`) when it has them, else the stored ones."""
    if not view:
        return None
    c = view.get("cal") if calibrated and isinstance(view.get("cal"), dict) else None
    src = c if c and isinstance(c.get("total"), dict) else view
    t = src.get("total") or {}
    if lognormal(t.get("p50_s"), t.get("p90_s")) is None:
        return None
    return {"source": view.get("source"), "total": t, "tokens": src.get("tokens"), "cost_usd": src.get("cost_usd"),
            # calibrated: read from the calibrated bands, unless every factor is the unfitted 1.0
            "calibrated": src is c and not (isinstance(c.get("factors"), dict) and c["factors"] and all(
                isinstance(f, dict) and f.get("bias", 1) == 1 and f.get("width", 1) == 1 for f in c["factors"].values()))}


def estimates_for(est_tasks: dict[str, Any], ids: list[str], calibrated: bool = True) -> dict[str, dict[str, Any] | None]:
    """Each task's estimate: its latest agent row, else its latest baseline row (board_view's views),
    calibrated (phase D) unless `calibrated` is false."""
    out = {}
    for tid in ids:
        e = est_tasks.get(tid) or {}
        out[tid] = _est(e.get("agent"), calibrated) or _est(e.get("baseline"), calibrated)
    return out


def rho_from(calibration: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    """The correlation the trials use: RHO, unless the calibration chose its fitted rho because a
    backtest of backlog sums favoured it (phase D, `calibrate.choose_rho`)."""
    r = (calibration or {}).get("rho") or {}
    v = r.get("value")
    info = {"fitted_value": r.get("fitted_value"), "n": r.get("n"), "se": r.get("se"),
            "note": r.get("choice") or r.get("note") or "no calibration: the default"}
    if r.get("use_fitted") and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 1:
        return float(v), {"value": float(v), "fitted": True, **info}
    return RHO, {"value": RHO, "fitted": False, **info}


def _params(ests: dict[str, dict[str, Any] | None], key: str, lo: str, hi: str) -> tuple[dict[str, tuple[float, float] | None], int]:
    """(mu, sigma) per task for one measure; a task without it takes the median P50/P90 of the rest."""
    have = {t: (e[key][lo], e[key][hi]) for t, e in ests.items() if e and isinstance(e.get(key), dict)
            and lognormal(e[key].get(lo), e[key].get(hi))}
    if not have:
        return {t: None for t in ests}, len(ests)
    med = (quantile([v[0] for v in have.values()], 0.5), quantile([v[1] for v in have.values()], 0.5))
    out, missing = {}, 0
    for t in ests:
        if t in have:
            out[t] = lognormal(*have[t])
        else:
            out[t] = lognormal(*med)
            missing += 1
    return out, missing


# ------------------------------------------------------------------------------------ the simulation

def simulate(order: list[str], deps: dict[str, list[str]], dur: dict[str, tuple[float, float]],
             meas: dict[str, dict[str, tuple[float, float] | None]], gaps: list[float], now: float,
             flight_elapsed: dict[str, float], trials: int = TRIALS, seed: int = SEED,
             targets: dict[str, list[str]] | None = None, burn: dict[str, Any] | None = None,
             rho: float | None = None, session: dict[str, Any] | None = None,
             slots: int = 1, alone: set[str] | None = None) -> dict[str, Any]:
    """Monte Carlo over the order (`rho`: the deviates' correlation, RHO by default). Returns, per target (a list of task ids), the completion times and
    each measure summed (`meas`: name -> task -> (mu, sigma); tokens, cost; the in-flight task's
    remainder only); with `burn` (the allowance: `measure`, k per unit, the baseline %/s, the current
    %, the reset and the levels), the weekly % per trial at each target's end, its spill past the
    reset, and when each level is crossed. With `session` too (the 5-hour window: `r5`, `park`,
    `margin`, the current window's end `w_end` and its % `pct_now`), the 5-hour limit's pauses shift
    every later time (`_pauses`), and each target gets its number of pauses and paused seconds. The
    pauses draw no random numbers, so the trials' draws are the same with and without them.
    `slots` (§16.7, parallel.max_in_flight): a task starts at the earliest free slot after its
    dependencies; a task in `alone` takes every slot. One slot is the model before §16, exactly: the
    one slot's free time is the frontier, and the draws are the same."""
    rng = random.Random(seed)
    gauss, choice, rand = rng.gauss, rng.choice, rng.random
    idx = {t: i for i, t in enumerate(order)}
    dep_ix = [[idx[d] for d in deps.get(t, []) if d in idx and idx[d] < i] for i, t in enumerate(order)]
    mus = [dur[t][0] for t in order]
    sig = [dur[t][1] for t in order]
    names = list(meas)
    nm = len(names)
    mpar = [[meas[k].get(t) for t in order] for k in names]   # per measure, per task: (mu, sigma) or None
    bi = names.index(burn["measure"]) if burn and burn.get("measure") in names else None
    fl = [flight_elapsed.get(t) for t in order]
    slots = max(1, int(slots or 1))
    alone_ix = [slots > 1 and t in (alone or set()) for t in order]
    targets = targets or {}
    tix = {k: [idx[t] for t in v if t in idx] for k, v in targets.items()}
    res: dict[str, dict[str, list[Any]]] = {k: {"end": [], "pct": [], "spill": [], "burn": [], "exhaust": [],
                                                "pauses": [], "paused_s": [], **{m: [] for m in names}}
                                              for k in tix if tix[k]}
    sess = session if session and bi is not None else None
    cross: dict[str, list[float | None]] = {str(lv): [] for lv in (burn or {}).get("levels", [])} if bi is not None else {}
    n = len(order)
    gaps = gaps or [0.0]
    exp, log = math.exp, math.log
    cdf, inv = _ND.cdf, _ND.inv_cdf
    rho = RHO if rho is None else rho
    rc, ri = math.sqrt(rho), math.sqrt(1 - rho)  # corr(z_i, z_j) = rc * rc = rho
    rng_n = range(n)
    for _ in range(trials):
        common = rc * gauss(0.0, 1.0)
        end = [0.0] * n
        start = [0.0] * n
        zs = [0.0] * n
        fr = [1.0] * n
        prev_start = now
        free = [now] * slots  # each slot's free time; one slot: the frontier
        for i in rng_n:
            mu, s = mus[i], sig[i]
            el = fl[i]
            if el is not None:  # in flight: drawn given it has not finished yet
                # z = common + ri * e > z0 (it has run el seconds): e is drawn above (z0 - common) / ri;
                # U0_MAX keeps a task far past its P90 running rather than drawn as already finished
                u0 = min(U0_MAX, cdf(((log(max(el, 1.0)) - mu) / s - common) / ri)) if el > 0 else 0.0
                z = common + ri * inv(u0 + (1 - u0) * max(1e-9, rand()))
                d = exp(mu + s * z)
                rem = d - el if d > el else 0.0
                st, e = now, now + rem
                fr[i] = rem / d
                k = free.index(min(free))
                if alone_ix[i]:  # a lone task in flight holds every slot until it ends
                    free = [max(f, e) for f in free]
            else:
                z = common + ri * gauss(0.0, 1.0)
                solo = alone_ix[i]
                k = free.index(max(free) if solo else min(free))
                st = free[k] + choice(gaps)
                if st < prev_start:
                    st = prev_start
                for j in dep_ix[i]:
                    if end[j] > st:
                        st = end[j]
                e = st + exp(mu + s * z)
                if solo:
                    free = [max(f, e) for f in free]
            zs[i] = z
            start[i] = st
            end[i] = e
            prev_start = st
            if e > free[k]:
                free[k] = e
        xs = [[(exp(p[0] + p[1] * zs[i]) * fr[i] if (p := mp[i]) else 0.0) for i in rng_n] for mp in mpar]
        pts: list[tuple[float, float]] = []
        if sess is not None:
            k = burn["k"]
            pts = _pauses(start, end, [k * x for x in xs[bi]], burn["per_s"], now, sess)
            if pts:
                pt = [p[0] for p in pts]
                active = end
                end = [e + (pts[j - 1][1] if (j := bisect.bisect_left(pt, e)) else 0.0) for e in end]
        traj = sorted(zip(end, xs[bi])) if bi is not None else None
        crossed = {lv: _crossing(traj, now, burn, float(lv)) for lv in burn["levels"]} if traj is not None else {}
        full = (crossed[100.0] if 100.0 in crossed else _crossing(traj, now, burn, 100.0)) if traj is not None else None
        for k, r in res.items():
            ix = tix[k]
            t_end = max(end[i] for i in ix)
            r["end"].append(t_end)
            if sess is not None:
                j = bisect.bisect_left([p[0] for p in pts], max(active[i] for i in ix)) if pts else 0
                r["pauses"].append(j)
                r["paused_s"].append(pts[j - 1][1] if j else 0.0)
            for c in range(nm):
                x = xs[c]
                r[names[c]].append(sum(x[i] for i in ix))
            if traj is not None:
                p_end = _pct_at(traj, now, burn, t_end)
                r["pct"].append(p_end)
                r["burn"].append(p_end - burn["pct_now"])
                r["spill"].append(max(0.0, p_end - _pct_at(traj, now, burn, burn["reset"])) if t_end > burn["reset"] else 0.0)
                # 100% reached before this target's work ends (and before the reset): the allowance runs out
                r["exhaust"].append(full if full is not None and full <= t_end else None)
        for lv, c in crossed.items():
            cross[str(lv)].append(c)
    return {"targets": res, "crossings": cross, "trials": trials}


def _pauses(start: list[float], end: list[float], wk: list[float], per_s: float, now: float,
            sess: dict[str, Any]) -> list[tuple[float, float]]:
    """The 5-hour limit's pauses in one trial: (the time on the unpaused timeline at which the window
    reaches the park %, the total pause from there on). The weekly % rises at `per_s` (use outside
    the plane) plus each task's weekly % `wk` spread evenly over its run, the 5-hour % at `r5` times
    that. The current window ends at `w_end` from `pct_now`; one that ends while work goes on is
    followed at once by the next (it rolls from first use) at 0%. At the park %, work stops until the
    window's end plus `margin`, and the next window starts at that resume, at 0%."""
    r5, park, margin = sess["r5"], sess["park"], sess["margin"]
    ev = []
    for s, e, x in zip(start, end, wk):
        if x > 0 and e > s:
            ev.append((s, x / (e - s)))
            ev.append((e, -x / (e - s)))
    ev.sort()
    horizon = max(end) if end else now
    t, shift, pct, we, rate = now, 0.0, sess["pct_now"], sess["w_end"], per_s
    out: list[tuple[float, float]] = []
    i, n = 0, len(ev)
    while t < horizon:
        while i < n and ev[i][0] <= t:
            rate += ev[i][1]
            i += 1
        nxt = min(ev[i][0], horizon) if i < n else horizon
        r = r5 * rate if rate > 0 else 0.0
        while t < nxt:
            if we is None:  # no window open: the next starts at the first use
                if r <= 0:
                    t = nxt
                    break
                we = t + shift + SESSION_S
            to_end = we - (t + shift)
            to_park = (park - pct) / r if r > 0 else math.inf
            step = nxt - t
            if step < to_end and step < to_park:
                pct += r * step
                t = nxt
            elif to_end <= to_park:
                t += max(to_end, 0.0)
                pct, we = 0.0, (t + shift + SESSION_S if r > 0 else None)
            else:
                t += max(to_park, 0.0)
                resume = we + margin
                shift += resume - (t + shift)
                out.append((t, shift))
                pct, we = 0.0, resume + SESSION_S
    return out


def _pct_at(traj: list[tuple[float, float]], now: float, burn: dict[str, Any], t: float) -> float:
    """The weekly % at time t: the current %, the baseline burn and the work's burn, spread evenly
    between completions (cumulative, ignoring the reset)."""
    k, b, p0 = burn["k"], burn["per_s"], burn["pct_now"]
    if t <= now:
        return p0
    cum, prev_t, prev_c = 0.0, now, 0.0
    for e, x in traj:
        cum += x
        if e >= t:
            span = e - prev_t
            part = prev_c + (cum - prev_c) * ((t - prev_t) / span if span > 0 else 1.0)
            return p0 + b * (t - now) + k * part
        prev_t, prev_c = max(prev_t, e), cum
    return p0 + b * (t - now) + k * cum


def _crossing(traj: list[tuple[float, float]], now: float, burn: dict[str, Any], level: float) -> float | None:
    """When the weekly % first reaches `level` (now if it already has); None when not before the reset."""
    k, b, p0, reset = burn["k"], burn["per_s"], burn["pct_now"], burn["reset"]
    if p0 >= level:
        return now
    prev_t, prev_p, cum = now, p0, 0.0
    for e, x in traj:
        cum += x
        e = max(e, prev_t)
        p = p0 + b * (e - now) + k * cum
        if p >= level:
            t = prev_t + (level - prev_p) / (p - prev_p) * (e - prev_t) if p > prev_p else e
            return t if t <= reset else None
        prev_t, prev_p = e, p
    if b > 0:
        t = prev_t + (level - prev_p) / b
        return t if t <= reset else None
    return None


# ------------------------------------------------------------------------------------ telemetry

def _line_at(line: str) -> float | None:
    """A row's `at` as epoch seconds (UTC), read from the line without parsing the whole row."""
    j = line.find('"at": "')
    if j < 0:
        return None
    k = line.find('"', j + 7)
    return _ep(line[j + 7:k]) if k > 0 else None


def _rows(paths: list[Path], after: float | None = None, offsets: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """Request rows from jsonl files, one per request id. `after` (epoch seconds) skips rows at or
    before it, their time parsed as a UTC datetime before the row is; `offsets` starts a file at a
    byte offset (the part appended since)."""
    out: dict[str, dict[str, Any]] = {}
    for p in paths:
        try:
            fh = p.open("rb")
        except OSError:
            continue
        with fh:
            if offsets and offsets.get(str(p)):
                fh.seek(offsets[str(p)])
            for i, raw in enumerate(fh):
                line = raw.decode("utf-8", "replace")
                if after is not None:
                    t = _line_at(line)
                    if t is not None and t <= after:
                        continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    out[str(r.get("request_id") or f"{p}:{i}")] = r
    return list(out.values())


def telemetry_paths(q: Path) -> tuple[list[Path], list[Path]]:
    """(the plane's request files: this queue's and every other product's bound queue, the system
    sink's). The plane's own development (a binding whose product_root is the plane itself) is not
    product work: its requests count with the system sink, as before it had a queue."""
    from ccp import otel  # noqa: PLC0415
    plane = [q / "board" / "usage-requests.jsonl"]
    own: list[Path] = []
    try:
        for _pid, root, oq in otel.bindings():
            p = oq / "board" / "usage-requests.jsonl"
            if p.resolve() == plane[0].resolve():
                continue
            (own if otel.is_plane_repo(root) else plane).append(p)
    except Exception:  # noqa: BLE001  (no bindings: this queue only)
        pass
    d = otel.telemetry_dir()
    sink = sorted(d.glob("usage-requests-????-??-??.jsonl")) if d.is_dir() else []
    return [p for p in plane if p.is_file()], sink + [p for p in own if p.is_file()]


def _tokens(r: dict[str, Any]) -> float:
    return sum(float(r.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"))


class Series:
    """Prefix sums of tokens and cost over time, overall and by model family, for interval sums."""

    def __init__(self, rows: list[dict[str, Any]]):
        pts = sorted(((t, r) for r in rows if (t := _ep(r.get("at"))) is not None), key=lambda p: p[0])
        self.t = [p[0] for p in pts]
        self.first = self.t[0] if self.t else None
        self.fams = sorted({family(r.get("model")) for _, r in pts})
        self.cum: dict[str, list[float]] = {}
        acc: dict[str, float] = {}
        keys = ["tokens", "cost"] + [f"{m}:{f}" for f in self.fams for m in ("tokens", "cost")]
        for k in keys:
            self.cum[k] = [0.0]
            acc[k] = 0.0
        for _, r in pts:
            tk, c, f = _tokens(r), float(r.get("cost_usd") or 0), family(r.get("model"))
            for k, v in (("tokens", tk), ("cost", c), (f"tokens:{f}", tk), (f"cost:{f}", c)):
                acc[k] += v
            for k in keys:
                self.cum[k].append(acc[k])

    def sum(self, key: str, a: float, b: float) -> float:
        c = self.cum.get(key)
        if not c:
            return 0.0
        i, j = bisect.bisect_right(self.t, a), bisect.bisect_right(self.t, b)
        return c[j] - c[i]


# ------------------------------------------------------------------------------------ the allowance fit

def intervals(samples: list[dict[str, Any]], since: float | None = None) -> list[dict[str, Any]]:
    """Consecutive samples in one weekly window whose % did not fall, joined to FIT_MIN_INTERVAL_S."""
    from ccp.usage import same_window, wname  # noqa: PLC0415
    # by time only: two samples taken in the same second keep their order (a tie never compares the rows)
    pts = sorted(((t, s) for s in samples if (t := _ep(s.get("at"))) is not None and _num(s.get("seven_day")) is not None),
                 key=lambda p: p[0])
    out, a = [], None
    for t, s in pts:
        if since is not None and t < since:
            continue
        if a is None:
            a = (t, s)
            continue
        ta, sa = a
        if not same_window(sa.get("resets_at"), s.get("resets_at")) or float(s["seven_day"]) < float(sa["seven_day"]) \
                or t - ta > FIT_MAX_INTERVAL_S or wname(sa, "weekly") != wname(s, "weekly"):
            a = (t, s)
            continue
        if t - ta >= FIT_MIN_INTERVAL_S:
            out.append({"a": ta, "b": t, "d": float(s["seven_day"]) - float(sa["seven_day"])})
            a = (t, s)
    return out


def _solve(A: list[list[float]], y: list[float]) -> list[float] | None:
    """Least squares through the origin (normal equations, Gaussian elimination)."""
    m = len(A[0]) if A else 0
    if not m or len(A) < m:
        return None
    M = [[sum(r[i] * r[j] for r in A) for j in range(m)] + [sum(r[i] * v for r, v in zip(A, y))] for i in range(m)]
    for c in range(m):
        p = max(range(c, m), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-18:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(m):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [x - f * yv for x, yv in zip(M[r], M[c])]
    return [M[i][m] / M[i][i] for i in range(m)]


def fit_model(X: list[list[float]], y: list[float]) -> dict[str, Any] | None:
    """Coefficients, in-sample error and the leave-one-out RMSE (percentage points per interval)."""
    k = _solve(X, y)
    if k is None or any(v <= 0 for v in k):
        return None
    pred = [sum(a * b for a, b in zip(r, k)) for r in X]
    res = [p - v for p, v in zip(pred, y)]
    loo = []
    for i in range(len(y)):
        ki = _solve(X[:i] + X[i + 1:], y[:i] + y[i + 1:])
        if ki is None:
            return None
        loo.append(sum(a * b for a, b in zip(X[i], ki)) - y[i])
    tot = sum(y)
    return {"k": k, "rmse": math.sqrt(sum(r * r for r in res) / len(y)), "loo_rmse": math.sqrt(sum(r * r for r in loo) / len(y)),
            "wape": round(sum(abs(r) for r in res) / tot, 3) if tot > 0 else None, "n": len(y)}


def allowance_fit(samples: list[dict[str, Any]], plane: Series, sink: Series | None, now: float) -> dict[str, Any]:
    """The fit of weekly % to usage (see the module doc), and the non-plane burn per hour."""
    starts = [x for x in (plane.first, sink.first if sink else None) if x is not None]
    since = max(starts) if sink and len(starts) == 2 else plane.first
    iv = intervals(samples, since)
    out: dict[str, Any] = {"v": FIT_V, "samples": len(samples), "intervals": len(iv), "since": iso(since),
                           "non_plane": "system sink" if sink and sink.first is not None else None, "models": {}, "chosen": None}
    if sink is None or sink.first is None:
        out["note"] = "no system sink: use outside the plane is unknown, so the fit overstates the plane's share"
    if len(iv) < FIT_MIN_N:
        out["note"] = f"{len(iv)} usable interval(s) between allowance samples; the fit needs {FIT_MIN_N}"
        return out
    y = [x["d"] for x in iv]

    def both(key: str, a: float, b: float) -> float:
        return plane.sum(key, a, b) + (sink.sum(key, a, b) if sink else 0.0)

    fams = sorted(set(plane.fams) | set(sink.fams if sink else []))
    for unit in ("tokens", "cost"):
        scale = 1e6 if unit == "tokens" else 1.0
        X = [[both(unit, x["a"], x["b"]) / scale] for x in iv]
        f = fit_model(X, y)
        if f:
            out["models"][unit] = {**f, "keys": [unit]}
        used = [fm for fm in fams if sum(1 for x in iv if both(f"{unit}:{fm}", x["a"], x["b"]) > 0) >= FIT_FAMILY_MIN]
        if len(used) >= 2 and len(iv) >= len(used) + 2:
            X = [[both(f"{unit}:{fm}", x["a"], x["b"]) / scale for fm in used] for x in iv]
            f = fit_model(X, y)
            if f:
                out["models"][f"{unit}_by_family"] = {**f, "keys": [f"{unit}:{fm}" for fm in used]}
    if not out["models"]:
        out["note"] = "no model fitted (too little usage in the intervals, or a negative coefficient)"
        return out
    # the lowest leave-one-out error wins; within 5% of it, the simpler model (one rate before rates by family)
    best = min(v["loo_rmse"] for v in out["models"].values())
    name = next(m for m in ("tokens", "cost", "tokens_by_family", "cost_by_family")
                if m in out["models"] and out["models"][m]["loo_rmse"] <= best * 1.05 + 1e-9)
    m = out["models"][name]
    unit = "tokens" if name.startswith("tokens") else "cost"
    scale = 1e6 if unit == "tokens" else 1.0
    kmap = dict(zip(m["keys"], m["k"]))
    lo = now - BASELINE_DAYS * 86400

    def k_eff(src: Series | None, a: float, b: float) -> float:
        """% per unit of the measure, for a source's mix of families over [a, b]."""
        if len(kmap) == 1:
            return m["k"][0] / scale
        tot = src.sum(unit, a, b) if src else 0.0
        if tot <= 0:
            return sum(m["k"]) / len(m["k"]) / scale
        return sum(kmap.get(f"{unit}:{fm}", 0.0) * src.sum(f"{unit}:{fm}", a, b) for fm in src.fams) / tot / scale

    sink_lo = max(lo, sink.first) if sink and sink.first is not None else None
    hours = (now - sink_lo) / 3600 if sink_lo is not None else 0
    base_x = sink.sum(unit, sink_lo, now) if sink and sink_lo is not None else 0.0
    # a span under BASELINE_MIN_SPAN_H is averaged over that floor (see the constant)
    base = k_eff(sink, sink_lo, now) * base_x / max(hours, BASELINE_MIN_SPAN_H) if hours > 0.5 else None
    out.update({"chosen": name, "unit": unit,
                "k_plane": k_eff(plane, lo, now),       # % per token (or per dollar) of the plane's mix
                "per_unit_text": (f"{m['k'][0]:.3g}% per M tokens" if name == "tokens" else
                                  f"{m['k'][0]:.3g}% per $" if name == "cost" else
                                  ", ".join(f"{k.split(':')[1]} {v:.3g}%" for k, v in kmap.items())
                                  + (" per M tokens" if unit == "tokens" else " per $")),
                "loo_rmse": round(m["loo_rmse"], 2), "rmse": round(m["rmse"], 2), "wape": m["wape"], "n": m["n"],
                "mean_interval_h": round(sum(x["b"] - x["a"] for x in iv) / len(iv) / 3600, 2),
                "mean_delta": round(sum(y) / len(y), 2),
                "baseline_pct_per_h": round(base, 3) if base is not None else None,
                "baseline_hours": round(hours, 1), "baseline_floored": base is not None and hours < BASELINE_MIN_SPAN_H,
                "baseline_span_h": round(max(hours, BASELINE_MIN_SPAN_H), 1)})
    out["k_map"] = {k: v / scale for k, v in kmap.items()}
    for mm in out["models"].values():
        mm["k"] = [round(v, 6) for v in mm["k"]]
        mm["loo_rmse"], mm["rmse"] = round(mm["loo_rmse"], 2), round(mm["rmse"], 2)
    return out


def session_fit(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """`r5`, the 5-hour % per weekly %, from consecutive samples in one 5-hour window (the 5-hour % did
    not fall; both rows' `five_hour_resets_at`, where both have one, name the same window; at most 5 h
    apart) and one weekly window, whose weekly % rose by 1 or more (a smaller rise carries the start
    forward). The estimate is the ratio of the sums, sum(d5) / sum(dweekly): least squares through the
    origin weighted by 1/dweekly, so an interval counts by its weekly rise and the whole-percent
    rounding of a chain of samples cancels. Fewer than R5_MIN_N intervals: none."""
    from ccp.usage import same_session, same_window, wname  # noqa: PLC0415
    # by time only: two samples taken in the same second keep their order (a tie never compares the rows)
    pts = sorted(((t, s) for s in samples if (t := _ep(s.get("at"))) is not None
                  and _num(s.get("five_hour")) is not None and _num(s.get("seven_day")) is not None),
                 key=lambda p: p[0])
    iv, a = [], None
    for t, s in pts:
        if a is None:
            a = (t, s)
            continue
        ta, sa = a
        fa, fb = float(sa["five_hour"]), float(s["five_hour"])
        wa, wb = float(sa["seven_day"]), float(s["seven_day"])
        ra, rb = sa.get("five_hour_resets_at"), s.get("five_hour_resets_at")
        if fb < fa or wb < wa or t - ta > SESSION_S or not same_window(sa.get("resets_at"), s.get("resets_at")) \
                or (ra and rb and not same_session(ra, rb)) \
                or wname(sa, "weekly") != wname(s, "weekly") or wname(sa, "session") != wname(s, "session"):
            a = (t, s)
            continue
        if wb - wa >= 1:
            iv.append((fb - fa, wb - wa))
            a = (t, s)
    out: dict[str, Any] = {"n": len(iv), "r5": None, "estimator": "sum(d5) / sum(dweekly)"}
    if len(iv) < R5_MIN_N:
        out["note"] = f"{len(iv)} usable interval(s) in one 5-hour window; the 5-hour fit needs {R5_MIN_N}"
        return out
    d5, dw = sum(x[0] for x in iv), sum(x[1] for x in iv)
    out["r5"] = round(d5 / dw, 3)
    out["ratios"] = {"min": round(min(x[0] / x[1] for x in iv), 2), "max": round(max(x[0] / x[1] for x in iv), 2)}
    return out


def _since_sample(fit: dict[str, Any], plane_paths: list[Path], sink_paths: list[Path], at: str) -> float:
    """The fitted % of the usage recorded after the latest sample (the plane's and outside it)."""
    if not fit.get("chosen"):
        return 0.0
    unit, km = fit["unit"], fit.get("k_map") or {}
    tot = 0.0
    t0 = _ep(at)
    for r in _rows(plane_paths + sink_paths, after=t0):
        if t0 is not None and (_ep(r.get("at")) or 0) <= t0:
            continue
        v = _tokens(r) if unit == "tokens" else float(r.get("cost_usd") or 0)
        k = km.get(unit) if unit in km else km.get(f"{unit}:{family(r.get('model'))}", sum(km.values()) / max(1, len(km)))
        tot += (k or 0.0) * v
    return tot


def _sig(paths: list[Path]) -> list[Any]:
    """[path, size, mtime, inode] per file."""
    out = []
    for p in paths:
        try:
            st = p.stat()
            out.append([str(p), st.st_size, st.st_mtime_ns, st.st_ino])
        except OSError:
            out.append([str(p), None, None, None])
    return out


def _still_valid(cached: list[Any], now_sig: list[Any], upto: float | None) -> bool:
    """The telemetry the fit read is unchanged where it matters: each file is the same file (inode),
    no shorter, and what was appended since (read from the old size) holds no row at or before the
    fitted span's end (a late row inside it would change the fit). An unchanged size and mtime need
    no read; anything else that differs means a re-fit."""
    old = {c[0]: c for c in cached}
    if set(old) != {c[0] for c in now_sig}:
        return False
    grown: dict[str, int] = {}
    for path, size, mtime, ino in now_sig:
        _, osize, omtime, oino = old[path]
        if (size, mtime, ino) == (osize, omtime, oino):
            continue
        if size is None or osize is None or ino != oino or size < osize:
            return False
        grown[path] = osize
    if not grown:
        return True
    if upto is None:
        return False
    return not any((_ep(r.get("at")) or 0) <= upto for r in _rows([Path(p) for p in grown], offsets=grown))


def cached_fit(q: Path, now: float) -> tuple[dict[str, Any], list[Path], list[Path]]:
    """The allowance fit, re-fitted when the allowance samples change or the telemetry it read
    changed where it matters (`_still_valid`: the files, their sizes, mtimes and inodes, and any late
    row inside the fitted span)."""
    from ccp.usage import _jsonl  # noqa: PLC0415
    ap = q / "board" / "allowance.jsonl"
    plane_paths, sink_paths = telemetry_paths(q)
    tel = _sig(plane_paths + sink_paths)
    key = {"v": FIT_V, "allowance": _sig([ap])}
    cp = q / "board" / "forecast-fit.json"
    try:
        c = json.loads(cp.read_text())
        if isinstance(c, dict) and c.get("key") == key and isinstance(c.get("fit"), dict) \
                and _still_valid(c.get("telemetry") or [], tel, _ep(c.get("upto"))):
            return c["fit"], plane_paths, sink_paths
    except (OSError, ValueError, TypeError):
        pass
    samples = _jsonl(ap)
    last = _ep(samples[-1].get("at")) if samples else None
    upto = last if last is not None else now
    plane = Series([r for r in _rows(plane_paths) if (_ep(r.get("at")) or 0) <= upto])
    sink = Series([r for r in _rows(sink_paths) if (_ep(r.get("at")) or 0) <= upto]) if sink_paths else None
    fit = allowance_fit(samples, plane, sink, upto)
    fit["session"] = session_fit(samples)
    try:
        tmp = cp.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(json.dumps({"key": key, "telemetry": tel, "upto": iso(upto), "at": iso(now), "fit": fit}))
        os.replace(tmp, cp)
    except OSError:
        pass
    return fit, plane_paths, sink_paths


# ------------------------------------------------------------------------------------ the forecast

def _band(xs: list[float], digits: int | None = None) -> dict[str, Any] | None:
    if not xs:
        return None
    a, b = quantile(xs, 0.5), quantile(xs, 0.9)
    return {"p50": round(a, digits) if digits is not None else a, "p90": round(b, digits) if digits is not None else b}


def _time_band(xs: list[float]) -> dict[str, Any] | None:
    b = _band(xs)
    return {"p50": iso(b["p50"]), "p90": iso(b["p90"])} if b else None


def _flight_elapsed(q: Path | None, tid: str, drill: dict[str, Any] | None, work: dict[str, Any], now: float) -> float:
    d = (drill or {}).get(tid) or {}
    s = _ep(d.get("start_at")) if isinstance(d, dict) else None
    if s is None and q is not None:
        from ccp.queue import load_task_state  # noqa: PLC0415
        try:
            s = _ep(load_task_state(q, tid).get("claimed_at"))
        except Exception:  # noqa: BLE001
            s = None
    old = work.get("lease")  # an old work.json's top-level lease (§16.4: no writer keeps it now), read if present
    if s is None and isinstance(old, dict) and old.get("task_id") == tid:
        s = _ep(old.get("since"))
    return max(0.0, now - s) if s is not None else 0.0


def collect(cfg: Config, q: Path | None, *, tasks: list[dict[str, Any]] | None = None, drill: dict[str, Any] | None = None,
            est_tasks: dict[str, Any] | None = None, work: dict[str, Any] | None = None, merged: list[str] | None = None,
            open_items: dict[str, Any] | None = None, allowance: dict[str, Any] | None = None,
            now: float | None = None, trials: int = TRIALS, point: str | None = None,
            calibration: dict[str, Any] | None = None, calibrated: bool = True) -> dict[str, Any]:
    """The board's `forecast`: the review point's and the backlog's completion, tokens, cost and
    weekly %, P50 and P90, from the calibrated estimates and the calibration's rho (phase D;
    `calibrated=False`: the stored bands and RHO). Reads only (bar the fit's cache files)."""
    t0 = time.perf_counter()
    now = now if now is not None else time.time()
    from ccp.queue import load_work  # noqa: PLC0415
    if work is None:
        try:
            work = load_work(q) if q is not None else {}
        except Exception:  # noqa: BLE001
            work = {}
    if est_tasks is None:
        from ccp import estimate  # noqa: PLC0415
        bv = estimate.board_view(q, cfg=cfg) if q is not None else {}
        est_tasks = bv.get("tasks") or {}
        calibration = calibration if calibration is not None else bv.get("calibration")
    rho, rho_info = rho_from(calibration) if calibrated else (RHO, {"value": RHO, "fitted": False, "note": "raw estimates"})
    seq = sequence(cfg, q, tasks, merged)
    order = seq["order"]
    rp = point or seq["review_point"] or None
    if not rp:
        try:
            from ccp import reviewpoints  # noqa: PLC0415
            cur = reviewpoints.current(reviewpoints.load(cfg)[0])
            rp = cur.get("id") if cur else None
        except Exception:  # noqa: BLE001
            rp = None
    tags, status = seq["tags"], seq["status"]
    rp_open = [t for t in order if rp and tags.get(t) == rp]
    rp_basis = "tag"
    if rp and not rp_open and not any(tags.get(t) == rp for t in status) and seq["scope"]:
        rp_open = [t for t in order if tasklog.in_scope(t, seq["scope"])]
        rp_basis = "scope"
    out: dict[str, Any] = {
        "v": FORECAST_V, "advisory": True, "generated_at": iso(now), "trials": trials, "seed": SEED,
        "review_point": rp, "review_point_basis": rp_basis, "order": order, "in_flight": seq["in_flight"],
        "unreached": seq["unreached"], "point": None, "backlog": None, "allowance": None,
        "rho": rho_info, "calibrated": calibrated}
    ests = estimates_for(est_tasks, order, calibrated)
    dur, unest = _params(ests, "total", "p50_s", "p90_s")
    if not order:
        out["note"] = "no open task to forecast"
        out["ms"] = round((time.perf_counter() - t0) * 1000)
        return out
    if unest == len(order):
        out["note"] = "no open task has an estimate: run `ccp tasks estimate --all --baseline`"
        out["ms"] = round((time.perf_counter() - t0) * 1000)
        return out
    tok, tok_missing = _params(ests, "tokens", "p50", "p90")
    cost, cost_missing = _params(ests, "cost_usd", "p50", "p90")
    # §16.7: gaps come from serial history only (a window the runner shared would count overlap twice)
    from ccp import parallel  # noqa: PLC0415
    tp = throughput(windows(drill, _held_alone(q, drill)))
    slots = int(parallel.settings(cfg)["max_in_flight"]) if parallel.enabled(cfg) else 1
    alone: set[str] = set()
    if slots > 1:
        metas = {str(t.get("task_id")): t for t in (tasks if tasks is not None else tasklog.load(cfg))}
        alone = {t for t in order if t in metas and parallel.runs_alone(cfg, metas[t])}
        tp["model"] = "slots"
        tp["slots"] = slots
        tp["text"] = (f"up to {slots} tasks at once (parallel.max_in_flight, SPEC §16); each starts at the earliest "
                      f"free slot plus an observed gap; {len(alone)} task(s) run alone. Not modelled: two tasks "
                      "whose paths meet, or work past the 5-hour ceiling, still share slots. " + tp["text"])
    elapsed = {t: _flight_elapsed(q, t, drill, work, now) for t in seq["in_flight"]}
    # waits flagged now: an open wait, gate or question on a remaining task
    oi = open_items or {}
    flagged = sorted({str(x.get("task_id")) for k in ("waits", "gates", "questions") for x in oi.get(k) or []
                      if str(x.get("task_id")) in set(order)}
                     | ({str(work.get("task_id"))} if work.get("waiting_on") and str(work.get("task_id")) in set(order) else set()))
    # the allowance
    burn, fit, alw = None, None, None
    if q is not None:
        try:
            fit, pp, sp = cached_fit(q, now)
        except Exception as exc:  # noqa: BLE001  (the forecast stands without it)
            fit, pp, sp = {"error": f"{type(exc).__name__}: {exc}"[:200]}, [], []
        last = (allowance or {}).get("latest") or {}
        if not last:
            from ccp.usage import _jsonl  # noqa: PLC0415
            last = (_jsonl(q / "board" / "allowance.jsonl") or [{}])[-1]
        cur, reset = _num(last.get("seven_day")), _ep(last.get("resets_at"))
        if fit.get("chosen") and cur is not None and reset is not None:
            add = _since_sample(fit, pp, sp, str(last.get("at") or ""))
            while reset <= now:  # the sample's window has ended: the % starts again from 0
                reset += WEEK_S
                cur, add = 0.0, 0.0
            levels = sorted({float(x) for x in ((allowance or {}).get("project_checkpoint"),
                                                 (allowance or {}).get("checkpoint")) if _num(x) is not None})
            if not levels:  # the gating weekly window's own stop (§25.2 the usage windows)
                from ccp.usage import window_rules, wname  # noqa: PLC0415
                st = window_rules(cfg).get(wname(last, "weekly"), {}).get("stop_pct")
                levels = [float(st)] if _num(st) is not None else []
            burn = {"k": fit["k_plane"], "per_s": (fit.get("baseline_pct_per_h") or 0.0) / 3600, "pct_now": cur + add,
                    "reset": reset, "levels": sorted(set(levels) | {100.0})}
            alw = {"pct_sample": cur, "sample_at": last.get("at"), "pct_now": round(cur + add, 1),
                   "added_since_sample": round(add, 2), "resets_at": iso(reset), "levels": levels,
                   "checkpoint": _num((allowance or {}).get("checkpoint")),
                   "project_checkpoint": _num((allowance or {}).get("project_checkpoint"))}
    if burn:
        burn["measure"] = fit["unit"]
    sess, sess_info = _session(cfg, fit, burn, last if q is not None else {}, now)
    targets = {"backlog": order}
    if rp_open:
        targets["point"] = rp_open
    sim = simulate(order, seq["deps"], dur, {"tokens": tok, "cost": cost}, tp["gaps"], now, elapsed, trials, SEED,
                   targets, burn, rho, sess, slots, alone)
    for k in targets:
        ids = targets[k]
        r = sim["targets"][k]
        body = {"tasks": len(ids), "task_ids": ids, "eta": _time_band(r["end"]),
                "hours": _band([(e - now) / 3600 for e in r["end"]], 1),
                "tokens": _band(r["tokens"], 0) if tok_missing < len(order) else None,
                "cost_usd": _band(r["cost"], 2) if cost_missing < len(order) else None,
                "unestimated": sum(1 for t in ids if not ests.get(t)),
                "waits_flagged": [t for t in flagged if t in set(ids)],
                "waits_expected": [t for t in ids if ((est_tasks.get(t) or {}).get("agent") or {}).get("waits")]}
        if burn:
            ex = sorted(x if x is not None else math.inf for x in r["exhaust"])
            nx = sum(1 for x in r["exhaust"] if x is not None)
            body["allowance"] = {"burn": _band(r["burn"], 1), "pct": _band(r["pct"], 1), "spill": _band(r["spill"], 1),
                                 # fits: ends before the reset without reaching 100%
                                 "fits_share": round(sum(1 for e, x in zip(r["end"], r["exhaust"])
                                                         if e <= burn["reset"] and x is None) / len(r["end"]), 2),
                                 "exhausts": {"share": round(nx / len(ex), 2), "p50": iso(_rank(ex, 0.5)),
                                              "p90_early": iso(_rank(ex, 0.1))}}
        if sess:
            body["session"] = {"pauses": _band([float(x) for x in r["pauses"]], 0),
                               "paused_h": _band([x / 3600 for x in r["paused_s"]], 1),
                               "share": round(sum(1 for x in r["pauses"] if x) / len(r["pauses"]), 2)}
        if k == "point":
            body["review_point"] = rp
            body["done"] = sum(1 for t, s in status.items() if tags.get(t) == rp and s == "done")
            body["unreached"] = {t: w for t, w in seq["unreached"].items() if tags.get(t) == rp}
        out["point" if k == "point" else "backlog"] = body
    if out["point"] and out["backlog"]:
        out["backlog"]["same_as_point"] = out["point"]["task_ids"] == out["backlog"]["task_ids"]
    out["tokens_missing"], out["cost_missing"], out["unestimated"] = tok_missing, cost_missing, unest
    out["sources"] = {s: sum(1 for t in order if (ests.get(t) or {}).get("source") == s) for s in ("agent", "baseline")}
    out["calibrated_tasks"] = sum(1 for t in order if (ests.get(t) or {}).get("calibrated"))
    out["throughput"] = {k: v for k, v in tp.items() if k != "gaps"}
    out["in_flight_elapsed_s"] = {t: round(v) for t, v in elapsed.items()}
    if burn:
        cr = {}
        for lv, xs in sim["crossings"].items():
            vals = sorted(x if x is not None else math.inf for x in xs)
            share = sum(1 for x in xs if x is not None) / len(xs) if xs else 0.0
            cr[lv] = {"share": round(share, 2), "p50": iso(_rank(vals, 0.5)), "p90_early": iso(_rank(vals, 0.1))}
        alw["crossings"] = cr
        alw["fit"] = {k: fit.get(k) for k in ("chosen", "unit", "per_unit_text", "loo_rmse", "rmse", "wape", "n", "samples",
                                               "intervals", "mean_interval_h", "mean_delta", "baseline_pct_per_h",
                                               "baseline_hours", "baseline_floored", "baseline_span_h", "non_plane", "since",
                                               "note")}
        alw["fit"]["models"] = {k: {"loo_rmse": v["loo_rmse"], "wape": v["wape"]} for k, v in (fit.get("models") or {}).items()}
    elif fit is not None:
        alw = {"fit": {k: fit.get(k) for k in ("chosen", "samples", "intervals", "note", "error")}, "unavailable": True}
    out["allowance"] = alw
    out["session"] = sess_info
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    return out


def _session(cfg: Config, fit: dict[str, Any] | None, burn: dict[str, Any] | None, last: dict[str, Any],
             now: float) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """The 5-hour window for the trials (`simulate`'s `session`), and what the forecast says about it.
    None (with a note) when the park is off, the weekly fit is missing, or r5 has too few intervals."""
    from ccp.usage import session_settings  # noqa: PLC0415
    park, _arm, margin = session_settings(cfg, last)  # the gating session window's park (§25.4 the usage windows)
    sf = (fit or {}).get("session") or {}
    info: dict[str, Any] = {"window": last.get("session_window") or "five_hour",
                            "park_pct": park, "margin_s": margin, "r5": sf.get("r5"), "n": sf.get("n"),
                            "estimator": sf.get("estimator"), "modelled": False}
    if park is None:
        info["note"] = "the session window's park % is null (telemetry.windows / session_park_pct): no pauses modelled"
        return None, info
    from ccp.parallel import no_five_hour_limit  # noqa: PLC0415
    if no_five_hour_limit(last):  # §25.4: the account has no 5-hour limit since 2026-10-31
        info["note"] = "the latest sample has no 5-hour figure: no 5-hour limit, no pauses modelled"
        return None, info
    if not burn:
        info["note"] = "no weekly allowance fit: the 5-hour window is not modelled"
        return None, info
    if not sf.get("r5"):
        info["note"] = sf.get("note") or "no 5-hour fit"
        return None, info
    r5 = float(sf["r5"])
    five, reset = _num(last.get("five_hour")), _ep(last.get("five_hour_resets_at"))
    added = burn["pct_now"] - (_num(last.get("seven_day")) or 0.0) if _num(last.get("seven_day")) is not None else 0.0
    if five is not None and reset is not None and reset > now:
        w_end, pct, basis = reset, five + r5 * max(0.0, added), "the latest sample's window"
    else:  # the window's end is unknown, or it has passed: a fresh window from now
        w_end, pct, basis = now + SESSION_S, 0.0, "a fresh window from now (the latest sample's reset is unknown or past)"
    info.update(modelled=True, window_end=iso(w_end), pct_now=round(pct, 1), window_basis=basis)
    return {"r5": r5, "park": float(park), "margin": float(margin), "w_end": w_end, "pct_now": pct}, info


def _rank(vals: list[float], p: float) -> float | None:
    """The nearest-rank quantile of sorted values, None where it is infinite (not crossed)."""
    if not vals:
        return None
    v = vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))]
    return v if math.isfinite(v) else None


# ------------------------------------------------------------------------------------ terminal

def _when(s: Any) -> str:
    e = _ep(s)
    return "-" if e is None else datetime.fromtimestamp(e).strftime("%a %d %b %H:%M")


def _tok(n: Any) -> str:
    return "-" if n is None else f"{float(n) / 1e6:.0f}M" if float(n) >= 1e7 else f"{float(n) / 1e6:.1f}M"


def exhaust_text(x: dict[str, Any], when: Any = None) -> str:
    """Whether the work runs the weekly allowance out (100%) before it ends, in words."""
    when = when or _when
    e = x.get("exhausts") or {}
    if e.get("p50"):
        return f"exhausts the weekly allowance (100%) around {when(e['p50'])} (P50; P90 early {when(e.get('p90_early'))})"
    if e.get("p90_early"):
        return f"may exhaust the weekly allowance: 100% reached in {e.get('share', 0):.0%} of trials, P90 early {when(e['p90_early'])}"
    return f"reaches 100% of the weekly allowance before it ends in {e.get('share', 0):.0%} of trials"


def session_text(x: dict[str, Any], info: dict[str, Any]) -> str:
    """"5-hour limit: pauses P50 2 (1.6 h) / P90 3 (2.4 h), r5 6.4 (n 9)"."""
    p, h = x.get("pauses") or {}, x.get("paused_h") or {}
    return (f"5-hour limit: pauses P50 {p.get('p50', 0):.0f} ({h.get('p50', 0):.1f} h) / P90 {p.get('p90', 0):.0f} "
            f"({h.get('p90', 0):.1f} h), r5 {_r5(info.get('r5'))} (n {info.get('n')})")


def _r5(v: Any) -> str:
    return f"{v:.1f}" if _num(v) is not None else "-"


def text(f: dict[str, Any], which: str | None = None) -> str:
    lines = ["Forecast (advisory, SPEC §26.4): P50 / P90 over "
             f"{f.get('trials')} seeded trials"]
    if f.get("note"):
        return lines[0] + "\n" + f["note"]
    a = f.get("allowance") or {}
    for key, label in (("point", f"Review point {f.get('review_point')}"), ("backlog", "Open backlog")):
        b = f.get(key)
        if not b or (which and which != key):
            continue
        if b.get("same_as_point") and which is None:
            lines += ["", f"{label}: the same {b['tasks']} task(s) as the review point"]
            continue
        tk, c, eta = b.get("tokens") or {}, b.get("cost_usd") or {}, b.get("eta") or {}
        head = f"{label}: {b['tasks']} remaining" + (f", {b['done']} done" if "done" in b else "")
        lines += ["", head,
                  f"  ETA        {_when(eta.get('p50'))}  /  {_when(eta.get('p90'))}  (local time)",
                  f"  tokens     {_tok(tk.get('p50'))}  /  {_tok(tk.get('p90'))}",
                  "  cost       " + (f"${c['p50']:.0f}  /  ${c['p90']:.0f}" if c.get("p50") is not None else "-")]
        if b.get("allowance"):
            x = b["allowance"]
            lines.append(f"  weekly %   +{x['burn']['p50']:.0f}% -> {x['pct']['p50']:.0f}%  /  +{x['burn']['p90']:.0f}% -> "
                         f"{x['pct']['p90']:.0f}%;  fits (ends before the reset, under 100%) in {x['fits_share']:.0%} of trials; "
                         f"spills {x['spill']['p50']:.0f}% / {x['spill']['p90']:.0f}%")
            lines.append("  " + exhaust_text(x))
        if b.get("session"):
            lines.append("  " + session_text(b["session"], f.get("session") or {}))
        if b.get("waits_flagged"):
            lines.append(f"  waits open now (not modelled): {', '.join(b['waits_flagged'])}")
        if b.get("waits_expected"):
            lines.append(f"  waits the estimator expects (not modelled): {len(b['waits_expected'])} task(s)")
        if b.get("unestimated"):
            lines.append(f"  {b['unestimated']} task(s) without an estimate took the median")
        if b.get("unreached"):
            lines.append("  left out: " + "; ".join(f"{t} ({w})" for t, w in b["unreached"].items()))
    if a and not a.get("unavailable"):
        fit = a.get("fit") or {}
        lines += ["", f"Allowance: {a['pct_now']:.0f}% now (sample {a['pct_sample']:.0f}% at {_when(a['sample_at'])}, "
                      f"+{a['added_since_sample']:.1f}% since), resets {_when(a['resets_at'])}"]
        for lv, c in (a.get("crossings") or {}).items():
            lines.append(f"  {float(lv):.0f}% crossed: P50 {_when(c['p50']) if c['p50'] else 'not before the reset'}, "
                         f"P90 (early) {_when(c['p90_early']) if c['p90_early'] else 'not before the reset'} "
                         f"({c['share']:.0%} of trials cross before the reset)")
        lines.append(f"  fit: {fit.get('chosen')} ({fit.get('per_unit_text')}), leave-one-out error "
                     f"{fit.get('loo_rmse')} pp per interval (mean interval {fit.get('mean_interval_h')} h, mean rise "
                     f"{fit.get('mean_delta')} pp, n {fit.get('n')}); non-plane burn {fit.get('baseline_pct_per_h')}%/h"
                     + (f" (over {fit.get('baseline_hours')} h of history, averaged as {BASELINE_MIN_SPAN_H} h)"
                        if fit.get("baseline_floored") and fit.get("baseline_pct_per_h") is not None else ""))
        lines.append("  models: " + ", ".join(f"{k} {v['loo_rmse']}" for k, v in (fit.get("models") or {}).items()))
    s5 = f.get("session") or {}
    if s5.get("modelled"):
        lines.append(f"  5-hour window: {s5['pct_now']:.0f}% now, ends {_when(s5['window_end'])}; work pauses at "
                     f"{s5['park_pct']:g}% until the end + {s5['margin_s']} s (r5 {_r5(s5['r5'])} 5-hour % per weekly %, "
                     f"n {s5['n']})" + ("" if s5.get("window_basis", "").startswith("the latest") else
                                        f"; {s5.get('window_basis')}"))
    elif s5.get("note") and s5.get("park_pct") is not None and a and not a.get("unavailable"):
        lines.append(f"  5-hour window not modelled: {s5['note']}")
    elif a:
        lines += ["", f"Allowance projection unavailable: {(a.get('fit') or {}).get('note') or (a.get('fit') or {}).get('error') or 'no fit'}"]
    tp = f.get("throughput") or {}
    lines += ["", f"Throughput: {tp.get('text')}; median gap {tp.get('median_gap_s')} s, overlap in "
                  f"{tp.get('overlap_share')} of pairs, {tp.get('stops')} stop(s) left out",
              f"Estimates: {f.get('sources')}, {f.get('calibrated_tasks', 0)} calibrated (phase D); rho "
              f"{(f.get('rho') or {}).get('value')} ({'fitted' if (f.get('rho') or {}).get('fitted') else 'default'}); "
              f"built in {f.get('ms')} ms"]
    return "\n".join(lines)


def run(cfg: Config, q: Path, point: str | None = None) -> dict[str, Any]:
    """`ccp forecast`: the same as the board's, with the drill-down measured now."""
    from ccp import board, drill, health, usage  # noqa: PLC0415
    from ccp.queue import durable_statuses  # noqa: PLC0415
    try:
        rows = health.collect(cfg, q, files=False)["tasks"]
        report = usage.fold(q, None, (cfg.telemetry or {}).get("design_seat"))
        d = drill.collect(q, rows, report)
    except Exception:  # noqa: BLE001  (no history: back-to-back throughput)
        d = {}
    return collect(cfg, q, drill=d, open_items=board._open_items(q, durable_statuses(cfg)),
                   allowance=usage.status(cfg, q, sample=False), point=point)
