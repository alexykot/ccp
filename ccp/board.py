"""The project board (SPEC §28): one read model, `board.json`, and the page that shows it.

  ccp board build     fold every source into QUEUE_ROOT/board/board.json and write board/index.html
  ccp board status    a terminal summary of the same, with §23.4's exit codes (1: a blocker)
  ccp board task ID   one task's drill-down: where its wall time went (ccp/drill.py); reads only
  ccp board install   a launchd timer that rebuilds it every `board.refresh_minutes` (uninstall, status)

Each §10.3 command that changes delivery state also calls `refresh` once it succeeds: a detached,
debounced `board build --drain` that never blocks, fails or prints into the command (§28.3).

No LLM call, no tokens. The sources are the ones the plane already writes: the queue (work.json,
runs, tasks, gates, questions, proposals), the ledger, `ccp usage`'s fold, `ccp health`'s spans and
rounds, the allowance samples and git. The page embeds the board (a page opened from disk cannot
fetch the file beside it) and reloads itself every minute; each build rewrites it. A daily
snapshot of the counters goes to board/history/<date>.json.
"""
from __future__ import annotations

from ccp.envvars import envvar
from ccp.queue import events_path as _events_path
from ccp.queue import lib

import fcntl
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccp import health, plane, quality, refs, runs, suite, usage
from ccp.config import Config
from ccp.queue import (PLANE, durable_statuses, iso, launchd_bootout, launchd_reload, load_work, preferred_ids, read_json, run_ccp,
                       run_ccp_warning, script_drift)

PAGE = Path(__file__).resolve().parent / "board_page.html"
STALE_MINUTES = 30
SUITE_LIVE_MINUTES = 60  # a suite started this recently with no end yet shows its run is live (a gate typically runs minutes)
LOCK = ".build.lock"    # held (flock) by the one draining build; the kernel drops it if that build dies
DIRTY = ".build.dirty"  # "the state changed since the last build started"
FAILED = ".build.failed"  # the latest build's error, if it failed; cleared by the next build that writes
LOG = ".build.log"        # the drainer's stderr, restarted once it passes LOG_MAX
LOG_MAX = 64 * 1024



def _flight(q: Path, work: dict[str, Any]) -> list[dict[str, Any]]:
    """§16.7: every task the runner holds, with its phase, since when, and what it waits on."""
    from ccp.queue import load_task_state  # noqa: PLC0415
    out = []
    for tid in [str(x) for x in work.get("in_flight") or []]:
        st = load_task_state(q, tid)
        out.append({"task_id": tid, "phase": st.get("status"), "since": st.get("phase_since") or st.get("lease_since"),
                    "waiting_on": st.get("waiting_on"), "peak_in_flight": st.get("peak_in_flight"),
                    "holder": st.get("lease_holder")})  # §16.7: which runner slot holds it
    return out

def _age(p: Path) -> float | None:
    try:
        return round((datetime.now(timezone.utc).timestamp() - p.stat().st_mtime) / 60, 1)
    except OSError:
        return None


def _newest(d: Path, pattern: str = "*") -> Path | None:
    files = [f for f in d.rglob(pattern) if f.is_file()] if d.is_dir() else []
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def _sources(q: Path) -> dict[str, Any]:
    b = q / "board"
    named = {"events": _events_path(q), "work": q / "work.json",
             "usage requests": b / "usage-requests.jsonl", "usage spans": b / "usage-spans.jsonl",
             "allowance": b / "allowance.jsonl"}
    out = {k: {"path": str(v), "age_minutes": _age(v)} for k, v in named.items()}
    newest = _newest(q / "runs", "*.json")
    out["runs"] = {"path": str(q / "runs"), "age_minutes": _age(newest) if newest else None}
    return out


def _live(q: Path, report: dict[str, Any], open_ids: set[str]) -> dict[str, Any] | None:
    """§28: the newest sign that an open run is working, which work.json and runs/*.json (written
    only at phase changes) do not show: its latest telemetry request (`ccp usage`'s `recent`) or its
    latest suite row (`runs/_suites.jsonl`, started or ended), or a suite of it still running (started
    within SUITE_LIVE_MINUTES, no end yet), which counts as now. None when no open run has any."""
    now = datetime.now(timezone.utc).timestamp()
    best: tuple[float, str, str] | None = None
    running: tuple[float, str] | None = None  # the latest still-running suite: (started, run)
    for rid in open_ids:
        for row in (report.get("recent") or {}).get("runs", {}).get(rid) or []:
            t = _ts(row.get("at"))
            if t is not None and (best is None or t > best[0]):
                best = (t, "telemetry", rid)
    try:
        rows = suite.fold(q)
    except Exception:  # noqa: BLE001  (a damaged suites file never breaks the board)
        rows = []
    for row in rows:
        if row.get("run_id") in open_ids:
            for k in ("started_at", "ended_at"):
                t = _ts(row.get(k))
                if t is not None and (best is None or t > best[0]):
                    best = (t, "suite", str(row["run_id"]))
            t = _ts(row.get("started_at"))
            if t is not None and not row.get("ended_at") and now - t <= SUITE_LIVE_MINUTES * 60 \
                    and (running is None or t > running[0]):
                running = (t, str(row["run_id"]))
    if running is not None:
        since = datetime.fromtimestamp(running[0], timezone.utc).strftime("%H:%M")
        return {"via": "suite", "run_id": running[1], "age_seconds": 0,
                "label": f"live (suite running since {since}, {running[1]})"}
    if best is None:
        return None
    age = max(0, int(now - best[0]))
    return {"via": best[1], "run_id": best[2], "age_seconds": age,
            "label": f"live ({best[1]} {_ago(age)}, {best[2]})"}


def _ago(s: int) -> str:
    return f"{s}s ago" if s < 120 else f"{round(s / 60)} min ago"


RESOLVED = ("done", "dropped")


def _resolved(durable: dict[str, str], task_id: Any) -> str | None:
    """The durable status when it is done or dropped (§4: the task file is the source of truth)."""
    st = durable.get(str(task_id or "")) if task_id else None
    return st if st in RESOLVED else None


def _open_items(q: Path, durable: dict[str, str] | None = None) -> dict[str, Any]:
    """Waits, gates and questions that still block. One whose task is done or dropped in its task
    file is resolved: `_divergence` lists it as a stale queue file instead."""
    durable = durable or {}
    waits = []
    for f in sorted((q / "tasks").glob("*.json")) if (q / "tasks").is_dir() else []:
        t = read_json(f, {}) or {}
        tid = t.get("task_id") or f.stem if isinstance(t, dict) else f.stem
        if isinstance(t, dict) and t.get("waiting_on") and t.get("status") not in RESOLVED \
                and not _resolved(durable, tid):
            waits.append({"task_id": tid, "waiting_on": t["waiting_on"], "since": t.get("waiting_on_since")})
    gates = []
    for f in sorted((q / "escalations").rglob("*.json")) if (q / "escalations").is_dir() else []:
        g = read_json(f, {}) or {}
        if isinstance(g, dict) and g.get("status") in lib.OPEN_GATE_STATUSES and not _resolved(durable, g.get("task_id")):
            gates.append({"id": g.get("escalation_id") or f"{f.parent.name}/{f.stem}", "task_id": g.get("task_id"),
                          "class": g.get("class"),
                          "status": g.get("status"), "brief": str(g.get("brief") or "")[:160]})
    questions = []
    for f in _open_questions(q):
        qq = read_json(f, {}) or {}
        if not _resolved(durable, qq.get("task_id")):
            questions.append({"id": qq.get("question_id") or f.stem, "task_id": qq.get("task_id"),
                              "since": qq.get("asked_at")})
    return {"waits": waits, "gates": gates, "questions": questions}


def _open_questions(q: Path) -> list[Path]:
    out = []
    for f in sorted((q / "questions").glob("sm-*.json")) if (q / "questions").is_dir() else []:
        if f.name.endswith(".answer.json") or (q / "questions" / f"{f.stem}.answer.json").exists():
            continue
        qq = read_json(f, {}) or {}
        if isinstance(qq, dict) and qq.get("status", "open") == "open":
            out.append(f)
    return out


def merge_rev(cfg: Config, q: Path) -> str:
    """Where the board reads task merges: the integration branch's remote ref, `origin/<integration>`, so
    a merge shows before the checkout the board is built from pulls it; the local branch without that
    ref; HEAD when neither is here. Nothing is fetched."""
    tip = health.integration_tip(cfg, q)
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(cfg.root), "rev-parse", "--verify", "-q",
                        f"{tip}^{{commit}}"], capture_output=True, text=True)
    return tip if r.returncode == 0 and r.stdout.strip() else "HEAD"


def _tasks(cfg: Config, q: Path, report: dict[str, Any], limit: int = 60) -> tuple[list[dict[str, Any]], dict[str, int]]:
    try:
        h = health.collect(cfg, q, files=True, rev=merge_rev(cfg, q))
    except Exception:  # noqa: BLE001  (git or the queue unreadable: the board still builds)
        h = {"tasks": []}
    week = datetime.now(timezone.utc).timestamp() - 7 * 86400
    counts = {"merged_total": len(h["tasks"]),
              "merged_7d": sum(1 for r in h["tasks"] if (_ts(r.get("merged_at")) or 0) >= week)}
    per_task: dict[str, dict[str, Any]] = {}
    for r in report["runs"]:
        tid = r["run_id"].split("/", 1)[0]
        t = per_task.setdefault(tid, {"tokens": {}, "cost_usd": 0.0, "flags": []})
        u = r["usage"]
        tok = sum(u[k] for k in usage.TOKENS)
        if tok:
            t["tokens"][r["seat"] or "worker"] = t["tokens"].get(r["seat"] or "worker", 0) + tok
        t["cost_usd"] += u["cost_usd"]
        t["flags"] += [f"{r['run_id']}: {f}" for f in r["flags"]]
    suites = suite.safe_totals(q)["by_task"]  # §14.1: data only; the drill-down view comes later
    rows = []
    for row in h["tasks"][-limit:]:
        extra = per_task.get(row["task_id"], {"tokens": {}, "cost_usd": 0.0, "flags": []})
        rows.append({k: row.get(k) for k in ("task_id", "merged_at", "merge_sha", "wall_s", "implementing_s",
                                              "reviewing_s", "verifying_s", "fix_rounds", "review_rounds",
                                              "verify_rounds", "files", "lines", "areas", "metrics", "times",
                                              "prompts", "implement_prompt_chars")}
                    | {"tokens": extra["tokens"], "cost_usd": round(extra["cost_usd"], 4), "flags": extra["flags"]}
                    | _suite_fields(suites.get(row["task_id"])))
    return rows, counts


def _suite_fields(t: dict[str, Any] | None) -> dict[str, Any]:
    """A task row's recorded test time: `suite_s`, `suite_runs` and `suite_killed`, in all and per phase."""
    t = t or {"suite_s": 0.0, "suite_runs": 0, "suite_killed": 0, "phases": {}}
    return {"suite_s": t["suite_s"], "suite_runs": t["suite_runs"], "suite_killed": t["suite_killed"],
            "suite_phases": t["phases"]}


def _ts(s: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _trend(tasks: list[dict[str, Any]], counts: dict[str, int]) -> dict[str, Any]:
    walls = [t["wall_s"] for t in tasks if t.get("wall_s")]
    toks = [sum(t["tokens"].values()) for t in tasks if t.get("tokens")]
    rounds = [r for r in ((t.get("review_rounds") or 0) + (t.get("verify_rounds") or 0) for t in tasks) if r]
    med = lambda xs: statistics.median(xs) if xs else None  # noqa: E731
    return {"median_wall_s_last10": med(walls[-10:]), "median_wall_s_prior10": med(walls[-20:-10]),
            "median_tokens_per_task": med(toks), "median_review_verify_rounds": med(rounds),
            "tasks_merged": counts["merged_total"], "tasks_merged_7d": counts["merged_7d"]}


def _divergence(q: Path, durable: dict[str, str]) -> list[str]:
    """The queue against the task log (§4, §23.5). A task done or dropped in its task file whose
    queue file still says otherwise, waits or holds a lease is stale: `ccp tasks sync` fixes it."""
    out = []
    for f in sorted((q / "tasks").glob("*.json")) if (q / "tasks").is_dir() else []:
        t = read_json(f, {}) or {}
        st, d = t.get("status"), durable.get(f.stem)
        if d in RESOLVED and (st != d or t.get("waiting_on") or t.get("lease_holder")):
            stale = [f"{st or 'no status'} in the queue"] + ([f"waiting on {t['waiting_on']}"] if t.get("waiting_on") else []) \
                + ([f"leased by {t['lease_holder']}"] if t.get("lease_holder") else [])
            from ccp.queue import MID_FLIGHT  # noqa: PLC0415
            hint = (f"ccp tasks drop {f.stem} --reason …: sync skips a task leased mid-flight" if d == "dropped"
                    else "close it: sync skips a task leased mid-flight") \
                if t.get("lease_holder") and st in MID_FLIGHT else "ccp tasks sync"
            out.append(f"{f.stem}: {d} in its task file, {', '.join(stale)} ({hint})")
        elif st == "done" and d is not None and d not in RESOLVED:  # done in both is in step
            out.append(f"{f.stem}: done in the queue, {d} in its task file")
    for f in sorted((q / "escalations").rglob("*.json")) if (q / "escalations").is_dir() else []:
        g = read_json(f, {}) or {}
        if isinstance(g, dict) and g.get("status") in lib.OPEN_GATE_STATUSES and (d := _resolved(durable, g.get("task_id"))):
            out.append(f"gate {g.get('escalation_id') or f'{f.parent.name}/{f.stem}'} {g.get('status')}: "
                       f"{g.get('task_id')} is {d} in its task file")
    for f in _open_questions(q):
        qq = read_json(f, {}) or {}
        if d := _resolved(durable, qq.get("task_id")):
            out.append(f"question {qq.get('question_id') or f.stem} open: {qq.get('task_id')} is {d} in its task file")
    return out


def _refactors_waiting(cfg: Config, scope: list[str]) -> dict[str, Any] | None:
    """§20.4: outstanding refactors outside work.json's scope (neither named nor depended on; all of
    them when it records no scope), and the oldest one's age from its `created` date. None without the architect block (kind is not read)."""
    from ccp import tasklog  # noqa: PLC0415
    if cfg.architect is None:
        return None
    if scope:
        waiting = tasklog.waiting_refactors(cfg, [str(s) for s in scope])
    else:  # no scope recorded: every outstanding refactor is waiting for one
        waiting = [t for t in tasklog.load(cfg) if tasklog.kind_of(t) == "refactor" and t.get("status") == "pending"]
    days = []
    for t in waiting:
        c = _ts(f"{t.get('created')}T00:00:00+00:00") if t.get("created") else None
        days.append(round((datetime.now(timezone.utc).timestamp() - c) / 86400, 1) if c is not None else None)
    known = [(d, str(t.get("task_id"))) for d, t in zip(days, waiting) if d is not None]
    oldest = max(known) if known else None
    return {"count": len(waiting), "ids": [str(t.get("task_id")) for t in waiting][:50],
            "oldest_task_id": oldest[1] if oldest else None, "oldest_age_days": oldest[0] if oldest else None,
            "mode": cfg.architect["refactor_in_scope"]}


def _plan(cfg: Config, q: Path, work: dict[str, Any]) -> dict[str, Any]:
    """§28.3 priority 5 (ccp/plan.py). A failure leaves its error; the rest of the board stands."""
    from ccp import plan  # noqa: PLC0415
    try:
        return plan.collect(cfg, q, work)
    except Exception as exc:  # noqa: BLE001
        return {"errors": {"plan": f"{type(exc).__name__}: {exc}"[:200]}}


def _seats(cfg: Config, q: Path, report: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
    """§28.1 Now: the live seats, their pinned and observed model and effort (ccp/seats.py)."""
    from ccp import seats  # noqa: PLC0415
    try:
        return seats.collect(cfg, q, report, work)
    except Exception as exc:  # noqa: BLE001  (the board still builds; the page says why)
        return {"error": f"{type(exc).__name__}: {exc}"[:200], "rows": []}


def _holds(work: dict[str, Any]) -> list[dict[str, Any]]:
    """§10.4: the lead's holds (work.json `held`, `ccp tasks hold`): `next` passes over these."""
    held = work.get("held") if isinstance(work.get("held"), dict) else {}
    return [{"task_id": t, **(v if isinstance(v, dict) else {})} for t, v in sorted(held.items())]


def build(cfg: Config, q: Path) -> dict[str, Any]:
    tel = cfg.telemetry or {}
    report = usage.fold(q, None, tel.get("design_seat"))
    work = load_work(q)
    open_runs = [{"run_id": r["run_id"], "seat": r.get("seat"), "state": runs.state(r),
                  "opened_at": r.get("opened_at"), "expected_model": r.get("expected_model")}
                 for r in runs.open_on_live_tasks(q, cfg)]  # §11.1: never one of a done or dropped task
    tasks, counts = _tasks(cfg, q, report)
    sources = _sources(q)
    running = work.get("status") in ("running", "draining")
    # §28: work.json and runs/*.json move only at phase changes; an open run's telemetry or suite
    # rows newer than the threshold say the phase is live, not that the source is stale.
    live = _live(q, report, {r["run_id"] for r in open_runs})
    for k in ("work", "runs"):
        v = sources[k]
        if live and live["age_seconds"] <= STALE_MINUTES * 60 and v["age_minutes"] is not None \
                and v["age_minutes"] > STALE_MINUTES:
            v["live"] = live["label"]
    stale = [k for k, v in sources.items() if running and v["age_minutes"] is not None and not v.get("live")
             and v["age_minutes"] > STALE_MINUTES and k in ("events", "work", "runs")]
    proposals = [p for p in plane.proposals(q).values() if p["status"] == "open"]
    durable = durable_statuses(cfg)
    board = {
        "schema_version": 1, "generated_at": iso(), "project_id": cfg.project_id,
        "plane": {"path": str(PLANE), "head": _git_head()},
        "now": {"work": {k: work.get(k) for k in ("status", "task_id", "phase", "phase_since", "review_point",
                                                   "runner_tasks_done", "in_flight", "updated_at")},
                "flight": _flight(q, work),
                "scope_size": len(work.get("scope") or []), "open_runs": open_runs, **_open_items(q, durable),
                "refactors_waiting": _refactors_waiting(cfg, work.get("scope") or []),
                "next_tasks": ({"tasks": ids, "by": work.get("next_task_by"), "at": work.get("next_task_at"),
                                "reason": work.get("next_task_reason") or ""} if (ids := preferred_ids(work)) else None),
                "held": _holds(work),
                "allowance": usage.status(cfg, q, sample=False), "seats": _seats(cfg, q, report, work)},
        "usage": {k: report[k] for k in ("seats", "unattributed", "total", "how", "coverage", "traces", "advice",
                                         "unattributed_sources", "daily")},
        "runs": [r for r in report["runs"] if r["usage"]["requests"] or r["flags"]][-200:],
        "headless": report["headless"][-50:],
        "tasks": tasks, "trend": _trend(tasks, counts),
        "health": {"sources": sources, "stale_sources": stale, "scripts": script_drift(q),
                   "proposals_open": proposals, "divergence": _divergence(q, durable),
                   "last_rebuild_failure": last_failure(q)},
        "plan": _plan(cfg, q, work),
    }
    from ccp.architect import work_scope  # noqa: PLC0415  (the scope `ccp architect due` uses)
    try:
        scope = work_scope(q)
    except Exception:  # noqa: BLE001  (an odd work.json: no review-point trigger on the board)
        scope = None
    board["drill"] = _drill(q, tasks, report)
    board["estimates"] = _estimates(q, cfg)
    board["forecast"] = _forecast(cfg, q, board, work)
    board["quality"] = _quality(cfg, q, scope, board["generated_at"][:10])
    board["blockers"] = _blockers(board)
    return board


def _drill(q: Path, tasks: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    """§28.3: each recent task's drill-down (ccp/drill.py), keyed by task id. A failure leaves it
    empty with its error under `_error`; the rest of the board stands."""
    from ccp import drill  # noqa: PLC0415
    try:
        return drill.collect(q, tasks, report)
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"[:200]}


def _estimates(q: Path, cfg: Config | None = None) -> dict[str, Any]:
    """§26.6: the stored estimate and actual rows, their accuracy and the calibration
    (ccp/estimate.py, ccp/calibrate.py). Reads only (bar the calibration's cache): a build computes
    no estimate. A failure leaves its error; the rest of the board stands."""
    from ccp import estimate  # noqa: PLC0415
    try:
        return estimate.board_view(q, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"[:200], "tasks": {}}


def _forecast(cfg: Config, q: Path, board: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
    """§26.4 phase C: the review point's and the backlog's completion and the allowance projection
    (ccp/forecast.py), from what this build already read. A failure leaves its error; the rest stands."""
    from ccp import forecast  # noqa: PLC0415
    try:
        n = board["now"]
        return forecast.collect(cfg, q, drill=board.get("drill") if isinstance(board.get("drill"), dict) else None,
                                est_tasks=(board.get("estimates") or {}).get("tasks") or {}, work=work,
                                calibration=(board.get("estimates") or {}).get("calibration"),
                                open_items={k: n.get(k) for k in ("waits", "gates", "questions")},
                                allowance=n.get("allowance"),
                                merged=[str(t.get("task_id")) for t in sorted(board.get("tasks") or [],
                                                                              key=lambda t: str(t.get("merged_at") or ""))])
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{type(exc).__name__}: {exc}"[:200]}


def task_text(cfg: Config, q: Path, task: str) -> str:
    """`ccp board task <id>`: one task's drill-down in the terminal. Reads only."""
    from ccp import drill  # noqa: PLC0415
    from ccp.queue import QueueError, task_meta  # noqa: PLC0415
    try:
        tid = str(task_meta(cfg, task)["task_id"])
    except QueueError:
        known = sorted(d.name for d in (q / "runs").iterdir() if d.is_dir()) if (q / "runs").is_dir() else []
        hits = [k for k in known if refs.ids(cfg).same_task(k, task)]
        if len(hits) != 1:
            raise
        tid = hits[0]
    try:
        rows = health.collect(cfg, q, files=False, rev=merge_rev(cfg, q))["tasks"]
    except Exception:  # noqa: BLE001  (git unreadable: an open task's view still prints)
        rows = []
    report = usage.fold(q, None, (cfg.telemetry or {}).get("design_seat"))
    return drill.text(drill.collect(q, rows, report, only=tid)[tid])


def _quality(cfg: Config, q: Path, scope: list[str] | None, day: str) -> dict[str, Any]:
    """§28 priority 4 (ccp/quality.py), with the daily counters so far and today's."""
    try:
        qy = quality.collect(cfg, q, scope)
    except Exception as exc:  # noqa: BLE001  (the board still builds; the page says why)
        err = f"{type(exc).__name__}: {exc}"[:200]
        qy = {"architect": None, "rules": None, "friction": None,
              "errors": {"architect": err, "rules": err, "friction": err}}
    hist = quality.history(q / "board" / "history")
    earlier = next((h for h in hist if h["date"] == day), {})  # this day's last build, kept where a section failed
    qy["history"] = [h for h in hist if h["date"] != day] + [{**earlier, "date": day, **quality.counters(qy)}]
    return qy


def refresh(cfg: Config) -> bool:
    """Rebuild the board soon, without waiting for it: mark it dirty and, unless a build is already
    draining (it will see the mark and build once more), start a detached `board build --drain`.
    Never raises and prints nothing: the command that changed the state keeps its result.
    Skipped without QUEUE_ROOT and when board/ cannot be made. True when a build was started."""
    try:
        if envvar("CCP_NO_BOARD_REFRESH") == "1":
            return False
        qs = os.environ.get("QUEUE_ROOT")
        if not qs or not Path(qs).is_dir():
            return False
        q = Path(qs)
        d = q / "board"
        d.mkdir(parents=True, exist_ok=True)
        (d / DIRTY).touch()
        if _held(d / LOCK):
            return False
        _spawn(cfg, q)
        return True
    except Exception:  # noqa: BLE001  (the board is a view; the command's own result stands)
        return False


def _held(lock: Path) -> bool:
    with lock.open("a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fh, fcntl.LOCK_UN)
        return False


def _spawn(cfg: Config, q: Path) -> None:
    """The drainer imports this plane's ccp, whatever the caller's cwd or PYTHONPATH (as
    architect._spawn does). Its stderr goes to board/.build.log, so a build that keeps failing
    leaves a trace."""
    log = q / "board" / LOG
    mode = "w" if log.is_file() and log.stat().st_size > LOG_MAX else "a"
    boot = f"import sys; sys.path.insert(0, {str(PLANE)!r}); from ccp.cli import main; sys.exit(main(sys.argv[1:]))"
    with log.open(mode) as fh:
        subprocess.Popen([sys.executable, "-c", boot, "--root", str(cfg.root), "board", "build", "--quiet", "--drain"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=fh, cwd=cfg.root,
                         env={**os.environ, "QUEUE_ROOT": str(q)}, start_new_session=True, close_fds=True)


def drain(cfg: Config, q: Path) -> int:
    """`board build --drain`: build while the board is dirty, one drainer at a time. A burst of
    commands during a build costs one more build, not one each. After letting go of the lock it
    looks once more, so a mark set between its last look and the release is not lost. A failed
    build is written to board/.build.failed (which `board status` shows) and to stderr (the log);
    the drainer goes on with any later mark and exits 1."""
    import traceback  # noqa: PLC0415
    d = q / "board"
    d.mkdir(parents=True, exist_ok=True)
    code = 0
    while True:
        with (d / LOCK).open("a") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return code  # another drainer holds it and will see the mark
            while (d / DIRTY).exists():
                (d / DIRTY).unlink(missing_ok=True)
                try:
                    write(q, build(cfg, q))
                except Exception as exc:  # noqa: BLE001
                    code = 1
                    print(f"{iso()} board build failed:\n{traceback.format_exc()}", file=sys.stderr)
                    _atomic(d / FAILED, json.dumps({"at": iso(), "error": f"{type(exc).__name__}: {exc}"[:300]}) + "\n")
            fcntl.flock(fh, fcntl.LOCK_UN)
        if not (d / DIRTY).exists():
            return code


def last_failure(q: Path) -> dict[str, Any] | None:
    f = read_json(q / "board" / FAILED, None)
    return f if isinstance(f, dict) else None


def _git_head() -> str | None:
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(PLANE), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or None


def _blockers(b: dict[str, Any]) -> list[str]:
    out = [f"waiting: {w['task_id']} on {w['waiting_on']}" for w in b["now"]["waits"]]
    out += [f"gate {g['id']} ({g['class']}) {g['status']}" for g in b["now"]["gates"]]
    out += [f"question {q['id']} open" for q in b["now"]["questions"]]
    out += [f"stale source: {s}" for s in b["health"]["stale_sources"]]
    a = b["now"]["allowance"]
    seven = (a.get("latest") or {}).get("seven_day")
    if a.get("checkpoint") is not None and seven is not None and seven >= a["checkpoint"]:
        out.append(f"allowance at the checkpoint: {seven:g}% of {a['checkpoint']:g}%"
                   + (f" (decision lapsed at the counter reset {a['decision_lapsed_at']})" if a.get("decision_lapsed_at") else ""))
    return out


def _atomic(path: Path, text: str) -> None:
    """One writer's tmp per process: the launchd timer and a close may build at the same moment."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    tmp.replace(path)


def embed(board: dict[str, Any]) -> str:
    """The board as a JS literal inside <script>. Every `<`, `>` and `&` is escaped, so no string an
    agent wrote (a gate brief, a proposal) can close the script or open an HTML comment state."""
    s = json.dumps(board, default=sorted)
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def write(q: Path, board: dict[str, Any]) -> dict[str, str]:
    d = q / "board"
    d.mkdir(parents=True, exist_ok=True)
    if isinstance(board.get("health"), dict):
        board["health"]["last_rebuild_failure"] = None  # this build is writing, so that failure is over
    _atomic(d / "board.json", json.dumps(board, indent=2, default=sorted) + "\n")
    _atomic(d / "index.html", PAGE.read_text().replace("/*__BOARD__*/null", embed(board)))
    (d / FAILED).unlink(missing_ok=True)
    day = board["generated_at"][:10]
    h = d / "history" / f"{day}.json"
    h.parent.mkdir(exist_ok=True)
    tot = board["usage"]["total"]
    prev = read_json(h, {}) if h.is_file() else {}
    # A section that failed this build leaves its counters out; the day's earlier values stand.
    q_counts = {**((prev.get("quality") if isinstance(prev, dict) and isinstance(prev.get("quality"), dict) else None) or {}),
                **quality.counters(board.get("quality") or {})}
    _atomic(h, json.dumps({"date": day, "generated_at": board["generated_at"],
                             "tasks_merged": board["trend"]["tasks_merged"],
                             "tokens": sum(tot[k] for k in usage.TOKENS), "cost_usd": tot["cost_usd"],
                             "coverage": board["usage"]["coverage"], "seats": {
                                 k: sum(v[t] for t in usage.TOKENS) for k, v in board["usage"]["seats"].items()},
                             "quality": q_counts},
                           indent=2) + "\n")
    return {"board": str(d / "board.json"), "page": str(d / "index.html")}


def status_text(b: dict[str, Any]) -> str:
    w = b["now"]["work"]
    a = b["now"]["allowance"]
    seven = (a.get("latest") or {}).get("seven_day")
    lines = [f"{b['project_id']}  board {b['generated_at']}  plane {b['plane']['head']}",
             f"runner {w.get('status') or '-'}  "
             f"task {w.get('task_id') or '-'}  phase {w.get('phase') or '-'} since {w.get('phase_since') or '-'}",
             f"allowance weekly {seven if seven is not None else '?'}%  checkpoint "
             f"{a.get('checkpoint') if a.get('checkpoint') is not None else '-'}%"
             + (f"  decision lapsed at the counter reset {a['decision_lapsed_at']}" if a.get("decision_lapsed_at") else ""),
             f"usage coverage {b['usage']['coverage'] * 100:.1f}%" if b["usage"]["coverage"] is not None
             else "usage: none recorded yet"]
    from ccp import seats  # noqa: PLC0415
    lines += seats.status_lines(b["now"].get("seats"))
    nt = b["now"].get("next_tasks")  # §10.4: the lead's `ccp tasks prefer` list
    if nt:
        lines.append(f"next: {', '.join(nt['tasks'])} ({', '.join(x for x in (nt.get('by') or '?', nt.get('reason')) if x)})")
    for h in b["now"].get("held") or []:
        lines.append(f"held: {h['task_id']} ({', '.join(x for x in (h.get('by') or '?', h.get('reason')) if x)})")
    rw = b["now"].get("refactors_waiting")
    if rw and rw["count"]:
        lines.append(f"refactors waiting {rw['count']} outside the scope, oldest {rw['oldest_task_id'] or '?'} "
                     f"({rw['oldest_age_days'] if rw['oldest_age_days'] is not None else '?'} d)")
    lines += _quality_lines(b.get("quality") or {})
    from ccp import plan  # noqa: PLC0415
    lines += plan.status_lines(b.get("plan"))
    for x in b["usage"]["advice"]:
        lines.append(f"advice: {x}")
    f = b["health"].get("last_rebuild_failure")
    if f:
        lines.append(f"last rebuild failed: {f.get('at')} {f.get('error')} (see board/{LOG})")
    lines += [f"source {k}: {v['live']}" for k, v in b["health"]["sources"].items() if v.get("live")]
    lines += [f"BLOCKER {x}" for x in b["blockers"]]
    lines += [f"divergence: {x}" for x in b["health"]["divergence"]]
    return "\n".join(lines)


def _quality_lines(qy: dict[str, Any]) -> list[str]:
    a, r, f = qy.get("architect"), qy.get("rules"), qy.get("friction")
    out = []
    if a:
        last = (a.get("last") or {}).get("review_id") or "none"
        s = a["settings"]
        out.append(f"architect last pass {last}, {a.get('done_since_last')}/{s['every_n_tasks']} tasks and "
                   f"{a.get('notes_since_last')}/{s['notes_due']} notes since; "
                   + ("pass due: " + (a.get("reason") or "") if a.get("due")
                      else a.get("reason") if a.get("running") or a.get("awaiting_triage") or a.get("due") is None
                      else "not due"))
        for w in a.get("awaiting_triage") or []:
            out.append(f"architect {w['review_id']} awaits triage ({w['merges_since']} merge(s) since)")
        if a.get("unreadable"):
            out.append(f"architect {a['unreadable']} pass record(s) unreadable (architect.json or reviews/)")
        fl = a.get("filed") or {}
        if fl.get("open"):
            out.append(f"architect tasks open {len(fl['open'])} of {fl['total']} filed")
    if r and (r.get("budgets_over") or r.get("doc_errors")):
        over = [f"{b['id']} {b['max_path']} {b['max']}>{b['limit']}" for b in r["budgets"] if b["over"]]
        over += [f"{b['id']} {m} missing" for b in r["budgets"] for m in b.get("missing_paths") or []]
        out.append(f"house rules: {r['budgets_over']} budget(s) over" + (f" ({'; '.join(over[:3])})" if over else "")
                   + (f", {len(r['doc_errors'])} rules-doc problem(s)" if r.get("doc_errors") else ""))
    if f and f.get("total"):
        out.append(f"friction notes {f['last_7d']} in 7 days, {f['total']} in all")
    for k, e in sorted((qy.get("errors") or {}).items()):
        out.append(f"quality {k} failed: {e}")
    return out


def _plist(cfg: Config, minutes: int) -> tuple[str, str]:
    from xml.sax.saxutils import escape  # noqa: PLC0415
    from ccp.queue import launchd_prefix  # noqa: PLC0415
    label = f"{launchd_prefix()}.control-plane.board.{cfg.project_id}"
    log = escape(str(Path.home() / "Library" / "Logs" / f"control-plane-board-{cfg.project_id}.log"))
    args = "".join(f"<string>{escape(x)}</string>" for x in (str(run_ccp()), "--root", str(cfg.root),
                                                            "board", "build", "--quiet"))
    return label, (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                   f'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
                   f"<key>Label</key><string>{label}</string><key>ProgramArguments</key><array>{args}</array>"
                   f"<key>StartInterval</key><integer>{minutes * 60}</integer><key>RunAtLoad</key><true/>"
                   f"<key>StandardErrorPath</key><string>{log}</string>"
                   f"<key>StandardOutPath</key><string>{log}</string></dict></plist>\n")


def launchd(cfg: Config, action: str) -> dict[str, Any]:
    minutes = int((cfg.board or {}).get("refresh_minutes") or 5)
    label, text = _plist(cfg, minutes)
    p = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    dom = f"gui/{os.getuid()}"
    if action == "status":
        r = subprocess.run(["launchctl", "print", f"{dom}/{label}"], capture_output=True, text=True)
        return {"ok": r.returncode == 0, "label": label, "plist": str(p), "loaded": r.returncode == 0}
    if action == "uninstall":
        launchd_bootout(label)
        p.unlink(missing_ok=True)
        return {"ok": True, "removed": str(p)}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    r = launchd_reload(label, p, want_running=False)  # StartInterval: idle between builds
    warns = (r.pop("warnings", None) or []) + [w for w in [run_ccp_warning()] if w]
    return {**r, "label": label, "plist": str(p), "every_minutes": minutes, "ccp": str(run_ccp()),
            **({"warnings": warns} if warns else {})}
