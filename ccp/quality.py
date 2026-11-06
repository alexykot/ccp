"""The board's Quality section (SPEC §28.3 priority 4): architect passes and triage, house-rule
checks and budgets, friction notes.

Read only, no LLM call, and nothing the plane does not already record:

- **architect:** `architect.json` (passes, their status and the triage outcome), each report's
  `reviews/<id>.json` (finding severities and categories) and `<id>.triage.json` (dispositions),
  `ccp architect due`'s reasons computed without writing (`due_info(record=False)`), and the task
  log for the state of the tasks each triage created;
- **rules:** the rules doc's shape (`rules.check_doc`, no product command is run), the
  `architect.checks` ids (the verifier runs them; no result is recorded, so none is shown), and
  each `architect.budgets` entry measured over tracked files (`rules.budget_status`);
- **suite:** `health/metrics.jsonl`'s suite series (`health.suite_trend`): cold runs (the suite's
  time, a product's watch on it), and warm, part-lane and unverified runs apart from them (§27.2);
- **friction:** `health/notes.jsonl` (`ccp report`'s Friction lines, `ccp health note`, and
  `tasks next --allow-overdue`), counted per day, week, seat and source, with the latest few.
  Notes carry no tag or category, so there are no themes.

Free text (a note, a pass's error, a task title) is cut short here and escaped by the page.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ccp import health, refs, rules, tasklog
from ccp.config import Config

PASSES = 20       # the latest passes shown
RECENT = 10       # the latest friction notes shown
DAYS = 28         # friction per day, this many days back
TEXT = 240        # a note's text is cut to this many characters
SEVERITIES = ("critical", "high", "medium", "low", "info")


def _read(p: Path) -> Any:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _cut(s: Any, n: int = TEXT) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _epoch(at: Any) -> float | None:
    return health._epoch(str(at or "")) if at else None


def architect(cfg: Config, q: Path, tasks: list[dict[str, Any]], scope: list[str] | None) -> dict[str, Any] | None:
    """Passes, triage and the cadence; None without the architect block (the seat is off)."""
    if cfg.architect is None:
        return None
    from ccp import architect as arch  # noqa: PLC0415
    a = cfg.architect
    try:
        due = arch.due_info(cfg, q, scope, record=False, tasks=tasks)
    except Exception as exc:  # noqa: BLE001  (a broken state file must not stop the board)
        due = {"due": None, "reason": f"ccp architect due failed: {type(exc).__name__}"}
    st = arch.load(q, reap=False) if (q / "architect.json").is_file() else {"reviews": {}}
    reviews = st.get("reviews") if isinstance(st.get("reviews"), dict) else {}
    good = {rid: rec for rid, rec in reviews.items() if isinstance(rec, dict)}
    unreadable = len(reviews) - len(good)
    by_id = {str(t.get("task_id")): t for t in tasks}
    passes: list[dict[str, Any]] = []
    disp_total: Counter[str] = Counter()
    rule_total: Counter[str] = Counter()
    sev_total: Counter[str] = Counter()
    filed: list[dict[str, Any]] = []
    for rid, rec in sorted(good.items(), key=lambda kv: str(kv[1].get("started_at") or "")):
        try:
            row, rows_filed, counts = _pass(q, rid, rec, by_id)
        except Exception:  # noqa: BLE001  (one bad record or file is counted, never blanks the section)
            unreadable += 1
            continue
        passes.append(row)
        filed += rows_filed
        if rec.get("status") == "triaged":
            sev_total.update(counts[0])
            disp_total.update(counts[1])
            rule_total.update(counts[2])
    last = st.get("last") if isinstance(st.get("last"), dict) else {}
    return _architect_view(cfg, a, due, tasks, passes, filed, sev_total, disp_total, rule_total, last, unreadable,
                           arch.unfinished_backfills({"reviews": good}))


def _int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


def _pass(q: Path, rid: str, rec: dict[str, Any], by_id: dict[str, dict[str, Any]]) \
        -> tuple[dict[str, Any], list[dict[str, Any]], tuple[Counter[str], Counter[str], Counter[str]]]:
    """One pass's row, the tasks its triage filed, and its severity and disposition counts."""
    rep = _read(q / "reviews" / f"{rid}.json") or {}
    tri = _read(q / "reviews" / f"{rid}.triage.json") or {}
    rep = rep if isinstance(rep, dict) else {}
    tri = tri if isinstance(tri, dict) else {}
    from ccp.queue import lib  # noqa: PLC0415
    finds = [f for f in _list(rep.get("findings")) if isinstance(f, dict)]
    sev = Counter(str(f.get("severity") or "?") for f in finds)
    cats = Counter(str(f.get("category") or "?") for f in finds)
    disp = Counter(str(d.get("disposition") or "?") for d in _list(tri.get("dispositions")) if isinstance(d, dict))
    rdisp = Counter(str(d.get("disposition") or "?") for d in _list(tri.get("rule_changes")) if isinstance(d, dict))
    created, filed = [], []
    for tid in _list(rec.get("tasks_created")):
        t = by_id.get(str(tid)) or {}
        t_row = {"task_id": str(tid), "status": str(t.get("status") or "unknown"),
                 "kind": tasklog.kind_of(t) if t else None, "title": _cut(t.get("title"), 100) or None}
        created.append(t_row)
        filed.append({**t_row, "review_id": rid})
    row = {
        "review_id": rid, "mode": rec.get("mode"), "status": rec.get("status"), "adr": rec.get("adr"),
        "started_at": rec.get("started_at"), "updated_at": rec.get("updated_at"),
        "triaged_at": rec.get("triaged_at"), "due_reason": _cut(rec.get("due_reason"), 200) or None,
        "error": _cut(rec.get("error"), 200) or None,
        "findings": _int(rec.get("findings", len(finds) if finds else None)), "rule_changes": _int(rec.get("rule_changes")),
        "severity": dict(sev), "categories": dict(cats.most_common(6)), "dispositions": dict(disp),
        "rule_dispositions": dict(rdisp), "tasks_created": created,
    }
    return row, filed, (sev, disp, rdisp)


def _architect_view(cfg: Config, a: dict[str, Any], due: dict[str, Any], tasks: list[dict[str, Any]],
                    passes: list[dict[str, Any]], filed: list[dict[str, Any]], sev_total: Counter[str],
                    disp_total: Counter[str], rule_total: Counter[str], last: dict[str, Any], unreadable: int,
                    backfills: list[Any]) -> dict[str, Any]:
    filed_status = Counter(f["status"] for f in filed)
    try:
        since_refactor = tasklog.features_since_refactor(cfg, tasks) if a["refactor_every"] else None
    except Exception:  # noqa: BLE001  (git unreadable)
        since_refactor = None
    drift = due.get("health") or {}
    return {
        "settings": {k: a[k] for k in ("every_n_tasks", "max_days", "notes_due", "drift_ratio", "grace_tasks",
                                       "triage_grace_tasks", "refactor_every")},
        "due": due.get("due"), "reason": _cut(due.get("reason"), 300), "reasons": [_cut(r, 200) for r in due.get("reasons") or []],
        "done_since_last": due.get("done_since_last"), "days_since_last": due.get("days_since_last"),
        "notes_since_last": due.get("notes_since_last"), "running": due.get("running") or [],
        "awaiting_triage": due.get("awaiting_triage") or [], "shape_due": due.get("shape_due") or [],
        "failed_in_a_row": due.get("failed_in_a_row") or 0,
        "drift": {k: drift.get(k) for k in ("drift_ratio", "drift_limit", "drift", "timed_tasks")} if drift else None,
        "last": {"review_id": last.get("review_id"), "started_at": last.get("started_at"), "at": last.get("at")}
        if last else None,
        "passes": passes[-PASSES:], "passes_total": len(passes),
        "passes_by_status": dict(Counter(str(p["status"] or "?") for p in passes)),
        "severity_total": {k: sev_total[k] for k in [*SEVERITIES, *sorted(set(sev_total) - set(SEVERITIES))] if sev_total[k]},
        "dispositions_total": dict(disp_total), "rule_dispositions_total": dict(rule_total),
        "backfills": len(backfills), "unreadable": unreadable,
        "filed": {"total": len(filed), "by_status": dict(filed_status),
                  "open": [f for f in filed if f["status"] not in ("done", "dropped")][:30]},
        "features_since_refactor": since_refactor,
    }


def house_rules(cfg: Config) -> dict[str, Any] | None:
    """The rules doc's shape, the product checks it names, and each budget now. None without the
    architect block."""
    a = cfg.architect
    if a is None:
        return None
    s = rules.summary(cfg)
    doc = cfg.root / a["rules_doc"] if a["rules_doc"] else None
    parsed = rules.parse_rules(doc.read_text(), refs.ids(cfg))[0] if doc and doc.is_file() else {}
    try:
        budgets = rules.budget_status(cfg)
    except Exception:  # noqa: BLE001
        budgets = []
    return {"rules_doc": s["rules_doc"], "present": s["present"], "rules": s["rules"], "lines": s["lines"],
            "rules_max_lines": s["rules_max_lines"],
            "by_check": dict(Counter(str(k or "none") for k in parsed.values())),
            "doc_errors": [_cut(e, 200) for e in rules.check_doc(cfg)][:20],
            "checks": [c["id"] for c in a["checks"]], "budgets": budgets,
            "budgets_over": sum(1 for b in budgets if b["over"] or b["missing"])}


def friction(q: Path, since: str | None, notes_due: int | None) -> dict[str, Any]:
    """Friction notes: how many, when, from which seat and source, and the latest few."""
    ns = health.notes(q)
    now = datetime.now(timezone.utc)
    days: Counter[str] = Counter()
    weeks: Counter[str] = Counter()
    for n in ns:
        e = _epoch(n.get("at"))
        if e is None:
            continue
        d = datetime.fromtimestamp(e, timezone.utc)
        days[d.strftime("%Y-%m-%d")] += 1
        y, w, _ = d.isocalendar()
        weeks[f"{y}-W{w:02d}"] += 1
    first = (now - timedelta(days=DAYS - 1)).date()
    per_day = {(first + timedelta(days=i)).isoformat(): days.get((first + timedelta(days=i)).isoformat(), 0)
               for i in range(DAYS)}
    s = _epoch(since) if since else None
    week_ago = (now - timedelta(days=7)).timestamp()
    return {"total": len(ns), "since_last_pass": sum(1 for n in ns if s is None or (_epoch(n.get("at")) or 0) > s),
            "notes_due": notes_due, "last_7d": sum(1 for n in ns if (_epoch(n.get("at")) or 0) >= week_ago),
            "per_day": per_day, "per_week": dict(sorted(weeks.items())[-12:]),
            "by_seat": dict(Counter(str(n.get("by") or "unknown") for n in ns).most_common()),
            "by_source": dict(Counter(str(n.get("source") or "unknown") for n in ns).most_common()),
            "top_tasks": Counter(str(n.get("task_id") or "-") for n in ns).most_common(5),
            "recent": [{"at": n.get("at"), "task_id": n.get("task_id"), "by": n.get("by"), "source": n.get("source"),
                        "text": _cut(n.get("text"))} for n in ns[-RECENT:]][::-1]}


def suite_series(q: Path) -> dict[str, Any]:
    """The suite series, cold apart from warm, part and unverified (§27.2)."""
    return health.suite_trend(health._jsonl(q / "health" / "metrics.jsonl"))


def _guard(errors: dict[str, str], name: str, fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001  (one section failing never blanks the others)
        errors[name] = f"{type(exc).__name__}: {exc}"[:200]
        return None


def collect(cfg: Config, q: Path, scope: list[str] | None = None) -> dict[str, Any]:
    """Each section on its own: a section that fails is None and its error is in `errors`."""
    errors: dict[str, str] = {}
    tasks = _guard(errors, "tasks", tasklog.load, cfg)
    arch = _guard(errors, "architect", architect, cfg, q, tasks or [], scope) if tasks is not None else None
    if tasks is None and cfg.architect is not None:
        errors["architect"] = errors["tasks"]
    last = ((arch or {}).get("last") or {}).get("started_at")
    return {"architect": arch, "rules": _guard(errors, "rules", house_rules, cfg),
            "suite": _guard(errors, "suite", suite_series, q),
            "friction": _guard(errors, "friction", friction, q, last, (cfg.architect or {}).get("notes_due")),
            "errors": errors}


def counters(qy: dict[str, Any]) -> dict[str, Any]:
    """The day's quality counters for board/history/<date>.json, which the page draws as trends.
    Only the sections that built: a failed or absent one leaves its keys out, so the snapshot keeps
    the day's earlier values (`board.write` merges)."""
    a, r, f, st = qy.get("architect"), qy.get("rules"), qy.get("friction"), qy.get("suite")
    out: dict[str, Any] = {}
    if isinstance(st, dict):  # each series' median of its last 5 runs: cold is the suite's time
        out.update({f"suite_{k}_s": (st.get(k) or {}).get("median_last5_s") for k in ("cold", "warm", "part")})
    if isinstance(f, dict):
        out.update(friction_total=f.get("total"), friction_since_pass=f.get("since_last_pass"))
    if isinstance(a, dict):
        out.update(passes=a.get("passes_total"), awaiting_triage=len(a.get("awaiting_triage") or []),
                   filed_open=len((a.get("filed") or {}).get("open") or []))
    if isinstance(r, dict):
        out.update(budgets_over=r.get("budgets_over"), rules_lines=r.get("lines"),
                   rule_doc_errors=len(r.get("doc_errors") or []))
    return out


def history(d: Path, days: int = 60) -> list[dict[str, Any]]:
    """The daily snapshots' quality counters, oldest first (only days that recorded them)."""
    out = []
    for f in sorted(d.glob("*.json"))[-days:] if d.is_dir() else []:
        h = _read(f)
        if isinstance(h, dict) and isinstance(h.get("quality"), dict):
            out.append({"date": h.get("date") or f.stem, **h["quality"]})
    return out
