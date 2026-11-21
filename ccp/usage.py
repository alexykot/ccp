"""Usage, model and effort per run (SPEC §24.5, docs/design/telemetry.md), and the allowance (§25.1).

The join, from the spike (docs/design/telemetry.md):

- a span whose `agent_id` is a bound run's `agent_id` → that worker run;
- a span `agent_id` of `<name>@session-…` → that teammate (the runner's name, `runner`, or a name a rotation bound, → the runner seat);
- a request with no `agent_id`, from the main thread → the lead (the design seat);
- a request with no span (no traces) and `query_source: agent:*` → the one run open at that time
  whose model and effort match, else unattributed.

The fold reads `board/usage-requests.jsonl` and `board/usage-spans.jsonl` (written by
`ccp otel serve`) and the run records. It writes nothing but returns per-run, per-seat and
coverage figures, and flags a run whose observed model or effort differs from what its
definition pins (an alias pin, §2.4, matches any full id of its family: `models.matches`; so does the
window join). With plane.json `usage.advice` it also advises on cost (§24.6): short-lived cache writes,
an oversized context, a high coordination share (`cost_advice`), from the requests since the advice's
start (`advice_start`: `--since`, else `window_hours` back, else every request), each line naming it.

It also keeps each run's and seat's latest requests (`recent`: time, model, effort, query source,
session, tokens), from which the board's live seats read the model and effort now in use, and each
run's request intervals (`timeline`: when a request was in flight), from which the board's drill-down
takes model time (ccp/drill.py). `by_model` compares one seat's tasks by the model they ran on
(`ccp usage --by-model`, §2.4: the trial of plane.json `models.implementer_small` and `models.implementer_refactor`). Headless runs
(architect passes, triage) are recorded from `claude -p`'s own `modelUsage` in
`board/headless-usage.jsonl`.

The allowance (§25.1) is read through one reader per machine (`reading`): a cache per allowance command
beside the machine file, under its lock, keeps the last good reading's raw windows, reuses it for
READ_TTL_S and backs off after a failed read; each product appends its own sample, its fields worked out
by its own `project`. A failed sample is never judged: the rules that stop work judge the latest good
sample (`latest_good`) while its window is open, the rules that let work through the reading in force
(`in_force`), and the account unread for UNREAD_STOP_S stops a new claim (`checkpoint_stop`, §25.3).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccp import config, models, runs
from ccp.config import PARALLEL_DEFAULTS, TELEMETRY_DEFAULTS, Config
from ccp.queue import QueueError, emit, iso, lib, runner_names

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
    the derived runner worktree (`lib.runner_worktree`), and with several runners (§16.4) each slot's own
    (`-<slot>`, or as recorded)."""
    import os  # noqa: PLC0415
    from ccp.queue import lib  # noqa: PLC0415
    data = lib.binding_data(q)
    root, wt = lib.binding_str(data, "product_root"), lib.runner_worktree(q)
    # a relative recorded worktree is the product root's, as `ccp tasks worktree` reads it (§16.5)
    at = lambda p: os.path.realpath(p if os.path.isabs(p) or not root else os.path.join(root, p))  # noqa: E731
    wts = {at(wt)} if wt else set()
    try:
        from ccp.queue import load_work, runner_slots  # noqa: PLC0415
        for slot, rec in runner_slots(load_work(q)).items():
            for p in (rec.get("worktree"), f"{wt}-{slot}" if wt else None):
                if p:
                    wts.add(at(str(p)))
    except Exception:  # noqa: BLE001  (an unreadable work.json: the binding's one checkout)
        pass
    return os.path.realpath(root) if root else None, wts


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


SINCE_FORMS = "YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ"


def since_epoch(s: str) -> float | None:
    """A `--since` value as epoch seconds: `YYYY-MM-DD` (that day's midnight, UTC) or `YYYY-MM-DDTHH:MM:SSZ`;
    None for any other value."""
    import re  # noqa: PLC0415
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        s += "T00:00:00Z"
    return _t(s) if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", s) else None


def advice_start(knobs: dict[str, Any] | None, since: float | None = None, now: float | None = None) -> float | None:
    """§24.6: where the cost advice starts reading requests: `since` (epoch seconds) when given, else plane.json
    `usage.advice.window_hours` before `now`, to the second; None, every request, when that is 0."""
    if since is not None:
        return since
    hours = int((knobs or {}).get("window_hours") or 0)
    return None if hours <= 0 else float(int(time.time() if now is None else now) - hours * 3600)


def fold(q: Path, task_id: str | None = None, design_seat: dict[str, str] | None = None,
         knobs: dict[str, Any] | None = None, advice_since: float | None = None) -> dict[str, Any]:
    """Every request attributed to a run or a seat (the module docstring), and the advice: the design seat's
    model and effort against `design_seat` (§24.5; `config.design_seat`, which follows `models.lead`) and, with
    `knobs` (plane.json `usage.advice`), the cost advice (§24.6, `cost_advice`). The cost advice reads only the requests whose `at` is at or after
    `advice_since` (epoch seconds; None: every request), and each of its lines ends naming that start
    (`advice_since` in the result, UTC); every other figure reads every request."""
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
    # §24.6, the cost advice's own figures, from the requests since `advice_since` only:
    contexts: dict[str, list[int]] = {}  # seat → each request's context; the lead's are in lead_calls
    lead_calls: list[tuple[str, Any, int, int]] = []  # the lead's (session, model, tokens, context), for its median
    adv_seats: dict[str, dict[str, Any]] = {}  # seat → its figures
    adv_runs: set[str] = set()  # the worker runs with requests
    run_models: dict[str, dict[str, float]] = {}  # run → model → its cost (§2.4, `by_model`)
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
        if (run is not None or seat is not None) and (
                advice_since is None or (_t(req.get("at")) or float("-inf")) >= advice_since):
            _add(adv_seats.setdefault(bucket, _blank()), req)
            if run is not None:
                adv_runs.add(run["run_id"])
            ctx = sum(int(_n(req.get(k))) for k in CONTEXT_TOKENS)
            if run is None and seat == "design-seat":
                lead_calls.append((str(req.get("session_id") or ""), req.get("model"),
                                   sum(int(_n(req.get(k))) for k in TOKENS), ctx))
            else:
                contexts.setdefault((run.get("seat") or "worker") if run is not None else str(seat), []).append(ctx)
        if run is not None:
            iv = _interval(req, span)
            if iv is not None:
                timeline.setdefault(run["run_id"], []).append(iv)
            acc = per_run.setdefault(run["run_id"], _blank())
            _add(acc, req)
            if req.get("model"):
                mc = run_models.setdefault(run["run_id"], {})
                mc[str(req["model"])] = mc.get(str(req["model"]), 0.0) + _n(req.get("cost_usd"))
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
            if r.get("expected_model") and u["observed_models"] \
                    and not all(models.matches(m, r["expected_model"]) for m in u["observed_models"]):
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
        if design_seat.get("model") and not any(str(m).startswith(design_seat["model"])
                                                or models.matches(m, design_seat["model"]) for m in lead["models"]):
            advice.append(f"the design seat ran on {', '.join(sorted(lead['models']))}; the operator expects {design_seat['model']}")
        if design_seat.get("effort") and design_seat["effort"] not in lead["efforts"]:
            advice.append(f"the design seat ran at effort {', '.join(sorted(lead['efforts']))}; the operator expects {design_seat['effort']}")
    if knobs is not None:
        if lead_calls:
            contexts["design-seat"] = main_model_contexts(lead_calls)
        start = f" (requests since {_utc(advice_since)})" if advice_since is not None else " (every request)"
        advice += [line + start for line in
                   cost_advice({k: _out(v) for k, v in adv_seats.items()}, contexts, knobs, worker_runs=len(adv_runs))]
    return {"advice_since": None if advice_since is None else _utc(advice_since),
            "recent": {k: {key: sorted(v, key=lambda x: str(x.get("at") or ""))[-RECENT:] for key, v in d.items()}
                       for k, d in recent.items()},
            "timeline": timeline, "run_models": run_models, "runs": rows, "task_id": task_id, "task_total": task_total, "advice": advice, "daily": daily,
            "seats": {k: _out(v) for k, v in sorted(seats.items())},
            "unattributed": _out(unattributed), "unattributed_sources": stray, "total": tot, "how": how,
            "other_sessions": dict(sorted(others.items(), key=lambda kv: -kv[1])),
            "coverage": round(attributed / all_tokens, 4) if all_tokens else None,
            "traces": bool(spans), "headless": headless}


COORDINATION = ("design-seat", "runner")  # the lead and the runner: the seats that coordinate the workers (§24.6)
CONTEXT_SETTING = {"design-seat": "with autoCompactWindow (.claude/settings.json)",
                   "runner": "by rotating it sooner (`team.sh runner rotate`, SPEC §10.2)"}


def main_model_contexts(calls: list[tuple[str, Any, int, int]]) -> list[int]:
    """The contexts of the lead's calls on its session's main model, the model of most of that session's
    tokens: its helper calls (titles and the like, on another model) are left out of its median (§24.6).
    `calls` are (session, model, tokens, context)."""
    per: dict[str, dict[str, int]] = {}
    for sid, model, tokens, _ctx in calls:
        m = per.setdefault(sid, {})
        m[str(model)] = m.get(str(model), 0) + tokens
    main = {sid: max(m.items(), key=lambda kv: (kv[1], kv[0]))[0] for sid, m in per.items()}
    return [ctx for sid, model, _tokens, ctx in calls if str(model) == main[sid]]


def cost_advice(seats: dict[str, dict[str, Any]], contexts: dict[str, list[int]], knobs: dict[str, Any],
                worker_runs: int = 0) -> list[str]:
    """§24.6: one advice line per measure past its plane.json `usage.advice` threshold, naming the seat, the
    measure and the setting that fixes it. `seats` are the fold's per-seat figures, `contexts` each seat's
    request contexts (input, cache read and cache written), `worker_runs` the runs with requests: the
    coordination share is advised only once a worker has run, since before that it is the whole cost.
    Advice only: nothing is changed."""
    import statistics  # noqa: PLC0415
    pct = lambda x: f"{x * 100:.0f}%"  # noqa: E731
    out = []
    for name, u in sorted(seats.items()):
        written = u.get("cache_creation_tokens") or 0
        share = (u.get("cache_creation_5m_tokens") or 0) / written if written > 0 else 0.0
        if share > knobs["cache_5m_share"]:
            out.append(f"{name}: {pct(share)} of its cache-write tokens are 5-minute writes (above "
                       f"{pct(knobs['cache_5m_share'])}): set subagentPromptCacheTtl to 1h")
    for name in COORDINATION:
        if contexts.get(name) and (m := statistics.median(contexts[name])) > knobs["context_tokens"]:
            out.append(f"{name}: median context {m:.0f} tokens per request (above {knobs['context_tokens']}): "
                       f"lower it {CONTEXT_SETTING[name]}")
    total = sum(u.get("cost_usd") or 0 for u in seats.values())
    coord = sum((seats.get(n) or {}).get("cost_usd") or 0 for n in COORDINATION)
    if worker_runs > 0 and total > 0 and coord / total > knobs["coordination_share"]:
        out.append(f"coordination (design-seat plus runner) is {pct(coord / total)} of all seats' cost (above "
                   f"{pct(knobs['coordination_share'])})")
    return out


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
        if r.get("expected_model") and req.get("model") and not models.matches(req["model"], r["expected_model"]):
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
    if not keys or not p.is_file():
        return None
    with p.open() as fh:  # the file is large: stream it, and parse only the lines that may match
        for line in fh:
            if not any(k in line for k in keys):
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


def account(cfg: Config) -> dict[str, Any]:
    """The facts about the Claude account on this machine, the one place that reads them (§25): the
    allowance command (`allowance_cmd`, or None) and the weekly stop (`stop_weekly`, default 90), each the
    machine file's (§8.3) when it sets it, else plane.json's old `telemetry` key; the usage
    windows (`windows`: each name's rule {kind, stop_pct, park_pct}; the built-in seven_day, weekly, stopping
    at `stop_weekly`, and five_hour, session, parking at `park_pct`, then `telemetry.windows` merged over
    them per name), the session park % (`park_pct`, or None when the park is off), the wake-arm % and the
    wake margin in seconds (`wake_arm_pct`, `wake_margin_s`), and the parallel session ceiling (`ceiling_pct`,
    §16.3 rule 5), each with its default filled in and a null or bad value handled as it always was."""
    D = TELEMETRY_DEFAULTS
    tel = cfg.telemetry or {}
    mine = config.machine_account()
    cmd = mine.get("allowance_cmd") or tel.get("allowance_cmd") or None
    stop = mine.get("allowance_stop_weekly")
    if stop is None:
        stop = tel.get("allowance_stop_weekly")
    if stop is None:
        stop = config.ALLOWANCE_STOP_WEEKLY_DEFAULT
    park = _num_or_none(tel.get("session_park_pct", D["session_park_pct"]))
    windows: dict[str, dict[str, Any]] = {
        "seven_day": {"kind": "weekly", "stop_pct": stop, "park_pct": None},
        "five_hour": {"kind": "session", "stop_pct": None, "park_pct": park}}
    for name, w in (tel.get("windows") or {}).items():
        base = windows.get(name, {"kind": "weekly", "stop_pct": None, "park_pct": None})
        windows[name] = {**base, **{k: (_num_or_none(v) if k != "kind" else v) for k, v in w.items()}}
    margin = tel.get("session_wake_margin_s", D["session_wake_margin_s"])
    return {"allowance_cmd": cmd,
            "stop_weekly": stop,
            "windows": windows,
            "park_pct": park,
            "wake_arm_pct": (_num_or_none(tel.get("session_wake_arm_pct", D["session_wake_arm_pct"]))
                             or float(D["session_wake_arm_pct"])),
            "wake_margin_s": (int(margin) if isinstance(margin, int) and not isinstance(margin, bool)
                              else D["session_wake_margin_s"]),
            "ceiling_pct": (getattr(cfg, "parallel", None) or PARALLEL_DEFAULTS)["session_ceiling_pct"]}


def usage_read(cfg: Config) -> bool:
    """§25.1: an allowance command is set, so usage is read. Without one nothing is sampled and nothing bounds spend."""
    return bool(account(cfg)["allowance_cmd"])


def unread_warning() -> str:
    """§25.1: the one warning given when no allowance command is set (`ccp init`, the session-start check)."""
    return ("no usage is read and nothing bounds spend: no `allowance_cmd` is set in the machine file "
            f"{lib.machine_path()}, so the weekly stop and the session park have no reading to act on "
            "(SPEC §25.1)")


def window_rules(cfg: Config) -> dict[str, dict[str, Any]]:
    """Each known window's rule {kind, stop_pct, park_pct}, as `account` builds them."""
    return account(cfg)["windows"]


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


# ------------------------------------------------------------------------------------- the shared reader

# §25.1: one reader per machine. None of these is a setting.
READ_TTL_S = 60           # a good reading younger than this is reused: the command does not run
BACKOFF_MIN_S = 60        # after a failed read, no caller runs the command for this long,
BACKOFF_MAX_S = 900       # doubling at each further failure up to this,
RETRY_AFTER_MAX_S = 3600  # or for the `retry_after_s` the command printed, when longer, up to this
IN_FORCE_S = 900          # the reading in force: the latest good sample no older than this
UNREAD_STOP_S = 3600      # the account unread this long, a new claim stops at the checkpoint (§25.3)
# Test-only: every call runs the command, with no cache, no reuse and no backoff, as before the shared
# reader; its rows say `shared: false` (tests/__init__.py sets it, so a test's stub reaches no other test).
UNSHARED_ENV = "CCP_ALLOWANCE_UNSHARED"
FIELDS = ("five_hour", "seven_day", "resets_at", "five_hour_resets_at")  # what `allowance/sample` carries


def now() -> float:
    """The one clock of the shared reader and of every judgment on its readings (§25.1)."""
    return time.time()


def good(windows: Any) -> bool:
    """§25.1: a reading is good when at least one of its windows has a figure."""
    return isinstance(windows, list) and any(isinstance(w, dict) and w.get("pct") is not None for w in windows)


def _row_windows(row: dict[str, Any]) -> list[dict[str, Any]]:
    """A sample's windows; a row written before the usage windows has none listed, and its legacy
    figures stand for its built-in windows."""
    if isinstance(row.get("windows"), list):
        return [w for w in row["windows"] if isinstance(w, dict) and isinstance(w.get("name"), str)]
    return [{"name": wname(row, kind), "pct": _num_or_none(row.get(f)), "resets_at": row.get(r)}
            for kind, f, r in (("weekly", "seven_day", "resets_at"), ("session", "five_hour", "five_hour_resets_at"))]


def good_row(row: Any) -> bool:
    """§25.1: a sample that is not `failed: true` and whose windows are a good reading."""
    return isinstance(row, dict) and not row.get("failed") and good(_row_windows(row))


def _when(v: Any) -> float | None:
    """A recorded time as epoch seconds: an ISO time, or a number; None for anything else."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return _ts(v)


def _rows(q: Path) -> list[dict[str, Any]]:
    return _jsonl(q / "board" / "allowance.jsonl")


def latest_good(q: Path) -> dict[str, Any] | None:
    """§25.1: the product's latest good sample, of any age, or None."""
    return next((r for r in reversed(_rows(q)) if good_row(r)), None)


def fresh(row: dict[str, Any] | None, t: float) -> bool:
    """A sample no older than IN_FORCE_S at `t`."""
    at = _when((row or {}).get("at"))
    return at is not None and t - at <= IN_FORCE_S


def in_force(q: Path, t: float | None = None) -> dict[str, Any] | None:
    """§25.1: the reading in force, the latest good sample when it is no older than IN_FORCE_S; else None."""
    row = latest_good(q)
    return row if fresh(row, now() if t is None else t) else None


def unread_since_log(rows: list[dict[str, Any]]) -> float | None:
    """When the account went unread, from a product's own samples: the first failed sample after its latest
    good one, or the log's first failed sample when none is good; None when the latest sample is good."""
    last_good = max((i for i, r in enumerate(rows) if good_row(r)), default=-1)
    return next((_when(r.get("at")) for r in rows[last_good + 1:]), None)


def next_backoff(prev_s: Any) -> float:
    """§25.1: the backoff after a failure: BACKOFF_MIN_S on the first, doubling on each further one up to BACKOFF_MAX_S."""
    prev = _num_or_none(prev_s)
    return float(BACKOFF_MIN_S) if not prev or prev <= 0 else float(min(prev * 2, BACKOFF_MAX_S))


def backoff_end(at: float, backoff_s: float, retry_after_s: float | None) -> float:
    """When a backoff begun at `at` ends: `backoff_s` on, or the `retry_after_s` the command printed when that
    is longer (at most RETRY_AFTER_MAX_S)."""
    wait = backoff_s if retry_after_s is None else max(backoff_s, min(retry_after_s, RETRY_AFTER_MAX_S))
    return at + wait


def backoff_from_log(rows: list[dict[str, Any]]) -> float | None:
    """§25.1, the reader's fallback without its cache: when the backoff the product's own samples give
    ends. With n failed samples after the latest good one, BACKOFF_MIN_S doubled n-1 times up to
    BACKOFF_MAX_S, raised to the last one's `retry_after_s`, from that sample's `at`. None with no failure."""
    last_good = max((i for i, r in enumerate(rows) if good_row(r)), default=-1)
    failed = rows[last_good + 1:]
    at = _when(failed[-1].get("at")) if failed else None
    if at is None:
        return None
    s = float(min(BACKOFF_MIN_S * 2 ** min(len(failed) - 1, 16), BACKOFF_MAX_S))
    return backoff_end(at, s, _num_or_none(failed[-1].get("retry_after_s")))


def plan_read(cache: dict[str, Any], t: float) -> str:
    """§25.1, under the reader's lock: `backoff` (inside a backoff: the command does not run), `reuse` (the
    last good reading is younger than READ_TTL_S) or `run`."""
    until = _when(cache.get("backoff_until"))
    if until is not None and t < until:
        return "backoff"
    at = _when((cache.get("good") or {}).get("at"))
    if at is not None and good((cache.get("good") or {}).get("windows")) and t - at < READ_TTL_S:
        return "reuse"
    return "run"


def after_read(cache: dict[str, Any], t: float, wins: list[dict[str, Any]] | None,
               retry_after_s: float | None) -> dict[str, Any]:
    """The reader's cache after the command ran at `t`: a good reading (`wins`) is kept and ends the
    backoff; a failure (`wins` None) keeps the last good reading, starts or doubles the backoff, and
    sets `failing_since` on the first failure only."""
    if wins is not None:
        return {"good": {"windows": wins, "at": _utc(t)}, "failing_since": None, "backoff_s": None, "backoff_until": None}
    s = next_backoff(cache.get("backoff_s"))
    since = cache.get("failing_since") if _when(cache.get("failing_since")) is not None else _utc(t)
    return {"good": cache.get("good"), "failing_since": since, "backoff_s": s,
            "backoff_until": _utc(backoff_end(t, s, retry_after_s))}


def cache_path(cmd: str) -> Path:
    """§8.3, §25.1: the reader's cache for one allowance command, in the machine file's directory."""
    import hashlib  # noqa: PLC0415
    return lib.bindings_dir() / f"allowance-cache-{hashlib.sha256(cmd.encode()).hexdigest()[:12]}.json"


def _run(cmd: str) -> tuple[list[dict[str, Any]], bool, int | None, float | None]:
    """Run the allowance command once: (its windows, read only on exit 0; whether the read is good; the exit
    code, None when it did not exit; the `retry_after_s` it printed). Stdout is parsed whatever the exit, but
    windows only on exit 0. No output text is kept."""
    try:
        r = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, text=True, timeout=8)
    except (OSError, ValueError, subprocess.SubprocessError):
        return [], False, None, None
    try:
        data = json.loads(r.stdout or "")
    except ValueError:
        data = None
    retry = _num_or_none(data.get("retry_after_s")) if isinstance(data, dict) else None
    retry = retry if retry is not None and math.isfinite(retry) and retry >= 0 else None  # `Infinity` is no JSON
    wins = parse_windows(data) if r.returncode == 0 else []
    return wins, r.returncode == 0 and good(wins), r.returncode, retry


def _append(q: Path, row: dict[str, Any]) -> dict[str, Any]:
    p = q / "board" / "allowance.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def _record(cfg: Config, q: Path, t: float, wins: list[dict[str, Any]], ok: bool, code: int | None,
            retry: float | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append the product's sample of a run of the command, and emit `allowance/sample`. A failed run
    is the unknown sample, never zero (a window with no figure keeps its reset), with `failed`, its exit
    and any `retry_after_s`."""
    row: dict[str, Any] = {"at": _utc(t), **project(cfg, wins, q, latest_good(q))}
    if not ok:
        row.update({"failed": True, "exit": code, **({"retry_after_s": retry} if retry is not None else {})})
    row.update(extra or {})
    _append(q, row)
    emit(q, cfg, "", "allowance", "sample", {k: row[k] for k in FIELDS})
    return row


def _reuse(cfg: Config, q: Path, kept: Any) -> dict[str, Any] | None:
    """A reading the command did not take now: appended to the product's samples, its fields worked out
    for this product, with its own `at` and `reused: true`, when it is newer than the product's latest good
    sample. Emits nothing."""
    kept = kept if isinstance(kept, dict) else {}
    at, wins = _when(kept.get("at")), kept.get("windows")
    mine = latest_good(q)
    if at is None or not good(wins) or (mine is not None and (_when(mine.get("at")) or 0) >= at):
        return None
    return _append(q, {"at": _utc(at), **project(cfg, wins, q, mine), "reused": True})


def _load_cache(path: Path) -> dict[str, Any]:
    """The reader's cache; one that is missing or unreadable is empty (it is state, and may be deleted)."""
    try:
        data = json.loads(path.read_text()) if path.is_file() else {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def reading(cfg: Config, q: Path) -> dict[str, Any]:
    """§25.1: take a reading of the machine's allowance command through the one shared reader. Under an
    exclusive lock on the command's cache: inside a backoff nothing runs; a good reading younger than
    READ_TTL_S is reused; otherwise the command runs, and its sample is appended. A reading the command did
    not take now reaches the product's samples (`_reuse`). Returns `ran` (the command ran), `row` (the sample
    this call appended, or None), `unread_since` (epoch seconds: when the current run of failures began, or
    None) and `warnings` (the cache could not be used). No `allowance_cmd`: nothing is read."""
    cmd = account(cfg)["allowance_cmd"]
    out: dict[str, Any] = {"ran": False, "row": None, "unread_since": None, "warnings": []}
    if not cmd:
        return out
    if os.environ.get(UNSHARED_ENV) == "1":
        wins, ok, code, retry = _run(cmd)
        out.update(ran=True, row=_record(cfg, q, now(), wins, ok, code, retry, {"shared": False}))
        out["unread_since"] = unread_since_log(_rows(q))
        return out
    from contextlib import ExitStack  # noqa: PLC0415
    from ccp.queue import file_lock, write_json  # noqa: PLC0415
    path = cache_path(cmd)
    with ExitStack() as stack:
        try:
            stack.enter_context(file_lock(path))
        except OSError as exc:
            return _read_unshared(cfg, q, cmd, out, f"usage reads are not shared: {exc}")
        if not os.access(path.parent, os.W_OK):
            return _read_unshared(cfg, q, cmd, out, f"usage reads are not shared: {path.parent} is not writable")
        cache = _load_cache(path)
        t = now()
        if plan_read(cache, t) != "run":
            out["row"] = _reuse(cfg, q, cache.get("good"))
        else:
            wins, ok, code, retry = _run(cmd)
            out.update(ran=True, row=_record(cfg, q, t, wins, ok, code, retry))
            cache = after_read(cache, t, wins if ok else None, retry)
            try:
                write_json(path, cache)
            except OSError as exc:
                out["warnings"].append(f"usage reads are not shared: {exc}")
        out["unread_since"] = _when(cache.get("failing_since"))
    return out


def _read_unshared(cfg: Config, q: Path, cmd: str, out: dict[str, Any], why: str) -> dict[str, Any]:
    """§25.1, the reader without its cache: from the product's own samples, a good one younger than
    READ_TTL_S is reused and the backoff they give is kept; otherwise the command runs."""
    rows, t = _rows(q), now()
    out["warnings"].append(why)
    last = latest_good(q)
    until = backoff_from_log(rows)
    recent = last is not None and (at := _when(last.get("at"))) is not None and t - at < READ_TTL_S
    if not (until is not None and t < until) and not recent:
        wins, ok, code, retry = _run(cmd)
        out.update(ran=True, row=_record(cfg, q, t, wins, ok, code, retry))
        rows = _rows(q)
    out["unread_since"] = unread_since_log(rows)
    return out


def reader_state(cfg: Config, q: Path) -> dict[str, Any]:
    """What `ccp allowance status` shows of the shared reader (§25.1): `backoff_until`, when the command may
    next run (None outside a backoff), and `unread_since`, when the current run of failed reads began. From
    the cache, read without its lock; under the test-only switch or with no cache, from the product's samples."""
    cmd = account(cfg)["allowance_cmd"]
    if not cmd:
        return {"backoff_until": None, "unread_since": None}
    rows, t = _rows(q), now()
    cache = {} if os.environ.get(UNSHARED_ENV) == "1" else _load_cache(cache_path(cmd))
    if cache:
        until, since = _when(cache.get("backoff_until")), _when(cache.get("failing_since"))
    else:
        until = None if os.environ.get(UNSHARED_ENV) == "1" else backoff_from_log(rows)
        since = unread_since_log(rows)
    return {"backoff_until": _utc(until) if until is not None and until > t else None,
            "unread_since": _utc(since) if since is not None else None}


def unread_minutes(q: Path, read: dict[str, Any], t: float) -> int | None:
    """For how many whole minutes the account has gone unread: since its failures began, else since its
    latest good sample; None when neither is known."""
    since = read.get("unread_since")
    if since is None:
        since = _when((latest_good(q) or {}).get("at"))
    return None if since is None else max(0, int((t - since) // 60))


def reading_warnings(cfg: Config, q: Path, read: dict[str, Any]) -> list[str]:
    """The claim's and the prompt's warnings on a reading (§25.1): the cache could not be used; no
    good reading is in force."""
    out = list(read.get("warnings") or [])
    t = now()
    if usage_read(cfg) and in_force(q, t) is None:
        n = unread_minutes(q, read, t)
        out.append("no good allowance reading in force: the account's usage has gone unread for "
                   f"{'an unknown number of' if n is None else n} minutes (SPEC §25.1)")
    return out


class CheckpointStop(QueueError):
    """§25.3: a new claim refused at the allowance checkpoint (exit 5); `reason` is the notice's
    (`usage unread`, or empty for a weekly checkpoint)."""

    def __init__(self, msg: str, reason: str = ""):
        super().__init__(msg, 5)
        self.reason = reason


def weekly_over(cfg: Config, q: Path, row: dict[str, Any] | None, t: float) -> tuple[dict[str, Any], float] | None:
    """§25.3 on the latest good sample: the first weekly window, by name, at or past its own checkpoint
    while its reset is still ahead (one with no reset time only while the sample is in force); None when none."""
    if row is None:
        return None
    rules, live = window_rules(cfg), fresh(row, t)
    for w in sorted(_row_windows(row), key=lambda w: w["name"]):
        pct = _num_or_none(w.get("pct"))
        if pct is None or window_kind(rules, w["name"]) != "weekly":
            continue
        rt = _ts(w.get("resets_at"))
        if (rt is None and not live) or (rt is not None and rt <= t):
            continue
        cp = checkpoint(cfg, q, w.get("resets_at"), w["name"])
        if cp is not None and pct >= cp:
            return w, cp
    return None


def checkpoint_stop(cfg: Config, q: Path, read: dict[str, Any]) -> CheckpointStop | None:
    """§25.3: why a new claim stops at the allowance checkpoint, or None: a weekly window of the latest good
    sample past its checkpoint (`weekly_over`), or the account unread for UNREAD_STOP_S with no reading in force."""
    if not usage_read(cfg):
        return None
    t = now()
    if over := weekly_over(cfg, q, latest_good(q), t):
        w, stop = over
        resets = w.get("resets_at")
        return CheckpointStop(
            f"allowance checkpoint: the {w['name']} window is at {float(w['pct']):g}%, its checkpoint is {stop:g}% "
            f"(SPEC §25.3); resets {resets or 'at an unknown time'}. Runner: stop and tell the lead. Lead: ask the operator, "
            "and record their decision with `ccp allowance continue --to <percent> --reason \"<their words>\"`")
    since = read.get("unread_since")
    if in_force(q, t) is None and since is not None and t - since >= UNREAD_STOP_S:
        return CheckpointStop(
            f"allowance checkpoint: the account's usage has not been read for {int((t - since) // 60)} minutes "
            "(SPEC §25.3). Runner: stop and tell the lead. Lead: check `allowance_cmd`, run `ccp allowance status "
            "--sample` until it shows a good reading, then tell the runner to resume; no decision is recorded",
            "usage unread")
    return None


def claim_reading(cfg: Config, q: Path, new: bool = True) -> dict[str, Any]:
    """§25.1, §25.3: the claim's reading (`reading`); a `new` claim at the allowance checkpoint raises
    `CheckpointStop` (exit 5). A resumed claim of a runner's own lease is never refused."""
    read = reading(cfg, q)
    if new and (stop := checkpoint_stop(cfg, q, read)):
        raise stop
    return read


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
    the machine's `allowance_stop_weekly`), raised by the operator's decisions for this window that no counter reset has
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
    last = latest_good(q) or {}  # §25.1: a failed sample is never judged
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
    """The latest sample (`latest`, a failed one included), the latest good one (`latest_good`) and whether
    it is in force (`in_force`, §25.1), the checkpoint in force and this window's decisions, each with
    `lapsed_at` (the counter reset that lapsed it, or None), all of the latest good sample's window.
    `decision_lapsed_at` is the reset that lapsed the latest decision, when that one is no longer in force.
    `backoff_until` is when the shared reader may next run the command (None outside a backoff) and
    `unread_since` when the current run of failed reads began. `usage_read` says whether an allowance command
    is set (§25.1); when it is not, `warning` says that no usage is read and nothing bounds spend."""
    if sample:
        reading(cfg, q)
    last = (_rows(q) or [None])[-1]
    good_last = latest_good(q)
    resets = (good_last or {}).get("resets_at")
    win = wname(good_last, "weekly")
    times = counter_resets(q, resets, win)
    dec = [{**d, "lapsed_at": _lapsed_at(d, times)} for d in decisions(q)
           if wname(d, "weekly") == win and same_window(resets, d.get("resets_at"))]
    read = usage_read(cfg)
    return {"ok": True, "usage_read": read, **({} if read else {"warning": unread_warning()}),
            "latest": last, "latest_good": good_last, "in_force": fresh(good_last, now()), **reader_state(cfg, q),
            "window": win, "checkpoint": checkpoint(cfg, q, resets, win),
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
    acct = account(cfg)
    # the park % is the window's rule now (§25.4), not one stored in the sample
    park = acct["windows"].get(wname(rec, "session"), {}).get("park_pct") if rec and rec.get("session_window") \
        else acct["park_pct"]
    return (park, acct["wake_arm_pct"], acct["wake_margin_s"])


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


def clear_park(cfg: Config, q: Path, tid: str, why: str = "session_reset") -> bool:
    """Lift a 5-hour park on `tid` (a later claim or prompt that passed the gate); False when none. Like the
    park, task-only: work.json changes only when it names this task."""
    from ccp import lifecycle  # noqa: PLC0415
    if not any(p["task_id"] == tid for p in parked(q)):
        return False
    lifecycle.set_wait(cfg, q, "clear", tid, why, task_only=True)
    return True


def _park(cfg: Config, q: Path, tid: str, five: float, park: float, reset: Any, planned: str) -> None:
    from ccp.queue import load_task_state, save_task_state  # noqa: PLC0415
    st = load_task_state(q, tid)
    if st.get("waiting_on") == "quota" and st.get("quota_class") == "session" and st.get("planned_resume_at") == planned:
        return  # parked already, for this window
    if not st:  # a refused new claim: a queue file of its own carries the wait (the hook and --fire read it)
        save_task_state(q, tid, {"task_id": tid, "project_id": cfg.project_id, "status": "pending", "lease_holder": None})
    from ccp import lifecycle  # noqa: PLC0415
    # task-only: a refused new claim never overwrites work.json's account of the task in flight
    lifecycle.set_wait(cfg, q, "set", tid, "quota", task_only=True, quota_class="session",
                       detail=f"5-hour window at {five:g}% (park at {park:g}%)", resets_at=reset or planned,
                       planned_resume_at=planned)


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


def session_gate(cfg: Config, q: Path, tid: str, step: str) -> list[str]:
    """§25.4: when the latest good sample (§25.1) shows the session window at or past the park % and its
    reset still ahead (with no reset time, only while that sample is in force), park `tid` and refuse
    (exit 6); otherwise lift any park the task had once the window is free (the reading in force shows it
    known and under the park, or no 5-hour limit; the latest good sample's reset has passed; or the park is
    off), and warn from the arm % while no wake is armed for this window. With no good sample whose window
    is still open nothing parks. Best effort: any failure but the park itself is a warning (`session_step`)."""
    rec = latest_good(q)
    t = now()  # the one clock (§25.1)
    live = rec if fresh(rec, t) else None
    park, arm, margin = session_settings(cfg, rec)
    five = _num_or_none((rec or {}).get("five_hour"))
    reset = (rec or {}).get("five_hour_resets_at")
    rt = _ts(reset)
    if park is not None and five is not None and five >= park and (rt is not None and rt > t or rt is None and live):
        if rt is not None:
            planned = _utc(wake_time(rt, margin))
        else:  # a retry: a live retry park keeps its time, so a refusal never pushes it out again
            from ccp.queue import load_task_state  # noqa: PLC0415
            st = load_task_state(q, tid)
            held = st.get("waiting_on") == "quota" and st.get("quota_class") == "session" \
                and st.get("planned_resume_at") and not expired(st, t)
            planned = st["planned_resume_at"] if held else _utc(t + PARK_RETRY_S)
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
    # lifted only when the window is free: the reading in force shows it known and under the park %, the
    # latest good sample's reset has passed, or the park is off. With none in force a live park is kept
    from ccp.parallel import no_five_hour_limit  # noqa: PLC0415
    # §25.2: a weekly-only reading means no 5-hour limit (since 2026-10-31): the window is free
    free = park is None or (live is not None and five is not None and five < park) or (rt is not None and rt <= t) \
        or no_five_hour_limit(live)
    for x in [tid, *(_held_others(cfg, q, tid, parked_too=True) if free else [])]:  # §16.5 rule 6: all held lift too
        if free and clear_park(cfg, q, x):
            out.append(f"{x}: the 5-hour park is lifted" + (f" (the window is at {five:g}%)" if five is not None else ""))
    if park is not None and five is not None and five >= arm and rt is not None and rt > t \
            and armed_wake(q, reset, t) is None:
        out.append(f"5-hour window at {five:g}%: no session wake armed; tell the lead to arm one "
                   "(`ccp allowance session-wake`)")
    return out


def session_step(cfg: Config, q: Path, tid: str, step: str, read: Any = None) -> list[str]:
    """`session_gate`, best effort (claim and prompt): only the park (exit 6) refuses; any other failure
    (a reading, the wait's writer, the wake records) becomes a warning. `read`, when given, is a callable
    that takes the reading first and returns its warnings."""
    warns: list[str] = []
    try:
        if read is not None:
            warns = list(read())
        return warns + session_gate(cfg, q, tid, step)
    except QueueError as e:
        if e.code == PARK_EXIT:
            raise
        return warns + [f"the session park was not checked: {e} (SPEC §25.4)"]
    except Exception as exc:  # noqa: BLE001
        return warns + [f"the session park was not checked: {type(exc).__name__}: {exc} (SPEC §25.4)"]


def session_wake(cfg: Config, q: Path, sample: bool = False, rearm: bool = False) -> dict[str, Any]:
    """`ccp allowance session-wake`: whether the lead should arm a wake now, and the CronCreate call.
    The wake time comes from the reading's `five_hour.resets_at`, never from now + 5 h: the limit is
    usually met well inside the window (e.g. 40 minutes before its reset). With the reset
    unknown, a parked task's retry time (`PARK_RETRY_S`) is the wake. `rearm` (from `--fire` before the
    window reset: the cron fired early, e.g. at a clock change) offers the armed wake again."""
    if sample:
        reading(cfg, q)
    last = latest_good(q) or {}  # §25.1: the window, reset and park of the latest good sample
    park, arm_pct, margin = session_settings(cfg, last or None)
    t = now()
    five, reset = _num_or_none(last.get("five_hour")), last.get("five_hour_resets_at")
    rt = _ts(reset)
    waiting = parked(q)
    retry = min((d for p in waiting if (d := _ts(p.get("planned_resume_at"))) and d > t), default=None)
    out: dict[str, Any] = {"ok": True, "sample_at": last.get("at"), "window": last.get("session_window") or "five_hour",
                           "five_hour": five, "five_hour_resets_at": reset,
                           "park_pct": park, "arm_pct": arm_pct, "margin_s": margin, "parked": waiting,
                           "wake_at": None, "wake_local": None, "cron": None, "armed": None, "prompt": WAKE_PROMPT}
    wt = wake_time(rt, margin) if rt is not None and rt > t else (wake_time(retry, 0) if retry else None)
    if wt is not None:
        out.update(wake_at=_utc(wt), wake_local=_local(wt), cron=cron_for(wt),
                   armed=armed_wake(q, reset if rt is not None and rt > t else None, t, wt))
    arm = False
    if not account(cfg)["allowance_cmd"]:  # §25.1: nothing to sample, with --sample or without
        why = "no allowance_cmd in the machine file: no allowance sample can be taken (SPEC §25.1)"
    elif park is None:
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
            "; its reset is unknown, so the wake is the park's retry" if rt is None or rt <= t else "")
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
    park, _arm, _margin = session_settings(cfg, latest_good(q))
    if park is None:
        raise QueueError("telemetry.session_park_pct is null: the session park and wake are off", 2)
    w = session_wake(cfg, q)
    if not w.get("wake_at"):
        raise QueueError("no 5-hour reset ahead in the latest sample: run `ccp allowance session-wake --sample` "
                         "and arm the wake it prints", 3)
    if w.get("armed"):
        return {"ok": True, "already": True, "armed": w["armed"]}
    reset = w["five_hour_resets_at"] if (_ts(w["five_hour_resets_at"]) or 0) > now() else None
    rec = {"at": iso(), "by": actor("design-seat"), "five_hour_resets_at": reset, "wake_at": w["wake_at"],
           "wake_local": w["wake_local"], "cron": w["cron"], "five_hour": w.get("five_hour")}
    from ccp.queue import append_jsonl  # noqa: PLC0415
    append_jsonl(q / "board" / WAKES, rec)
    emit(q, cfg, "", "allowance", "armed", {"five_hour_resets_at": reset, "wake_at": rec["wake_at"]}, rec["by"])
    return {"ok": True, "already": False, "armed": rec}


def session_fire(cfg: Config, q: Path) -> dict[str, Any]:
    """`ccp allowance session-wake --fire` (the wake's prompt): takes a reading (§25.1) and judges the reading
    in force. The window has reset when its 5-hour figure is under the park %, or its own reset time has
    passed (the endpoint may still show the old window's %); then every parked task whose planned resume is
    due (within FIRE_SLACK_S) is un-parked, and the lead is told how to resume the runner. Otherwise it says
    the window has not reset, with the wake to arm (again)."""
    from ccp.queue import actor, load_work  # noqa: PLC0415
    reading(cfg, q)
    t = now()
    rec = in_force(q, t)
    park, _arm, _margin = session_settings(cfg, rec or latest_good(q))  # the reading's window
    five = (rec or {}).get("five_hour")
    rt = _ts((rec or {}).get("five_hour_resets_at"))
    waiting = parked(q)
    out: dict[str, Any] = {"ok": True, "five_hour": five, "five_hour_resets_at": (rec or {}).get("five_hour_resets_at"),
                           "park_pct": park, "unparked": [], "still_parked": []}
    from ccp.parallel import no_five_hour_limit  # noqa: PLC0415
    # §25.4: a weekly-only reading means no 5-hour limit (since 2026-10-31): every park lifts
    reset = park is not None and (five is not None and five < park or rt is not None and rt <= t
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
        if due is not None and due > t + FIRE_SLACK_S and not nolimit:  # no limit: nothing to wait for
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


# ------------------------------------------------------------------------------------- usage by model

def by_model(q: Path, report: dict[str, Any], seat: str = "implementer") -> dict[str, Any]:
    """§2.4: one seat's work compared by model, for a trial of the `models` block. A task's model is
    the one that carried most of the cost of its first run of the seat (none observed: that run's expected
    model). Per model: the tasks, the seat's cost per task, its rounds per task (the task's runs of the seat,
    leaving out one abandoned before it started) and MAJOR review findings per task (the review runs'
    severities, else their reports' `Severity:` lines, as the estimate's actuals read them)."""
    from ccp import estimate  # noqa: PLC0415
    from ccp.queue import load_task_state  # noqa: PLC0415
    cost = {r["run_id"]: r["usage"]["cost_usd"] for r in report.get("runs") or []}
    rm = report.get("run_models") or {}
    tasks: dict[str, list[dict[str, Any]]] = {}
    for r in runs.all_runs(q):
        if r.get("seat") != seat or (r.get("abandoned_at") and not (r.get("agent_id") or r.get("started_at"))):
            continue
        tasks.setdefault(str(r.get("task_id")), []).append(r)
    acc: dict[str, dict[str, Any]] = {}
    for tid, rs in sorted(tasks.items()):
        rs.sort(key=lambda r: (str(r.get("opened_at") or ""), r.get("round") or 0))
        first = rm.get(rs[0]["run_id"]) or {}
        model = max(first, key=lambda m: (first[m], m)) if first else str(rs[0].get("expected_model") or "unknown")
        a = acc.setdefault(model, {"tasks": [], "done": 0, "cost_usd": 0.0, "rounds": 0, "major": 0})
        a["tasks"].append(tid)
        a["done"] += load_task_state(q, tid).get("status") == "done"
        a["cost_usd"] += sum(cost.get(r["run_id"], 0.0) for r in rs)
        a["rounds"] += len(rs)
        a["major"] += estimate._findings(q, tid).get("MAJOR", 0)
    rows = []
    for model, a in sorted(acc.items()):
        n = len(a["tasks"])
        rows.append({"model": model, "tasks": n, "done": a["done"], "cost_usd": round(a["cost_usd"], 4),
                     "cost_per_task": round(a["cost_usd"] / n, 4), "rounds_per_task": round(a["rounds"] / n, 2),
                     "major_per_task": round(a["major"] / n, 2), "task_ids": a["tasks"]})
    return {"seat": seat, "models": rows}


def by_model_table(r: dict[str, Any]) -> str:
    if not r["models"]:
        return f"no {r['seat']} runs recorded yet"
    width = max(len("MODEL"), *(len(m["model"]) for m in r["models"]))
    lines = [f"{'MODEL':<{width}} {'TASKS':>5} {'DONE':>4} {'COST$/TASK':>10} {'ROUNDS/TASK':>11} {'MAJOR/TASK':>10}"]
    for m in r["models"]:
        lines.append(f"{m['model']:<{width}} {m['tasks']:>5} {m['done']:>4} {m['cost_per_task']:>10.2f} "
                     f"{m['rounds_per_task']:>11.2f} {m['major_per_task']:>10.2f}")
    lines.append(f"seat {r['seat']}; a task counts under the model of its first {r['seat']} run; "
                 "cost is Claude Code's client-side estimate (§24.5)")
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
