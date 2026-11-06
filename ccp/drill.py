"""The board's per-task drill-down (SPEC §28.3): where one task's wall time went.

  ccp board task <id>    the same breakdown in the terminal (reads, never writes)

For each run of the task (implement, review, fix, verify), its window is split four ways:

- **model:** the union of its `claude_code.llm_request` intervals (span start to end; a request
  with no span: its `at` less `duration_ms`). Requests may overlap, so this is a union, not a sum.
- **suite:** the union of its recorded `ccp suite run` intervals, less the model time: the tests
  ran and no request was in flight. A suite that ran while the model worked counts as model time;
  `suite_all_s` keeps the whole suite union.
- **other tools / idle:** what is left is gaps with neither a request in flight nor a recorded suite.
  The telemetry keeps no tool spans (the receiver folds only `llm_request` spans, §24), so the
  gaps are told apart by length: a gap shorter than IDLE_GAP_S is other tools (file reads, edits,
  git, a command not run through `ccp suite`); one of IDLE_GAP_S or more is idle, since no single
  foreground tool call runs that long (Claude Code's Bash timeout is at most 10 minutes). A run
  with no telemetry at all has no model, other or idle time: its time outside suites is
  `unknown_s`.

A run's window is its agent's start (`started_at`, else `opened_at`) to the later of its last stop
and its report (else its abandonment; a live run: now), clipped to its task's window. A run still
open on a merged task ends at the merge (`stale_run`). A live run is measured to its latest
evidence; the stretch after it is `live_s`, never idle (unless the receiver is shown fresh). Where
runs overlap, the task's split counts each instant once (PRIORITY) and reports `overlap_s`. A
stretch before telemetry first reached the queue is unknown, never idle. The task's own window is the one
`ccp health` gives its wall time (first recorded event to the merge; an open task: to now). Time
in it outside every run is **runner** time: launching the next run, reading reports, merging,
waiting. Waits (`waiting_on` set to clear, from the ledger), the queue wait (the last dependency's
merge to the claim), suite runs, rounds, verdicts, tokens and cost per run, and the task's friction
notes are listed beside it. A task from before run records (2026-10-21) shows its phases from the
prompt stamps and report file times, and its reports' `Suite:` lines.

Reads only what the plane records; writes nothing and runs no product command.
"""
from __future__ import annotations

from ccp.queue import events_path as _events_path
from ccp.queue import lib as _lib

import re
import time
from pathlib import Path
from typing import Any

from ccp import health, runs, suite
from ccp.queue import read_json

IDLE_GAP_S = 600       # a gap this long with nothing in flight is idle, not a tool call
MAX_SEGMENTS = 200     # per run, after coarsening
LIMIT_MERGED = 30      # drill records for the last this many merged tasks, plus the open ones
MAX_SUITES = 60        # suite runs listed per run
MAX_NOTES = 20         # friction notes per task
TEXT = 240             # a note's text is cut to this many characters
KINDS = {"m": "model", "s": "suite", "o": "other tools", "i": "idle", "u": "unknown", "l": "live, no telemetry yet"}
# Per instant, where runs overlap, the first of these wins in the task's split (each counted once).
PRIORITY = (("m", "model_s"), ("s", "suite_s"), ("o", "other_s"), ("i", "idle_s"), ("u", "unknown_s"), ("l", "live_s"))
NO_RUNS = "no run telemetry (before 2026-10-21)"
OPEN_STATES = ("pending", "done", "dropped")  # a queue status not in these is a task in flight


# ------------------------------------------------------------------------------------ intervals

Iv = list[tuple[float, float]]


def union(iv: Iv) -> Iv:
    """Overlapping or touching intervals merged, sorted; empty and reversed ones dropped."""
    out: list[list[float]] = []
    for a, b in sorted((a, b) for a, b in iv if b > a):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def clip(iv: Iv, lo: float, hi: float) -> Iv:
    return [(max(a, lo), min(b, hi)) for a, b in iv if min(b, hi) > max(a, lo)]


def subtract(a: Iv, b: Iv) -> Iv:
    """a less b; both unions."""
    out = []
    j = 0
    for s, e in a:
        cur = s
        while j < len(b) and b[j][1] <= cur:
            j += 1
        k = j
        while k < len(b) and b[k][0] < e:
            if b[k][0] > cur:
                out.append((cur, b[k][0]))
            cur = max(cur, b[k][1])
            k += 1
        if cur < e:
            out.append((cur, e))
    return out


def length(iv: Iv) -> float:
    return sum(b - a for a, b in iv)


def partition(lo: float, hi: float, model: Iv, suites: Iv, telemetry: bool = True,
              idle_gap: float = IDLE_GAP_S, measured_from: float | None = None) -> dict[str, Any]:
    """A run window split into model, suite (not under model), other tools and idle (module doc).
    Without telemetry: suite and unknown. A gap before `measured_from` (when telemetry began to
    reach this queue) is unknown, never idle. Returns the totals and the segments, oldest first."""
    m = union(clip(model, lo, hi)) if telemetry else []
    s_all = union(clip(suites, lo, hi))
    s = subtract(s_all, m)
    gaps = subtract([(lo, hi)] if hi > lo else [], union(m + s_all))
    segs = [(a, b, "m") for a, b in m] + [(a, b, "s") for a, b in s]
    for a, b in gaps:
        if not telemetry:
            segs.append((a, b, "u"))
            continue
        if measured_from is not None and a < measured_from:
            cut = min(b, measured_from)
            segs.append((a, cut, "u"))
            a = cut
            if a >= b:
                continue
        segs.append((a, b, "i" if b - a >= idle_gap else "o"))
    segs.sort()
    tot = {k: 0.0 for k in KINDS}
    for a, b, k in segs:
        tot[k] += b - a
    return {"wall_s": round(max(0.0, hi - lo), 1), "model_s": round(tot["m"], 1) if telemetry else None,
            "suite_s": round(tot["s"], 1), "suite_all_s": round(length(s_all), 1),
            "other_s": round(tot["o"], 1) if telemetry else None, "idle_s": round(tot["i"], 1) if telemetry else None,
            "unknown_s": round(tot["u"], 1), "segments": segs}


def _f(v: Any) -> float | None:
    """A finite number, else None (as `suite._acc` guards seconds)."""
    import math  # noqa: PLC0415
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def coarsen(segs: list[tuple[float, float, str]], lo: float, hi: float,
            limit: int = MAX_SEGMENTS) -> tuple[list[tuple[float, float, str]], bool]:
    """At most `limit` segments: same-kind neighbours joined, and past that the window cut into
    `limit` equal bins, each labelled by the kind that fills most of it. Totals are not taken from
    these (they come from the exact intervals)."""
    joined: list[list[Any]] = []
    for a, b, k in segs:
        if joined and joined[-1][2] == k and a - joined[-1][1] < 1e-6:
            joined[-1][1] = b
        else:
            joined.append([a, b, k])
    if len(joined) <= limit or hi <= lo:
        return [(a, b, k) for a, b, k in joined], False
    w = (hi - lo) / limit
    out: list[list[Any]] = []
    j = 0
    for i in range(limit):
        b0, b1 = lo + i * w, lo + (i + 1) * w
        share: dict[str, float] = {}
        while j < len(joined) and joined[j][1] <= b0:
            j += 1
        k = j
        while k < len(joined) and joined[k][0] < b1:
            share[joined[k][2]] = share.get(joined[k][2], 0.0) + min(b1, joined[k][1]) - max(b0, joined[k][0])
            k += 1
        if not share:
            continue
        kind = max(share, key=lambda x: (share[x], x == "m"))
        if out and out[-1][2] == kind and abs(out[-1][1] - b0) < 1e-6:
            out[-1][1] = b1
        else:
            out.append([b0, b1, kind])
    return [(a, b, k) for a, b, k in out], True


def _num(x: float) -> str:
    v = round(x, 1)
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def encode(segs: list[tuple[float, float, str]], origin: float) -> str:
    """`<kind><start>+<seconds>` tokens, space-separated, start from `origin`: compact in board.json."""
    return " ".join(f"{k}{_num(a - origin)}+{_num(b - a)}" for a, b, k in segs if b > a)


SEG_RE = re.compile(r"^([msoiul])(\d+(?:\.\d+)?)\+(\d+(?:\.\d+)?)$")


def decode(s: str) -> list[tuple[float, float, str]]:
    out = []
    for tok in str(s or "").split():
        m = SEG_RE.match(tok)
        if m:
            a = float(m.group(2))
            out.append((a, a + float(m.group(3)), m.group(1)))
    return out


# ------------------------------------------------------------------------------------ sources

def _ep(at: Any) -> float | None:
    return health._epoch(str(at)) if at else None


def _iso(e: float | None) -> str | None:
    return health._ts(e) if e is not None else None


def _cut(s: Any, n: int = TEXT) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def run_window(r: dict[str, Any], now: float) -> tuple[float | None, float | None]:
    start = _ep(r.get("started_at")) or _ep(r.get("opened_at"))
    ends = [e for e in (_ep(r.get("stopped_at")), _ep(r.get("reported_at"))) if e is not None]
    end = max(ends) if ends else _ep(r.get("abandoned_at"))
    if end is None and runs.state(r) in ("running", "pending") and r.get("started_at"):
        end = now
    if start is None or end is None or end < start:
        return start, None
    return start, end


def _events(q: Path) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for e in health._jsonl(_events_path(q)):
        if e.get("task_id") and e.get("type") in ("waiting_on", "lease", "phase", "review", "verify", "question"):
            by.setdefault(str(e["task_id"]), []).append(e)
    return by


def _waits(evs: list[dict[str, Any]], lo: float | None, hi: float) -> list[dict[str, Any]]:
    """waiting_on set → clear, by what it waited on; one still set runs to `hi`."""
    out = []
    cur: dict[str, Any] | None = None
    for e in sorted((e for e in evs if e.get("type") == "waiting_on"), key=lambda e: str(e.get("at"))):
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        at = _ep(e.get("at"))
        if at is None:
            continue
        if e.get("op") == "set":
            if cur:
                cur["end"] = at
                out.append(cur)
            cur = {"on": _cut(p.get("waiting_on") or p.get("reason") or "?", 80), "start": at,
                   "detail": _cut(p.get("detail"), 60) or None}
        elif e.get("op") == "clear" and cur:
            cur["end"] = at
            cur["cleared"] = _cut(p.get("reason"), 80) or None
            out.append(cur)
            cur = None
    if cur:
        cur["end"] = hi
        cur["open"] = True
        out.append(cur)
    return [w for w in out if lo is None or w["end"] >= lo]


def _report_suites(q: Path, tid: str) -> list[dict[str, Any]]:
    from ccp.report import SUITE_RE, cache_counts  # noqa: PLC0415
    out = []
    d = q / "progress" / tid
    files = []
    for f in d.glob("*-report.md") if d.is_dir() else []:
        try:
            files.append((f.stat().st_mtime, f))
        except OSError:
            continue
    for _, f in sorted(files):  # the order the phases reported in
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        m = SUITE_RE.search(text)
        if m:
            row: dict[str, Any] = {"report": f.name[: -len("-report.md")][:40], "tests": int(m.group(1)), "s": float(m.group(2))}
            c = cache_counts(text[m.start():].split("\n", 1)[0])
            if c:  # a warm run: the units that ran and those the product's cache had (§15.3)
                row.update(ran=c[0], cached=c[1])
            out.append(row)
    return out


def _old_phases(q: Path, tid: str, lo: float | None, hi: float | None) -> list[dict[str, Any]]:
    """Before run records: each phase ends at its report file's time and starts at its prompt
    stamp, else at the previous phase's end (else the task's start). Approximate."""
    ends = []
    d = q / "progress" / tid
    for f in d.glob("*-report.md") if d.is_dir() else []:
        try:
            ends.append((f.stat().st_mtime, f.name[: -len("-report.md")]))
        except OSError:
            continue
    stamps: dict[str, list[float]] = {}
    pd = q / "prompts" / tid
    for f in pd.rglob("*.json") if pd.is_dir() else []:
        m = health.STAMP_RE.match(f.name)
        if m and (e := health._epoch(m.group(1))) is not None:
            stamps.setdefault(health._phase(m.group(2)), []).append(e)
    out = []
    prev = lo
    for end, name in sorted(ends):
        ph = health._phase(name)
        mine = [s for s in stamps.get(ph, []) if s <= end and (prev is None or s >= prev - 1)]
        start = min(mine) if mine else prev
        if start is None or end < start:
            prev = end
            continue
        out.append({"phase": name[:40], "start": start, "end": min(end, hi) if hi else end})
        prev = end
    return out


# ------------------------------------------------------------------------------------ records

def _run_record(r: dict[str, Any], fold_row: dict[str, Any] | None, model: Iv, suites: list[dict[str, Any]],
                verdict: str | None, now: float, telemetry_since: float | None, *, t_lo: float | None = None,
                t_hi: float | None = None, closed: bool = False, latest_any: float | None = None) -> dict[str, Any]:
    """One run, its window clipped to its task's [t_lo, t_hi]. A run still open on a closed task
    ends at the task's end (`stale_run`). A live run is measured to its latest evidence (a request
    or suite end, or now while a suite is open); the stretch from there to now is `live_s`, unless
    the receiver is shown fresh (a newer request anywhere, IDLE_GAP_S or more later), when it is idle."""
    lo, hi = run_window(r, now)
    state = runs.state(r)
    stale = closed and state in ("running", "pending") and lo is not None and t_hi is not None and (hi is None or hi > t_hi)
    if stale:
        hi = t_hi
    if lo is not None and hi is not None:
        lo = max(lo, t_lo) if t_lo is not None else lo
        hi = min(hi, t_hi) if t_hi is not None else hi
        hi = max(hi, lo)
    u = (fold_row or {}).get("usage") or {}
    tok = {k: int(_f(u.get(k)) or 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")}
    s_iv: Iv = []
    rows = []
    suite_open = False
    for s in suites:
        a = _ep(s.get("started_at"))
        b = _ep(s.get("ended_at"))
        secs = _f(s.get("seconds"))
        if a is not None and b is None and secs is not None:
            b = a + secs
        if a is not None and b is None and s.get("state") == "open":
            b = now
            suite_open = True
        if a is not None and b is not None:
            s_iv.append((a, b))
        rows.append({"off": round(a - lo, 1) if a is not None and lo is not None else None,
                     "s": secs, "lane": s.get("lane"), "tests": s.get("tests"),
                     "exit": s.get("exit_code"), "state": s.get("state")})
    lanes: dict[str, dict[str, Any]] = {}
    for x in rows:
        ln = lanes.setdefault(str(x["lane"] or "-"), {"n": 0, "s": 0.0})
        ln["n"] += 1
        ln["s"] = round(ln["s"] + (x["s"] or 0.0), 1)
    # Telemetry for this run: requests attributed to it, or (none) a run after the receiver began.
    has_tel = bool(model) or bool(u.get("requests"))
    rec: dict[str, Any] = {
        "run_id": r.get("run_id"), "phase": r.get("phase"), "round": r.get("round"), "seat": r.get("seat"),
        "state": state, "outcome": r.get("outcome"), "verdict": verdict, "stale_run": bool(stale),
        "abandoned_reason": r.get("abandoned_reason") if state == "abandoned" else None,
        "start_at": _iso(lo), "end_at": _iso(hi),
        "expected_model": r.get("expected_model"), "expected_effort": r.get("expected_effort"),
        "models": u.get("observed_models") or [], "efforts": u.get("observed_efforts") or [],
        "flags": (fold_row or {}).get("flags") or [], "requests": int(_f(u.get("requests")) or 0),
        "tokens": sum(tok.values()), "cost_usd": round(_f(u.get("cost_usd")) or 0.0, 4),
        "telemetry": has_tel,
        "suites": {"runs": len(rows), "killed": sum(1 for x in rows if x["state"] == "killed"),
                   "failed": sum(1 for x in rows if x["state"] == "failed"), "by_lane": lanes,
                   "list": rows[:MAX_SUITES], "more": max(0, len(rows) - MAX_SUITES)},
    }
    if lo is None or hi is None:
        rec.update(wall_s=None, model_s=None, suite_s=None, suite_all_s=None, other_s=None, idle_s=None,
                   unknown_s=None, live_s=0.0, segments="", coarsened=False, _segs=[])
        return rec
    mhi = hi
    if state == "running" and not closed and not stale:
        evidence = [b for _, b in model] + [b for _, b in s_iv]
        ev = hi if suite_open else (max(evidence) if evidence else lo)
        ev = min(max(ev, lo), hi)
        fresh = latest_any is not None and latest_any >= ev + IDLE_GAP_S
        if not fresh and ev < hi:
            mhi = ev
            rec["live_since"] = _iso(ev)
    p = partition(lo, mhi, model, s_iv, has_tel, measured_from=telemetry_since if has_tel else None)
    exact = p.pop("segments") + ([(mhi, hi, "l")] if mhi < hi else [])
    p["wall_s"] = round(hi - lo, 1)
    p["live_s"] = round(hi - mhi, 1)
    segs, coarse = coarsen(exact, lo, hi)
    rec.update(p, segments=encode(segs, lo), coarsened=coarse, _segs=exact)
    if not has_tel:
        rec["telemetry_note"] = ("no requests attributed to this run" if telemetry_since is not None and lo >= telemetry_since
                                 else "before telemetry reached this queue")
    elif telemetry_since is not None and lo < telemetry_since:
        rec["telemetry_note"] = "started before telemetry reached this queue: that stretch is unmeasured"
    return rec


def _task_state(q: Path, tid: str) -> dict[str, Any]:
    t = read_json(q / "tasks" / f"{tid}.json", {}) or {}
    return t if isinstance(t, dict) else {}


def record(q: Path, tid: str, row: dict[str, Any] | None, *, run_recs: list[dict[str, Any]],
           fold_rows: dict[str, dict[str, Any]], timeline: dict[str, Iv], suites_by_run: dict[str, list[dict[str, Any]]],
           suites_unbound: list[dict[str, Any]], events: list[dict[str, Any]], notes: list[dict[str, Any]],
           merged_at: dict[str, float], now: float, telemetry_since: float | None,
           latest_any: float | None = None) -> dict[str, Any]:
    """One task's drill record (module doc)."""
    st = _task_state(q, tid)
    end = _ep((row or {}).get("merged_at"))
    lo = end - row["wall_s"] if end is not None and (row or {}).get("wall_s") is not None else None
    claims = sorted(e for e in (_ep(x.get("at")) for x in health.after_release(events) if x.get("type") == "lease"
                                and x.get("op") == "set") if e is not None)
    if row is None:  # open: its claim (or first run) to now
        end = now
        starts = [x for x in [claims[0] if claims else None, _ep(st.get("claimed_at"))]
                  + [_ep(r.get("opened_at")) for r in run_recs] if x is not None]
        lo = min(starts) if starts else None
    verdicts = {}
    for e in events:
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if e.get("type") in ("review", "verify") and e.get("op") == "recorded" and p.get("run_id"):
            verdicts[str(p["run_id"])] = _cut(p.get("verdict"), 24) or None
    hi = end if end is not None else now
    rr = [_run_record(r, fold_rows.get(r["run_id"]), timeline.get(r["run_id"], []), suites_by_run.get(r["run_id"], []),
                      verdicts.get(r["run_id"]), now, telemetry_since, t_lo=lo, t_hi=hi, closed=row is not None,
                      latest_any=latest_any) for r in run_recs]
    origin = lo if lo is not None else min([_ep(x["start_at"]) for x in rr if x["start_at"]] or [now])
    for x in rr:
        x["off"] = round(_ep(x["start_at"]) - origin, 1) if x["start_at"] else None
    # The task's split: each instant once, the first kind in PRIORITY winning where runs overlap.
    split = {k: 0.0 for _, k in PRIORITY} | {"runner_s": 0.0}
    claimed: Iv = []
    for kind, key in PRIORITY:
        iv = union([(a, b) for x in rr for a, b, k in x["_segs"] if k == kind])
        if lo is not None:
            iv = clip(iv, lo, hi)
        mine = subtract(iv, union(claimed))
        split[key] = length(mine)
        claimed = union(claimed + mine)
    windows = [(_ep(x["start_at"]), _ep(x["end_at"])) for x in rr if x["wall_s"] is not None]
    overlap = sum(b - a for a, b in windows) - length(union(windows))
    for x in rr:
        x.pop("_segs", None)
    wall = round(hi - lo, 1) if lo is not None and hi >= lo else (row or {}).get("wall_s")
    phases = []
    if lo is not None:
        split["runner_s"] = length(subtract([(lo, hi)], claimed)) if rr else 0.0
        if not rr:
            split["unknown_s"] = hi - lo
    reported = _report_suites(q, tid)
    if not rr:
        by_report = {x["report"]: x["s"] for x in reported}
        phases = [{"phase": p["phase"], "off": round(p["start"] - origin, 1), "s": round(p["end"] - p["start"], 1),
                   "suite_s": by_report.get(p["phase"])} for p in _old_phases(q, tid, lo, hi)]
    waits = [{"on": w["on"], "detail": w.get("detail"), "cleared": w.get("cleared"), "open": bool(w.get("open")),
              "off": round(max(0.0, w["start"] - origin), 1), "s": round(w["end"] - max(w["start"], origin), 1)}
             for w in _waits(events, lo, hi) if w["end"] >= origin]
    deps = st.get("depends_on")
    deps = [str(d) for d in deps if isinstance(d, str)] if isinstance(deps, list) else []
    ready = [merged_at[d] for d in deps if d in merged_at]
    claim = claims[0] if claims else _ep(st.get("claimed_at"))
    deps_known = bool(deps) and len(ready) == len(deps)
    queue_wait = round(claim - max(ready), 1) if deps_known and claim is not None and claim >= max(ready) else None
    tn = [n for n in notes if n.get("task_id") == tid][-MAX_NOTES:]
    return {
        "task_id": tid, "open": row is None, "status": st.get("status") or ("done" if row else None),
        "merged_at": (row or {}).get("merged_at"), "start_at": _iso(lo), "end_at": _iso(hi), "wall_s": wall,
        "telemetry": "runs" if any(x["telemetry"] for x in rr) else ("runs-no-telemetry" if rr else "none"),
        "note": None if rr else NO_RUNS,
        "split": {k: round(v, 1) for k, v in split.items()}, "overlap_s": round(overlap, 1),
        "runs": rr, "phases": phases,
        "rounds": {"review": (row or {}).get("review_rounds", sum(1 for r in run_recs if r.get("phase") == "review")),
                   "verify": (row or {}).get("verify_rounds", sum(1 for r in run_recs if r.get("phase") == "verify")),
                   "fix": (row or {}).get("fix_rounds", sum(1 for r in run_recs if r.get("phase") == "fix"))},
        "phase_s": {k: (row or {}).get(k) for k in ("implementing_s", "reviewing_s", "verifying_s")},
        "times": (row or {}).get("times"),
        "waits": waits, "waits_s": round(sum(w["s"] for w in waits), 1),
        "queue_wait_s": queue_wait, "ready_at": _iso(max(ready)) if deps_known else None, "claimed_at": _iso(claim),
        "suites_unbound": len(suites_unbound),
        "reported_suites": reported, "reported_suite_s": round(sum(x["s"] for x in reported), 1),
        "tokens": sum(x["tokens"] for x in rr), "cost_usd": round(sum(x["cost_usd"] for x in rr), 4),
        "friction": [{"at": n.get("at"), "by": _cut(n.get("by"), 40) or None, "text": _cut(n.get("text"))} for n in tn],
        "friction_total": sum(1 for n in notes if n.get("task_id") == tid),
    }


def collect(q: Path, rows: list[dict[str, Any]], report: dict[str, Any], *, only: str | None = None,
            limit: int = LIMIT_MERGED, now: float | None = None) -> dict[str, dict[str, Any]]:
    """Drill records for the last `limit` merged tasks (`rows`, `ccp health`'s, oldest first) and
    every task in flight, or for `only`."""
    now = time.time() if now is None else now
    merged = {r["task_id"]: r for r in rows}
    merged_at = {t: e for t, r in merged.items() if (e := _ep(r.get("merged_at"))) is not None}
    all_runs = runs.all_runs(q)
    by_task: dict[str, list[dict[str, Any]]] = {}
    for r in all_runs:
        by_task.setdefault(str(r.get("task_id")), []).append(r)
    if only is not None:
        ids = [only]
    else:
        ids = [r["task_id"] for r in rows][-limit:]
        for f in sorted((q / "tasks").glob("*.json")) if (q / "tasks").is_dir() else []:
            st = _task_state(q, f.stem)
            if st.get("status") and st["status"] not in OPEN_STATES and f.stem not in merged and f.stem not in ids:
                ids.append(f.stem)
    try:
        suites = suite.fold(q, now)
    except Exception:  # noqa: BLE001  (a damaged suites file: no suite time, as safe_totals)
        suites = []
    s_run: dict[str, list[dict[str, Any]]] = {}
    s_unbound: dict[str, list[dict[str, Any]]] = {}
    for s in suites:
        if s.get("run_id"):
            s_run.setdefault(str(s["run_id"]), []).append(s)
        elif s.get("task_id"):
            s_unbound.setdefault(str(s["task_id"]), []).append(s)
    fold_rows = {r["run_id"]: r for r in report.get("runs") or []}
    timeline = report.get("timeline") or {}
    starts = [a for iv in timeline.values() for a, _ in iv]
    tel_since = min(starts) if starts else None
    evs = _events(q)
    notes = health.notes(q)
    # The newest request the receiver delivered anywhere: proof it is fresh (a live run's tail).
    seen = [b for iv in timeline.values() for _, b in iv]
    seats = (report.get("recent") or {}).get("seats") if isinstance(report.get("recent"), dict) else None
    for v in (seats.values() if isinstance(seats, dict) else ()):
        seen += [e for x in (v if isinstance(v, list) else ()) if isinstance(x, dict) and (e := _ep(x.get("at"))) is not None]
    latest_any = max(seen) if seen else None
    out: dict[str, dict[str, Any]] = {}
    for tid in ids:
        try:  # one bad record costs that task's drill-down, never the others'
            out[tid] = record(q, tid, merged.get(tid), run_recs=by_task.get(tid, []), fold_rows=fold_rows,
                              timeline=timeline, suites_by_run=s_run, suites_unbound=s_unbound.get(tid, []),
                              events=evs.get(tid, []), notes=notes, merged_at=merged_at, now=now,
                              telemetry_since=tel_since, latest_any=latest_any)
        except Exception as exc:  # noqa: BLE001
            out[tid] = {"task_id": tid, "_error": f"{type(exc).__name__}: {exc}"[:200]}
    return out


# ------------------------------------------------------------------------------------ terminal

def _d(s: float | None) -> str:
    if s is None:
        return "-"
    s = float(s)
    return f"{s / 3600:.1f}h" if s >= 3600 else f"{s / 60:.0f}m" if s >= 60 else f"{s:.0f}s"


def text(d: dict[str, Any]) -> str:
    if d.get("_error"):
        return f"{d.get('task_id')}: the drill-down failed to build: {d['_error']}"
    sp = d["split"]
    lines = [f"{d['task_id']}  {'open, ' + str(d.get('status') or '?') if d['open'] else 'merged ' + str(d.get('merged_at'))}"
             f"  wall {_d(d['wall_s'])}  ({d['start_at'] or '?'} to {d['end_at'] or '?'})"]
    if d.get("note"):
        lines.append(d["note"])
    lines.append("split: " + ", ".join(f"{name} {_d(sp.get(k))}" for k, name in (
        ("model_s", "model"), ("suite_s", "suite"), ("other_s", "other tools"), ("idle_s", "idle"),
        ("unknown_s", "unknown"), ("live_s", "live, no telemetry yet"), ("runner_s", "runner (between runs)")) if sp.get(k)))
    if d.get("overlap_s"):
        lines.append(f"runs overlapped for {_d(d['overlap_s'])}: each instant counted once (model, suite, other, idle)")
    r = d["rounds"]
    lines.append(f"rounds: review {r['review']}, verify {r['verify']}, fix {r['fix']}"
                 + (f"; queue wait {_d(d['queue_wait_s'])} (ready {d['ready_at']}, claimed {d['claimed_at']})"
                    if d.get("queue_wait_s") is not None else ""))
    if d["runs"]:
        lines.append(f"{'RUN':<14} {'START':>6} {'WALL':>6} {'MODEL':>6} {'SUITE':>6} {'OTHER':>6} {'IDLE':>6} "
                     f"{'SUITES':>7} {'TOKENS':>7} {'COST$':>6}  MODEL / EFFORT")
        for x in d["runs"]:
            name = str(x["run_id"]).split("/", 1)[-1]
            su = x["suites"]
            tag = f"{su['runs']}" + (f" {su['killed']}k" if su["killed"] else "") + (f" {su['failed']}f" if su["failed"] else "")
            lines.append(f"{name:<14} {_d(x['off']):>6} {_d(x['wall_s']):>6} {_d(x['model_s']):>6} {_d(x['suite_s']):>6} "
                         f"{_d(x['other_s']):>6} {_d(x['idle_s']):>6} {tag:>7} {x['tokens'] // 1000:>6}k {x['cost_usd']:>6.2f}  "
                         f"{','.join(x['models']) or x['expected_model'] or '-'} / {','.join(x['efforts']) or x['expected_effort'] or '-'}"
                         + (f"  {x['verdict']}" if x.get("verdict") else "")
                         + (f"  ({x['telemetry_note']})" if x.get("telemetry_note") else "")
                         + (f"  live, no telemetry since {str(x['live_since'])[11:16]} ({_d(x['live_s'])})" if x.get("live_since") else "")
                         + ("  stale: still open after its task closed" if x.get("stale_run") else "")
                         + (f"  abandoned: {x['abandoned_reason'] or 'no reason recorded'}" if x.get("state") == "abandoned" else "")
                         + (f"  ! {'; '.join(x['flags'])}" if x["flags"] else ""))
            for lane, v in sorted(su["by_lane"].items()):
                lines.append(f"  suite {lane}: {v['n']} run(s), {_d(v['s'])}")
    for p in d["phases"]:
        lines.append(f"phase {p['phase']}: from +{_d(p['off'])}, {_d(p['s'])} (prompt stamp to report file time)"
                     + (f"; its Suite: line {p['suite_s']:g} s" if p.get("suite_s") is not None else ""))
    for w in d["waits"]:
        lines.append(f"wait on {w['on']}: +{_d(w['off'])}, {_d(w['s'])}" + (" (still waiting)" if w["open"] else "")
                     + (f", {w['detail']}" if w.get("detail") else ""))
    for s in d["reported_suites"]:
        lines.append(f"report {s['report']}: Suite {s['tests']} tests, {s['s']:g} s"
                     + (f", modules {s['ran']} ran, {s['cached']} cached" if "cached" in s else ""))
    if d.get("suites_unbound"):
        lines.append(f"{d['suites_unbound']} suite run(s) recorded against the task but no run")
    for n in d["friction"]:
        lines.append(f"friction {str(n.get('at') or '')[:16]} {n.get('by') or '-'}: {n['text']}")
    lines.append(f"model: requests in flight; suite: recorded tests with no request in flight; other tools: shorter "
                 f"gaps; idle: gaps of {IDLE_GAP_S // 60} min or more (no tool spans in the telemetry)")
    return "\n".join(lines)
