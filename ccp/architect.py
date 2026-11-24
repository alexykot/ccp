"""The architect seat (SPEC §19): when a pass is due, the isolated pass itself, and its triage.

One seat owns a product's structural health across four lenses (structure, docs, tests, process).
A fresh, read-only `claude -p` runs the product's managed `architect` skill and returns one report;
the task-log owner triages it under `docs/delivery/REVIEW-TRIAGE.md`. Everything after the call is
§19's review kit (`architecture_review.py`), as a review *kind* with its own state
(`architect.json`), lock (`architect.lock`) and id prefixes: `ar-` for a pass, `sh-` for a shape.

`ccp` computes when a pass is due, so no seat has to remember it (§19.6), from:

- **cadence:** `every_n_tasks` times the slots (`parallel.max_in_flight`, 1 when tasks run one at a time) tasks
  done since the last pass, or `max_days` with at least one;
- **a review point closing:** every task in the scope `ccp tasks next` was given is done;
- **friction:** `notes_due` times the slots distinct tasks with a worker's friction note since the last pass;
- **drift:** `ccp health` drift (on active time: wall time less waits), or a budget failing, that the last
  pass did not see and no `pending` task cites in its `rule_refs`.

All of these count from the product's adoption point (§19.11). Before its first pass, a review point counts
its tasks numbered from that point, friction counts only those tasks' notes, drift is not judged, and a budget
counts only if it was not already failing when the seat first checked it (`budget_baseline` in the state file),
so a product that adopts with history owes no pass at once.

`gate()` is what `ccp tasks next` enforces (§19.6). A running pass blocks nothing. Merges are counted as
tasks reaching `done` in the task log, as §19 counts them; the moment a non-cadence trigger was first seen is
kept in the state file (`seen`), and a started pass that failed restarts the grace: `next` blocks again only
after one more merge (or a `--force` run), and its message names the failed pass and the first line of its
`failed.txt`. After two failed passes in a row `next` stops blocking on the pass and tells the runner to take
it to the owner: a systematic failure (a broken prompt or skill) must not burn a full pass per merge.

Every write to `architect.json` is a short read-modify-write under its own lock
(`architecture_review.update_state`): a detached pass writes its record while `next` and triage
write theirs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from ccp import config, headless, health, parallel, pkgdocs, refs, rules, tasklog, wt
from ccp.adr import find_file as find_adr_file
from ccp.config import ARCHITECT_DEFAULTS, Config
from ccp.queue import spawn_detached

PLANE = Path(__file__).resolve().parent.parent
OBS = PLANE / "scripts" / "observability"
sys.path.insert(0, str(OBS))

import architecture_review as ar  # noqa: E402  (review kinds, lock, validation, triage)
from lib import fmt_dt, lock_is_stale, parse_dt, read_json, write_json  # noqa: E402

LENSES: dict[str, tuple[str, ...]] = {
    "structure": ar.CATEGORIES,
    "docs": ("doc-wrong", "doc-missing", "doc-aspirational", "doc-padding", "doc-history"),
    "tests": ("test-cost", "test-brittle"),
    "process": ("process-cost",),
}
ARCH = ar.Kind("architect", "Architect pass", "ar", "architect.json", "architect.lock", "architect",
               tuple(c for cats in LENSES.values() for c in cats), "ccp architect triage", ("sh",))
SKILL = ar.ARCHITECT_SKILL
MAX_FINDINGS = {"pass": 25, "shape": 10}
AWAITING = ("reported", "triaging", "triage_sent", "triage_failed")
RULE_ACTIONS = ("add", "amend", "delete")
RULE_DISPOSITIONS = ("applied", "rejected", "needs_operator")
STALE_AFTER_S = 120  # a `running` pass whose lock is gone this long after its start has died


# ---------------------------------------------------------------- state

def queue_root(required: bool = True) -> Path | None:
    q = os.environ.get("QUEUE_ROOT")
    if q and Path(q).is_dir():
        return Path(q)
    if required:
        raise SystemExit("ccp architect: set QUEUE_ROOT to this project's runtime queue (SPEC §19.3)")
    return None


def _settings(cfg: Config) -> dict[str, Any]:
    return cfg.architect or ARCHITECT_DEFAULTS


def _done(tasks: list[dict[str, Any]]) -> set[str]:
    return {str(t.get("task_id")) for t in tasks if t.get("status") == "done"}


def _tasked_rules(tasks: list[dict[str, Any]]) -> set[str]:
    """The house-rule ids `pending` tasks cite in `rule_refs`: a budget breach among them is already tasked
    and makes no pass due (§19.6)."""
    return {str(r) for t in tasks if t.get("status") == "pending" for r in tasklog._as_list(t.get("rule_refs"))}


def _slots(cfg: Config) -> int:
    """The tasks the product runs at once (§19.6): `parallel.max_in_flight`, 1 when tasks run one at a time."""
    return int(parallel.settings(cfg)["max_in_flight"]) if parallel.enabled(cfg) else 1


def _cadence(cfg: Config) -> int:
    """The merges the cadence waits for (§19.6): `every_n_tasks` times the tasks the product runs at once."""
    return int(_settings(cfg)["every_n_tasks"]) * _slots(cfg)


def _notes_tasks(cfg: Config) -> int:
    """The noted tasks the friction trigger waits for (§19.6): `notes_due` times the tasks the product runs at once."""
    return int(_settings(cfg)["notes_due"]) * _slots(cfg)


def noted_tasks(notes: list[dict[str, Any]], counts: Callable[[str], bool]) -> set[str]:
    """The distinct tasks with a worker's friction note (§19.6): a note with no task, or with any source but
    `worker` (the plane's own override notes), does not count; `counts` keeps only the tasks the trigger counts."""
    return {str(n["task_id"]) for n in notes
            if n.get("source") == "worker" and n.get("task_id") and counts(str(n["task_id"]))}


def work_scope(q: Path, given: str | None = None) -> list[str] | None:
    """The scope for the review-point trigger: `--scope` when given, else the running runner's
    scope from work.json."""
    if given:
        return [x.strip() for x in given.split(",") if x.strip()] or None
    try:
        w = read_json(q / "work.json")
    except (OSError, ValueError):
        return None
    return list(w.get("scope") or []) or None if w.get("status") == "running" else None


def _drop_worktree(main: str | Path, path: str | Path) -> None:
    """Remove a pass's own worktree (§12.1 `arch-<review id>`) from the main checkout it was made in.
    Failures are ignored: the worktree may be gone already."""
    wt.remove_unrecorded(Path(main), Path(path))


def _reap(q: Path, st: dict[str, Any], actor: str) -> None:
    """A `running` pass whose lock is gone or stale has died with its process: mark it failed, and
    remove its own worktree if it is still there."""
    lock = q / ARCH.lock
    try:
        cur = read_json(lock) if lock.is_file() else {}
    except (OSError, ValueError):
        cur = {}
    now = ar.now_utc()
    for rid, rec in list(st["reviews"].items()):
        if rec.get("status") != "running":
            continue
        age = (now - parse_dt(rec.get("started_at") or fmt_dt(now))).total_seconds()
        alive = cur.get("review_id") == rid and not lock_is_stale(cur, now)
        if not alive and age > STALE_AFTER_S:
            rec["error"] = "its process ended without a result (lock gone or stale)"
            ar.transition(q, st, rid, "failed", actor, ARCH)
            if rec.get("worktree") and rec.get("main") and Path(rec["worktree"]).exists():
                _drop_worktree(rec["main"], rec["worktree"])


def load(q: Path, actor: str = "system", reap: bool = True) -> dict[str, Any]:
    """The state file. `reap=False` only reads: no dead pass is marked failed and no worktree is removed
    (the board's view)."""
    st = ar.load_state(q, ARCH)
    st.setdefault("reviews", {})
    st.setdefault("seen", {})
    if reap:
        _reap(q, st, actor)
    return st


# ---------------------------------------------------------------- due

def _covered(st: dict[str, Any], ids: set[str]) -> bool:
    """Some pass that did not fail started with every one of `ids` done."""
    return any(r.get("mode") == "pass" and r.get("status") not in ("failed", "quota_parked")
               and ids <= set(r.get("done") or []) for r in st["reviews"].values())


def shape_due(cfg: Config, tasks: list[dict[str, Any]]) -> list[str]:
    """ADRs that pending tasks cite with no shaping record and no waiver (§19.6); `ccp tasks check`
    is what enforces it."""
    if not config.architect_on(cfg) or not cfg.architect["shape_adrs"]:
        return []
    shaped = tasklog.shaped_adrs(cfg)
    out: set[str] = set()
    for t in tasks:
        if not tasklog._check_shaping(cfg, t, "", shaped) or str(t.get("shaping") or ""):
            continue
        for ref in tasklog._as_list(t.get("adr_refs")):
            n = tasklog.adr_number(ref, cfg)
            if n is not None and n not in shaped:
                out.add(refs.ids(cfg).adr_id(n))
    return sorted(out)


NO_ADOPTION_POINT = ('no adoption point: record architect.shape_from_task (the next task number) '
                    'or set "architect": false')


def _rules_doc_state(cfg: Config) -> str | None:
    """The house rules doc `due` reports: its path, `missing: <path>` when the file is absent (a pass then runs
    without house rules, §19.11), None when the product names none."""
    rel = _settings(cfg).get("rules_doc")
    if not rel:
        return None
    return rel if (cfg.root / rel).is_file() else f"missing: {rel}"


def due_info(cfg: Config, q: Path, scope: list[str] | None = None, record: bool = True,
             tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Whether a pass is due, why, and how many merges each reason has waited; and any report
    awaiting triage with the merges since it was reported. With `record=False` it writes nothing:
    no `seen` moment and no reaping (`ccp architect status` reaps first; the board never writes)."""
    a = _settings(cfg)
    st = load(q, reap=record)
    tasks = tasks if tasks is not None else tasklog.load(cfg)
    done = _done(tasks)
    adopted = config.architect_adopted(cfg)
    last = st.get("last") or {}
    label = last.get("review_id") or "none"
    # §19.11: the cadence counts the tasks numbered from the adoption point (none before it, none unadopted).
    start = config.adoption_point(cfg)
    def from_adoption(tid: Any) -> bool:
        return adopted and ((n := tasklog._number(tid, cfg)) is None or n >= (start or 0))
    counted = {tid for tid in done if from_adoption(tid)}
    since = len(counted - set(last.get("done") or []))
    days = round((ar.now_utc() - parse_dt(last["started_at"])).total_seconds() / 86400, 1) \
        if last.get("started_at") else None
    cadence = _cadence(cfg)
    running = [r for r, rec in st["reviews"].items() if rec.get("status") == "running"]
    awaiting = [{"review_id": r, "mode": rec.get("mode"),
                 "merges_since": len(done - set(rec.get("done_at_report") or rec.get("done") or []))}
                for r, rec in st["reviews"].items() if rec.get("status") in AWAITING]
    # Each reason: (key, text, the done count when it became due).
    reasons: list[tuple[str, str, int]] = []
    if not adopted:
        pass  # the seat enforces nothing without an adoption point
    elif since >= cadence:
        reasons.append(("cadence", f"{since} task(s) done since {label}", len(done) - (since - cadence)))
    elif days is not None and days >= a["max_days"] and since >= 1:
        reasons.append(("max_days", f"{days} days and {since} task(s) done since {label}", -1))
    scope_ids = {str(t.get("task_id")) for t in tasks if scope and tasklog.in_scope(str(t.get("task_id")), scope)}
    if not last:  # §19.6: before the first pass a review point counts its tasks from the adoption point
        scope_ids = {tid for tid in scope_ids if from_adoption(tid)}
    if adopted and scope_ids and scope_ids <= done and not _covered(st, scope_ids):
        reasons.append(("review_point", "review point closes: every task in scope is done", -1))
    # Before the first pass, only the tasks from the adoption point count.
    noted = len(noted_tasks(health.notes(q, last.get("started_at")), (lambda _: True) if last else from_adoption))
    notes_tasks = _notes_tasks(cfg)
    if adopted and noted >= notes_tasks:
        reasons.append(("notes", f"{noted} task(s) with a friction note since {label}", -1))
    drift = None
    if adopted:
        drift = health.trend(health.collect(cfg, q, files=False)["tasks"], a["drift_ratio"])
        if last and drift["drift"] and not last.get("health_drift"):  # no drift is judged before the first pass
            reasons.append(("drift", f"health drift: median active time of the last 5 tasks is {drift['drift_ratio']}x "
                                     f"the 10 before (limit {a['drift_ratio']})", -1))
    budgets = rules.budget_failures(cfg) if adopted else []
    if last:
        known = set(last.get("budget_ids") or [])
    else:
        # Before the first pass, the budgets failing when the seat first checks once adopted are the baseline.
        known = set(st.get("budget_baseline") or []) if "budget_baseline" in st else {b.split(":", 1)[0] for b in budgets}
        if adopted and "budget_baseline" not in st and record:
            def keep_baseline(fresh: dict[str, Any]) -> None:
                if not fresh.get("last") and "budget_baseline" not in fresh:
                    fresh["budget_baseline"] = sorted(known)
            ar.update_state(q, ARCH, keep_baseline)
    skip = known | _tasked_rules(tasks)  # a breach a pending task already fixes calls no pass
    new_budgets = [b for b in budgets if b.split(":", 1)[0] not in skip]
    if new_budgets:
        reasons.append(("budget", "budget check fails: " + "; ".join(new_budgets[:3]), -1))
    # A non-cadence reason became due when it was first seen; remember that moment.
    seen = st["seen"]
    keys = {k for k, _, _ in reasons}
    changed = False
    for i, (k, text, at) in enumerate(reasons):
        if at == -1:
            if k not in seen:
                seen[k], changed = len(done), True
            reasons[i] = (k, text, seen[k])
    for k in [k for k in seen if k not in keys]:
        del seen[k]
        changed = True
    if changed and record:
        def keep_seen(fresh: dict[str, Any]) -> None:
            # Only if no pass finished meanwhile: a finished pass clears `seen`.
            if (fresh.get("last") or {}).get("review_id") == last.get("review_id"):
                fresh["seen"] = seen
        ar.update_state(q, ARCH, keep_seen)
    attempt = st.get("last_attempt") or {}
    restart = attempt.get("done_count") if attempt.get("review_id") != last.get("review_id") else None
    waited = [len(done) - max(at, restart if restart is not None else at) for _, _, at in reasons]
    failed = st["reviews"].get(attempt.get("review_id") or "") if restart is not None else None
    last_failure = None
    if failed and failed.get("status") in ("failed", "quota_parked"):
        ft = q / "reviews" / f"{attempt['review_id']}.failed.txt"  # not ar.rdir: no mkdir on a read
        first = next((ln.strip() for ln in ft.read_text(errors="ignore").splitlines() if ln.strip()), "") \
            if ft.is_file() else ""
        last_failure = {"review_id": attempt["review_id"], "status": failed["status"], "error": failed.get("error"),
                        "failed_txt": first[:160] or None}
    passes = sorted(((rec.get("started_at") or "", rec.get("status")) for rec in st["reviews"].values()
                     if rec.get("mode") == "pass"), key=lambda p: p[0])  # a tie never compares a None status
    failed_in_a_row = 0
    for _, status in reversed(passes):
        if status not in ("failed", "quota_parked"):
            break
        failed_in_a_row += 1
    info: dict[str, Any] = {
        "enabled": config.architect_on(cfg), "done_total": len(done), "done_since_last": since,
        "days_since_last": days, "cadence_tasks": cadence, "notes_tasks": notes_tasks,
        "last_review_id": last.get("review_id"), "running": running,
        "awaiting_triage": awaiting, "noted_tasks_since_last": noted, "budget_failures": budgets,
        "health": drift, "reasons": [t for _, t, _ in reasons], "merges_since_due": max(waited, default=0),
        "shape_due": shape_due(cfg, tasks), "last_failure": last_failure, "failed_in_a_row": failed_in_a_row,
        "merges_since_attempt": len(done) - attempt["done_count"] if restart is not None else None,
        "grace_tasks": a["grace_tasks"], "triage_grace_tasks": a["triage_grace_tasks"],
        "adoption_point": start, "rules_doc": _rules_doc_state(cfg),
    }
    if not config.architect_on(cfg):
        info.update(due=False, reason=f'the architect seat is off ("architect": false in {config.CONFIG_REL})')
    elif not adopted:
        info.update(due=False, reason=NO_ADOPTION_POINT)
    elif running:
        info.update(due=False, reason=f"pass {running[0]} is running")
    elif awaiting:
        info.update(due=False, reason=f"{awaiting[0]['review_id']} awaits triage: run "
                                      f"`ccp architect triage {awaiting[0]['review_id']}`")
    elif reasons:
        info.update(due=True, reason="; ".join(info["reasons"]))
    else:
        info.update(due=False, reason=f"{since} of {cadence} tasks done since {label}; nothing else due")
    return info


def gate(cfg: Config, q: Path, scope: list[str] | None, task: dict[str, Any] | None) -> dict[str, Any]:
    """What `ccp tasks next` enforces (§19.6). `blocked` is the exit-4 reason, or None; `notices`
    are what the runner should act on without being blocked."""
    a = _settings(cfg)
    info = due_info(cfg, q, scope)
    notices: list[str] = []
    if not config.architect_adopted(cfg):
        return {"blocked": None, "notices": notices, "info": info}  # the seat enforces nothing yet (§19.11)
    for w in info["awaiting_triage"]:
        if w["merges_since"] >= a["triage_grace_tasks"]:
            action = (f"run `ccp architect triage {w['review_id']}` and hand it to the task-log owner "
                      "(message the lead), then ask `ccp tasks next` again")
            return {"blocked": f"architect report {w['review_id']} awaits triage: {w['merges_since']} task(s) done "
                               "since it was reported",
                    "kind": "triage", "review_id": w["review_id"],
                    "action": action, "notices": [], "info": info}
        notices.append(f"report {w['review_id']} awaits triage: run `ccp architect triage {w['review_id']}` and hand "
                       f"it to the owner (blocks `next` after {a['triage_grace_tasks'] - w['merges_since']} more merge(s))")
    if info["due"]:
        run = "ccp architect run --detach" + (f" --scope {','.join(scope)}" if scope else "")
        f = info["last_failure"]
        why = ""
        if f:
            why = f"; the last pass {f['review_id']} {f['status']}: {f.get('error') or 'see its log'}"
            if f.get("failed_txt"):
                why += f" (reviews/{f['review_id']}.failed.txt: \"{f['failed_txt']}\")"
        if info["failed_in_a_row"] >= 2:
            # A pass that keeps failing goes to the owner; it never burns a full pass per merge.
            notices.append(f"architect pass due ({info['reason']}), but the last {info['failed_in_a_row']} passes "
                           f"failed{why}. Not blocking: take it to the task-log owner (the lead); "
                           "`ccp architect run --force --detach` retries once it is fixed")
            return {"blocked": None, "notices": notices, "info": info}
        # A failed attempt never re-blocks at the done count it failed at: only a merge (or --force) re-arms it.
        retried_here = bool(f) and info["merges_since_attempt"] == 0
        if info["merges_since_due"] >= a["grace_tasks"] or (task is None and not retried_here):
            return {"blocked": "architect pass due: " + info["reason"] + why, "kind": "pass",
                    "action": f"run `{run}`, then ask `ccp tasks next` again",
                    "notices": notices, "info": info}
        notices.append(f"architect pass due ({info['reason']}{why}): run `{run}` "
                       f"(blocks `next` after {a['grace_tasks'] - info['merges_since_due']} more merge(s))")
    return {"blocked": None, "notices": notices, "info": info}


# ---------------------------------------------------------------- run

def _lenses(arg: str | None) -> list[str]:
    ls = [x.strip() for x in (arg or "").split(",") if x.strip()] or list(LENSES)
    bad = [x for x in ls if x not in LENSES]
    if bad:
        raise SystemExit(f"ccp architect: unknown lens(es) {', '.join(bad)}; lenses are {', '.join(LENSES)}")
    return list(dict.fromkeys(ls))


def adr_id(arg: str, cfg: Config | None = None) -> str:
    """`ADR-0031`, `0031` or `31` → `ADR-0031`; anything else is kept as given (refs.Ids.adr_canonical)."""
    return refs.ids(cfg).adr_canonical(arg)


def adr_plan(arg: str | None, mode: str, due: Any, canon: Any = adr_id) -> list[str]:
    """The ADRs one `run` names, in order (§19.5): `--adr`'s comma-separated ids, each canonical, or `due`,
    every ADR `due()` lists (`shape_due`, read once, when the call starts). Empty without `--adr`. `due` or
    several ids with a mode other than `shape` is refused (SystemExit)."""
    items = [x.strip() for x in (arg or "").split(",") if x.strip()]
    if not items:
        return []
    if items == ["due"] or len(items) > 1:
        if mode != "shape":
            raise SystemExit("ccp architect run: --adr due or several ADRs need --mode shape (SPEC §19.5)")
        if items == ["due"]:
            return list(due())
    if "due" in items:
        raise SystemExit("ccp architect run: --adr takes ADR ids, comma-separated, or `due` alone")
    return list(dict.fromkeys(canon(x) for x in items))


def deny_rules(private_dirs: list[str], roots: list[str]) -> list[str]:
    """§19.7: `Read(./<p>)` and `Read(./<p>/**)` for each private path, and the same two rules on `<p>`'s
    absolute path under each of `roots` (the pass's cwd and the product root), in Claude Code's absolute
    form: a rule path that begins `//` is read from the filesystem root."""
    out: list[str] = []
    for p in private_dirs:
        out += [f"Read(./{p})", f"Read(./{p}/**)"]
        for r in roots:
            out += [f"Read(/{r.rstrip('/')}/{p})", f"Read(/{r.rstrip('/')}/{p}/**)"]
    return list(dict.fromkeys(out))


def _adr_path(cfg: Config, adr: str) -> str | None:
    m = re.search(r"(\d+)", adr or "")
    if not m:
        return None
    f = find_adr_file(cfg, int(m.group(1)))
    return cfg.rel(f) if f else None


def prompt_for(cfg: Config, q: Path, rid: str, mode: str, lenses: list[str], head: str, base: str | None,
               dirty: bool, adr: str | None, due_reason: str, notes_since: str | None,
               own_worktree: bool = False) -> str:
    a = _settings(cfg)
    rs = rules.summary(cfg)
    probe_txt = ", ".join(f"`{p}`" for p in a["probes"]) or "none (read-only git and file commands only)"
    lines = [
        f"/architect mode={mode} lenses={','.join(lenses)} review_id={rid} project_id={cfg.project_id} "
        f"head={head} base={base or 'none'}" + (f" adr={adr}" if adr else ""),
        "",
        f"You are the isolated architect for project {cfg.project_id} (control-plane SPEC §19). If the architect "
        f"skill is not loaded, read {ar.architect_skill(cfg.root)} now and follow it exactly. You are read-only: no edits, no commits, "
        "nothing that writes, spends or sends.",
        f"Mode: {mode}. Lenses: {', '.join(lenses)}. At most {MAX_FINDINGS[mode]} findings.",
    ]
    if mode == "shape":
        p = _adr_path(cfg, adr or "")
        lines.append(f"ADR to shape: {adr}" + (f" ({p})" if p else " (find it in the design record)")
                     + ". Return the `shape` object as well as findings.")
    if rs["rules_doc"] and not rs["present"]:
        lines.append(f"House rules: {rs['rules_doc']} is missing, so this pass runs without house rules. "
                     "Propose a first set in `rule_changes`.")
    elif rs["rules_doc"]:
        lines.append(f"House rules: {rs['rules_doc']} ({rs['rules']} rules, {rs['lines']} of "
                     f"{rs['rules_max_lines']} lines). Propose additions, amendments and deletions in `rule_changes`.")
    else:
        lines.append("House rules: none yet (architect.rules_doc is not set). Propose a first set in `rule_changes`.")
    lines.append(f"Allowed probe commands besides read-only git/ls/wc: {probe_txt}.")
    if "docs" in lenses and config.package_docs_on(cfg):
        dirs = [{"dir": cfg.rel(d), "doc": pkgdocs.doc_for(cfg, d).name} for d in pkgdocs.source_dirs(cfg)]
        lines.append(f"Docs lens, directories `ccp docs check` judges (each against its own package doc): {json.dumps(dirs)}")
    lines.append(f"Shape-only directories (read for structure, never quote a value): {json.dumps(a['shape_only_dirs'])}")
    lines.append(f"Private paths (never open, never quote): {json.dumps(a['private_dirs'])}")
    if mode == "pass":
        lines.append(f"Due because: {due_reason or 'on demand'}.")
    lines += ["", "Delivery health (`ccp health`; diagnostics, never targets):",
              health.summary_text(health.collect(cfg, q)), ""]
    ns = health.notes(q, notes_since)
    lines.append("Friction notes since the last pass (leads to check, not findings):" if ns else
                 "Friction notes since the last pass: none.")
    lines += [f"- {n.get('at')} [{n.get('task_id') or '-'}, {n.get('by') or n.get('source') or '-'}] {n.get('text')}"
              for n in ns]
    if dirty and own_worktree:
        lines.append(f"The caller's checkout was dirty; you are reading `{head[:7]}`.")
    elif dirty:
        lines.append("The working tree has uncommitted changes from other work: review the committed state "
                     "(`git show HEAD:<path>` for any modified file).")
    lines.append("Finish with the report JSON object as your final message and nothing after it.")
    return "\n".join(lines) + "\n"


def validate(report: Any, rid: str, pid: str, mode: str, lenses: list[str],
             ids: refs.Ids = refs.DEFAULT) -> list[str]:
    """§19.7's checks with the lenses' categories, plus §19.7: mode, lenses, rule_changes, metrics."""
    cats = tuple(c for lens in lenses for c in LENSES[lens])
    errs = ar.validate_report(report, rid, pid, ARCH._replace(categories=cats), MAX_FINDINGS[mode])
    if not isinstance(report, dict):
        return errs
    if report.get("mode") not in (None, mode):
        errs.append(f"mode {report.get('mode')!r} != {mode}")
    got = report.get("lenses")
    if got is not None and (not isinstance(got, list) or not set(got) <= set(lenses)):
        errs.append(f"lenses {got!r} are not within {lenses}")
    rc = report.get("rule_changes") or []
    if not isinstance(rc, list):
        errs.append("rule_changes is not a list")
        rc = []
    for i, c in enumerate(rc):
        if not isinstance(c, dict):
            errs.append(f"rule_changes[{i}] is not an object")
            continue
        if not ids.is_rule_id(c.get("rule")):
            errs.append(f"rule_changes[{i}]: rule {c.get('rule')!r} is not a rule id ({ids.rule_shape})")
        if c.get("action") not in RULE_ACTIONS:
            errs.append(f"rule_changes[{i}]: action {c.get('action')!r} is not one of {', '.join(RULE_ACTIONS)}")
        if not str(c.get("check") or "").strip():
            errs.append(f"rule_changes[{i}]: names no check")
    if report.get("metrics") is not None and not isinstance(report["metrics"], dict):
        errs.append("metrics is not an object")
    if mode == "shape":
        sh = report.get("shape")
        if not isinstance(sh, dict):
            errs.append("a shape report carries a `shape` object")
        else:
            for k in ("hot_spots", "preparatory_refactors", "single_sources", "task_graph"):
                if k in sh and not isinstance(sh[k], list):
                    errs.append(f"shape.{k} is not a list")
    return errs


def render(report: dict[str, Any]) -> str:
    """§19's rendered report, with the rule changes and, for a shape, the ADR and its advice."""
    label = "Architect shape" if report.get("mode") == "shape" else "Architect pass"
    md = ar.render_md(report, ARCH._replace(label=label))
    head, _, rest = md.partition("\n\n")
    extra = [f"mode `{report.get('mode')}` · lenses {', '.join(report.get('lenses') or [])}"]
    if report.get("adr"):
        extra.append(f"ADR: {report['adr']}")
    md = head + "\n\n" + "\n".join(extra) + "\n\n" + rest
    rc = report.get("rule_changes") or []
    if rc:
        md += "\n## Rule changes\n\n| rule | action | check | text |\n| --- | --- | --- | --- |\n"
        md += "".join(f"| {c.get('rule')} | {c.get('action')} | {c.get('check')} | {c.get('text') or ''} |\n" for c in rc)
    sh = report.get("shape")
    if isinstance(sh, dict):
        md += "\n## Shape\n"
        for k in ("hot_spots", "preparatory_refactors", "single_sources", "task_graph"):
            md += f"\n### {k.replace('_', ' ').capitalize()}\n\n" + "".join(
                f"- {json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x}\n" for x in sh.get(k) or []) \
                + ("" if sh.get(k) else "- none\n")
    return md


def _spawn(cfg: Config, q: Path, argv: list[str], many: bool = False) -> int:
    """Run the pass in its own session so it outlives the caller (a runner's shell call is shorter
    than a pass), and return once it is recorded as running. `many` (the several-ADR form, `--adr due`
    included) prints `review_ids` however many ids there are."""
    rids = argv[argv.index("--review-id") + 1].split(",")
    rid = rids[0]  # several shapes run in turn: the call returns once the first is running
    log = ar.rdir(q) / f"{rid}.log"
    with log.open("w") as fh:
        p = spawn_detached(cfg.root, q, ["architect", "run", *argv], stdout=fh, stderr=subprocess.STDOUT)
    deadline = time.time() + 30
    status = None
    while time.time() < deadline:
        status = (ar.load_state(q, ARCH).get("reviews", {}).get(rid) or {}).get("status")
        if status not in (None, "none") or p.poll() is not None:
            break
        time.sleep(0.2)
    status = (ar.load_state(q, ARCH).get("reviews", {}).get(rid) or {}).get("status")
    if status in (None, "none") and p.poll() is not None:
        text = log.read_text() if log.is_file() else ""
        try:
            return ar.out({**json.loads(text[text.find("{"):]), "detached": True}, p.returncode or 1)
        except ValueError:
            return ar.out({"outcome": "failed", "review_id": rid, "detached": True, "exit_code": p.returncode,
                           "log": str(log)}, 1)
    ids = {"review_ids": rids} if many else {}
    return ar.out({"outcome": "started", "review_id": rid, **ids, "status": status or "starting", "pid": p.pid,
                   "log": str(log), "detail": "The pass runs on its own; task work goes on. `ccp architect status` "
                                              "shows it; `ccp tasks next` notices the report."})


def _new_rid(mode: str, taken: set[str] | None = None) -> str:
    """A fresh review id: `sh-…` for a shape, `ar-…` for a pass, none of `taken`."""
    while True:
        rid = f"{'sh' if mode == 'shape' else 'ar'}-{ar.now_utc().strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"
        if rid not in (taken or set()):
            return rid


def _refused(cfg: Config, q: Path, a: argparse.Namespace, mode: str) -> tuple[dict[str, Any] | None, int, dict[str, Any]]:
    """§19.6 rule 5: why a run of `mode` may not start now (the outcome object and exit 3), or None; and `due_info`."""
    info = due_info(cfg, q, work_scope(q, a.scope))
    if mode == "pass":
        if not config.architect_on(cfg) and not a.force:
            return {"outcome": "disabled", **info}, 3, info
        if not a.force and not info["due"]:
            return {"outcome": "not_due", **info}, 3, info
        if info["running"] or info["awaiting_triage"]:
            return {"outcome": "blocked", "reason": info["reason"]}, 3, info
    elif info["running"]:
        return {"outcome": "blocked", "reason": info["reason"]}, 3, info
    return None, 0, info


def _head(cfg: Config) -> str:
    """§19.7 step 1: HEAD of the product root, and the architect skill present; else exit."""
    pr = str(cfg.root)
    head = ar.git(pr, "rev-parse", "HEAD")
    if not head:
        raise SystemExit(f"ccp architect: not a git checkout: {pr}")
    if not Path(ar.architect_skill(cfg.root)).is_file():
        raise SystemExit(f"ccp architect: no architect skill: neither {SKILL} nor the plugin's (SPEC §9.1)")
    return head


def cmd_run(cfg: Config, q: Path, a: argparse.Namespace, actor: str) -> int:
    """One pass, or (§19.5) one shape per ADR when `--adr` names several or `due`, one after another."""
    mode = a.mode or "pass"
    lenses = _lenses(a.lens)
    items = [x.strip() for x in (a.adr or "").split(",") if x.strip()]
    many = items == ["due"] or len(items) > 1
    adrs = adr_plan(a.adr, mode, lambda: shape_due(cfg, tasklog.load(cfg)), lambda x: adr_id(x, cfg))
    if mode == "shape" and not adrs:
        if many:
            return ar.out({"outcome": "not_due", "shape_due": [], "reason": "no ADR awaits a shape"}, 3)
        raise SystemExit("ccp architect run --mode shape: give --adr <id>")
    rids = [x for x in (a.rid or "").split(",") if x]
    if many and rids and len(rids) != len(adrs):
        raise SystemExit("ccp architect run: --review-id needs one id per ADR")
    if a.detach:
        refused, code, _ = _refused(cfg, q, a, mode)
        if refused:
            return ar.out(refused, code)
        _head(cfg)
        if not rids:
            for _ in adrs if many else [None]:
                rids.append(_new_rid(mode, set(rids)))
        return _spawn(cfg, q, ["--review-id", ",".join(rids), "--mode", mode, "--lens", ",".join(lenses),
                               "--actor", actor]
                      + (["--adr", ",".join(adrs)] if adrs else []) + (["--force"] if a.force else [])
                      + (["--scope", a.scope] if a.scope else []), many=many)
    if not many:
        return ar.out(*_run_one(cfg, q, a, actor, mode, lenses, adrs[0] if adrs else None, rids[0] if rids else None))
    runs: list[dict[str, Any]] = []
    for i, adr in enumerate(adrs):
        rid = rids[i] if rids else _new_rid(mode, {r.get("review_id") for r in runs})
        runs.append(_run_one(cfg, q, a, actor, mode, lenses, adr, rid)[0])
    return ar.out({"runs": runs}, 0 if all(r.get("outcome") == "reported" for r in runs) else 1)


def _make_worktree(cfg: Config, main: Path, path: Path, head: str) -> None:
    """§12.1 `arch-<review id>`: made detached at `head` from the main checkout, with `worktrees.links`
    linked in; env.setup is not run. A git error raises, and fails the pass."""
    wt.add_unrecorded(cfg, main, path, head)


def _abs_roots(*dirs: str) -> list[str]:
    """Each directory's absolute path, as given and resolved, once each (§19.7's absolute deny rules)."""
    return list(dict.fromkeys(x for d in dirs for x in (str(Path(d).absolute()), str(Path(d).resolve()))))


def _run_one(cfg: Config, q: Path, a: argparse.Namespace, actor: str, mode: str, lenses: list[str],
             adr: str | None, rid: str | None) -> tuple[dict[str, Any], int]:
    """One pass, synchronous (§19.7): its outcome object and exit code. Its headless call runs in its own
    worktree, `arch-<review id>` under the worktree directory (§12.1), detached at `head` and removed when
    the pass ends; with no worktree directory, in the product root."""
    s = _settings(cfg)
    refused, code, info = _refused(cfg, q, a, mode)
    if refused:
        return refused, code
    pr, pid = str(cfg.root), cfg.project_id
    head = _head(cfg)
    rid = rid or _new_rid(mode)
    dirty = bool(ar.git(pr, "status", "--porcelain", "--untracked-files=no"))
    timeout_s = int(s["call_timeout_minutes"]) * 60
    ok, cur = ar.lock_take(q, actor, rid, timeout_s + 600, ARCH)
    if not ok:
        return {"outcome": "locked", "lock": cur}, 3
    st = load(q, actor)
    last = st.get("last") or {}
    base = last.get("head")
    tasks = tasklog.load(cfg)
    done, tasked = sorted(_done(tasks)), _tasked_rules(tasks)
    result: dict[str, Any] = {"review_id": rid, "mode": mode, "lenses": lenses, "head": head, "base": base, "dirty": dirty}
    # This pass's record, re-applied on every write so no other writer can lose it.
    rec0 = {"mode": mode, "lenses": lenses, "adr": adr, "head": head, "base": base, "done": done,
            "started_at": fmt_dt(ar.now_utc()), "due_reason": info.get("reason")}
    # §12.1: the pass's own worktree, recorded before it is made so a pass that dies meanwhile is cleaned up.
    wdir, main = wt.base_dir(cfg), wt.main_checkout(cfg)
    own = wdir / f"{wt.ARCH_PREFIX}-{rid}" if wdir else None
    if own:
        rec0.update(worktree=str(own), main=str(main))

    def move(to: str, **fields: Any) -> None:
        ar.transition(q, {"reviews": {rid: {**rec0, **fields}}}, rid, to, actor, ARCH)

    try:
        if mode == "pass":
            ar.update_state(q, ARCH, lambda f: f.__setitem__(
                "last_attempt", {"review_id": rid, "done_count": len(done), "at": rec0["started_at"]}))
        move("running")
        if own:
            _make_worktree(cfg, main, own, head)
        cwd = str(own) if own else pr
        prompt = prompt_for(cfg, q, rid, mode, lenses, head, base, dirty, adr,
                            info["reason"] if info["due"] else "", last.get("started_at"), own_worktree=bool(own))
        tools = ar.BASE_READ_TOOLS + [f"Bash({p}:*)" for p in s["probes"]]
        deny = [ar.DENY_TOOLS] + deny_rules(list(s["private_dirs"]), _abs_roots(cwd, pr))
        argv = ["env"]
        for k in headless.STRIP_KEYS:
            argv += ["-u", k]
        argv += [os.environ.get("DA_CLAUDE_BIN") or "claude", "-p", prompt, *ar.headless_flags(cfg), *ar.plugin_args(cfg.root),
                 "--output-format", "json", "--allowedTools", ",".join(tools), "--disallowedTools", ",".join(deny)]
        audit = subprocess.run(
            ["bash", str(OBS / "write-prompt-audit.sh"), "--task-id", ARCH.audit_task, "--phase", f"architect-{mode}",
             "--prompt-file", "-", "--argv", json.dumps(argv), "--actor", actor, "--project-id", pid,
             "--worktree", cwd, "--git-head", head, "--notes", f"review_id={rid}"]
            + (["--keep-body"] if (cfg.prompts or {}).get("keep_body") else []),  # §23.8
            input=prompt, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)})
        if audit.returncode != 0:
            raise RuntimeError(f"write-prompt-audit failed: {audit.stderr.strip()}")
        prompt_ref = audit.stdout.strip().splitlines()[-1]
        result["prompt_ref"] = prompt_ref
        ar.emit(q, actor, "launch", {"review_id": rid, "phase": mode, "prompt_ref": prompt_ref}, ARCH)
        env = headless.headless_env(pid, f"architect-{mode}")
        try:
            proc = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=timeout_s, env=env)
            code, so, se = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            so = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            code, se = 124, "timeout"
        res = headless.parse_claude_json(so)
        ar.emit(q, actor, "exit", {"review_id": rid, "phase": mode, "exit_code": code}, ARCH)
        from ccp import usage  # noqa: PLC0415
        usage.record_headless(q, f"architect-{mode}", rid, res)
        is_quota, qclass, resets = headless.detect_quota(res, so, se)
        if is_quota:
            move("quota_parked", error=f"quota ({qclass}); resets {resets}")
            return {**result, "outcome": "quota_parked", "quota_class": qclass, "resets_at": resets,
                    "actions": [{"action": "retry_after_reset", "detail": "Run `ccp architect run --force` after the reset."}]}, 1
        report = ar.last_json_object(str(res.get("result") or ""))
        errs = validate(report, rid, pid, mode, lenses, refs.ids(cfg)) if report is not None else ["no JSON report in the final message"]
        if errs:
            (ar.rdir(q) / f"{rid}.failed.txt").write_text((str(res.get("result") or se or ""))[-20000:])
            move("failed", error="; ".join(errs)[:500])
            return {**result, "outcome": "failed", "errors": errs,
                    "actions": [{"action": "retry_next_due", "detail": f"Raw output kept in reviews/{rid}.failed.txt."}]}, 1
        report.update({"schema_version": 1, "review_id": rid, "project_id": pid, "head": head, "base": base,
                       "mode": mode, "lenses": lenses, "rule_changes": report.get("rule_changes") or []})
        if adr:
            report["adr"] = adr
        write_json(ar.report_path(q, rid), report)
        (ar.rdir(q) / f"{rid}.md").write_text(render(report))
        rec0.update(findings=len(report["findings"]), rule_changes=len(report["rule_changes"]),
                    done_at_report=sorted(_done(tasklog.load(cfg))))
        if mode == "pass":
            def finish(f: dict[str, Any]) -> None:
                f["last"] = {"review_id": rid, "started_at": rec0["started_at"], "at": fmt_dt(ar.now_utc()),
                             "head": head, "done": done, "health_drift": bool((info.get("health") or {}).get("drift")),
                             "budget_ids": sorted({b.split(":", 1)[0] for b in info.get("budget_failures") or []} - tasked)}
                f["seen"] = {}
            ar.update_state(q, ARCH, finish)
        if mode == "pass" and not report["findings"] and not report["rule_changes"]:
            move("no_findings")
            return {**result, "outcome": "no_findings", "report": str(ar.report_path(q, rid))}, 0
        move("reported")
        return {**result, "outcome": "reported", "findings": len(report["findings"]),
                "rule_changes": len(report["rule_changes"]), "report": str(ar.report_path(q, rid)),
                "actions": [{"action": "triage", "cmd": f"ccp architect triage {rid}"}]}, 0
    except Exception as exc:  # noqa: BLE001
        move("failed", error=str(exc)[:500])
        return {**result, "outcome": "failed", "errors": [str(exc)]}, 1
    finally:
        if own:
            _drop_worktree(main, own)
        ar.lock_release(q, actor, rid, ARCH)


# ---------------------------------------------------------------- triage

def triage_check(t: dict[str, Any], report: dict[str, Any]) -> list[str]:
    """§19.8 on top of §19's triage contract: rule-cost goes to the operator; every rule change is applied,
    rejected or taken to the operator, with a reason; applied changes are committed."""
    errs = []
    disp = {d.get("finding"): d.get("disposition") for d in t.get("dispositions") or [] if isinstance(d, dict)}
    for f in report.get("findings") or []:
        if f.get("category") == "rule-cost" and disp.get(f.get("id")) != "needs_operator":
            errs.append(f"{f.get('id')} is a rule-cost finding: its disposition is needs_operator (SPEC §19.8)")
    if any(v == "needs_operator" for v in disp.values()) and not t.get("question_for_operator"):
        errs.append("needs_operator dispositions without question_for_operator")
    got = t.get("rule_changes") or []
    if not isinstance(got, list):
        return errs + ["rule_changes is not a list"]
    seen = {(c.get("rule"), c.get("action")): c for c in got if isinstance(c, dict)}
    for c in report.get("rule_changes") or []:
        d = seen.get((c.get("rule"), c.get("action")))
        if not d:
            errs.append(f"rule change {c.get('action')} {c.get('rule')} has no disposition")
        elif d.get("disposition") not in RULE_DISPOSITIONS or not str(d.get("reason") or "").strip():
            errs.append(f"rule change {c.get('action')} {c.get('rule')}: disposition is one of "
                        f"{', '.join(RULE_DISPOSITIONS)}, with a reason")
    applied = [c for c in got if isinstance(c, dict) and c.get("disposition") == "applied"]
    if applied:
        sha = t.get("commit_sha")
        if sha == "pending":
            if not str(t.get("pending_change") or "").strip():
                errs.append("commit_sha pending needs a pending_change description")
        elif not ar.is_commit_sha(sha):
            errs.append("rule changes applied without commit_sha")
    return errs


def triage_extra(cfg: Config, report: dict[str, Any]) -> str:
    s = _settings(cfg)
    lines = [f"This is an architect {report.get('mode') or 'pass'} report (SPEC §19.8). "
             "Every rule-cost finding is needs_operator. "
             f"Apply each rule_changes entry to {s['rules_doc'] or 'the house rules (architect.rules_doc)'} or reject it "
             "with a reason, and list each in the triage file's rule_changes."]
    if report.get("mode") == "shape":
        lines.append(f"After this shape of {report.get('adr')}: write the shaping record "
                     f"{cfg.rel(cfg.reviews_dir)}/{report.get('review_id')}.md with the line `ADR: {report.get('adr')}`, "
                     "adjust the ADR's task graph, and create at most 3 preparatory refactor tasks "
                     "(kind: refactor) that its first feature tasks depend on.")
    return "\n".join(lines) + "\n"


def cmd_triage_list(q: Path) -> int:
    """Reports awaiting triage, with their report and triage-file paths. No `claude -p`."""
    st = ar.load_state(q, ARCH)
    rows = []
    for rid, rec in sorted((st.get("reviews") or {}).items()):
        if rec.get("status") in AWAITING:
            rows.append({"review_id": rid, "status": rec.get("status"), "mode": rec.get("mode"),
                         "report": str(ar.report_path(q, rid)), "triage_file": str(ar.triage_path(q, rid))})
    return ar.out({"outcome": "awaiting_triage", "reviews": rows,
                   "action": "Write each triage file in this checkout, then `ccp architect triage <id>` applies it. "
                             "No Mac and no claude -p."})


def unfinished_backfills(st: dict[str, Any]) -> list[dict[str, str]]:
    """Triages that finalised with commit_sha pending. Empty once --backfill records the sha."""
    rows = []
    for rid, rec in sorted((st.get("reviews") or {}).items()):
        if rec.get("commit_sha") != "pending":
            continue
        rows.append({
            "review_id": rid,
            "commit_sha": "pending",
            "pending_change": str(rec.get("pending_change") or ""),
        })
    return rows


def _commit_exists(root: Path, sha: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
        capture_output=True, text=True)
    return proc.returncode == 0


def _same_commit(recorded: str, sha: str) -> bool:
    a, b = recorded.lower(), sha.lower()
    return a == b or a.startswith(b) or b.startswith(a)


def cmd_backfill(cfg: Config, q: Path, rid: str, sha: str, actor: str) -> int:
    """Record the integration-branch sha for a triage that finalised with commit_sha pending."""
    if not ARCH.rid_re.match(rid):
        return ar.out({"outcome": "bad_review_id", "review_id": rid}, 2)
    if not ar.is_commit_sha(sha):
        return ar.out({"outcome": "invalid_sha", "review_id": rid,
                       "error": "backfill needs a 7 to 40 character hex sha"}, 2)
    if not _commit_exists(cfg.root, sha):
        return ar.out({"outcome": "unknown_commit", "review_id": rid, "commit_sha": sha,
                       "error": "that sha is not a commit in this checkout"}, 1)
    st = ar.load_state(q, ARCH)
    rec = (st.get("reviews") or {}).get(rid) or {}
    if rec.get("status") != "triaged":
        return ar.out({"outcome": "not_triaged", "review_id": rid, "status": rec.get("status")}, 1)
    current = str(rec.get("commit_sha") or "")
    if ar.is_commit_sha(current) and _same_commit(current, sha):
        return ar.out({"outcome": "already", "review_id": rid, "commit_sha": current})
    if current != "pending":
        return ar.out({"outcome": "not_pending", "review_id": rid, "commit_sha": current or None}, 1)
    tp = ar.triage_path(q, rid)
    if not tp.is_file():
        return ar.out({"outcome": "no_triage_file", "review_id": rid}, 1)
    t = read_json(tp)
    if not isinstance(t, dict):
        return ar.out({"outcome": "invalid_triage", "review_id": rid}, 1)
    full = subprocess.run(
        ["git", "-C", str(cfg.root), "rev-parse", f"{sha}^{{commit}}"],
        capture_output=True, text=True, check=True).stdout.strip()
    t["commit_sha"] = full
    t["backfilled_at"] = fmt_dt(ar.now_utc())
    write_json(tp, t)

    def apply(fresh: dict[str, Any]) -> None:
        row = fresh.setdefault("reviews", {}).setdefault(rid, {})
        row["commit_sha"] = full
        row["backfilled_at"] = t["backfilled_at"]

    ar.update_state(q, ARCH, apply)
    return ar.out({"outcome": "backfilled", "review_id": rid, "commit_sha": full,
                   "pending_change": rec.get("pending_change")})


def _rebuild_index(cfg: Config) -> str:
    """Regenerate INDEX.yaml from the durable task files. The triage file lives on the queue;
    the index lives on the product checkout."""
    from ccp import tasklog  # noqa: PLC0415

    return tasklog.write_index(cfg)


def cmd_apply(cfg: Config, q: Path, rid: str, actor: str) -> int:
    """Validate a triage file already committed by hand, finalise it, and rebuild the index.

    `ccp architect triage <id>` asks the lead to write the file when it is missing. A file
    committed ahead of architect.json (status still triage_sent) is this path: do not send a prompt.
    """
    if not ARCH.rid_re.match(rid):
        return ar.out({"outcome": "bad_review_id", "review_id": rid}, 2)
    rp, tp = ar.report_path(q, rid), ar.triage_path(q, rid)
    if not rp.is_file():
        return ar.out({"outcome": "no_report", "review_id": rid, "report": str(rp)}, 1)
    if not tp.is_file():
        return ar.out({"outcome": "no_triage_file", "review_id": rid, "triage_file": str(tp),
                       "error": "commit the triage file first; --apply does not ask anyone to write it"}, 1)
    t = read_json(tp)
    report = read_json(rp)
    errs = ar.validate_triage(t, rid) if isinstance(t, dict) else ["triage is not an object"]
    if not errs and isinstance(report, dict):
        errs = triage_check(t, report)
    elif not errs:
        errs = ["report is not an object"]
    if errs:
        return ar.out({"outcome": "invalid_triage", "review_id": rid, "errors": errs}, 1)
    st = ar.load_state(q, ARCH)
    status = (st.get("reviews") or {}).get(rid, {}).get("status")
    index = _rebuild_index(cfg)
    if status == "triaged":
        return ar.out({"outcome": "already_triaged", "review_id": rid, "index": index})
    result = ar.apply_triage(q, rid, actor, t, ARCH)
    return ar.out({**result, "outcome": "applied", "index": index})


def cmd_triage(cfg: Config, q: Path, rid: str, actor: str) -> int:
    s = _settings(cfg)
    rp = ar.report_path(q, rid)
    report = read_json(rp) if rp.is_file() else {}
    return ar.triage(q, rid, actor, ARCH, max_new=s["max_new_tasks"],
                     prompt_extra=triage_extra(cfg, report), extra_check=triage_check,
                     product_dir=str(cfg.root))


# ---------------------------------------------------------------- status and CLI

def _brief(rec: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in rec.items() if k not in ("done", "done_at_report")}
    if "done" in rec:
        out["done_count"] = len(rec["done"])
    return out


def main(cfg: Config, a: argparse.Namespace) -> int:
    q = queue_root()
    actor = ar.actor_of(a.actor)
    if a.action == "due":
        info = due_info(cfg, q, work_scope(q, a.scope))
        return ar.out(info, 0 if info["due"] else 3)
    if a.action == "run":
        return cmd_run(cfg, q, a, actor)
    if a.action == "triage":
        if a.backfill and a.review_id:
            print("ccp architect triage: pass the id to --backfill, not also as a positional", file=sys.stderr)
            return 2
        if a.apply and (a.review_id or a.backfill):
            print("ccp architect triage: pass the id to --apply, not also as a positional or --backfill",
                  file=sys.stderr)
            return 2
        if a.backfill:
            rid, sha = a.backfill
            return cmd_backfill(cfg, q, rid, sha, actor)
        if a.apply:
            return cmd_apply(cfg, q, a.apply, actor)
        if not a.review_id:
            return cmd_triage_list(q)
        return cmd_triage(cfg, q, a.review_id, actor)
    st = load(q, actor)
    return ar.out({"due": due_info(cfg, q, work_scope(q, a.scope), record=False),
                   "last": _brief(st.get("last") or {}) or None,
                   "reviews": {r: _brief(rec) for r, rec in st["reviews"].items()},
                   "backfills": unfinished_backfills(st)})
