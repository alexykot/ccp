"""Usage, model and effort per run (SPEC §24.5, docs/design/telemetry.md), and the allowance (§25.1).

The join, from the spike (docs/design/telemetry.md):

- a span whose `agent_id` is a bound run's `agent_id` → that worker run;
- a span `agent_id` of `<name>@session-…` → that teammate (`runner.name`, or a name a rotation bound, → the runner seat);
- a request with no `agent_id`, from the main thread → the lead (the design seat);
- a request with no span (no traces) and `query_source: agent:*` → the one run open at that time
  whose model and effort match, else unattributed.

The fold reads `board/usage-requests.jsonl` and `board/usage-spans.jsonl` (written by
`ccp otel serve`) and the run records. It writes nothing but returns per-run, per-seat and
coverage figures, and flags a run whose observed model or effort differs from what its
definition pins. It also keeps each run's and seat's latest requests (`recent`: time, model,
effort, query source, session, tokens), from which the board's live seats read the model and effort now in use,
and each run's request intervals (`timeline`: when a request was in flight), from which the board's
drill-down takes model time (ccp/drill.py). Headless runs (architect passes, triage) are recorded from `claude -p`'s own
`modelUsage` in `board/headless-usage.jsonl`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccp import runs
from ccp.config import Config
from ccp.queue import QueueError, emit, iso, runner_names

TOKENS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")
# The cache writes by lifetime: parts of cache_creation_tokens, so never added to a total. 0 on rows
# received before the receiver kept them (§24.2, §2 cache lifetime).
TTL_SPLIT = ("cache_creation_5m_tokens", "cache_creation_1h_tokens")
RECENT = 200  # the latest requests kept per run and per seat, for the board's live seats (§28.3)


def _jsonl(p: Path) -> list[dict[str, Any]]:
    out = []
    for line in p.read_text().splitlines() if p.is_file() else []:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _t(s: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _blank() -> dict[str, Any]:
    return {**{k: 0 for k in TOKENS + TTL_SPLIT}, "cost_usd": 0.0, "requests": 0, "models": set(), "efforts": set()}


def _n(v: Any) -> float:
    import math  # noqa: PLC0415
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0


def _add(acc: dict[str, Any], req: dict[str, Any]) -> None:
    for k in TOKENS + TTL_SPLIT:
        acc[k] += int(_n(req.get(k)))
    acc["cost_usd"] += _n(req.get("cost_usd"))
    acc["requests"] += 1
    if req.get("model"):
        acc["models"].add(req["model"])
    if req.get("effort"):
        acc["efforts"].add(req["effort"])


def _out(acc: dict[str, Any]) -> dict[str, Any]:
    return {**{k: acc[k] for k in TOKENS + TTL_SPLIT}, "cost_usd": round(acc["cost_usd"], 4), "requests": acc["requests"],
            "observed_models": sorted(acc["models"]), "observed_efforts": sorted(acc["efforts"])}


def _places(q: Path) -> tuple[str | None, set[str]]:
    """Real paths of the product root and of the team runners' checkouts, from the queue's binding (§24):
    `runner.worktree`, and with several runners (§16.4) each slot's own (`-<slot>`, or as recorded)."""
    import os  # noqa: PLC0415
    import re  # noqa: PLC0415
    from ccp.queue import binding_text  # noqa: PLC0415
    text = binding_text(q) + "\n"
    root = re.search(r"^product_root:\s*([^#\n]+)", text, re.M)
    wt = re.search(r"^runner:\s*\n(?:[ \t]+.*\n)*?[ \t]+worktree:\s*([^#\n]+)", text, re.M)
    real = lambda m: os.path.realpath(m.group(1).strip().strip("'\"")) if m else None  # noqa: E731
    prod = root.group(1).strip().strip("'\"") if root else None
    # a relative runner.worktree is the product root's, as `ccp tasks worktree` reads it (§16.5)
    at = lambda p: os.path.realpath(p if os.path.isabs(p) or not prod else os.path.join(prod, p))  # noqa: E731
    wts = {at(wt.group(1).strip().strip("'\""))} if wt else set()
    try:
        from ccp.queue import load_work, runner_slots  # noqa: PLC0415
        base = wt.group(1).strip().strip("'\"") if wt else None
        for slot, rec in runner_slots(load_work(q)).items():
            for p in (rec.get("worktree"), f"{base}-{slot}" if base else None):
                if p:
                    wts.add(at(str(p)))
    except Exception:  # noqa: BLE001  (an unreadable work.json: the binding's one checkout)
        pass
    return real(root), wts


UNTAGGED = "headless-untagged"


def _main_seat(row: dict[str, Any], root: str | None, runner_wts: set[str]) -> str:
    """A call with no agent_id, by the cwd of its session (§24): the product root is the lead's (the
    design seat), the runner's checkout the runner's, anything else (a worker or scratch worktree, an
    ad hoc session) `other-sessions`. A row with no cwd, or a binding with no product_root, is the lead's,
    except a `claude -p` call (`query_source: sdk`) with no cwd: it reached here untagged and unmatched
    to a headless session (a pass launched before §24's tag), so it is `headless-untagged`, kept
    out of the design seat and its advice. A `claude -p` call from a runner's checkout is
    `headless-untagged` too: the runner teammate's own calls carry `<name>@session-…` and are never
    `sdk`, so a headless session run from that checkout is not the runner (§2.4: the runner seat's
    model is its definition's)."""
    import os  # noqa: PLC0415
    cwd = row.get("cwd")
    sdk = row.get("query_source") == "sdk"
    if not cwd and sdk:
        return UNTAGGED
    if not cwd or not root:
        return "design-seat"
    real = os.path.realpath(str(cwd))
    if real in runner_wts:
        return UNTAGGED if sdk else "runner"
    return "design-seat" if real == root else "other-sessions"


def fold(q: Path, task_id: str | None = None, design_seat: dict[str, str] | None = None) -> dict[str, Any]:
    # An exporter retries after a timeout: one request is one row, the last one received.
    reqs = list({r.get("request_id") or f"_{i}": r
                 for i, r in enumerate(_jsonl(q / "board" / "usage-requests.jsonl"))}.values())
    spans = {s.get("request_id"): s for s in _jsonl(q / "board" / "usage-spans.jsonl") if s.get("request_id")}
    all_runs = runs.all_runs(q)
    by_agent = {r["agent_id"]: r for r in all_runs if r.get("agent_id")}
    rnames = runner_names(q)
    root, runner_wts = _places(q)
    headless = _jsonl(q / "board" / "headless-usage.jsonl")
    # §24: a plane-launched `claude -p` session, and its subagents, is its kind's seat.
    headless_sessions = {h["session_id"]: str(h.get("kind") or "headless") for h in headless if h.get("session_id")}
    others: dict[str, int] = {}  # cwd → tokens of `other-sessions`
    per_run: dict[str, dict[str, Any]] = {}
    seats: dict[str, dict[str, Any]] = {}
    unattributed = _blank()
    stray: dict[str, int] = {}  # agent ids behind unattributed tokens: a worker launched without a run
    daily: dict[str, dict[str, int]] = {}  # date → seat → tokens, for the board's per-day chart
    how = {"headless": 0, "untagged": 0, "span": 0, "teammate": 0, "lead": 0, "session": 0, "window": 0, "nospan": 0,
           "none": 0}
    traced = bool(spans)
    total = _blank()
    recent: dict[str, dict[str, list[dict[str, Any]]]] = {"runs": {}, "seats": {}}  # the board's live seats (§28.3)
    timeline: dict[str, list[tuple[float, float]]] = {}  # run → its requests' (start, end), for the drill-down
    for req in reqs:
        _add(total, req)
        span = spans.get(req.get("request_id")) or {}
        aid = str(span.get("agent_id") or "")
        run = None
        seat = None
        tagged = req.get("seat") or span.get("seat") or headless_sessions.get(str(req.get("session_id") or ""))
        if tagged:
            seat, how_key = str(tagged), "headless"
        elif aid and aid in by_agent:
            run, how_key = by_agent[aid], "span"
        elif "@session-" in aid:
            name = aid.split("@", 1)[0]
            seat, how_key = ("runner" if name in rnames else f"teammate:{name}"), "teammate"
        elif span and not aid:
            seat = _main_seat(req, root, runner_wts)
            how_key = "lead" if seat == "design-seat" else "untagged" if seat == UNTAGGED else "session"
        elif not span and str(req.get("query_source") or "").startswith("agent:"):
            run, how_key = _window(all_runs, req), "window"
            if run is None:
                how_key = "none"
        elif not span and not traced:
            seat = _main_seat(req, root, runner_wts)  # no traces at all: a main-thread call, placed by its cwd
            how_key = "lead" if seat == "design-seat" else "untagged" if seat == UNTAGGED else "session"
        elif not span:
            how_key = "nospan"  # traces exist but this call has none (lost or late): not counted as attributed
        else:
            how_key = "none"
        how[how_key] += 1
        bucket = (run.get("seat") or "worker") if run is not None else (seat or "unattributed")
        day = str(req.get("at") or "")[:10]
        if day:
            d = daily.setdefault(day, {})
            d[bucket] = d.get(bucket, 0) + sum(int(_n(req.get(k))) for k in TOKENS)
        if run is not None or seat is not None:
            kind, key = ("runs", run["run_id"]) if run is not None else ("seats", seat)
            recent[kind].setdefault(key, []).append(
                {"at": req.get("at"), "model": req.get("model"), "effort": req.get("effort"),
                 "query_source": req.get("query_source"), "session_id": req.get("session_id"),
                 "tokens": sum(int(_n(req.get(k))) for k in TOKENS)})
        if run is not None:
            iv = _interval(req, span)
            if iv is not None:
                timeline.setdefault(run["run_id"], []).append(iv)
            acc = per_run.setdefault(run["run_id"], _blank())
            _add(acc, req)
            _add(seats.setdefault(run.get("seat") or "worker", _blank()), req)
        elif seat is not None:
            _add(seats.setdefault(seat, _blank()), req)
            if seat == "other-sessions":
                c = str(req.get("cwd"))
                others[c] = others.get(c, 0) + sum(int(_n(req.get(k))) for k in TOKENS)
        else:
            _add(unattributed, req)
            key = aid or f"(no span, {req.get('query_source') or '?'})"
            stray[key] = stray.get(key, 0) + 1
    rows = []
    for r in all_runs:
        if task_id and r.get("task_id") != task_id:
            continue
        u = _out(per_run.get(r["run_id"], _blank()))
        flags = []
        if u["requests"]:
            if r.get("expected_model") and u["observed_models"] and u["observed_models"] != [r["expected_model"]]:
                flags.append(f"model {', '.join(u['observed_models'])}, pinned {r['expected_model']}")
            if r.get("expected_effort") and u["observed_efforts"] and u["observed_efforts"] != [r["expected_effort"]]:
                flags.append(f"effort {', '.join(u['observed_efforts'])}, pinned {r['expected_effort']}")
        rows.append({"run_id": r["run_id"], "seat": r.get("seat"), "state": runs.state(r),
                     "expected_model": r.get("expected_model"), "expected_effort": r.get("expected_effort"),
                     "usage": u, "flags": flags})
    tot = _out(total)
    attributed = sum(tot[k] for k in TOKENS) - sum(_out(unattributed)[k] for k in TOKENS)
    all_tokens = sum(tot[k] for k in TOKENS)
    task_total = None
    if task_id is not None:
        tt = _blank()
        for r in all_runs:
            if r.get("task_id") == task_id and r["run_id"] in per_run:
                for k in TOKENS + TTL_SPLIT:
                    tt[k] += per_run[r["run_id"]][k]
                tt["cost_usd"] += per_run[r["run_id"]]["cost_usd"]
                tt["requests"] += per_run[r["run_id"]]["requests"]
        task_total = _out(tt)
    advice = []
    lead = seats.get("design-seat")
    if design_seat and lead and lead["requests"]:
        # §24.5: advice only. The lead also makes small helper calls (titles) on other models: compare the
        # model of most of its tokens, and every effort it used.
        if design_seat.get("model") and not any(str(m).startswith(design_seat["model"]) for m in lead["models"]):
            advice.append(f"the design seat ran on {', '.join(sorted(lead['models']))}; the operator expects {design_seat['model']}")
        if design_seat.get("effort") and design_seat["effort"] not in lead["efforts"]:
            advice.append(f"the design seat ran at effort {', '.join(sorted(lead['efforts']))}; the operator expects {design_seat['effort']}")
    return {"recent": {k: {key: sorted(v, key=lambda x: str(x.get("at") or ""))[-RECENT:] for key, v in d.items()}
                       for k, d in recent.items()},
            "timeline": timeline, "runs": rows, "task_id": task_id, "task_total": task_total, "advice": advice, "daily": daily,
            "seats": {k: _out(v) for k, v in sorted(seats.items())},
            "unattributed": _out(unattributed), "unattributed_sources": stray, "total": tot, "how": how,
            "other_sessions": dict(sorted(others.items(), key=lambda kv: -kv[1])),
            "coverage": round(attributed / all_tokens, 4) if all_tokens else None,
            "traces": bool(spans), "headless": headless}


def _interval(req: dict[str, Any], span: dict[str, Any]) -> tuple[float, float] | None:
    """When a request was in flight: its span's start and end, else its `at` (the response) less
    `duration_ms`. None when neither is known."""
    a, b = _t(span.get("at")), _t(span.get("end"))
    if a is not None and b is not None and b >= a:
        return a, b
    b = _t(req.get("at"))
    d = _n(req.get("duration_ms")) / 1000
    return (b - d, b) if b is not None and d > 0 else None


def _window(all_runs: list[dict[str, Any]], req: dict[str, Any]) -> dict[str, Any] | None:
    """The one run open when the request was made whose pinned model and effort match it."""
    t = _t(req.get("at"))
    if t is None:
        return None
    hits = []
    for r in all_runs:
        start = _t(r.get("started_at"))  # only a run whose agent started (bound); an unlaunched one never matches
        end = _t(r.get("stopped_at") or r.get("reported_at") or r.get("abandoned_at")) or float("inf")
        if start is None or not start <= t <= end:
            continue
        if r.get("expected_model") and req.get("model") and r["expected_model"] != req["model"]:
            continue
        if r.get("expected_effort") and req.get("effort") and r["expected_effort"] != req["effort"]:
            continue
        hits.append(r)
    return hits[0] if len(hits) == 1 else None


CONTEXT_TOKENS = ("input_tokens", "cache_read_tokens", "cache_creation_tokens")  # what a request sends


def runner_context(q: Path, names: set[str], since: Any = None) -> dict[str, Any] | None:
    """§10.2 step 4: the latest request of a runner teammate named one of `names`, made at or after
    `since` (its spawn), and its context: the tokens it sent (input, cache read, cache written). From
    the trace spans (`board/usage-spans.jsonl`), whose `agent_id` `<name>@session-…` names the
    teammate (§24.4). None when there is none."""
    p = q / "board" / "usage-spans.jsonl"
    keys = [f"{n}@session-" for n in names if n]
    t0 = _t(since) if since else None
    best: tuple[float, dict[str, Any]] | None = None
    for line in p.read_text().splitlines() if keys and p.is_file() else []:
        if not any(k in line for k in keys):  # the file is large: parse only the lines that may match
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        aid = str(row.get("agent_id") or "") if isinstance(row, dict) else ""
        if "@session-" not in aid or aid.split("@", 1)[0] not in names:
            continue
        t = _t(row.get("at"))
        if t is None or (t0 is not None and t < t0) or (best is not None and t < best[0]):
            continue
        best = (t, row)
    if best is None:
        return None
    return {"at": best[1].get("at"), "tokens": sum(int(_n(best[1].get(k))) for k in CONTEXT_TOKENS),
            "request_id": best[1].get("request_id")}


# ------------------------------------------------------------------------------------- allowance

# §25.2 the usage windows. The allowance command reports any number of named windows; each window's
# rule (`telemetry.windows`, over the built-in two) says whether it is weekly (a stop checkpoint) or a
# session window (a park). The most constrained window of each kind gates, and is written into the
# sample's legacy fields (`seven_day`/`resets_at` and `five_hour`/`five_hour_resets_at`), which every
# reader, the forecast and the board keep using.
BUILTIN_WINDOWS = {"seven_day": "weekly", "five_hour": "session"}


def wname(rec: dict[str, Any] | None, kind: str) -> str:
    """The window a sample's (or a decision's) weekly or session fields belong to; rows written before
    the usage windows carry no name and belong to the built-in ones."""
    r = rec or {}
    if kind == "weekly":
        return str(r.get("weekly_window") or r.get("window") or "seven_day")
    return str(r.get("session_window") or "five_hour")


def window_rules(cfg: Config) -> dict[str, dict[str, Any]]:
    """Each known window's rule {kind, stop_pct, park_pct}: the built-in seven_day (weekly, stop at
    `allowance_stop_weekly`) and five_hour (session, park at `session_park_pct`), then `telemetry.windows`
    merged over them per name."""
    from ccp.config import TELEMETRY_DEFAULTS as D  # noqa: PLC0415
    tel = cfg.telemetry or {}
    rules: dict[str, dict[str, Any]] = {
        "seven_day": {"kind": "weekly", "stop_pct": tel.get("allowance_stop_weekly"), "park_pct": None},
        "five_hour": {"kind": "session", "stop_pct": None,
                      "park_pct": _num_or_none(tel.get("session_park_pct", D["session_park_pct"]))}}
    for name, w in (tel.get("windows") or {}).items():
        base = rules.get(name, {"kind": "weekly", "stop_pct": None, "park_pct": None})
        rules[name] = {**base, **{k: (_num_or_none(v) if k != "kind" else v) for k, v in w.items()}}
    return rules


def window_kind(rules: dict[str, dict[str, Any]], name: str) -> str | None:
    """A window's kind; a window neither built in nor named by `telemetry.windows` has none (recorded only)."""
    return (rules.get(name) or {}).get("kind")


def parse_windows(data: Any) -> list[dict[str, Any]]:
    """The windows an allowance reading names: the generic `{windows: [{name, pct, resets_at}]}`, or the
    legacy shape (`{<name>: {utilization, resets_at}}`, e.g. five_hour and seven_day). A window whose
    figure is unknown keeps its reset with `pct` None (it gates nothing)."""
    out: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return out
    if isinstance(data.get("windows"), list):
        items = [(w.get("name"), w.get("pct"), w.get("resets_at")) for w in data["windows"] if isinstance(w, dict)]
    else:
        items = [(k, v.get("utilization"), v.get("resets_at")) for k, v in data.items() if isinstance(v, dict)]
    for name, pct, reset in items:
        if isinstance(name, str) and name:
            out.append({"name": name, "pct": _num_or_none(pct), "resets_at": _time_or_none(reset)})
    return out


def _binding(wins: list[dict[str, Any]], rules: dict[str, dict[str, Any]], kind: str,
             lim: Any, prev: str | None) -> dict[str, Any] | None:
    """The window of `kind` that gates, stably (§25.2): among the windows at or past their threshold
    (`lim(window)`), the previous sample's window while it is one of them, else the first by name; with
    none past, the one nearest its threshold, the previous one while it is as near, ties by name;
    without thresholds, the highest figure. None when no window of the kind has a figure."""
    cands = sorted((w for w in wins if w.get("pct") is not None and window_kind(rules, w["name"]) == kind),
                   key=lambda w: w["name"])
    if not cands:
        return None
    past = [w for w in cands if lim(w) is not None and w["pct"] >= lim(w)]
    if past:
        return next((w for w in past if w["name"] == prev), past[0])
    with_lim = [w for w in cands if lim(w)]
    pool, score = (with_lim, lambda w: w["pct"] / float(lim(w))) if with_lim else (cands, lambda w: w["pct"])
    best = max(score(w) for w in pool)
    near = [w for w in pool if score(w) >= best - 1e-9]
    return next((w for w in near if w["name"] == prev), near[0])


def project(cfg: Config, wins: list[dict[str, Any]], q: Path | None = None,
            prev: dict[str, Any] | None = None) -> dict[str, Any]:
    """The sample's fields from its windows: the gating weekly window into seven_day/resets_at (with its
    name), the gating session window into five_hour/five_hour_resets_at (with its name). A weekly window's
    threshold is its checkpoint in force (decisions for that window included, when `q` is given)."""
    rules = window_rules(cfg)
    def stop(w: dict[str, Any]) -> float | None:
        return checkpoint(cfg, q, w.get("resets_at"), w["name"]) if q is not None else rules[w["name"]].get("stop_pct")
    wk = _binding(wins, rules, "weekly", stop, (prev or {}).get("weekly_window"))
    ss = _binding(wins, rules, "session", lambda w: rules[w["name"]].get("park_pct"), (prev or {}).get("session_window"))
    def reset_of(kind: str) -> Any:  # a weekly or session reading with no figure still keeps its reset (legacy)
        return next((w.get("resets_at") for w in sorted(wins, key=lambda w: w["name"])
                     if window_kind(rules, w["name"]) == kind and w.get("resets_at")), None)
    rec: dict[str, Any] = {"five_hour": ss and ss["pct"], "seven_day": wk and wk["pct"],
                           "resets_at": wk.get("resets_at") if wk else reset_of("weekly"),
                           "five_hour_resets_at": ss.get("resets_at") if ss else reset_of("session"),
                           "windows": wins}
    if wk:
        rec["weekly_window"] = wk["name"]
    if ss:
        rec["session_window"] = ss["name"]
    return rec


def sample_allowance(cfg: Config, q: Path, gate: bool = True) -> dict[str, Any] | None:
    """§25.1: run the binding's allowance command, record the sample, refuse past the weekly stop.
    A command that fails or prints something unexpected records the sample as unknown, never zero."""
    tel = cfg.telemetry or {}
    cmd = tel.get("allowance_cmd")
    if not cmd:
        return None
    try:
        r = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, text=True, timeout=8)
        wins = parse_windows(json.loads(r.stdout) if r.returncode == 0 else {})
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        wins = []
    rec = {"at": iso(), **project(cfg, wins, q, _latest(q))}
    seven, resets = rec["seven_day"], rec["resets_at"]
    p = q / "board" / "allowance.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    emit(q, cfg, "", "allowance", "sample", {k: rec[k] for k in ("five_hour", "seven_day", "resets_at", "five_hour_resets_at")})
    if seven is None:
        rec["warning"] = "the allowance reading is unknown; the weekly checkpoint was not checked (SPEC §25.3)"
    # every weekly window is held to its own checkpoint (§25.3): one past it refuses, whichever window gates
    rules = window_rules(cfg)
    over = [(w, cp) for w in sorted(rec["windows"], key=lambda w: w["name"])
            if w.get("pct") is not None and window_kind(rules, w["name"]) == "weekly"
            and (cp := checkpoint(cfg, q, w.get("resets_at"), w["name"])) is not None and w["pct"] >= cp]
    if gate and over:
        w, stop = over[0]
        seven, resets = w["pct"], w.get("resets_at")
        raise QueueError(f"allowance checkpoint: the {w['name']} window is at {seven:g}%, its checkpoint is {stop:g}% "
                         f"(SPEC §25.3); resets {resets or 'at an unknown time'}. Runner: stop and tell the lead. Lead: ask the operator, "
                         "and record their decision with `ccp allowance continue --to <percent> --reason \"<their words>\"`", 5)
    return rec


def decisions(q: Path) -> list[dict[str, Any]]:
    return _jsonl(q / "board" / "allowance-decisions.jsonl")


WINDOW_TOLERANCE_S = 6 * 3600  # the usage endpoint's resets_at jitters by milliseconds between readings


def _iso_ts(v: Any) -> float:
    """An ISO time as epoch seconds; any fraction is padded to 6 digits, which Python 3.10's
    fromisoformat needs (it refuses ".52")."""
    import re  # noqa: PLC0415
    t = re.sub(r"\.(\d{1,6})\d*", lambda m: "." + m.group(1).ljust(6, "0"), str(v).replace("Z", "+00:00"), count=1)
    return datetime.fromisoformat(t).timestamp()


def same_window(a: Any, b: Any) -> bool:
    """Two readings of the weekly `resets_at` name the same window when they are within hours of each
    other: the next window resets a week later, while one window's readings differ by milliseconds
    (2026-10-27T03:59:59.52Z against 04:00:00.24Z)."""
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        ta, tb = (_iso_ts(x) for x in (a, b))
    except ValueError:
        return False
    return abs(ta - tb) <= WINDOW_TOLERANCE_S


# A counter reset (§25.2): Anthropic can zero the weekly counter early while `resets_at` stays put
# (e.g. 97% at 07:56Z, 0% at 08:09Z, resets_at still the same week). Within one window
# the counter only rises, bar a point of rounding, so a fall this large is a reset. A fall to near zero
# from high up is always at least this large; and a decision exists only near the checkpoint, so the
# counter is high whenever a reset could lapse one.
RESET_DROP_PP = 20.0


def counter_resets(q: Path, resets_at: Any, window: str | None = None) -> list[str]:
    """The times of the samples, in the weekly window `window` (default seven_day) ending `resets_at`, at
    which the counter reset early: its % fell by RESET_DROP_PP or more since the previous known sample of
    the same window. Samples whose gating weekly window is another one are not compared."""
    out: list[str] = []
    prev: dict[str, Any] | None = None
    for r in _jsonl(q / "board" / "allowance.jsonl"):
        if wname(r, "weekly") != (window or "seven_day"):
            continue
        seven = _num_or_none(r.get("seven_day"))
        if seven is None or not r.get("at"):
            continue  # an unknown reading is neither a reset nor a baseline
        if prev is not None and same_window(prev.get("resets_at"), r.get("resets_at")) \
                and same_window(resets_at, r.get("resets_at")) and float(prev["seven_day"]) - seven >= RESET_DROP_PP:
            out.append(r["at"])
        prev = {**r, "seven_day": seven}
    return out


def _lapsed_at(d: dict[str, Any], resets: list[str]) -> str | None:
    """The first counter reset after the decision was taken, at which it lapsed; None while in force."""
    try:
        at = _iso_ts(d.get("at"))
    except (TypeError, ValueError):
        return None
    for r in resets:
        try:
            if _iso_ts(r) > at:
                return r
        except ValueError:
            continue
    return None


def checkpoint(cfg: Config, q: Path, resets_at: Any, window: str | None = None) -> float | None:
    """The checkpoint in force: the weekly window's own stop (`window`'s rule; default seven_day, i.e.
    `allowance_stop_weekly`), raised by the operator's decisions for this window that no counter reset has
    lapsed since (§25.3)."""
    window = window or "seven_day"
    base = window_rules(cfg).get(window, {}).get("stop_pct")
    levels = [float(base)] if base is not None else []
    resets = counter_resets(q, resets_at, window)
    for d in decisions(q):  # a decision applies to its own window; one recorded without a name, to seven_day
        if wname(d, "weekly") == window and same_window(resets_at, d.get("resets_at")) and _lapsed_at(d, resets) is None:
            try:
                levels.append(float(d["to"]))
            except (KeyError, TypeError, ValueError):
                continue  # a malformed row is skipped, never fatal to claim or the board
    return max(levels) if levels else None


def continue_(cfg: Config, q: Path, to: float, reason: str) -> dict[str, Any]:
    """§25.3: the lead records the operator's decision to continue past the checkpoint, up to `to`."""
    from ccp import health  # noqa: PLC0415
    if not reason.strip():
        raise QueueError("give --reason: the operator's decision, in their words", 2)
    if health.looks_like_secret(reason):
        raise QueueError("--reason looks like it holds a secret", 2)
    if not 0 < to <= 100:
        raise QueueError("--to is a percentage of the weekly allowance", 2)
    last = (_jsonl(q / "board" / "allowance.jsonl") or [{}])[-1]
    if not last.get("resets_at"):
        raise QueueError("no allowance sample with a reset time yet: a decision belongs to a weekly window "
                         "(run `ccp allowance status --sample`)", 3)
    win = wname(last, "weekly")
    cur = checkpoint(cfg, q, last["resets_at"], win)
    if cur is not None and to <= cur:
        raise QueueError(f"--to {to:g}% does not raise the checkpoint in force ({cur:g}%)", 2)
    rec = {"at": iso(), "by": "design-seat", "to": to, "reason": reason.strip(), "resets_at": last["resets_at"],
           "window": win, "seven_day_then": last.get("seven_day")}
    p = q / "board" / "allowance-decisions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    emit(q, cfg, "", "allowance", "decided", {"to": to, "reason": rec["reason"][:200], "resets_at": rec["resets_at"]},
         "design-seat")
    return {"ok": True, **rec}


def status(cfg: Config, q: Path, sample: bool) -> dict[str, Any]:
    """The latest sample, the checkpoint in force and this window's decisions, each with `lapsed_at`
    (the counter reset that lapsed it, or None). `decision_lapsed_at` is the reset that lapsed the
    latest decision, when that one is no longer in force."""
    if sample:
        sample_allowance(cfg, q, gate=False)
    last = (_jsonl(q / "board" / "allowance.jsonl") or [None])[-1]
    resets = (last or {}).get("resets_at")
    win = wname(last, "weekly")
    times = counter_resets(q, resets, win)
    dec = [{**d, "lapsed_at": _lapsed_at(d, times)} for d in decisions(q)
           if wname(d, "weekly") == win and same_window(resets, d.get("resets_at"))]
    return {"ok": True, "latest": last, "window": win, "checkpoint": checkpoint(cfg, q, resets, win),
            "project_checkpoint": window_rules(cfg).get(win, {}).get("stop_pct"),
            "decisions": dec, "counter_resets": times,
            "decision_lapsed_at": dec[-1]["lapsed_at"] if dec else None}


def _time_or_none(v: Any) -> str | None:
    """An ISO time as given, when it parses; anything else is unknown."""
    if not isinstance(v, str) or not v:
        return None
    try:
        _iso_ts(v)
    except ValueError:
        return None
    return v


def _num_or_none(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------- the 5-hour window

# §25.4 the session park (operator, 2026-10-23). The 5-hour window is the account's: when it runs out the
# runner's turn fails, and so does the lead's, which then cannot schedule its own resume. So claim and
# prompt park the task at `session_park_pct`, and the lead keeps a one-shot wake armed (Claude Code's
# CronCreate, session-only) at the window's actual reset plus a margin, armed while it can still act.
PARK_EXIT = 6
SAME_SESSION_S = 600  # two readings of five_hour.resets_at within 10 minutes name the same window (ms jitter)
# A park whose window's reset is unknown is retried this long after it was set: its planned_resume_at,
# after which the park has expired like any other (`expired`), and the next claim or prompt samples again.
PARK_RETRY_S = 1800
FIRE_SLACK_S = 120  # `--fire` un-parks a task whose planned resume is this close (a wake a little early)
WAKES = "session-wakes.jsonl"


def session_settings(cfg: Config, rec: dict[str, Any] | None = None) -> tuple[float | None, float, int]:
    """(park %, or None when the park is off; wake-arm %; wake margin in seconds), defaults filled in.
    With a sample, the park % is its gating session window's (`park_pct`, §25.4 the usage windows)."""
    from ccp.config import TELEMETRY_DEFAULTS as D  # noqa: PLC0415
    tel = cfg.telemetry or {}
    # the park % is the window's rule now (§25.4), not one stored in the sample
    park = window_rules(cfg).get(wname(rec, "session"), {}).get("park_pct") if rec and rec.get("session_window") \
        else tel.get("session_park_pct", D["session_park_pct"])
    arm = tel.get("session_wake_arm_pct", D["session_wake_arm_pct"])
    margin = tel.get("session_wake_margin_s", D["session_wake_margin_s"])
    return (_num_or_none(park), _num_or_none(arm) or float(D["session_wake_arm_pct"]),
            int(margin) if isinstance(margin, int) and not isinstance(margin, bool) else D["session_wake_margin_s"])


def _ts(v: Any) -> float | None:
    try:
        return _iso_ts(v) if v else None
    except (TypeError, ValueError):
        return None


def _utc(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local(t: float) -> str:
    return datetime.fromtimestamp(t).astimezone().strftime("%a %d %b %H:%M %Z")


def same_session(a: Any, b: Any) -> bool:
    ta, tb = _ts(a), _ts(b)
    return ta is not None and tb is not None and abs(ta - tb) <= SAME_SESSION_S


def wake_time(reset: float, margin: int) -> float:
    """The reset rounded to the nearest second (its readings jitter by milliseconds around it), plus the
    margin, up to the next whole minute (a cron fires on minutes): 03:59:59.7 and 04:00:00.3 give one wake."""
    t = round(reset) + margin
    return float(t if t % 60 == 0 else (t // 60 + 1) * 60)


def cron_for(t: float) -> str:
    """Five-field cron for one moment in local time (CronCreate reads local time): minute, hour, day and
    month pinned, any weekday."""
    d = datetime.fromtimestamp(t)
    return f"{d.minute} {d.hour} {d.day} {d.month} *"


def wakes(q: Path) -> list[dict[str, Any]]:
    return _jsonl(q / "board" / WAKES)


def armed_wake(q: Path, reset: Any, now: float | None = None, wake_at: float | None = None) -> dict[str, Any] | None:
    """The wake recorded for the window that resets at `reset` (with no reset known: the retry wake at
    `wake_at`), while it has yet to fire."""
    now = time.time() if now is None else now
    for w in reversed(wakes(q)):
        if (_ts(w.get("wake_at")) or 0) <= now:
            continue
        if same_session(reset, w.get("five_hour_resets_at")) or (
                not reset and wake_at is not None and abs((_ts(w.get("wake_at")) or 0) - wake_at) <= SAME_SESSION_S):
            return w
    return None


def expired(st: dict[str, Any], now: float | None = None) -> bool:
    """A 5-hour park whose planned resume has passed no longer holds the task back: nothing may have
    lifted it (the wake lost with the lead's session), and the next claim or prompt samples again."""
    due = _ts(st.get("planned_resume_at"))
    return due is not None and due <= (time.time() if now is None else now)


def parked(q: Path) -> list[dict[str, Any]]:
    """The tasks waiting on the 5-hour window (`waiting_on: quota`, `quota_class: session`): their queue
    files, and work.json's task when its queue file has none, each with `expired`."""
    from ccp.queue import load_work, read_json  # noqa: PLC0415
    out, seen = [], set()
    for f in sorted((q / "tasks").glob("*.json")) if (q / "tasks").is_dir() else []:
        st = read_json(f, {})
        if isinstance(st, dict) and st.get("waiting_on") == "quota" and st.get("quota_class") == "session":
            out.append({"task_id": f.stem, "phase": st.get("status"), "planned_resume_at": st.get("planned_resume_at"),
                        "expired": expired(st)})
            seen.add(f.stem)
    w = load_work(q)
    if w.get("waiting_on") == "quota" and w.get("quota_class") == "session" and w.get("task_id") \
            and w["task_id"] not in seen:
        out.append({"task_id": w["task_id"], "phase": None, "planned_resume_at": w.get("planned_resume_at"),
                    "expired": expired(w)})
    return out


def _set_wait(cfg: Config, q: Path, action: str, tid: str, reason: str, *extra: str) -> None:
    """`waiting_on` through its single writer, set-waiting-on.sh (§23.2). Always `--task-only`: the
    task's queue file, and work.json only when it names this task, so a refused new claim never
    overwrites work.json's account of the task in flight."""
    from ccp.queue import OBS, actor  # noqa: PLC0415
    cmd = [str(OBS / "set-waiting-on.sh"), action, tid, reason, "--actor", actor(), "--project-id", cfg.project_id,
           "--task-only", *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)}, timeout=30)
    if r.returncode != 0:
        raise QueueError(f"set-waiting-on: {tid}: {(r.stderr or r.stdout).strip()}", 1)


def clear_park(cfg: Config, q: Path, tid: str, why: str = "session_reset") -> bool:
    """Lift a 5-hour park on `tid` (a later claim or prompt that passed the gate); False when none."""
    if not any(p["task_id"] == tid for p in parked(q)):
        return False
    _set_wait(cfg, q, "clear", tid, why)
    return True


def _park(cfg: Config, q: Path, tid: str, five: float, park: float, reset: Any, planned: str) -> None:
    from ccp.queue import load_task_state, save_task_state  # noqa: PLC0415
    st = load_task_state(q, tid)
    if st.get("waiting_on") == "quota" and st.get("quota_class") == "session" and st.get("planned_resume_at") == planned:
        return  # parked already, for this window
    if not st:  # a refused new claim: a queue file of its own carries the wait (the hook and --fire read it)
        save_task_state(q, tid, {"task_id": tid, "project_id": cfg.project_id, "status": "pending", "lease_holder": None})
    extra = ["--quota-class", "session", "--detail", f"5-hour window at {five:g}% (park at {park:g}%)",
             "--resets-at", reset or planned, "--planned-resume-at", planned]
    _set_wait(cfg, q, "set", tid, "quota", *extra)


def _held_others(cfg: Config, q: Path, tid: str, parked_too: bool = False) -> list[str]:
    """§16.5 rule 6, with parallel on: the other tasks the runner holds that the session park parks with
    `tid`. One already waiting on someone else (a gate, a question, the lead) keeps that wait: it is
    blocked anyway, and a park would overwrite it. `parked_too` also returns those parked already."""
    from ccp import parallel  # noqa: PLC0415
    if not parallel.enabled(cfg):
        return []
    from ccp.queue import load_task_state, load_work  # noqa: PLC0415
    out = []
    for t in parallel.active_tasks(cfg, q, load_work(q), but=tid):
        st = load_task_state(q, str(t.get("task_id")))
        session = st.get("waiting_on") == "quota" and st.get("quota_class") == "session"
        if not st.get("waiting_on") or (parked_too and session):
            out.append(str(t.get("task_id")))
    return out


def session_gate(cfg: Config, q: Path, tid: str, rec: dict[str, Any] | None, step: str) -> list[str]:
    """§25.4: at or past the park %, park `tid` and refuse (exit 6); otherwise lift any park the task
    had, and warn from the arm % while no wake is armed for this window. An unknown reading, a park
    that is off, or a window whose reset has passed gates nothing; the last two lift the park, an
    unknown reading keeps it. Best effort:
    any failure but the park itself is a warning (`session_step`)."""
    park, arm, margin = session_settings(cfg, rec)
    five = (rec or {}).get("five_hour")
    reset = (rec or {}).get("five_hour_resets_at")
    rt, now = _ts(reset), time.time()
    if park is not None and five is not None and five >= park and not (rt is not None and rt <= now):
        if rt is not None:
            planned = _utc(wake_time(rt, margin))
        else:  # a retry: a live retry park keeps its time, so a refusal never pushes it out again
            from ccp.queue import load_task_state  # noqa: PLC0415
            st = load_task_state(q, tid)
            live = st.get("waiting_on") == "quota" and st.get("quota_class") == "session" \
                and st.get("planned_resume_at") and not expired(st, now)
            planned = st["planned_resume_at"] if live else _utc(now + PARK_RETRY_S)
        note = ""
        try:
            _park(cfg, q, tid, five, park, reset, planned)
        except Exception as exc:  # noqa: BLE001  (the park still refuses: the limit is near)
            note = f" (the wait could not be recorded: {exc})"
        from ccp import parallel  # noqa: PLC0415
        for other in _held_others(cfg, q, tid):  # §16.5 rule 6: the window is the account's: every task held parks
            try:
                _park(cfg, q, other, five, park, reset, planned)
            except Exception as exc:  # noqa: BLE001
                note += f" ({other}'s wait could not be recorded: {exc})"
        when = f"{_utc(rt)} ({_local(rt)})" if rt is not None else \
            f"at an unknown time; ccp retries after {planned}"
        raise QueueError(
            f"session park: the {(rec or {}).get('session_window') or 'five_hour'} window is at {five:g}%, the park is "
            f"{park:g}% (SPEC §25.4); it resets {when}. "
            f"{tid} is parked (waiting_on quota, session, until {planned}){note}; {step} did nothing. "
            "Runner: send the lead one message with this %, the reset time and the task, then idle. "
            "Lead: `ccp allowance session-wake --sample`, and arm the wake it prints", PARK_EXIT)
    out = []
    # lifted only on a reading that shows the window free: known and under the park %, its reset past,
    # or the park off. An unknown reading proceeds (best effort) but keeps a live park
    from ccp.parallel import no_five_hour_limit  # noqa: PLC0415
    # §25.2: a weekly-only reading means no 5-hour limit (since 2026-10-31): the window is free
    free = park is None or (five is not None and five < park) or (rt is not None and rt <= now) or no_five_hour_limit(rec)
    for t in [tid, *(_held_others(cfg, q, tid, parked_too=True) if free else [])]:  # §16.5 rule 6: all held lift too
        if free and clear_park(cfg, q, t):
            out.append(f"{t}: the 5-hour park is lifted" + (f" (the window is at {five:g}%)" if five is not None else ""))
    if park is not None and five is not None and five >= arm and rt is not None and rt > now \
            and armed_wake(q, reset, now) is None:
        out.append(f"5-hour window at {five:g}%: no session wake armed; tell the lead to arm one "
                   "(`ccp allowance session-wake`)")
    return out


def session_step(cfg: Config, q: Path, tid: str, rec: Any, step: str) -> list[str]:
    """`session_gate`, best effort (claim and prompt): only the park (exit 6) refuses; any other failure
    (a sample, the wait's writer, the wake records) becomes a warning. `rec` may be a callable that
    takes the sample."""
    try:
        return session_gate(cfg, q, tid, rec() if callable(rec) else rec, step)
    except QueueError as e:
        if e.code == PARK_EXIT:
            raise
        return [f"the session park was not checked: {e} (SPEC §25.4)"]
    except Exception as exc:  # noqa: BLE001
        return [f"the session park was not checked: {type(exc).__name__}: {exc} (SPEC §25.4)"]


def _latest(q: Path) -> dict[str, Any]:
    return (_jsonl(q / "board" / "allowance.jsonl") or [{}])[-1]


def session_wake(cfg: Config, q: Path, sample: bool = False, rearm: bool = False) -> dict[str, Any]:
    """`ccp allowance session-wake`: whether the lead should arm a wake now, and the CronCreate call.
    The wake time comes from the reading's `five_hour.resets_at`, never from now + 5 h: the limit is
    usually met well inside the window (e.g. 40 minutes before its reset). With the reset
    unknown, a parked task's retry time (`PARK_RETRY_S`) is the wake. `rearm` (from `--fire` before the
    window reset: the cron fired early, e.g. at a clock change) offers the armed wake again."""
    if sample:
        sample_allowance(cfg, q, gate=False)
    park, arm_pct, margin = session_settings(cfg, _latest(q))
    last, now = _latest(q), time.time()
    five, reset = _num_or_none(last.get("five_hour")), last.get("five_hour_resets_at")
    rt = _ts(reset)
    waiting = parked(q)
    retry = min((t for p in waiting if (t := _ts(p.get("planned_resume_at"))) and t > now), default=None)
    out: dict[str, Any] = {"ok": True, "sample_at": last.get("at"), "window": last.get("session_window") or "five_hour",
                           "five_hour": five, "five_hour_resets_at": reset,
                           "park_pct": park, "arm_pct": arm_pct, "margin_s": margin, "parked": waiting,
                           "wake_at": None, "wake_local": None, "cron": None, "armed": None, "prompt": WAKE_PROMPT}
    wt = wake_time(rt, margin) if rt is not None and rt > now else (wake_time(retry, 0) if retry else None)
    if wt is not None:
        out.update(wake_at=_utc(wt), wake_local=_local(wt), cron=cron_for(wt),
                   armed=armed_wake(q, reset if rt is not None and rt > now else None, now, wt))
    arm = False
    if park is None:
        why = "telemetry.session_park_pct is null: the session park and wake are off"
    elif not last.get("at"):
        why = "no allowance sample yet (run with --sample)"
    elif wt is None and five is None:
        why = "the 5-hour reading is unknown"
    elif wt is None and rt is None:
        why = "the 5-hour window's reset time is unknown: no wake can be timed"
    elif wt is None:
        why = "the 5-hour window in the latest sample has already reset: run with --sample"
    elif out["armed"] and rearm:
        arm, why = True, (f"the wake fired before the window reset (a clock change?): arm it again for "
                          f"{out['armed'].get('wake_at')}")
    elif out["armed"]:
        why = f"a wake is already armed for this window ({out['armed'].get('wake_at')})"
    elif waiting:
        arm, why = True, f"{len(waiting)} task(s) parked on the 5-hour window" + (
            "; its reset is unknown, so the wake is the park's retry" if rt is None or rt <= now else "")
    elif five is not None and five >= arm_pct:
        arm, why = True, f"the 5-hour window is at {five:g}% (arm from {arm_pct:g}%)"
    else:
        why = f"the 5-hour window is at {five:g}%, under {arm_pct:g}%: no wake needed yet" if five is not None \
            else "the 5-hour reading is unknown"
    out["arm"] = arm
    out["reason"] = why
    if out["arm"]:
        out["instruction"] = (f"call CronCreate with cron \"{out['cron']}\", recurring: false and this `prompt`, "
                              "then run `ccp allowance session-wake --armed`")
    return out


WAKE_PROMPT = ("Session wake (control plane, SPEC §25.4): the 5-hour window has reset. Run "
               "`ccp allowance session-wake --fire` and do what it prints.")


def session_armed(cfg: Config, q: Path) -> dict[str, Any]:
    """`ccp allowance session-wake --armed`: the lead records the wake it armed, the one `session-wake`
    prints now. A second record for the same window (or retry time) is not written."""
    from ccp.queue import actor  # noqa: PLC0415
    park, _arm, _margin = session_settings(cfg, _latest(q))
    if park is None:
        raise QueueError("telemetry.session_park_pct is null: the session park and wake are off", 2)
    w = session_wake(cfg, q)
    if not w.get("wake_at"):
        raise QueueError("no 5-hour reset ahead in the latest sample: run `ccp allowance session-wake --sample` "
                         "and arm the wake it prints", 3)
    if w.get("armed"):
        return {"ok": True, "already": True, "armed": w["armed"]}
    reset = w["five_hour_resets_at"] if (_ts(w["five_hour_resets_at"]) or 0) > time.time() else None
    rec = {"at": iso(), "by": actor("design-seat"), "five_hour_resets_at": reset, "wake_at": w["wake_at"],
           "wake_local": w["wake_local"], "cron": w["cron"], "five_hour": w.get("five_hour")}
    from ccp.queue import append_jsonl  # noqa: PLC0415
    append_jsonl(q / "board" / WAKES, rec)
    emit(q, cfg, "", "allowance", "armed", {"five_hour_resets_at": reset, "wake_at": rec["wake_at"]}, rec["by"])
    return {"ok": True, "already": False, "armed": rec}


def session_fire(cfg: Config, q: Path) -> dict[str, Any]:
    """`ccp allowance session-wake --fire` (the wake's prompt): a fresh sample. The window has reset when
    the 5-hour reading is under the park %, or the reading's own reset time has passed (the endpoint
    may still show the old window's %); then every parked task whose planned resume is due (within
    FIRE_SLACK_S) is un-parked, and the lead is told how to resume the runner. Otherwise it says the
    window has not reset, with the wake to arm (again)."""
    from ccp.queue import actor, load_work  # noqa: PLC0415
    rec = sample_allowance(cfg, q, gate=False)
    park, _arm, _margin = session_settings(cfg, rec or _latest(q))  # the fresh reading's window
    five = (rec or {}).get("five_hour")
    rt = _ts((rec or {}).get("five_hour_resets_at"))
    now = time.time()
    waiting = parked(q)
    out: dict[str, Any] = {"ok": True, "five_hour": five, "five_hour_resets_at": (rec or {}).get("five_hour_resets_at"),
                           "park_pct": park, "unparked": [], "still_parked": []}
    from ccp.parallel import no_five_hour_limit  # noqa: PLC0415
    # §25.4: a weekly-only reading means no 5-hour limit (since 2026-10-31): every park lifts
    reset = park is not None and (five is not None and five < park or rt is not None and rt <= now
                                  or no_five_hour_limit(rec))
    if not reset:
        out["reset"] = False
        out["instruction"] = ("the 5-hour window has not reset yet" if five is not None and park is not None else
                              "the 5-hour reading is unknown" if park is not None else "the session park is off") \
            + ": nothing was un-parked. Arm the next wake as `wake` says"
        out["wake"] = session_wake(cfg, q, rearm=True)
        return out
    out["reset"] = True
    nolimit = no_five_hour_limit(rec)
    for p in waiting:
        due = _ts(p.get("planned_resume_at"))
        if due is not None and due > now + FIRE_SLACK_S and not nolimit:  # no limit: nothing to wait for
            out["still_parked"].append(p)
            continue
        clear_park(cfg, q, p["task_id"])
        out["unparked"].append(p)
    if out["unparked"]:
        from ccp.queue import holder_teammate  # noqa: PLC0415
        who: dict[str, list[str]] = {}  # §16.5: each unparked task's own runner
        for p in out["unparked"]:
            who.setdefault(holder_teammate(q, p["task_id"]), []).append(p["task_id"])
        out["instruction"] = ("; ".join(f"message {n}: resume {', '.join(t)} at its recorded phase (the task's queue "
                                        "file)" for n, t in who.items())
                              + "; a runner that is gone is respawned per SPEC §10.2 (§16.5: its slot)")
    else:
        w = load_work(q)
        tid = w.get("task_id")
        out["instruction"] = ("nothing was parked" + (f"; if the runner stopped on the 5-hour limit, message it: resume "
                                                        f"{tid} at its recorded phase ({w.get('phase') or '?'})" if tid else "")
                              + "; if the runner is gone, respawn it per SPEC §10.2")
    if out["still_parked"]:
        out["wake"] = session_wake(cfg, q)
    emit(q, cfg, "", "allowance", "fired", {"five_hour": five, "unparked": [p["task_id"] for p in out["unparked"]]},
         actor("design-seat"))
    return out


# ------------------------------------------------------------------------------------- headless

def record_headless(q: Path, kind: str, review_id: str, res: dict[str, Any]) -> None:
    """§24.5: a headless run's own `modelUsage` (tokens and cost per model, subagents included). A
    diagnostic: it never raises, so a pass is never failed over it."""
    try:
        _record_headless(q, kind, review_id, res)
    except Exception:  # noqa: BLE001
        pass


def _record_headless(q: Path, kind: str, review_id: str, res: dict[str, Any]) -> None:
    if not isinstance(res, dict):
        return
    mu = res.get("modelUsage")
    if not isinstance(mu, dict):
        if not res.get("session_id"):
            return
        mu = {}  # §24: the session id alone still places the session's telemetry on its seat
    models = {m: {k: v.get(k) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                                         "cacheCreationInputTokens", "costUSD") if isinstance(v, dict)}
              for m, v in mu.items()}
    rec = {"at": iso(), "kind": kind, "review_id": review_id, "models": models,
           "total_cost_usd": res.get("total_cost_usd"), "duration_ms": res.get("duration_ms"),
           "num_turns": res.get("num_turns"), "session_id": res.get("session_id")}
    p = q / "board" / "headless-usage.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def table(report: dict[str, Any]) -> str:
    def k(n: int) -> str:
        return f"{n / 1000:.0f}k" if n >= 1000 else str(n)
    lines = [f"{'RUN':<44} {'IN':>6} {'OUT':>6} {'CACHE-R':>8} {'CACHE-W':>8} {'W-1H':>6} {'REQ':>4}  MODEL / EFFORT"]
    for r in report["runs"]:
        u = r["usage"]
        lines.append(f"{r['run_id']:<44} {k(u['input_tokens']):>6} {k(u['output_tokens']):>6} "
                     f"{k(u['cache_read_tokens']):>8} {k(u['cache_creation_tokens']):>8} "
                     f"{k(u.get('cache_creation_1h_tokens', 0)):>6} {u['requests']:>4}  "
                     f"{','.join(u['observed_models']) or '-'} / {','.join(u['observed_efforts']) or '-'}"
                     + (f"  ! {'; '.join(r['flags'])}" if r["flags"] else ""))
    for s, u in report["seats"].items():
        lines.append(f"{'[' + s + ']':<44} {k(u['input_tokens']):>6} {k(u['output_tokens']):>6} "
                     f"{k(u['cache_read_tokens']):>8} {k(u['cache_creation_tokens']):>8} "
                     f"{k(u.get('cache_creation_1h_tokens', 0)):>6} {u['requests']:>4}")
    for a in report.get("advice") or []:
        lines.append(f"advice: {a}")
    if report.get("other_sessions"):
        lines.append("other sessions: " + ", ".join(f"{c} {k(n)}" for c, n in report["other_sessions"].items()))
    if report.get("unattributed_sources"):
        lines.append("unattributed: " + ", ".join(f"{k} ×{v}" for k, v in sorted(report["unattributed_sources"].items())))
    cov = report["coverage"]
    if report.get("task_total"):
        tt = report["task_total"]
        lines.append(f"task {report['task_id']}: {sum(tt[k] for k in TOKENS) // 1000}k tokens over {tt['requests']} requests")
    lines.append(f"coverage {cov * 100:.1f}% of the project's tokens attributed" if cov is not None
                 else "no usage recorded yet")
    if not report["traces"]:
        lines.append("no trace spans: attribution is by time window only (CLAUDE_CODE_ENHANCED_TELEMETRY_BETA, docs/design/telemetry.md)")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------- system usage

def system_report(since: str | None = None, d: Path | None = None) -> dict[str, Any]:
    """§24: Claude usage outside every project, from the receiver's system sink: tokens, requests,
    cost and models by cwd and by day. Reads `usage-requests-<day>.jsonl`; one row per `request_id`."""
    from ccp.otel import telemetry_dir  # noqa: PLC0415
    d = d or telemetry_dir()
    files = sorted(f for f in (d.glob("usage-requests-????-??-??.jsonl") if d.is_dir() else [])
                   if not since or f.stem[-10:] >= since[:10])
    reqs = list({r.get("request_id") or f"_{f.name}:{i}": r
                 for f in files for i, r in enumerate(_jsonl(f))}.values())
    by_cwd: dict[str, dict[str, Any]] = {}
    by_day: dict[str, dict[str, Any]] = {}
    total = _blank()
    for r in reqs:
        day = str(r.get("at") or "")[:10]
        if since and day and day < since[:10]:
            continue
        _add(total, r)
        _add(by_cwd.setdefault(str(r.get("cwd") or "(unknown session)"), _blank()), r)
        if day:
            _add(by_day.setdefault(day, _blank()), r)
    return {"since": since, "sink": str(d), "files": len(files), "total": _out(total),
            "by_cwd": {k: _out(v) for k, v in sorted(by_cwd.items(), key=lambda kv: -sum(kv[1][t] for t in TOKENS))},
            "by_day": {k: _out(v) for k, v in sorted(by_day.items())}}


def system_table(report: dict[str, Any]) -> str:
    def k(n: int) -> str:
        return f"{n / 1000:.0f}k" if n >= 1000 else str(n)

    def line(name: str, u: dict[str, Any], width: int) -> str:
        return (f"{name:<{width}} {k(sum(u[t] for t in TOKENS)):>7} {k(u['output_tokens']):>6} {u['requests']:>5} "
                f"{u['cost_usd']:>8.2f}  {','.join(u['observed_models']) or '-'}")
    if not report["total"]["requests"]:
        return f"no system usage recorded in {report['sink']}" + (f" since {report['since']}" if report["since"] else "")
    width = max([len("CWD")] + [len(c) for c in report["by_cwd"]])
    head = f"{'TOKENS':>7} {'OUT':>6} {'REQ':>5} {'COST$':>8}  MODELS"
    lines = [f"{'CWD':<{width}} {head}"] + [line(c, u, width) for c, u in report["by_cwd"].items()]
    lines += ["", f"{'DAY':<10} {head}"] + [line(dy, u, 10) for dy, u in report["by_day"].items()]
    lines += ["", line("total", report["total"], 10),
              "outside every project; cost is Claude Code's client-side estimate (§24.4)"]
    return "\n".join(lines)


def system_main(argv: list[str]) -> int:
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(prog="ccp usage --system")
    ap.add_argument("--system", action="store_true", required=True)
    ap.add_argument("--since", help="YYYY-MM-DD: only from this day (UTC)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.since and not (len(a.since) == 10 and _t(a.since + "T00:00:00Z") is not None):
        print("ccp usage --system: --since takes YYYY-MM-DD", file=sys.stderr)
        return 2
    r = system_report(a.since)
    print(json.dumps(r, indent=2) if a.json else system_table(r))
    return 0
