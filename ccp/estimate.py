"""Task estimation, phase A (SPEC §26.3): estimate records, actuals at close, a reference-class
baseline with no LLM, its accuracy, and a backfill over history.

  ccp tasks estimate ID --baseline [--force] [--dry-run]   a baseline row when the task changed
  ccp tasks estimate --all --baseline [--dry-run]          every open task that needs one
  ccp tasks estimate show ID                               a task's rows and the latest of each source
  ccp estimate accuracy [--json]                           estimates against actuals
  ccp estimate backfill [--dry-run]                        baselines for history, with no leakage

**Records.** `QUEUE_ROOT/estimates/<task_id>.jsonl`, append-only. An estimate row is
`{at, as_of, task_id, source, version, task_hash, inputs, phases, total, tokens, cost_usd, rounds,
notes}`; `source` is "baseline" (this module) or "agent" (ccp/estimator.py, phase B: same shape);
`version` counts that source's rows for the task. An actual row (`source: "actual"`) is written by
`ccp tasks close` and by the backfill: wall time, the phases, tokens, cost, rounds and findings,
from the sources the drill-down reads (ccp/drill.py: `ccp health`'s rows, the usage fold, the runs).
Its phases and rounds give merge and ruling rounds their own `merge` and `ruling` buckets, beside
implement, review, fix and verify; an estimate bands only those four.
Every value is a number, an id or a short label: no task text.

**The baseline.** For a task, its features (`features`: kind, the task-id family, the cited path
prefixes, cited files and their lines, ADR, spec and rule refs, dod_checks by kind, dependencies,
text length) are compared with every completed task that has actuals (`similarity`), each score
weighted by recency (a half-life in completed tasks). The k best of the tasks that share the
family, an area or an ADR are the reference class; with fewer than K_MIN of those, the same kind;
then all. P50 and P90 of the class's actuals, per phase and in total, are the estimate; tokens and
cost take their own class from the tasks with telemetry. `plane.json estimate.reference_since`
leaves out tasks merged before a process change.

**No leakage.** The backfill estimates each completed task from the tasks merged before it started,
with its features read as they were before its work: the task file without its Implementation and
Verification notes, and the cited files' lines at the commit it started from (the integration
branch's tip at its start; its merge's first parent when that is unknown).

**Calibration** (phase D, ccp/calibrate.py) is derived at read time: `latest(..., calibrated=True,
cal=model)` and the board's views (`cal`) carry the calibrated bands beside the stored ones; no row
is rewritten.

Estimates are advisory (§26.6): nothing reads them to gate, order or block.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import subprocess
from pathlib import Path
from typing import Any

from ccp import refs, tasklog
from ccp.config import Config
from ccp.queue import append_jsonl, iso

METHOD = "reference-class"
METHOD_V = 1
PHASES = ("implement", "review", "fix", "verify")   # what an estimate bands (the baseline's and the estimator's)
ACTUAL_PHASES = (*PHASES, "merge", "ruling")        # what an actual measures: merge and ruling rounds their own
SOURCES = ("baseline", "agent")
K_DEFAULT = 6
K_MIN = 3
HALF_LIFE = 30          # completed tasks: a task this many completions older weighs half
NOTES = tasklog.NOTES_SECTIONS  # written during the work, not by the task's writer (SPEC §5)
VOLATILE = ("status", "updated", "review_point")        # frontmatter that changes without the task changing
CITE_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_.\-/]*)`")
EXTS = (".py", ".md", ".sql", ".json", ".yaml", ".yml", ".toml", ".sh", ".txt", ".html", ".js", ".ts", ".csv")
MAX_FILE = 5 * 1024 * 1024
SEVERITIES = ("BLOCKER", "MAJOR", "MINOR", "NIT")


# ------------------------------------------------------------------------------------ records

def path(q: Path, tid: str) -> Path:
    return q / "estimates" / f"{tid}.jsonl"


def _parse(text: str) -> list[dict[str, Any]]:
    out = []
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _order(r: dict[str, Any]) -> tuple[str, int]:
    v = r.get("version")
    return str(r.get("at") or ""), v if isinstance(v, int) and not isinstance(v, bool) else 0


def rows(q: Path, tid: str) -> list[dict[str, Any]]:
    """A task's rows, oldest first (a row merged in from the other team sorts by its own time)."""
    p = path(q, tid)
    try:
        return sorted(_parse(p.read_text()), key=_order) if p.is_file() else []
    except OSError:
        return []


def all_rows(q: Path) -> dict[str, list[dict[str, Any]]]:
    d = q / "estimates"
    out: dict[str, list[dict[str, Any]]] = {}
    for f in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        try:
            rs = sorted(_parse(f.read_text()), key=_order)
        except OSError:
            continue
        if rs:
            out[f.stem] = rs
    return out


def latest(rs: list[dict[str, Any]], source: str, before: str | None = None, *, calibrated: bool = False,
           cal: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The newest row of `source`, optionally only those made (`as_of`) at or before `before`. With
    `calibrated` (phase D), a copy whose `total`, `tokens` and `cost_usd` are the calibrated bands of
    `cal` (`calibrate.model`), the stored ones under `raw` and the factors under `calibration`;
    nothing is rewritten. An actual row is returned as it is."""
    mine = [r for r in rs if r.get("source") == source
            and (before is None or str(r.get("as_of") or r.get("at") or "") <= before)]
    r = max(mine, key=lambda r: (str(r.get("as_of") or r.get("at") or ""), _order(r))) if mine else None
    if not calibrated or r is None or source not in SOURCES:
        return r
    if cal is None:
        raise ValueError("latest(calibrated=True) needs the calibration model (cal=calibrate.model(q, cfg))")
    from ccp import calibrate  # noqa: PLC0415
    c = calibrate.apply(r, cal.get("factors"), source) or {}
    return {**r, "total": c.get("total"), "tokens": c.get("tokens"), "cost_usd": c.get("cost_usd"),
            "raw": {k: r.get(k) for k in ("total", "tokens", "cost_usd")}, "calibration": c.get("factors")}


def _version(rs: list[dict[str, Any]], source: str) -> int:
    return 1 + max([int(r["version"]) for r in rs if r.get("source") == source and isinstance(r.get("version"), int)],
                   default=0)


def _append(q: Path, row: dict[str, Any]) -> None:
    append_jsonl(path(q, str(row["task_id"])), row)


# ------------------------------------------------------------------------------------ features

def strip_notes(text: str) -> str:
    """The task as written before the work: the runtime sections and volatile frontmatter left out."""
    for name in NOTES:
        m = re.search(rf"^## {re.escape(name)}[ \t]*$", text, re.M)
        if m:
            nxt = re.search(r"^## ", text[m.end():], re.M)
            text = text[:m.start()] + (text[m.end() + nxt.start():] if nxt else "")
    if text.startswith("---\n") and (end := text.find("\n---\n", 4)) != -1:
        fm = [ln for ln in text[4:end].splitlines() if ln.split(":", 1)[0].strip() not in VOLATILE]
        text = "---\n" + "\n".join(fm) + text[end:]
    return text


def task_hash(text: str) -> str:
    return hashlib.sha256(strip_notes(text.replace("\r\n", "\n")).encode()).hexdigest()[:16]


def family(tid: str, cfg: Config | None = None) -> str:
    return refs.ids(cfg).family(tid) if cfg is not None else refs.DEFAULT.family(tid)


def suffixes(cfg: Config | None) -> tuple[str, ...]:
    """The suffixes that make a backticked token a cited path: `estimate.path_suffixes`, else EXTS."""
    given = ((cfg.estimate or {}).get("path_suffixes") if cfg is not None else None)
    return tuple(given) if given else EXTS


def cited(text: str, cfg: Config | None = None) -> list[str]:
    """Path-like citations in backticks: a slash, or a known suffix (§26.3, `estimate.path_suffixes`);
    no URLs or globs."""
    exts = suffixes(cfg)
    out: list[str] = []
    for c in CITE_RE.findall(text):
        c = c[2:] if c.startswith("./") else c
        if ("/" in c or c.endswith(exts)) and "://" not in c and c not in out and not c.startswith("-"):
            out.append(c.rstrip("/"))
    return out


def _area(p: str) -> str:
    parts = p.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0] if len(parts) == 2 else "."


def _lines_now(root: Path, rels: list[str]) -> dict[str, int]:
    out = {}
    for rel in rels:
        f = root / rel
        try:
            if f.is_file() and f.stat().st_size <= MAX_FILE:
                out[rel] = f.read_bytes().count(b"\n")
        except OSError:
            continue
    return out


def _lines_at(root: Path, rev: str, rels: list[str]) -> dict[str, int]:
    """Each file's lines at `rev` (one `git cat-file --batch`); a path not there is left out."""
    if not rels:
        return {}
    r = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"], input="".join(f"{rev}:{p}\n" for p in rels).encode(),
                       capture_output=True)
    if r.returncode != 0:
        return {}
    out, buf, i = {}, r.stdout, 0
    for rel in rels:
        nl = buf.find(b"\n", i)
        if nl == -1:
            break
        head = buf[i:nl].split()
        i = nl + 1
        if len(head) == 3 and head[1] == b"blob" and head[2].isdigit():
            n = int(head[2])
            if n <= MAX_FILE:
                out[rel] = buf[i:i + n].count(b"\n")
            i += n + 1
        elif len(head) == 3 and head[2].isdigit():  # a tree: not a file
            i += int(head[2]) + 1
    return out


def features(cfg: Config, t: dict[str, Any], rev: str | None = None) -> dict[str, Any]:
    """A task's features, from its file as written before the work (`strip_notes`). With `rev`,
    the cited files' lines are read at that commit (the backfill: the tree before the task merged)."""
    text = strip_notes(str(t.get("_text") or ""))
    tid = str(t.get("task_id") or "")
    paths = cited(text, cfg)
    lines = _lines_at(cfg.root, rev, paths) if rev else _lines_now(cfg.root, paths)
    areas = sorted({_area(p) for p in paths if p in lines or (cfg.root / p.split("/")[0]).is_dir()})
    checks = tasklog.CHECK_RE.findall(tasklog._section(text, tasklog.SEC_CHECKS) or "")
    kinds: dict[str, int] = {}
    for c in checks:
        k = c.rsplit("-", 1)[0]
        kinds[k] = kinds.get(k, 0) + 1
    body = tasklog._section(text, tasklog.SEC_CHECKS) or ""
    adrs = sorted({n for r in tasklog._as_list(t.get("adr_refs")) if (n := tasklog.adr_number(str(r), cfg)) is not None})
    return {"kind": tasklog.kind_of(t), "family": family(tid, cfg), "areas": areas[:20],
            "cited_paths": len(lines), "cited_lines": sum(lines.values()),
            "adr_refs": len(tasklog._as_list(t.get("adr_refs"))), "adrs": adrs[:20],
            "spec_refs": len(tasklog._as_list(t.get("spec_refs"))), "rule_refs": len(tasklog._as_list(t.get("rule_refs"))),
            "dod_checks": len(checks), "dod_kinds": dict(sorted(kinds.items())[:12]),
            "dod_mutation": len(re.findall(r"\bmutation\b", body, re.I)),
            "dod_story": len(re.findall(r"^\s*story:", body, re.M)),
            "deps": len(tasklog._as_list(t.get("depends_on"))), "text_chars": len(text)}


# ------------------------------------------------------------------------------------ similarity

def _jac(a: list[Any], b: list[Any]) -> float | None:
    sa, sb = set(a or []), set(b or [])
    return len(sa & sb) / len(sa | sb) if sa or sb else None


def _close(a: Any, b: Any) -> float:
    return math.exp(-abs(math.log((float(a or 0) + 1) / (float(b or 0) + 1))))


def similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    """0..1: kind, family, shared areas and ADRs, and closeness in size."""
    parts: list[tuple[float, float]] = [(1.0, 1.0 if a.get("kind") == b.get("kind") else 0.0),
                                        (2.0, 1.0 if a.get("family") and a.get("family") == b.get("family") else 0.0)]
    for key, w in (("areas", 2.0), ("adrs", 1.5)):
        j = _jac(a.get(key) or [], b.get(key) or [])
        if j is not None:
            parts.append((w, j))
    for key in ("cited_lines", "dod_checks", "text_chars", "deps"):
        parts.append((0.5, _close(a.get(key), b.get(key))))
    return sum(w * v for w, v in parts) / sum(w for w, _ in parts)


def _related(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return bool((a.get("family") and a.get("family") == b.get("family"))
                or set(a.get("areas") or []) & set(b.get("areas") or []) or set(a.get("adrs") or []) & set(b.get("adrs") or []))


def quantile(xs: list[float], p: float) -> float | None:
    xs = sorted(float(x) for x in xs if x is not None)
    if not xs:
        return None
    pos = (len(xs) - 1) * p
    lo = math.floor(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _band(xs: list[Any], digits: int = 0) -> dict[str, Any] | None:
    vals = [float(x) for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
    if not vals:
        return None
    p50, p90 = quantile(vals, 0.5), quantile(vals, 0.9)
    return {"p50": round(p50, digits) if digits else int(round(p50)), "p90": round(p90, digits) if digits else int(round(p90))}


def _pick(target: dict[str, Any], pool: list[dict[str, Any]], k: int) -> tuple[list[dict[str, Any]], str]:
    """The reference class: (the k best by score, the tier it came from). `pool` is oldest first."""
    n = len(pool)
    scored = [(similarity(target, c["features"]) * 0.5 ** ((n - 1 - i) / HALF_LIFE), i, c) for i, c in enumerate(pool)]
    for tier, keep in (("similar", lambda c: _related(target, c["features"])),
                       ("kind", lambda c: c["features"].get("kind") == target.get("kind")), ("all", lambda c: True)):
        cand = [s for s in scored if keep(s[2])]
        if len(cand) >= K_MIN or (tier == "all" and cand):
            cand.sort(key=lambda s: (-s[0], -s[1]))
            return [c for _, _, c in cand[:k]], tier
    return [], "none"


def baseline(target: dict[str, Any], pool: list[dict[str, Any]], k: int = K_DEFAULT) -> dict[str, Any] | None:
    """The estimate's numbers for features `target` from `pool` (history entries with `actual`, oldest
    first). None when the pool has no task with a wall time."""
    walled = [c for c in pool if (c["actual"].get("wall_s") or 0) > 0]
    ref, tier = _pick(target, walled, k)
    if not ref:
        return None
    tok_pool = [c for c in pool if c["actual"].get("tokens")]
    tok_ref, tok_tier = _pick(target, tok_pool, k) if tok_pool else ([], "none")
    phases = {}
    for ph in PHASES:
        b = _band([(c["actual"].get("phases") or {}).get(ph) for c in ref])
        phases[ph] = {"p50_s": b["p50"], "p90_s": b["p90"]} if b else None
    total = _band([c["actual"]["wall_s"] for c in ref])
    tokens = _band([c["actual"].get("tokens") for c in tok_ref])
    cost = _band([c["actual"].get("cost_usd") for c in tok_ref], 2)
    rr = [((c["actual"].get("rounds") or {}).get("review")) for c in ref]
    fx = [((c["actual"].get("rounds") or {}).get("fix")) for c in ref]
    fx = [x for x in fx if isinstance(x, int)]
    novelty = {"family": sum(1 for c in pool if target.get("family") and c["features"].get("family") == target.get("family")),
               "areas": sum(1 for c in pool if set(c["features"].get("areas") or []) & set(target.get("areas") or [])),
               "adrs": sum(1 for c in pool if set(c["features"].get("adrs") or []) & set(target.get("adrs") or []))}
    return {"phases": phases, "total": {"p50_s": total["p50"], "p90_s": total["p90"]},
            "tokens": tokens, "cost_usd": cost,
            "rounds": {"review_p50": quantile([x for x in rr if isinstance(x, int)], 0.5),
                       "fix_risk": round(sum(1 for x in fx if x > 0) / len(fx), 2) if fx else None},
            "reference_tasks": [c["task_id"] for c in ref], "reference_tasks_tokens": [c["task_id"] for c in tok_ref],
            "tier": tier, "tokens_tier": tok_tier, "pool": len(walled), "tokens_pool": len(tok_pool), "novelty": novelty}


# ------------------------------------------------------------------------------------ history and actuals

def _ep(s: Any) -> float | None:
    from ccp import health  # noqa: PLC0415
    return health._epoch(str(s)) if s else None


def _findings(q: Path, tid: str) -> dict[str, int]:
    """Review findings by severity: the review runs' records, else the review reports' Severity: lines."""
    from ccp import runs  # noqa: PLC0415
    from ccp.report import SEV_PART_RE, SEVERITY_RE  # noqa: PLC0415
    out = {k: 0 for k in SEVERITIES}
    seen = False
    for r in runs.all_runs(q, tid):
        if r.get("phase") == "review" and isinstance(r.get("severity"), dict):
            seen = True
            for k in SEVERITIES:
                v = r["severity"].get(k)
                out[k] += v if isinstance(v, int) else 0
    if not seen:
        d = q / "progress" / tid
        for f in sorted(d.glob("review*-report.md")) if d.is_dir() else []:
            try:
                m = SEVERITY_RE.search(f.read_text(errors="replace"))
            except OSError:
                continue
            for k, v in SEV_PART_RE.findall(m.group(1)) if m else []:
                out[k.upper()] += int(v)
    return out


def actual_from(q: Path, tid: str, row: dict[str, Any], d: dict[str, Any] | None) -> dict[str, Any]:
    """An actual row's body from `ccp health`'s row and the drill-down record (ccp/drill.py)."""
    from ccp import drill  # noqa: PLC0415
    d = d if d and not d.get("_error") else {}
    runs_ = d.get("runs") or []
    # The task's window is the drill-down's (its wall time): the first recorded event to the merge.
    merged = _ep(row.get("merged_at"))
    wall = d.get("wall_s") if d.get("wall_s") is not None else row.get("wall_s")
    hi = _ep(d.get("end_at")) or merged
    lo = _ep(d.get("start_at")) or (hi - wall if hi is not None and wall is not None else None)
    if runs_:  # each phase: the union of its runs' windows, inside the task's window (the drill clips them)
        phases: dict[str, Any] = {}
        for ph in ACTUAL_PHASES:
            iv = [(a, b) for r in runs_ if r.get("phase") == ph
                  and (a := _ep(r.get("start_at"))) is not None and (b := _ep(r.get("end_at"))) is not None]
            if lo is not None and hi is not None:
                iv = drill.clip(iv, lo, hi)
            phases[ph] = round(drill.length(drill.union(iv)))
        frm = "runs"
    else:  # before run records: `ccp health`'s spans laid end to end from the start, clipped to the window
        phases = {ph: None for ph in ACTUAL_PHASES}
        at = lo
        for ph, key in (("implement", "implementing_s"), ("review", "reviewing_s"), ("verify", "verifying_s")):
            v = row.get(key)
            if v is None or at is None or hi is None:
                continue
            phases[ph] = round(drill.length(drill.clip([(at, at + float(v))], lo, hi)))
            at += float(v)
        frm = "spans"
    tel = d.get("telemetry") == "runs" and (d.get("tokens") or 0) > 0
    start = lo
    return {"merged_at": row.get("merged_at"), "start_at": iso_ep(start), "merge_sha": row.get("merge_sha"),
            "wall_s": wall, "phases": phases, "phases_from": frm,
            "tokens": int(d["tokens"]) if tel else None, "cost_usd": round(float(d.get("cost_usd") or 0), 2) if tel else None,
            "rounds": {"review": row.get("review_rounds"), "fix": row.get("fix_rounds"), "verify": row.get("verify_rounds"),
                       "merge": row.get("merge_rounds"), "ruling": row.get("ruling_rounds")},
            "findings": _findings(q, tid), "telemetry": d.get("telemetry") or "none"}


def iso_ep(e: float | None) -> str | None:
    from ccp import health  # noqa: PLC0415
    return health._ts(e) if e is not None else None


def _live(cfg: Config, q: Path, only: str | None = None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    from ccp import drill, health, usage  # noqa: PLC0415
    rows_ = health.collect(cfg, q, files=False)["tasks"]
    if only is not None and not any(r["task_id"] == only for r in rows_):
        return [], {}
    if not rows_:
        return [], {}
    report = usage.fold(q, None, (cfg.telemetry or {}).get("design_seat"))
    d = drill.collect(q, rows_, report, only=only) if only is not None else drill.collect(q, rows_, report, limit=len(rows_) + 1)
    return ([r for r in rows_ if r["task_id"] == only] if only is not None else rows_), d


def history(cfg: Config, q: Path, tasks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every merged task with a wall time: {task_id, merged_at, start, features, actual}, oldest
    merge first. The actual is the task's stored actual row when it has one, else measured now.
    Features are read as before the work (`strip_notes`, the cited lines at the commit it started from)."""
    tasks = tasks if tasks is not None else tasklog.load(cfg)
    by_id = {str(t.get("task_id")): t for t in tasks}
    stored = {tid: a for tid, rs in all_rows(q).items() if (a := latest(rs, "actual"))}
    rows_, d = _live(cfg, q)
    since = _ep(str((cfg.estimate or {}).get("reference_since") or "") + "T00:00:00Z") \
        if (cfg.estimate or {}).get("reference_since") else None
    out = []
    for row in rows_:
        tid = row["task_id"]
        t = by_id.get(tid)
        if t is None:
            continue
        act = stored.get(tid) or actual_from(q, tid, row, d.get(tid))
        merged = _ep(act.get("merged_at") or row.get("merged_at"))
        if merged is None or not act.get("wall_s"):
            continue
        out.append({"task_id": tid, "merged_at": merged, "start": _ep(act.get("start_at")) or merged,
                    "excluded": since is not None and merged < since, "task": t,
                    "rev": _start_rev(cfg, _ep(act.get("start_at")),
                                      act.get("merge_sha") or row.get("merge_sha")),
                    "actual": act})
    out.sort(key=lambda h: h["merged_at"])
    return out


def _start_rev(cfg: Config, start: float | None, merge_sha: str | None) -> str | None:
    """The commit the task started from: the integration branch's tip at its start time (first-parent
    HEAD), else its merge's first parent."""
    if start is not None:
        r = subprocess.run(["git", "-C", str(cfg.root), "rev-list", "-1", "--first-parent", f"--before={int(start)}", "HEAD"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return f"{merge_sha}^" if merge_sha else None


def _featured(cfg: Config, hist: list[dict[str, Any]]) -> None:
    for h in hist:
        if "features" not in h:
            h["features"] = features(cfg, h["task"], h["rev"])


def _row(tid: str, src: str, version: int, thash: str, feats: dict[str, Any], b: dict[str, Any],
         cfg: Config, deps_done: list[str], as_of: str, notes: str, **extra: Any) -> dict[str, Any]:
    k = int((cfg.estimate or {}).get("k") or K_DEFAULT)
    return {"at": iso(), "as_of": as_of, "task_id": tid, "source": src, "version": version, "task_hash": thash,
            "inputs": {"features": feats, "novelty": b["novelty"], "reference_tasks": b["reference_tasks"],
                       "reference_tasks_tokens": b["reference_tasks_tokens"], "deps_done": deps_done,
                       "method": {"name": METHOD, "v": METHOD_V, "tier": b["tier"], "tokens_tier": b["tokens_tier"],
                                  "k": k, "pool": b["pool"], "tokens_pool": b["tokens_pool"],
                                  "reference_since": (cfg.estimate or {}).get("reference_since")}},
            "phases": {ph: ({"p50_s": v["p50_s"], "p90_s": v["p90_s"]} if v else None) for ph, v in b["phases"].items()},
            "total": b["total"], "tokens": b["tokens"], "cost_usd": b["cost_usd"], "rounds": b["rounds"],
            "notes": notes[:200], **extra}


def _note(b: dict[str, Any]) -> str:
    return (f"{len(b['reference_tasks'])} reference tasks ({b['tier']}) of {b['pool']}"
            + (f"; tokens from {len(b['reference_tasks_tokens'])} ({b['tokens_tier']}) of {b['tokens_pool']}"
               if b["reference_tasks_tokens"] else "; no token history"))


# ------------------------------------------------------------------------------------ commands

def _pool(hist: list[dict[str, Any]], before: float | None = None, not_id: str | None = None) -> list[dict[str, Any]]:
    return [h for h in hist if not h["excluded"] and h["task_id"] != not_id and (before is None or h["merged_at"] < before)]


def _why(rs: list[dict[str, Any]], thash: str, deps_done: list[str]) -> str | None:
    """Why a new baseline row is due, or None when the latest still stands."""
    last = latest(rs, "baseline")
    if last is None:
        return "no baseline yet"
    if last.get("task_hash") != thash:
        return "the task changed"
    have = (last.get("inputs") or {}).get("deps_done") or []
    if sorted(set(deps_done) - set(have)):
        return "a dependency merged since: " + ", ".join(sorted(set(deps_done) - set(have)))
    if ((last.get("inputs") or {}).get("method") or {}).get("v") != METHOD_V:
        return "the method changed"
    return None


def estimate_tasks(cfg: Config, q: Path, ids: list[str] | None, dry_run: bool = False, force: bool = False) -> dict[str, Any]:
    """Baseline rows for `ids` (None: every open task). A task is re-estimated when its file
    changed (`task_hash`), a dependency merged since its last row, or the method changed."""
    tasks = tasklog.load(cfg)
    done = {str(t.get("task_id")) for t in tasks if t.get("status") == "done"}
    if ids is None:
        targets = [t for t in tasks if t.get("status") not in ("done", "dropped")]
    else:
        targets = []
        for i in ids:
            t = next((x for x in tasks if refs.ids(cfg).same_task(x["_file"].stem, i)), None)
            if t is None:
                from ccp.queue import QueueError  # noqa: PLC0415
                raise QueueError(f"no task {i} in {cfg.rel(cfg.tasks_dir)}", 2)
            targets.append(t)
    hist = history(cfg, q, tasks)
    pool = None
    out = []
    for t in targets:
        tid = str(t.get("task_id"))
        if t.get("status") in ("done", "dropped"):
            out.append({"task_id": tid, "action": "skipped", "reason": f"{t.get('status')}: `ccp estimate backfill` covers history"})
            continue
        rs = rows(q, tid)
        thash = task_hash(str(t.get("_text") or ""))
        deps_done = sorted(d for d in tasklog._as_list(t.get("depends_on")) if d in done)
        why = "forced" if force else _why(rs, thash, deps_done)
        if why is None:
            out.append({"task_id": tid, "action": "unchanged", "reason": "the latest baseline stands"})
            continue
        if pool is None:
            pool = _pool(hist, not_id=None)
            _featured(cfg, pool)
        feats = features(cfg, t)
        b = baseline(feats, [h for h in pool if h["task_id"] != tid], int((cfg.estimate or {}).get("k") or K_DEFAULT))
        if b is None:
            out.append({"task_id": tid, "action": "skipped", "reason": "no completed task with a wall time to compare with"})
            continue
        now = iso()
        row = _row(tid, "baseline", _version(rs, "baseline"), thash, feats, b, cfg, deps_done, now, _note(b))
        if not dry_run:
            _append(q, row)
        out.append({"task_id": tid, "action": "would write" if dry_run else "written", "reason": why, "row": row})
    return {"ok": True, "dry_run": dry_run, "tasks": out,
            "written": sum(1 for x in out if x["action"] == "written")}


def record_actuals(cfg: Config, q: Path, tid: str) -> dict[str, Any] | None:
    """`ccp tasks close`: the task's actual row, once. None when it already has one or no row to read."""
    rs = rows(q, tid)
    if latest(rs, "actual"):
        return None
    hrows, d = _live(cfg, q, only=tid)
    if not hrows:
        return None
    from ccp.queue import load_task_state  # noqa: PLC0415
    st = load_task_state(q, tid)  # §16.7: what parallel work recorded on the task
    row = {"at": iso(), "task_id": tid, "source": "actual", "version": _version(rs, "actual"),
           **actual_from(q, tid, hrows[-1], d.get(tid)),
           **{k: st[k] for k in ("peak_in_flight", "undeclared_paths") if st.get(k) is not None}}
    _append(q, row)
    return row


def backfill(cfg: Config, q: Path, dry_run: bool = False) -> dict[str, Any]:
    """For each completed task: the baseline it would have got from the tasks merged before it
    started (its features as before its work), and its actual row; then the accuracy over them.
    A task that already has a backfilled baseline of this method, or an actual row, keeps it."""
    tasks = tasklog.load(cfg)
    hist = history(cfg, q, tasks)
    _featured(cfg, hist)
    k = int((cfg.estimate or {}).get("k") or K_DEFAULT)
    by = all_rows(q)
    made: list[dict[str, Any]] = []
    stats = {"baselines": 0, "actuals": 0, "kept": 0, "no_pool": 0}
    for h in hist:
        tid = h["task_id"]
        rs = list(by.get(tid, []))
        new: list[dict[str, Any]] = []
        if not latest(rs, "actual"):
            new.append({"at": iso(), "task_id": tid, "source": "actual", "version": _version(rs, "actual"), **h["actual"]})
            stats["actuals"] += 1
        cut = str(h["actual"].get("start_at") or h["actual"].get("merged_at") or "") or None
        have = [r for r in rs if r.get("source") == "baseline" and (
            (r.get("backfill") and ((r.get("inputs") or {}).get("method") or {}).get("v") == METHOD_V)
            or (not r.get("backfill") and cut is not None and str(r.get("as_of") or r.get("at") or "") <= cut))]
        if have:  # a backfill of this method, or a live baseline made before the task started
            stats["kept"] += 1
        else:
            pool = _pool(hist, before=h["start"], not_id=tid)
            b = baseline(h["features"], pool, k)
            if b is None:
                stats["no_pool"] += 1
            else:
                deps = sorted(tasklog._as_list(h["task"].get("depends_on")))
                new.append(_row(tid, "baseline", _version(rs, "baseline"), task_hash(str(h["task"].get("_text") or "")),
                                h["features"], b, cfg, deps, iso_ep(h["start"]) or iso(),
                                "backfill: " + _note(b), backfill=True))
                stats["baselines"] += 1
        for r in new:
            if not dry_run:
                _append(q, r)
            by.setdefault(tid, []).append(r)
        made += new
    acc = accuracy(by)
    return {"ok": True, "dry_run": dry_run, "tasks": len(hist), **stats, "accuracy": acc,
            "rows": len(made) if dry_run else None}


# ------------------------------------------------------------------------------------ accuracy

def _pair(rs: list[dict[str, Any]], src: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(the estimate the task is scored on, its actual): the latest row of `src` made before the
    task started (its merge when the start is unknown), a live one before a backfilled one."""
    act = latest(rs, "actual")
    if not act:
        return None
    cut = str(act.get("start_at") or act.get("merged_at") or "") or None
    est = latest([r for r in rs if not r.get("backfill")], src, before=cut) or latest(rs, src, before=cut)
    return (est, act) if est else None


def _score(pairs: list[tuple[float, dict[str, Any] | None]]) -> dict[str, Any]:
    ok = [(a, b) for a, b in pairs if a is not None and b and b.get("p50") is not None]
    if not ok:
        return {"n": 0}
    ratios = [a / b["p50"] for a, b in ok if b["p50"]]
    return {"n": len(ok), "le_p50": sum(1 for a, b in ok if a <= b["p50"]), "le_p90": sum(1 for a, b in ok if a <= b["p90"]),
            "share_p50": round(sum(1 for a, b in ok if a <= b["p50"]) / len(ok), 3),
            "share_p90": round(sum(1 for a, b in ok if a <= b["p90"]) / len(ok), 3),
            "median_ratio": round(statistics.median(ratios), 2) if ratios else None}


def _bands(est: dict[str, Any]) -> dict[str, Any]:
    t = est.get("total") or {}
    return {"wall": {"p50": t.get("p50_s"), "p90": t.get("p90_s")} if t.get("p50_s") is not None else None,
            "tokens": est.get("tokens"), "cost": est.get("cost_usd")}


def accuracy(by: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Per source: the share of actuals at or under P50 and P90 (wall, tokens, cost), the median
    actual/P50 ratio (above 1: the estimates run low), and the wall-time bias by kind and family."""
    out: dict[str, Any] = {"actuals": sum(1 for rs in by.values() if latest(rs, "actual")), "sources": {}, "bias": {}}
    for src in SOURCES:
        got: dict[str, list[tuple[float, Any]]] = {"wall": [], "tokens": [], "cost": []}
        groups: dict[str, dict[str, list[tuple[float, Any]]]] = {"kind": {}, "family": {}}
        for tid, rs in by.items():
            p = _pair(rs, src)
            if not p:
                continue
            est, act = p
            b = _bands(est)
            got["wall"].append((act.get("wall_s"), b["wall"]))
            got["tokens"].append((act.get("tokens"), b["tokens"]))
            got["cost"].append((act.get("cost_usd"), b["cost"]))
            f = (est.get("inputs") or {}).get("features") or {}
            for g, key in (("kind", f.get("kind") or "?"), ("family", f.get("family") or "?")):
                groups[g].setdefault(str(key), []).append((act.get("wall_s"), b["wall"]))
        out["sources"][src] = {k: _score(v) for k, v in got.items()}
        out["bias"][src] = {g: {k: _score(v) for k, v in sorted(d.items()) if len(v) >= 2} for g, d in groups.items()}
    return out


def accuracy_text(acc: dict[str, Any]) -> str:
    def one(s: dict[str, Any]) -> str:
        if not s.get("n"):
            return "no pairs"
        return (f"n {s['n']}: <=P50 {s['share_p50'] * 100:.0f}%, <=P90 {s['share_p90'] * 100:.0f}%"
                + (f", actual/P50 median {s['median_ratio']}" if s.get("median_ratio") is not None else ""))
    lines = [f"tasks with actuals: {acc['actuals']} (targets: about 50% at or under P50, about 90% under P90)"]
    for src in SOURCES:
        s = acc["sources"].get(src) or {}
        lines.append(f"{src}: wall {one(s.get('wall') or {})}; tokens {one(s.get('tokens') or {})}; cost {one(s.get('cost') or {})}")
        for g, d in (acc["bias"].get(src) or {}).items():
            for k, v in d.items():
                lines.append(f"  {g} {k}: wall {one(v)}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------ the board

def _est_view(r: dict[str, Any] | None, cal: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """A row for the board: the stored (raw) bands, and under `cal` the calibrated ones (phase D)."""
    if not r:
        return None
    m = (r.get("inputs") or {}).get("method") or {}
    f = (r.get("inputs") or {}).get("features") or {}
    from ccp import calibrate  # noqa: PLC0415
    return {"source": r.get("source"), "at": r.get("as_of") or r.get("at"), "version": r.get("version"),
            "kind": f.get("kind"), "family": f.get("family"),
            "cal": calibrate.apply(r, (cal or {}).get("factors"), r.get("source")) if cal is not None else None,
            "total": r.get("total"), "tokens": r.get("tokens"), "cost_usd": r.get("cost_usd"), "phases": r.get("phases"),
            "rounds": r.get("rounds"), "tier": m.get("tier"), "refs": ((r.get("inputs") or {}).get("reference_tasks") or [])[:8],
            "backfill": bool(r.get("backfill")),
            **({"reasoning": str(r.get("reasoning") or "")[:600], "complexity": r.get("complexity"), "waits": r.get("waits"),
                "model": m.get("model"), "cost_seat": (r.get("seat") or {}).get("cost_usd")} if r.get("source") == "agent" else {})}


def board_view(q: Path, limit: int = 400, cfg: Config | None = None) -> dict[str, Any]:
    """The board's estimates (§28.3): per task the latest of each source and the actual, and the
    accuracy; each view carries its calibrated bands (`cal`, phase D) and the board the calibration.
    Reads the stored rows only; no estimate is computed here, and the calibration is cached by the
    hash of its inputs (ccp/calibrate.py), so a build stays fast."""
    from ccp import calibrate  # noqa: PLC0415
    by = all_rows(q)
    try:
        cal = calibrate.model(q, cfg, by)
    except Exception as exc:  # noqa: BLE001  (the raw estimates stand without it)
        cal = {"_error": f"{type(exc).__name__}: {exc}"[:200]}
    fac = cal if "factors" in cal else None
    tasks: dict[str, Any] = {}
    for tid in sorted(by)[-limit:]:
        rs = by[tid]
        act = latest(rs, "actual")
        tasks[tid] = {"baseline": _est_view(latest(rs, "baseline"), fac), "agent": _est_view(latest(rs, "agent"), fac),
                      "actual": {k: act.get(k) for k in ("wall_s", "phases", "phases_from", "tokens", "cost_usd", "rounds",
                                                          "findings", "merged_at")} if act else None}
        if act:  # the estimate the task had when it started, which the accuracy compares
            for src in SOURCES:
                p = _pair(rs, src)
                tasks[tid][f"{src}_scored"] = _est_view(p[0], fac) if p else None
    from ccp import estimator  # noqa: PLC0415  (phase B: the seat's calls and spend)
    return {"tasks": tasks, "accuracy": accuracy(by), "advisory": True, "estimator": estimator.spend(q),
            "calibration": calibrate.summary(cal) if fac else cal}


# ------------------------------------------------------------------------------------ terminal

def _d(s: Any) -> str:
    if s is None:
        return "-"
    s = float(s)
    return f"{s / 3600:.1f}h" if s >= 3600 else f"{s / 60:.0f}m"


def _tok(n: Any) -> str:
    return "-" if n is None else f"{float(n) / 1e6:.1f}M" if float(n) >= 1e6 else f"{float(n) / 1e3:.0f}k"


def row_text(r: dict[str, Any]) -> str:
    if r.get("source") == "actual":
        return (f"actual  v{r.get('version')}  {str(r.get('at'))[:16]}  wall {_d(r.get('wall_s'))}  "
                + " ".join(f"{ph} {_d((r.get('phases') or {}).get(ph))}" for ph in ACTUAL_PHASES)
                + f"  tokens {_tok(r.get('tokens'))}  cost {'-' if r.get('cost_usd') is None else '$%.2f' % r['cost_usd']}"
                + f"  rounds {r.get('rounds')}")
    t, tk, c = r.get("total") or {}, r.get("tokens") or {}, r.get("cost_usd") or {}
    m = (r.get("inputs") or {}).get("method") or {}
    return (f"{r.get('source')}  v{r.get('version')}  {str(r.get('as_of') or r.get('at'))[:16]}"
            f"{'  (backfill)' if r.get('backfill') else ''}  wall {_d(t.get('p50_s'))}-{_d(t.get('p90_s'))}  "
            f"tokens {_tok(tk.get('p50'))}-{_tok(tk.get('p90'))}  cost "
            + (f"${float(c['p50']):.2f}-${float(c['p90']):.2f}" if c.get("p50") is not None else "-")
            + f"  {m.get('tier')} refs {','.join(refs.number_prefix(x) or x[:4] for x in (r.get('inputs') or {}).get('reference_tasks') or [])}")


def _bands_text(t: dict[str, Any] | None, tk: dict[str, Any] | None, c: dict[str, Any] | None) -> str:
    t, tk, c = t or {}, tk or {}, c or {}
    return (f"wall {_d(t.get('p50_s'))}-{_d(t.get('p90_s'))}  tokens {_tok(tk.get('p50'))}-{_tok(tk.get('p90'))}  cost "
            + (f"${float(c['p50']):.2f}-${float(c['p90']):.2f}" if c.get("p50") is not None else "-"))


def _factors_text(f: dict[str, Any] | None) -> str:
    return "; ".join(f"{m} x{v['bias']} ({v['group']}, n {v.get('n_group')}), width x{v['width']} (n {v['n']})"
                     if v.get("fitted")
                     else f"{m} 1.0 (n {v.get('n', 0)}: too few pairs)" for m, v in (f or {}).items())


def show_text(tid: str, rs: list[dict[str, Any]], cal: dict[str, Any] | None = None) -> str:
    """The rows, the latest of each source, and with `cal` each latest estimate raw and calibrated."""
    if not rs:
        return f"{tid}: no estimate rows"
    lines = [f"{tid}: {len(rs)} row(s)"] + ["  " + row_text(r) for r in rs]
    lines.append("latest: " + "; ".join(f"{s} v{x.get('version')}" for s in (*SOURCES, "actual") if (x := latest(rs, s))))
    if cal is not None and "factors" in cal:
        for s in SOURCES:
            if (x := latest(rs, s, calibrated=True, cal=cal)):
                raw = x["raw"]
                lines.append(f"  {s:<8} raw         {_bands_text(raw['total'], raw['tokens'], raw['cost_usd'])}")
                lines.append(f"  {s:<8} calibrated  {_bands_text(x['total'], x['tokens'], x['cost_usd'])}")
                lines.append(f"  {'':<8} factors     {_factors_text(x['calibration'])}")
    return "\n".join(lines)
