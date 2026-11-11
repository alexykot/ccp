#!/usr/bin/env python3
"""The Claude team (SPEC §2): the runner teammate's lifecycle and the gate ledger.

Called through scripts/team.sh. Runtime files only: QUEUE_ROOT/work.json, escalations/, prompts/,
observability/events.jsonl (through the §23 writers). Never spawns agents, sends messages or
touches product git: it prints what the calling seat (the team lead or the runner) must do.

  runner prompt|spawn|bind|scope|rotate|stop|status   the lead's bookkeeping for the runner teammate (§10.2)
  gate open|decide|ask-operator|status|list    gates the runner raises and the design seat decides (§17.9)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (OPEN_GATE_STATUSES, _yaml_block_scalars, die, fmt_dt, looks_like_secret,  # noqa: E402
                 project_yaml_text, read_json, utcnow, work_lock, write_json)
import spec_maintainer as sm  # noqa: E402

LEAD, RUNNER = "design-seat", "task-runner"
GATE_CLASSES = ("operator", "spend", "merge", "credential", "security", "reauth", "other")
DECIDERS = ("design_seat", "operator_via_design_seat")
RUNNER_AUDIT_TASK = "_runner"


# ---------------------------------------------------------------- helpers

def out(obj: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    return code


def runner_cfg(root: Path) -> dict[str, str]:
    c = _yaml_block_scalars(project_yaml_text(root), "runner")
    c.setdefault("agent_type", "delivery-runner")
    # SPEC §9: the product's own copy of the runner while it has one, else the plugin's type.
    t = c["agent_type"].split(":", 1)[-1]
    prod = sm.product_root(root)
    if prod and not (Path(prod) / ".claude" / "agents" / f"{t}.md").is_file() \
            and (HERE.parents[1] / "plugin" / "agents" / f"{t}.md").is_file():
        c["agent_type"] = f"ccp:{t}"
    c.setdefault("name", "runner")
    c.setdefault("rotate_after_tasks", "4")
    return c


def live_name(rc: dict[str, str], w: dict[str, Any]) -> str:
    """§10.2: the live runner's teammate name: work.json `runner` as bound, else the binding's."""
    return str(w.get("runner") or rc["name"])


def max_in_flight(root: Path) -> int:
    """SPEC §16.2: the product's plane.json parallel.max_in_flight (1 when absent or unreadable)."""
    prod = sm.product_root(root)
    try:
        par = json.loads((Path(prod) / "docs" / "delivery" / "plane.json").read_text()).get("parallel") or {}
        return max(1, int(par.get("max_in_flight", 1)))
    except (OSError, ValueError, TypeError, AttributeError):
        return 1


def parallel_on(root: Path) -> bool:
    """SPEC §16.2: the product's plane.json sets parallel.max_in_flight above 1."""
    return max_in_flight(root) > 1


def slots_of(w: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """§16.4: work.json `runners`, slot -> record; {} for one runner."""
    r = w.get("runners")
    return {str(k): dict(v) if isinstance(v, dict) else {} for k, v in r.items()} if isinstance(r, dict) else {}


def slot_tasks(root: Path, w: dict[str, Any], slot: str) -> list[str]:
    """The tasks in flight a slot holds (their lease_holder)."""
    out = []
    for tid in [str(x) for x in w.get("in_flight") or []]:
        try:
            st = read_json(root / "tasks" / f"{tid}.json")
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(st, dict) and st.get("lease_holder") == slot and st.get("status") != "done":
            out.append(tid)
    return out


def holder_name(root: Path, task_id: str) -> str:
    """§16.5: the teammate name of the runner holding `task_id` (its slot's bound name), else the one runner's."""
    w = load_work(root)
    slots = slots_of(w)
    try:
        st = read_json(root / "tasks" / f"{task_id}.json") if task_id else {}
    except (OSError, json.JSONDecodeError):
        st = {}
    slot = str((st or {}).get("lease_holder") or "") if isinstance(st, dict) else ""
    if slot in slots:
        return str(slots[slot].get("bound_name") or slot)
    if slot and slots:  # a slot the lead removed: its own name, never the single runner's stale one
        return slot
    return live_name(runner_cfg(root), w)


def open_worker_runs(root: Path, w: dict[str, Any]) -> list[str]:
    """Worker runs of the runner's tasks (work.json in_flight and task_id) still pending or running:
    opened by `ccp prompt` and not reported, abandoned or stopped. ccp/runs.py counts `stopped` as
    open too; here it is not, since a stopped run's worker is gone and messages no one."""
    tasks = {str(t) for t in (w.get("in_flight") or [])} | ({str(w["task_id"])} if w.get("task_id") else set())
    busy = []
    for tid in sorted(tasks):
        for f in sorted((root / "runs" / tid).glob("*.json")) if (root / "runs" / tid).is_dir() else []:
            try:
                r = read_json(f)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(r, dict) and r.get("run_id") and not any(
                    r.get(k) for k in ("abandoned_at", "reported_at", "stopped_at")):
                busy.append(str(r["run_id"]))
    return busy


def work_path(root: Path) -> Path:
    return root / "work.json"


def load_work(root: Path) -> dict[str, Any]:
    p = work_path(root)
    if p.is_file():
        try:
            w = read_json(p)
            if isinstance(w, dict):
                return w
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _write_work(root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge `updates` into work.json as read now. The caller holds work.json's lock."""
    w = load_work(root)
    w.update(updates)
    w["updated_at"] = fmt_dt(utcnow())
    write_json(work_path(root), w)
    return w


def save_work(root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    with work_lock(root):  # §16.4: read and write under work.json's lock
        return _write_work(root, updates)


def split_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("["):
        return [str(x) for x in json.loads(raw)]
    return [x.strip() for x in raw.split(",") if x.strip()]


def emit(root: Path, task_id: str, actor: str, typ: str, op: str, payload: dict[str, Any]) -> None:
    sm.emit(root, sm.project_id(root), task_id, actor, typ, op, payload)


# ---------------------------------------------------------------- runner lifecycle (§10.2)

def refactor_log(root: Path, quiet: bool = False) -> tuple[Any, list[dict[str, Any]], Any] | None:
    """SPEC §20: the product's ccp config, its task log and ccp's tasklog module, when the product
    runs `refactor_in_scope: "deps"`; None otherwise (no plane.json, no architect block, another mode).
    An unreadable plane.json or task log refuses (exit 2, before any write), or gives None when quiet."""
    prod = sm.product_root(root)
    if not prod or not (Path(prod) / "docs" / "delivery" / "plane.json").is_file():
        return None
    sys.path.insert(0, str(HERE.parents[1]))
    from ccp import config as ccp_config, tasklog  # noqa: PLC0415
    try:
        cfg = ccp_config.load(Path(prod))
        if cfg.architect is None or cfg.architect["refactor_in_scope"] != "deps":
            return None
        tasks = tasklog.load(cfg)
    except Exception as e:  # noqa: BLE001  (a bad plane.json or task file: refuse cleanly, write nothing)
        if quiet:
            return None
        die(f"runner spawn: cannot read the product's task log ({e}); fix it first, so a new review point "
            "gets its waiting refactors (SPEC §20.3)", 2)
    return cfg, tasks, tasklog


def product_log(root: Path, quiet: bool = False) -> tuple[Any, list[dict[str, Any]], Any] | None:
    """The product's ccp config, its task log and ccp's reviewpoints module, or None when the product
    has no plane.json. An unreadable plane.json or task log refuses (exit 2, before any write), or
    gives None when quiet."""
    prod = sm.product_root(root)
    if not prod or not (Path(prod) / "docs" / "delivery" / "plane.json").is_file():
        return None
    sys.path.insert(0, str(HERE.parents[1]))
    from ccp import config as ccp_config, reviewpoints, tasklog  # noqa: PLC0415
    try:
        cfg = ccp_config.load(Path(prod))
        return cfg, tasklog.load(cfg), reviewpoints
    except Exception as e:  # noqa: BLE001  (a bad plane.json or task file: refuse cleanly, write nothing)
        if quiet:
            return None
        die(f"runner spawn: cannot read the product's task log ({e}); fix it first (SPEC §22)", 2)
    return None


def review_point_scope(root: Path, args: argparse.Namespace, scope: list[str], rp: str | None) -> tuple[list[str], list[str]]:
    """SPEC §22, at spawn: the scope and the review-point warnings. With the product's
    review-point register: `--review-point` must be R<n> in it (exit 2, before any write), and without
    `--scope` the scope is the point's open tagged tasks. Without a register, the rule before it,
    unchanged: a point that `task_log.review_point_pattern` refuses is a warning (close will not stamp
    it), and the missing register is named once on stderr."""
    prod = sm.product_root(root)
    reg_file = None
    if prod and (Path(prod) / "docs" / "delivery" / "plane.json").is_file():
        sys.path.insert(0, str(HERE.parents[1]))
        from ccp import config as ccp_config, reviewpoints as _rp  # noqa: PLC0415
        try:
            reg_file = _rp.path(ccp_config.load(Path(prod))).is_file()
        except Exception:  # noqa: BLE001  (a bad plane.json is reported by the commands that need it)
            reg_file = None
    # With a register the task log must read (the strict checks need it); without one, as before.
    log = product_log(root, quiet=not reg_file)
    if not log:
        return scope, []
    cfg, tasks, reviewpoints = log
    entries = reviewpoints.load(cfg)[0]
    for note in reviewpoints.notes(cfg, entries):
        print(f"warning: {note}", file=sys.stderr)
    if entries is None:
        problem = reviewpoints.problem(cfg, rp, None) if rp else None
        return scope, ([f"{problem}: `ccp tasks close` will not stamp it into the tasks it closes. Widen the pattern "
                        "in docs/delivery/plane.json, or name the review point to fit it"] if problem else [])
    if args.review_point:
        problem = reviewpoints.problem(cfg, args.review_point, entries)
        if problem:
            die(f"runner spawn --review-point: {problem}", 2)
        if not args.scope:
            scope = tagged_open(tasks, args.review_point)
            if not scope:
                die(f"no open task is tagged review_point: {args.review_point}; tag the point's tasks "
                    f"(`ccp review-points tag {args.review_point} …`) or pass --scope (SPEC §22)", 2)
            return scope, []
        from ccp import tasklog  # noqa: PLC0415
        return scope, scope_warnings(tasks, args.review_point, scope, tasklog.in_scope)
    if rp and (problem := reviewpoints.problem(cfg, rp, entries)):
        return scope, [f"work.json's {problem}; `ccp tasks close` will not stamp it. Respawn with --review-point "
                       "R<n> (`ccp review-points migrate` renames it, SPEC §22.4)"]
    return scope, []


def tagged_open(tasks: list[dict[str, Any]], rp: str) -> list[str]:
    """§22.4: the tasks attached to the point at planning time that are still open, in task order."""
    return [str(t.get("task_id")) for t in tasks
            if t.get("review_point") == rp and t.get("status") in ("pending", "in_progress", "blocked")]


def scope_warnings(tasks: list[dict[str, Any]], rp: str, scope: list[str], in_scope: Any) -> list[str]:
    """§22: a given --scope against the tasks tagged with the point. The refactors §20 puts on
    top are not the point's own tasks, so they are not named."""
    by_id = {str(t.get("task_id")): t for t in tasks}
    out = []
    untagged = [s for s in scope if (t := next((by_id[k] for k in by_id if in_scope(k, [s])), None)) is not None
                and t.get("review_point") != rp and t.get("kind") != "refactor"]
    if untagged:
        out.append(f"{len(untagged)} scope task(s) are not tagged {rp}: {', '.join(untagged)}. Set "
                   f"`review_point: {rp}` on them (`ccp review-points tag {rp} …`) if they belong to it")
    missing = [t for t in tagged_open(tasks, rp) if not in_scope(t, scope)]
    if missing:
        out.append(f"{len(missing)} open task(s) tagged {rp} are not in the scope: {', '.join(missing)}")
    return out


def waiting_hint(root: Path, scope: list[str]) -> None:
    """§20.4: name the refactors that wait, and how they join, on stderr. Changes nothing."""
    log = refactor_log(root, quiet=True)
    n = len(log[2].waiting_refactors(log[0], scope, log[1])) if log else 0
    if n:
        print(f"team.sh: {n} refactor(s) wait outside this scope; they join only when a new --review-point "
              "is given to `runner spawn` (SPEC §20.4)", file=sys.stderr)


def spawn_prompt(root: Path, scope: list[str], review_point: str | None, added: list[str] | None = None) -> str:
    pid = sm.project_id(root)
    rc = runner_cfg(root)
    lines = [
        f"You are the Task Runner for project {pid} (control-plane SPEC §2).",
        "Your agent definition is your brief: follow it exactly. Also read docs/delivery/LOCAL.md if it exists.",
        f"Queue root: {root}",
        f"Scope: {', '.join(scope)}" + (f" (review point {review_point})" if review_point else ""),
    ]
    if added:
        lines.append(f"Refactors waiting from earlier cycles, placed first in the scope (SPEC §20.4): {', '.join(added)}. "
                     "`ccp tasks next` returns them before the rest of the scope.")
    if rc.get("worktree"):
        lines.append(f"Runner worktree: {rc['worktree']}")
    lines.append("Start by reading work.json in the queue root: resume any task that is mid-flight at its "
                 "recorded phase, then take the next ready task in scope.")
    return "\n".join(lines) + "\n"


def runner_scope(root: Path, rc: dict[str, str], w: dict[str, Any], add: list[str], remove: list[str]) -> int:
    """Widen or narrow a running runner's scope (§10.2): work.json, a runner/scope event, a prompt audit.
    §16.4: judged and written under work.json's lock, on the file as read then, so a claim landing
    meanwhile is seen."""
    with work_lock(root):
        return _runner_scope(root, rc, load_work(root), add, remove)


def _runner_scope(root: Path, rc: dict[str, str], w: dict[str, Any], add: list[str], remove: list[str]) -> int:
    if not (add or remove):
        die("runner scope needs --add IDS and/or --remove IDS (task ids, comma-separated)", 2)
    if w.get("status") not in ("running", "draining"):
        die(f"no running runner (work.json status: {w.get('status')}); use `team.sh runner spawn --scope ...`", 2)
    sm.check_task_ids(root, add, "--add")
    sm.check_task_ids(root, remove, "--remove")
    old = list(w.get("scope") or [])
    # §16.4: any task the runner holds (in_flight), not only the one it acted on last
    held = [t for t in remove if t in (w.get("in_flight") or [])
            or (t == w.get("task_id") and w.get("phase") not in (None, "", "done", "idle"))]
    if held:
        die(f"--remove {', '.join(held)}: in flight (work.json in_flight); let the runner finish it, "
            "or `ccp tasks release` it first", 2)
    scope = [t for t in old if t not in remove] + [t for t in add if t not in old]
    if not scope:
        die("that would leave the scope empty; use `team.sh runner stop` instead", 2)
    added = [t for t in scope if t not in old]
    removed = [t for t in old if t not in scope]
    msg = (f"Scope change from the lead (team.sh runner scope): now {', '.join(scope)}."
           + (f" Added: {', '.join(added)}." if added else "")
           + (f" Removed: {', '.join(removed)}." if removed else "")
           + " work.json has it; take the next task with `ccp tasks next --scope` from work.json's scope.")
    audit = subprocess.run(
        ["bash", str(HERE / "write-prompt-audit.sh"), "--task-id", RUNNER_AUDIT_TASK, "--phase", "runner-scope",
         "--prompt-file", "-", "--actor", LEAD, "--project-id", sm.project_id(root),
         "--argv", json.dumps(["SendMessage", *[f"to={n}" for n in
                                                  ([str(r.get("bound_name") or k) for k, r in slots_of(w).items()]
                                                   or [live_name(rc, w)])]]),
         "--notes", f"scope={','.join(scope)}"],
        input=msg + "\n", capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(root)})
    if audit.returncode != 0:
        die(f"write-prompt-audit failed: {audit.stderr.strip()}")
    prompt_ref = audit.stdout.strip().splitlines()[-1]
    emit(root, "", LEAD, "runner", "scope", {"name": ",".join(sorted(slots_of(w))) or live_name(rc, w),
                                              "scope": scope, "added": added,
                                              "removed": removed, "prompt_ref": prompt_ref})
    # §20.4: a refactor the lead removes leaves the review point's list too, so a respawn does not put it back.
    _write_work(root, {"scope": scope, "review_point_refactors": [
        r for r in w.get("review_point_refactors") or [] if r not in removed]})
    if added:
        waiting_hint(root, scope)
    names = [str(r.get("bound_name") or k) for k, r in slots_of(w).items()] or [live_name(rc, w)]
    return out({"outcome": "scope_recorded", "scope": scope, "added": added, "removed": removed,
                "prompt_ref": prompt_ref, "actions": [{
                    "action": "message_teammate", "name": n, "message": msg,
                    "detail": "Send it now with SendMessage: exactly this message."} for n in names]})


def refactor_scope(root: Path, args: argparse.Namespace, w: dict[str, Any],
                   scope: list[str]) -> tuple[list[str], list[str], list[str]]:
    """§20.4 at a spawn: (the scope, the refactors put on top, the review point's refactor list). A new
    review point (not work.json's last one) starts with every waiting refactor on top, and work.json keeps
    that list for the review point. A respawn of the same review point (rotate, restart, or the lead
    naming the scope again) puts back the ones still pending; it never looks for new ones: a refactor
    filed mid-cycle waits for the next review point."""
    new_rp = bool(args.review_point) and args.review_point != w.get("review_point")
    log = refactor_log(root)
    if not log:
        added, rp_refactors = [], ([] if new_rp else list(w.get("review_point_refactors") or []))
    elif new_rp:
        added = [str(t["task_id"]) for t in log[2].waiting_refactors(log[0], scope, log[1])]
        rp_refactors = added
    else:
        pending = {str(t.get("task_id")) for t in log[1] if t.get("status") == "pending"}
        rp_refactors = list(w.get("review_point_refactors") or [])
        added = [r for r in rp_refactors if r in pending and r not in scope]
    scope = added + [t for t in scope if t not in added]
    if not new_rp:
        waiting_hint(root, scope)
    return scope, added, rp_refactors


def cmd_slots(args: argparse.Namespace, root: Path, rc: dict[str, str], w: dict[str, Any]) -> int:
    """SPEC §16.5: several runner teammates, one per slot (`<runner.name>-<n>`), each holding one task.
    work.json `runners` maps slot -> {bound_name, spawned_at, tasks_done, bind_pending, rotated_at,
    worktree}; status, scope and the review point stay queue-wide."""
    slots = slots_of(w)
    if args.op == "status":
        def phase(t: str) -> Any:
            try:
                return (read_json(root / "tasks" / f"{t}.json") or {}).get("status")
            except (OSError, json.JSONDecodeError):
                return None
        gates = [g["escalation_id"] for g in iter_gates(root) if g.get("status") in OPEN_GATE_STATUSES]
        return out({"work": {k: w.get(k) for k in ("status", "scope", "review_point", "in_flight", "updated_at")},
                    "runners": {k: {**v, "tasks": {t: phase(t) for t in slot_tasks(root, w, k)}}
                                for k, v in sorted(slots.items())},
                    "open_gates": gates, "open_questions": [q["question_id"] for q in sm.open_questions(root)]})
    if args.op == "spawn":
        scope = split_ids(args.scope) or list(w.get("scope") or [])
        rp = args.review_point or w.get("review_point")
        scope, rp_warnings = review_point_scope(root, args, scope, rp)
        if not scope:
            die("--scope required (task ids, comma-separated)", 2)
        scope, added, rp_refactors = refactor_scope(root, args, w, scope)
        cap = max_in_flight(root)
        if args.slot:
            if args.slot not in slots:
                die(f"--slot {args.slot}: no such slot ({', '.join(sorted(slots)) or 'none'})", 2)
            new = [args.slot]  # a respawn: after a rotation or a lead restart
        else:
            want = args.count or len(slots) or 1
            if want > cap:
                die(f"--count {want} is above parallel.max_in_flight {cap} (SPEC §16.5)", 2)
            new = [f"{rc['name']}-{i}" for i in range(1, want + 1) if f"{rc['name']}-{i}" not in slots]
            if not new:
                die(f"{want} slot(s) are recorded already; respawn one with --slot", 2)
            # §16.5: a task the single runner still holds would belong to no slot and stall
            orphans = []
            for t in [str(x) for x in w.get("in_flight") or []]:
                try:
                    st = read_json(root / "tasks" / f"{t}.json") or {}
                except (OSError, json.JSONDecodeError):
                    st = {}
                h = st.get("lease_holder") if isinstance(st, dict) else None
                if h and st.get("status") != "done" and h not in slots and h not in new:
                    orphans.append(f"{t} (held by {h})")
            if orphans:
                die(f"{', '.join(orphans)}: held by no runner slot. Drain or stop the single runner first "
                    "(`team.sh runner stop --drain`), or `ccp tasks release` it (SPEC §16.5)", 2)
        base = rc.get("worktree") or ""
        actions = []
        for slot in new:
            prompt = spawn_prompt(root, scope, rp, added) + (
                f"Your runner slot is {slot}: claim with `ccp tasks claim <task> --holder {slot}`, hold one task at a "
                f"time, and work from your own worktree: `ccp tasks worktree --runner {slot}` makes it and prints it "
                "(SPEC §16.5). Resume only the task your slot holds.\n")
            audit = subprocess.run(
                ["bash", str(HERE / "write-prompt-audit.sh"), "--task-id", RUNNER_AUDIT_TASK, "--phase", "runner-spawn",
                 "--prompt-file", "-", "--actor", LEAD, "--project-id", sm.project_id(root),
                 "--argv", json.dumps(["Agent", f"name={slot}", f"subagent_type={rc['agent_type']}"]),
                 "--notes", f"slot={slot} scope={','.join(scope)}"],
                input=prompt, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(root)})
            if audit.returncode != 0:
                die(f"write-prompt-audit failed: {audit.stderr.strip()}")
            prompt_ref = audit.stdout.strip().splitlines()[-1]
            emit(root, "", LEAD, "runner", "spawn", {"name": slot, "scope": scope, "prompt_ref": prompt_ref,
                                                      "review_point": rp, "slot": slot})
            was = slots.get(slot, {})
            slots[slot] = {"bound_name": slot, "spawned_at": fmt_dt(utcnow()), "tasks_done": 0,
                           "bind_pending": bool(was.get("rotated_at")), "rotated_at": None,
                           "worktree": was.get("worktree") or (f"{base}-{slot}" if base else None)}
            actions.append({"action": "spawn_teammate", "name": slot, "subagent_type": rc["agent_type"], "prompt": prompt,
                            "detail": "Spawn it now with the Agent tool: exactly this name, agent type and prompt. "
                                      f"Then `team.sh runner bind --name <the name the Agent result gave> --as {slot}`, "
                                      "whatever the name."})
        save_work(root, {"status": "running", "scope": scope, "review_point": rp,
                         "review_point_refactors": rp_refactors, "runners": slots})
        for rpw in rp_warnings:
            print(f"warning: {rpw}", file=sys.stderr)
        return out({"outcome": "spawn_recorded", "slots": new, "scope": scope, "refactors_added": added, "actions": actions,
                    **({"warnings": rp_warnings} if rp_warnings else {})})
    if args.op == "bind":
        name, slot = (args.name or "").strip(), (args.as_slot or args.slot or "").strip()
        if not name or any(c.isspace() for c in name) or slot not in slots:
            die(f"runner bind needs --name NAME --as SLOT (slots: {', '.join(sorted(slots))})", 2)
        if other := [k for k, v in slots.items() if k != slot and str(v.get("bound_name") or k) == name]:
            die(f"{name} is bound to {other[0]} already: one teammate name per slot (SPEC §16.4)", 2)
        was = str(slots[slot].get("bound_name") or slot)
        slots[slot].update(bound_name=name, bind_pending=False)
        emit(root, "", LEAD, "runner", "bound", {"name": name, "previous": was, "slot": slot})
        save_work(root, {"runners": slots})
        return out({"outcome": "bound", "slot": slot, "name": name, "previous": was})
    if args.op == "rotate":
        slot = args.slot or ""
        if slot not in slots:
            die(f"runner rotate needs --slot SLOT ({', '.join(sorted(slots))})", 2)
        name = str(slots[slot].get("bound_name") or slot)
        busy = open_worker_runs(root, {"in_flight": slot_tasks(root, w, slot)})
        if busy and not args.force:
            die(f"runner rotate: {slot}'s worker run(s) still open: {', '.join(busy)}. Let them report, then rotate. "
                "A run whose worker is gone: --force --reason", 3)
        if busy and not (args.reason or "").strip():
            die("runner rotate --force needs --reason (why the open runs are not waited for)", 2)
        emit(root, "", LEAD, "runner", "rotate", {"name": name, "reason": args.reason or "rotate", "slot": slot})
        slots[slot]["rotated_at"] = fmt_dt(utcnow())
        save_work(root, {"runners": slots})
        return out({"outcome": "rotate_recorded", "slot": slot, "actions": [
            {"action": "shutdown_teammate", "name": name,
             "detail": "Send the shutdown_request and wait for its acknowledgement; without one, stop it (TaskStop)."},
            {"action": "respawn", "cmd": f"team.sh runner spawn --slot {slot}",
             "detail": f"Once {name} is gone; then `team.sh runner bind --name <the Agent result's name> --as {slot}`."}]})
    if args.op == "stop":
        if args.slot and args.slot not in slots:
            die(f"--slot {args.slot}: no such slot ({', '.join(sorted(slots))})", 2)
        which = [args.slot] if args.slot else sorted(slots)
        if args.slot and not args.drain and (mine := slot_tasks(root, w, args.slot)):
            die(f"--slot {args.slot} holds {', '.join(mine)}: `stop --slot {args.slot} --drain` lets it finish, or "
                f"`ccp tasks release` it first (SPEC §16.5)", 2)
        acts, held = [], []
        for slot in which:
            name = str(slots[slot].get("bound_name") or slot)
            emit(root, "", LEAD, "runner", "stop", {"name": name, "reason": args.reason or "stop", "slot": slot})
            acts.append({"action": "message_teammate", "name": name,
                         "message": "Drain: finish the task you hold, report, then stop."} if args.drain
                        else {"action": "shutdown_teammate", "name": name})
            held += slot_tasks(root, w, slot)
            if not args.drain and args.slot:
                slots.pop(slot)
        upd: dict[str, Any] = {"runners": slots}
        if not args.slot:
            upd["status"] = "draining" if args.drain else "idle"
        save_work(root, upd)
        warn = [f"{', '.join(held)} still held by the stopped runners: `team.sh runner spawn --slot <slot>` "
                 "resumes each, or `ccp tasks release` it"] if held and not args.drain else []
        return out({"outcome": "stop_recorded", "actions": acts, **({"warnings": warn} if warn else {})})
    die(f"runner {args.op}: not with runner slots (SPEC §16.5)", 2)
    return 2


def cmd_runner(args: argparse.Namespace) -> int:
    root = sm.root_dir()
    rc = runner_cfg(root)
    w = load_work(root)
    if args.op == "status" and slots_of(w):
        return cmd_slots(args, root, rc, w)
    if args.op == "status":
        gates = [g for g in iter_gates(root) if g.get("status") in OPEN_GATE_STATUSES]
        qs = [q["question_id"] for q in sm.open_questions(root)]
        keys = ("status", "phase", "task_id", "scope", "review_point", "runner", "runner_tasks_done",
                "waiting_on", "waiting_on_detail", "updated_at")
        return out({"work": {k: w.get(k) for k in keys}, "open_gates": [g["escalation_id"] for g in gates],
                    "open_questions": qs})

    if args.op == "scope":
        return runner_scope(root, rc, w, split_ids(args.add), split_ids(args.remove))
    if args.slot or slots_of(w) or (args.op == "spawn" and (args.count or 1) > 1):
        return cmd_slots(args, root, rc, w)

    scope = split_ids(args.scope) or list(w.get("scope") or [])
    rp = args.review_point or w.get("review_point")
    rp_warnings: list[str] = []
    if args.op in ("spawn", "prompt"):
        scope, rp_warnings = review_point_scope(root, args, scope, rp)
    if args.op == "prompt":
        for rpw in rp_warnings:
            print(f"warning: {rpw}", file=sys.stderr)
        if not scope:
            die("--scope required (task ids, comma-separated)", 2)
        sys.stdout.write(spawn_prompt(root, scope, rp))
        return 0

    if args.op == "spawn":
        if not scope:
            die("--scope required (task ids, comma-separated)", 2)
        scope, added, rp_refactors = refactor_scope(root, args, w, scope)
        prompt = spawn_prompt(root, scope, rp, added)
        audit = subprocess.run(
            ["bash", str(HERE / "write-prompt-audit.sh"), "--task-id", RUNNER_AUDIT_TASK, "--phase", "runner-spawn",
             "--prompt-file", "-", "--actor", LEAD, "--project-id", sm.project_id(root),
             "--argv", json.dumps(["Agent", f"name={rc['name']}", f"subagent_type={rc['agent_type']}"]),
             "--notes", f"scope={','.join(scope)}"],
            input=prompt, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(root)})
        if audit.returncode != 0:
            die(f"write-prompt-audit failed: {audit.stderr.strip()}")
        prompt_ref = audit.stdout.strip().splitlines()[-1]
        # §10.2: after a rotation the old teammate may still hold the name, so the harness may name the
        # fresh one otherwise; until the lead binds it, the hook nudges no one.
        pending = bool(w.get("runner_rotated_at")) and str(w.get("runner_rotated_at")) >= str(w.get("runner_spawned_at") or "")
        # §16.5: one runner at a time. A runner still recorded live (running or draining, not rotated
        # since its spawn: a rotation shut it down already) is stopped before the new one starts.
        old = live_name(rc, w) if w.get("status") in ("running", "draining") and not pending else None
        if old:
            emit(root, "", LEAD, "runner", "stop", {"name": old, "reason": "respawn"})
        emit(root, "", LEAD, "runner", "spawn", {"name": rc["name"], "scope": scope, "prompt_ref": prompt_ref,
                                                  "review_point": rp, "refactors_added": added})
        save_work(root, {"status": "running", "scope": scope, "review_point": rp,
                         "review_point_refactors": rp_refactors, "runner_bind_pending": pending,
                         "runner": rc["name"], "runner_spawned_at": fmt_dt(utcnow()), "runner_tasks_done": 0})
        detail = ("Spawn it now with the Agent tool: exactly this name, agent type and prompt. If the Agent result "
                  f"names the teammate otherwise (such as `{rc['name']}-2`, while the old one holds the name), run "
                  "`team.sh runner bind --name <that name>` at once, so the hook and the workers' prompts follow it.")
        if pending:
            detail += (" After a rotation the bind is required, whatever the name: until it runs, the idle hook "
                       "keeps no teammate working.")
        if added:
            detail += (f" The scope starts with the refactors waiting from earlier cycles ({', '.join(added)}, "
                       "SPEC §20), and `ccp tasks next` takes them first; `team.sh runner scope --remove` "
                       "takes one out.")
        for rpw in rp_warnings:
            print(f"warning: {rpw}", file=sys.stderr)
        stop = [{"action": "shutdown_teammate", "name": old,
                 "detail": f"First, before the spawn: send {old} the shutdown_request and wait for its "
                           "acknowledgement; without one, stop it (TaskStop). If it is gone already (a restarted "
                           "lead session), go on. Spawn only once it is gone: one runner at a time."}] if old else []
        return out({"outcome": "spawn_recorded", "prompt_ref": prompt_ref, "scope": scope, "refactors_added": added,
                    **({"warnings": rp_warnings} if rp_warnings else {}),
                    **({"stopped": old} if old else {}),
                    "actions": stop + [{"action": "spawn_teammate", "name": rc["name"],
                                        "subagent_type": rc["agent_type"], "prompt": prompt, "detail": detail}]})

    if args.op == "bind":
        name = (args.name or "").strip()
        if not name or any(c.isspace() for c in name):
            die("runner bind needs --name NAME, the teammate name the Agent result gave the runner", 2)
        if w.get("status") not in ("running", "draining"):
            die(f"no running runner (work.json status: {w.get('status')}); `team.sh runner spawn` first", 2)
        was = live_name(rc, w)
        emit(root, "", LEAD, "runner", "bound", {"name": name, "previous": was})
        save_work(root, {"runner": name, "runner_bind_pending": False})
        return out({"outcome": "bound", "name": name, "previous": was, "actions": [] if was == name else [
            {"action": "stop_teammate", "name": was,
             "detail": f"If {was} is still there, stop it (TaskStop): it is no longer the runner, and the hook "
                       "no longer keeps it working."}]})

    if args.op == "rotate":
        name = live_name(rc, w)
        # §16.5 rule 5: a worker's prompt names the runner that launched it, so rotation waits for quiet
        busy = open_worker_runs(root, w) if parallel_on(root) else []
        if busy and not args.force:
            die(f"runner rotate: worker run(s) still open: {', '.join(busy)}. Let them report (the runner "
                "takes no new claim meanwhile), then rotate. A run whose worker is gone: --force --reason", 3)
        if busy and not (args.reason or "").strip():
            die("runner rotate --force needs --reason (why the open runs are not waited for)", 2)
        emit(root, "", LEAD, "runner", "rotate", {"name": name, "reason": args.reason or "rotate"})
        save_work(root, {"runner_rotated_at": fmt_dt(utcnow())})
        return out({"outcome": "rotate_recorded", "actions": [
            {"action": "shutdown_teammate", "name": name,
             "detail": "Send the shutdown_request and wait for its acknowledgement; without one, stop it "
                       f"(TaskStop). Spawn only once {name} is gone: while it holds the name, the fresh one gets "
                       "a suffixed name."},
            {"action": "respawn", "cmd": "team.sh runner spawn",
             "detail": "Once the old runner has shut down: same scope, from work.json. If the Agent result still "
                       "names it otherwise, `team.sh runner bind --name <that name>`."}]})

    if args.op == "stop":
        name = live_name(rc, w)
        emit(root, "", LEAD, "runner", "stop", {"name": name, "reason": args.reason or "stop"})
        save_work(root, {"status": "idle" if not args.drain else "draining"})
        act = ({"action": "message_teammate", "name": name,
                "message": "Drain: finish the phase in flight, write work.json, report, then stop."}
               if args.drain else {"action": "shutdown_teammate", "name": name})
        return out({"outcome": "stop_recorded", "actions": [act]})
    die(f"unknown runner op {args.op}", 2)
    return 2


# ---------------------------------------------------------------- gates (§17.9)

def esc_dir(root: Path, task_id: str) -> Path:
    return root / "escalations" / task_id


def iter_gates(root: Path) -> list[dict[str, Any]]:
    res = []
    base = root / "escalations"
    if not base.is_dir():
        return res
    for p in sorted(base.glob("*/*.json")):
        try:
            g = read_json(p)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(g, dict) and g.get("to") == "design_seat":
            g["_path"] = str(p)
            res.append(g)
    return res


def find_gate(root: Path, eid: str) -> tuple[Path, dict[str, Any]]:
    task_id, _, n = eid.rpartition("-")
    p = esc_dir(root, task_id) / f"{n}.json"
    if not task_id or not n.isdigit() or not p.is_file():
        die(f"no gate {eid} (expected escalations/<task_id>/<n>.json)", 2)
    return p, read_json(p)


def cmd_gate(args: argparse.Namespace) -> int:
    root = sm.root_dir()
    pid = sm.project_id(root)
    now_s = fmt_dt(utcnow())

    if args.op == "open":
        if args.cls not in GATE_CLASSES:
            die(f"--class must be one of {', '.join(GATE_CLASSES)}", 2)
        d = esc_dir(root, args.task_id)
        d.mkdir(parents=True, exist_ok=True)
        n = 1 + max([int(p.stem) for p in d.glob("*.json") if p.stem.isdigit()] or [0])
        eid = f"{args.task_id}-{n}"
        g: dict[str, Any] = {
            "task_id": args.task_id, "project_id": pid, "escalation_id": eid, "class": args.cls,
            "to": "design_seat", "brief": args.brief, "ask": args.ask, "raised_by": RUNNER,
            "status": "open", "resolution": None, "question_ref": None, "decision": None, "decided_by": None,
            "authority": None, "decided_at": None, "created_at": now_s, "updated_at": now_s,
        }
        if args.standing:
            g.update({"status": "closed", "decision": "approved", "decided_by": "standing",
                      "authority": args.standing, "decided_at": now_s,
                      "resolution": f"Pre-approved by the standing approval at {args.standing}"})
        if looks_like_secret(json.dumps(g)):
            die("refusing secret-like value in gate")
        write_json(d / f"{n}.json", g)
        emit(root, args.task_id, RUNNER, "gate", "opened",
             {"escalation_id": eid, "class": args.cls, "standing": bool(args.standing)})
        if args.standing:
            emit(root, args.task_id, RUNNER, "gate", "decided",
                 {"escalation_id": eid, "decision": "approved", "decided_by": "standing", "authority": args.standing})
            return out({"escalation_id": eid, "outcome": "approved_standing", "actions": [
                {"action": "proceed", "detail": "Standing approval recorded; do the step."}]})
        sm.set_wait(root, "set", args.task_id, "design_seat", RUNNER, pid, eid)
        return out({"escalation_id": eid, "outcome": "open", "actions": [{
            "action": "send_message_to_lead", "to": "team-lead",
            "message": (f"Gate {eid} ({args.cls}) for task {args.task_id}: {args.brief}"
                        + (f" Ask: {args.ask}" if args.ask else "")
                        + f" Decide with: team.sh gate decide {eid} --decision approved|refused "
                          "--resolution TEXT --authority TEXT"),
            "detail": f"Do not do the step until `team.sh gate status {eid}` exits 0. Skip ahead meanwhile."}]})

    if args.op in ("decide", "ask-operator", "status"):
        p, g = find_gate(root, args.escalation_id)
        eid = g["escalation_id"]
        if args.op == "status":
            code = 0 if (g.get("status") == "closed" and g.get("decision") == "approved") else (
                4 if g.get("decision") == "refused" else 3)
            return out({k: g.get(k) for k in ("escalation_id", "task_id", "class", "status", "decision",
                                              "decided_by", "authority", "resolution")}, code)
        if g.get("status") == "closed":
            die(f"gate {eid} is already closed ({g.get('decision')})", 2)
        was = "operator" if g.get("status") == "waiting_operator" else "design_seat"
        if args.op == "ask-operator":
            g.update({"status": "waiting_operator", "updated_at": now_s})
            write_json(p, g)
            emit(root, g["task_id"], LEAD, "gate", "escalated", {"escalation_id": eid})
            sm.set_wait(root, "set", g["task_id"], "operator_decision", LEAD, pid, eid)
            warn = sm.notify_operator(root, "decision", str(g["task_id"]), eid)  # §3.6
            return out({"escalation_id": eid, "outcome": "waiting_operator", **({"warnings": warn} if warn else {}), "actions": [
                {"action": "ask_operator_in_session", "detail": "Ask the operator here; then team.sh gate decide "
                                                                f"{eid} --by operator_via_design_seat ..."}]})
        if args.decision not in ("approved", "refused"):
            die("--decision must be approved or refused", 2)
        if not (args.resolution and args.authority):
            die("--resolution and --authority are required (SPEC §17.9)", 2)
        by = args.by or ("operator_via_design_seat" if was == "operator" else "design_seat")
        if by not in DECIDERS:
            die(f"--by must be one of {', '.join(DECIDERS)}", 2)
        g.update({"status": "closed", "decision": args.decision, "decided_by": by, "authority": args.authority,
                  "resolution": args.resolution, "decided_at": now_s, "updated_at": now_s})
        if looks_like_secret(json.dumps(g)):
            die("refusing secret-like value in gate")
        write_json(p, g)
        emit(root, g["task_id"], LEAD, "gate", "decided",
             {"escalation_id": eid, "decision": args.decision, "decided_by": by, "authority": args.authority})
        sm.set_wait(root, "clear", g["task_id"], "gate_decided", LEAD, pid, eid)
        return out({"escalation_id": eid, "outcome": args.decision, "actions": [{
            "action": "message_teammate", "name": holder_name(root, str(g.get("task_id") or "")),
            "message": f"Gate {eid} {args.decision}: {args.resolution} (authority: {args.authority}).",
        }]})

    if args.op == "list":
        gates = iter_gates(root)
        if args.open:
            gates = [g for g in gates if g.get("status") in OPEN_GATE_STATUSES]
        return out({"gates": [{k: g.get(k) for k in ("escalation_id", "class", "status", "decision", "brief")}
                              for g in gates]})
    die(f"unknown gate op {args.op}", 2)
    return 2


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="team.sh", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("runner")
    r.add_argument("op", choices=("prompt", "spawn", "bind", "scope", "rotate", "stop", "status"))
    r.add_argument("--name", help="runner bind: the teammate name the Agent result gave the runner")
    r.add_argument("--scope")
    r.add_argument("--add", help="runner scope: task ids to add, comma-separated")
    r.add_argument("--remove", help="runner scope: task ids to remove, comma-separated")
    r.add_argument("--review-point")
    r.add_argument("--reason")
    r.add_argument("--drain", action="store_true")
    r.add_argument("--force", action="store_true", help="runner rotate: even with worker runs open (needs --reason)")
    r.add_argument("--count", type=int, help="runner spawn: this many runner slots (SPEC §16.5; at most max_in_flight)")
    r.add_argument("--slot", help="spawn, rotate, stop: one runner slot (SPEC §16.5)")
    r.add_argument("--as", dest="as_slot", metavar="SLOT", help="runner bind: the slot the name belongs to")
    r.set_defaults(fn=cmd_runner)
    g = sub.add_parser("gate")
    g.add_argument("op", choices=("open", "decide", "ask-operator", "status", "list"))
    g.add_argument("escalation_id", nargs="?")
    g.add_argument("--task-id")
    g.add_argument("--class", dest="cls")
    g.add_argument("--brief")
    g.add_argument("--ask")
    g.add_argument("--standing")
    g.add_argument("--decision")
    g.add_argument("--resolution")
    g.add_argument("--authority")
    g.add_argument("--by")
    g.add_argument("--open", action="store_true")
    g.set_defaults(fn=cmd_gate)
    argv = list(sys.argv[1:] if argv is None else argv)
    args = ap.parse_args(argv)
    if args.cmd == "gate":
        if args.op == "open" and not (args.task_id and args.cls and args.brief):
            ap.error("gate open needs --task-id, --class and --brief")
        if args.op in ("decide", "ask-operator", "status") and not args.escalation_id:
            ap.error(f"gate {args.op} needs an escalation id")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
