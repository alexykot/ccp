"""A task's runtime lifecycle (SPEC §10.5): claim, phase, wait and resume, release, close.

Each command does the step and writes what it changed to the ledger, so a seat cannot do the one
without the other. They replace the claim and reconcile the runner briefs used to describe in prose,
and the scripts runners wrote for themselves (§10.6).

`claim` samples the allowance first: past the weekly checkpoint a new claim refuses (exit 5), and at
the 5-hour park % any claim parks the task and refuses (exit 6, §25.4).

`close` is the merge and the reconcile as one step: `ccp verify merge-ok` first (§15.5), then the
merge pinned to the head it printed, then the task file, the product's records (`reconcile.log`,
`reconcile.hooks`), the index, one commit pushed to the integration branch, the adapter's
`post_close` commands and the queue. It refuses before merging when the runner worktree has
changes, so everything it commits is its own. Run it from the runner worktree (§12.1).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ccp.envvars import envvar, for_child
from ccp import refs, runs, tasklog
from ccp.queue import lib
from ccp.config import Config
from ccp.queue import (OBS, QueueError, actor, durable_statuses, emit, file_lock, git, heartbeat, integration_branch, iso,
                       load_task_state, load_work, now, phase_move, preferred_ids, progress_event, root,
                       runner_slots, save_task_state, save_work, script_drift, set_marker, task_meta, task_state_path)

VERIFY_PLACEHOLDER_RE = re.compile(r"^\*Append-only[^\r\n]*\*[ \t]*\r?$", re.M)


def _main_checkout(cfg: Config) -> Path:
    from ccp.prompt import main_checkout  # noqa: PLC0415

    return main_checkout(cfg)


def _worktree(cfg: Config, q: Path, tid: str) -> dict[str, Any] | None:
    """The task's implement worktree (§12.1, `ccp wt create --kind impl`): `impl-<nnnn>` under
    `worktrees.dir`, on `task/<id>` from origin/<integration>, links in, env.setup run when it is new.
    Kept when it already exists (a claim resumed after a restart)."""
    if not (cfg.worktrees or {}).get("dir") or envvar("CCP_NO_WORKTREE") == "1":
        return None
    from ccp import wt  # noqa: PLC0415

    st = wt.create(cfg, q, tid, "impl")
    out = {"path": st["path"], "branch": st["branch"], "created": st["created"], "name": st["name"]}
    if st.get("base"):
        out["base"] = st["base"]
    return out


STOPPED = ("draining", "stopped", "stopping")
EXIT_AUTH = 8  # §30: an auth probe failed, so `ccp tasks claim` took no task (7 is §16.3's "carry on")


def claim(cfg: Config, task: str, holder: str = "runner") -> dict[str, Any]:
    q = root()
    meta = task_meta(cfg, task)
    tid = str(meta["task_id"])
    if tasklog.canonical_status(meta.get("status")) != "pending":
        raise QueueError(f"{tid} is {meta.get('status')} in its task file: only a pending task is claimed", 3)
    st = load_task_state(q, tid)
    if st.get("status") == "done":
        raise QueueError(f"{tid} is done in the queue (tasks/{tid}.json)", 3)
    resumed = bool(st.get("lease_holder"))
    if resumed and st.get("lease_holder") != holder:
        raise QueueError(f"{tid} is held by {st['lease_holder']}: it releases it first. A runner that lost a race "
                         "for it asks `ccp tasks next` again (SPEC §16.5)", 3)
    slots = runner_slots(load_work(q))
    if slots:  # §16.4: runner slots: each claims as its slot, and holds one task
        if holder not in slots:
            raise QueueError(f"--holder {holder!r} is no runner slot ({', '.join(sorted(slots))}): claim with "
                             "--holder <your slot> (SPEC §16.4)", 2)
        if not resumed and (mine := [x for x in load_work(q).get("in_flight") or []
                                     if x != tid and load_task_state(q, str(x)).get("lease_holder") == holder]):
            from ccp import parallel  # noqa: PLC0415
            raise QueueError(f"{holder} already holds {', '.join(map(str, mine))}: one task per runner (SPEC §16.4). "
                             "Carry on with it", parallel.EXIT_SLOTS)
    from ccp import parallel, usage  # noqa: PLC0415
    if not resumed and (cfg.auth_check or {}).get("probes"):  # §30: the auth probes, before each task
        from ccp import wt as wtmod  # noqa: PLC0415
        auth = wtmod.auth_check(cfg, q)
        if not auth["ok"]:
            failed = ", ".join(f"{r['id']} (exit {r['exit']})" for r in auth["probes"] if not r["ok"])
            raise QueueError(f"auth probe(s) failed: {failed}. Set waiting_on reauth and raise it to the lead "
                             "(SPEC §30); `ccp auth check` shows each", EXIT_AUTH)
    # §25.1: refuses (exit 5) past the project's weekly stop; a resumed claim of its own lease is not refused.
    sample = usage.sample_allowance(cfg, q, gate=not resumed)
    status = str(load_work(q).get("status") or "")
    # The runner is started by `team.sh runner spawn` (status running); `stop` leaves idle.
    stopped = STOPPED + ("idle",)
    if not resumed and status in stopped:
        raise QueueError(f"work.json says {status}: the runner finishes what it holds and takes no new task", 3)
    # §16.3: beside tasks already in flight, a new claim must be able to join them (after the weekly stop
    # and a stopped runner, which say more; before the session park, which would park a task not taken)
    active = parallel.active_tasks(cfg, q, load_work(q), but=tid) if not resumed and parallel.enabled(cfg) else []
    if why := parallel.join_refusal(cfg, meta, active, sample):
        raise QueueError(f"{tid} cannot join the task(s) in flight: {why}. Carry on with what you hold (SPEC §16.3)",
                         parallel.EXIT_SLOTS)
    # §25.4 the session park: refuses (exit 6) and parks the task at the 5-hour park %, new or resumed
    session_warn = usage.session_step(cfg, q, tid, sample, "the claim")  # best effort but the park
    if not resumed:
        with file_lock(task_state_path(q, tid)):  # §16.4: two runners claiming one task: one wins
            again = load_task_state(q, tid).get("lease_holder")
            if again and again != holder:
                raise QueueError(f"{tid} is held by {again}: another runner claimed it meanwhile. Ask "
                                 "`ccp tasks next` again (SPEC §16.5)", 3)
            save_task_state(q, tid, {"lease_holder": holder, "task_id": tid})
    try:
        wt = _worktree(cfg, q, tid)
    except Exception:
        if not resumed:  # the lease taken just above is given back: the claim did not happen
            with file_lock(task_state_path(q, tid)):
                if load_task_state(q, tid).get("lease_holder") == holder:
                    save_task_state(q, tid, {"lease_holder": None})
        raise
    t = now()
    if not resumed:
        state = {"task_id": tid, "project_id": cfg.project_id, "title": meta.get("title"),
                 "kind": tasklog.kind_of(meta), "durable_path": cfg.rel(meta["_file"]),
                 "spec_refs": tasklog._as_list(meta.get("spec_refs")), "adr_refs": tasklog._as_list(meta.get("adr_refs")),
                 "depends_on": tasklog._as_list(meta.get("depends_on")), "dod_checks": meta["_checks"],
                 "integration_branch": integration_branch(q), "status": "leased", "lease_holder": holder,
                 "lease_since": iso(t), "claimed_at": st.get("claimed_at") or iso(t), "pr": None, "merge_sha": None,
                 "waiting_on": None, "branch": f"task/{tid}", "worktree_path": wt["path"] if wt else None}
        save_task_state(q, tid, state)
        emit(q, cfg, tid, "lease", "set", {"holder": holder})
        emit(q, cfg, tid, "phase", "transition", {"from": "pending", "to": "leased", "note": "ccp tasks claim"})
        progress_event(q, tid, "pending", "leased", "claimed")
        set_marker(q, tid, "leased")
    w = load_work(q)
    # §10.4: the claim that takes a preferred task removes only that entry, judged on the file as read at
    # the write (the lead may have set a new list since this read)
    took: list[list[str]] = []

    def unprefer(cur: dict[str, Any]) -> None:
        ids = preferred_ids(cur)
        if tid not in ids:
            return
        left = [x for x in ids if x != tid]
        took.append(left)
        cur.pop("next_task", None)
        if left:
            cur["next_tasks"] = left
        else:
            for k in PREFER_KEYS:
                cur.pop(k, None)

    def take(cur: dict[str, Any]) -> None:
        # §16.4: in_flight from the file as read under the lock, so a concurrent writer's entry is kept
        cur["in_flight"] = [x for x in cur.get("in_flight") or [] if x != tid] + [tid]
        # a stop or drain the lead set while this claim sampled and made its worktree is kept
        cur["status"] = cur.get("status") if cur.get("status") in STOPPED else "running"
        unprefer(cur)

    # §16.4: the lease is the task's own (`tasks/<id>.json` `lease_holder`); work.json keeps none, and an
    # old file's top-level `lease` is dropped here
    save_work(q, {"task_id": tid, "phase": load_task_state(q, tid).get("status"),
                  "runtime_status": "running", "waiting_on": None, "phase_since": iso(t)},
              drop=(OLD_WORK_LEASE,), edit=take)
    if parallel.enabled(cfg):  # §16.7: each task held records the most tasks held at once in its window
        held_now = [str(t.get("task_id")) for t in parallel.active_tasks(cfg, q, load_work(q))]  # still claimed
        for other in held_now:
            st_o = load_task_state(q, other)
            if st_o and st_o.get("status") != "done" and len(held_now) > int(st_o.get("peak_in_flight") or 0):
                save_task_state(q, other, {"peak_in_flight": len(held_now)})
    if took:
        emit(q, cfg, tid, "prefer", "clear", {"was": tid, "reason": "claimed", "left": took[0]})
    heartbeat(q, f"claim {tid}", task_id=tid)
    held = w.get("held") if isinstance(w.get("held"), dict) else {}
    hold_warn = [f"{tid} is held by {held[tid].get('by') or '?'}"
                 + (f" ({held[tid]['reason']})" if held[tid].get("reason") else "")
                 + f": claimed anyway; `ccp tasks hold --clear {tid}` once that is settled"] if tid in held else []
    return {"ok": True, "task_id": tid, "resumed": resumed, "worktree": wt, "kind": tasklog.kind_of(meta),
            "warnings": script_drift(q) + ([sample["warning"]] if sample and sample.get("warning") else []) + hold_warn
            + session_warn}


PREFER_KEYS = ("next_tasks", "next_task", "next_task_by", "next_task_at", "next_task_reason")


def _preference(w: dict[str, Any]) -> dict[str, Any] | None:
    ids = preferred_ids(w)
    if not ids:
        return None
    return {"tasks": ids, "by": w.get("next_task_by"), "at": w.get("next_task_at"),
            "reason": w.get("next_task_reason") or ""}


def prefer(cfg: Config, tasks: list[str], reason: str, clear: bool) -> dict[str, Any]:
    """§10.4 `ccp tasks prefer`: the lead names the runner's next tasks, in order, as queue state
    (work.json `next_tasks`), so `ccp tasks next` returns the first ready one ahead of its own pick,
    and the claim that takes one removes only that one. A new list replaces the old. No task and no
    --clear: show the current list, writing nothing."""
    q = root()
    w = load_work(q)
    if not tasks and not clear:
        return {"ok": True, "next_tasks": _preference(w)}
    if tasks and clear:
        raise QueueError("give tasks to prefer, or --clear, not both")
    who = actor("design-seat")
    if clear:
        was = _preference(w)
        if was:
            save_work(q, {}, drop=PREFER_KEYS)
            emit(q, cfg, was["tasks"][0], "prefer", "clear",
                 {"was": was["tasks"][0], "tasks": was["tasks"], "reason": reason or "cleared"}, who)
        return {"ok": True, "next_tasks": None, "cleared": was}
    scope = [str(x) for x in w.get("scope") or []] or None
    ids: list[str] = []
    warn: list[str] = []
    for task in tasks:  # every entry is checked before anything is written
        tid = str(task_meta(cfg, task)["task_id"])
        if tid in ids:
            raise QueueError(f"{tid} is named twice: each task once, in the order wanted")
        _, state = tasklog.preferred(cfg, tid, scope)
        if state != "ready" and state != "out of scope" and not state.startswith("waiting on"):
            raise QueueError(f"{tid} is {state} in its task file: only a pending task can be preferred")
        if state == "out of scope":
            raise QueueError(f"{tid} is not in the runner's scope (work.json): widen it first with "
                             f"`team.sh runner scope --add {tid}`, then prefer it")
        if state != "ready":
            warn.append(f"preferred {tid} is {state}: `ccp tasks next` skips it, keeping its place, until that is done")
        ids.append(tid)
    at = iso()
    save_work(q, {"next_tasks": ids, "next_task_by": who, "next_task_at": at, "next_task_reason": reason},
              drop=("next_task",))
    emit(q, cfg, ids[0], "prefer", "set", {"by": who, "reason": reason, "tasks": ids}, who)
    return {"ok": True, "next_tasks": {"tasks": ids, "by": who, "at": at, "reason": reason}, "warnings": warn}


def _set_hold(cur: dict[str, Any], tid: str, entry: dict[str, Any] | None) -> None:
    """One hold set or cleared in work.json as read under its lock (§16.4): another task's hold, set
    meanwhile, is kept."""
    held = dict(cur.get("held") or {}) if isinstance(cur.get("held"), dict) else {}
    if entry is None:
        held.pop(tid, None)
    else:
        held[tid] = entry
    if held:
        cur["held"] = held
    else:
        cur.pop("held", None)


def hold(cfg: Config, task: str | None, reason: str, clear: str | None) -> dict[str, Any]:
    """§10.4 `ccp tasks hold`: the lead holds a task back as queue state (work.json `held`), so
    `ccp tasks next` passes over it, preference or refactor alike, until `--clear`. No task and no
    --clear: list the holds, writing nothing."""
    q = root()
    w = load_work(q)
    held = dict(w.get("held") or {}) if isinstance(w.get("held"), dict) else {}
    if task is None and clear is None:
        return {"ok": True, "held": [{"task_id": t, **v} for t, v in sorted(held.items())]}
    if task is not None and clear is not None:
        raise QueueError("give a task to hold, or --clear ID, not both")
    who = actor("design-seat")
    if clear is not None:
        tid = str(task_meta(cfg, clear)["task_id"]) if clear not in held else clear
        was = held.pop(tid, None)
        if was is None:
            return {"ok": True, "cleared": None, "held": [{"task_id": t, **v} for t, v in sorted(held.items())],
                    "warnings": [f"{tid} is not held"]}
        save_work(q, {}, edit=lambda cur: _set_hold(cur, tid, None))
        emit(q, cfg, tid, "hold", "clear", {"was": was, "reason": reason or "cleared"}, who)
        return {"ok": True, "cleared": {"task_id": tid, **was},
                "held": [{"task_id": t, **v} for t, v in sorted(held.items())]}
    meta = task_meta(cfg, task)
    tid = str(meta["task_id"])
    if meta.get("status") != "pending":
        raise QueueError(f"{tid} is {meta.get('status') or 'no status'} in its task file: only a pending task can be held")
    entry = {"by": who, "at": iso(), "reason": reason}
    held[tid] = entry
    save_work(q, {}, edit=lambda cur: _set_hold(cur, tid, entry))
    emit(q, cfg, tid, "hold", "set", {"by": who, "reason": reason}, who)
    warn = [f"{tid} is in the lead's preference list too: `ccp tasks next` passes over it while it is held"] \
        if tid in preferred_ids(w) else []
    return {"ok": True, "held": [{"task_id": t, **v} for t, v in sorted(held.items())], "set": {"task_id": tid, **entry},
            "warnings": warn}


def phase(cfg: Config, task: str, to: str, note: str) -> dict[str, Any]:
    q = root()
    tid = str(task_meta(cfg, task)["task_id"])
    if not load_task_state(q, tid):
        raise QueueError(f"{tid} has no queue state: claim it first (ccp tasks claim)", 3)
    if not re.match(r"^[a-z][a-z_-]{1,30}$", to):
        raise QueueError(f"{to!r} is not a phase name", 2)
    frm = phase_move(q, cfg, tid, to, note)
    return {"ok": True, "task_id": tid, "from": frm, "to": to}


def wait(cfg: Config, task: str, action: str, reason: str, until: str | None, detail: str | None) -> dict[str, Any]:
    """`waiting_on` through its single writer, set-waiting-on.sh (§23.2)."""
    q = root()
    tid = str(task_meta(cfg, task)["task_id"])
    cmd = [str(OBS / "set-waiting-on.sh"), action, tid, reason, "--actor", actor(), "--project-id", cfg.project_id]
    if until:
        cmd += ["--resets-at", until]
    if detail:
        cmd += ["--detail", detail]
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)})
    if r.returncode != 0:
        raise QueueError(f"set-waiting-on: {(r.stderr or r.stdout).strip()}", r.returncode if r.returncode in (1, 2) else 1)
    return {"ok": True, "task_id": tid, "action": action, "reason": reason}


RESOLVED = ("done", "dropped")


def _markers(q: Path, tid: str) -> list[str]:
    base = q / "queue"
    return sorted(d.name for d in base.iterdir() if d.is_dir() and (d / tid).exists()) if base.is_dir() else []


def _plan(q: Path, tid: str, st: dict[str, Any], want: str) -> list[str]:
    """What sync would change for one queue file whose task is done or dropped in its task file,
    its open runs abandoned among it (§11.1)."""
    w = load_work(q)
    return ([f"cleared waiting_on {st['waiting_on']}"] if st.get("waiting_on") else []) \
        + ([f"cleared the lease of {st['lease_holder']}"] if st.get("lease_holder") else []) \
        + ([f"status {st.get('status') or 'none'} -> {want}"] if st.get("status") != want else []) \
        + ([f"marker queue/{want}/"] if _markers(q, tid) != [want] else []) \
        + (["left work.json"] if tid in (w.get("in_flight") or []) or w.get("task_id") == tid else []) \
        + [f"abandoned run {r['run_id']} ({runs.CLOSED_REASON[want]})" for r in runs.all_runs(q, tid) if runs.state(r) in runs.OPEN]


def drop(cfg: Config, task: str, reason: str) -> dict[str, Any]:
    """§10.4 `ccp tasks drop`: settle a task the lead dropped while it was in
    flight, the case `sync` skips (a mid-flight lease) and `release` refuses (it has runs). Only a task
    whose file on the integration tip says `dropped` (the decision is the lead's, in git), and only when
    its PR did not merge (a merged task is closed). Abandons its open runs, clears its wait and lease,
    takes the queue status `dropped` and leaves work.json: the slot that held it is free (`idle_runners`).
    Its worktree and branch are kept (an implementer may still be in it; `ccp wt gc` removes them
    later, §12.1)."""
    q = root()
    if not reason:
        raise QueueError("give --reason: one line on why the task is dropped", 2)
    meta = task_meta(cfg, task)
    tid = str(meta["task_id"])
    integ = integration_branch(q)
    git(cfg.root, "fetch", "-q", "origin", integ)  # a runner's worktree may be behind the lead's commit (§16)
    r = git(cfg.root, "show", f"origin/{integ}:{cfg.rel(meta['_file'])}")
    if r.returncode != 0:
        raise QueueError(f"{cfg.rel(meta['_file'])} is not on origin/{integ}: the lead's dropped status must be "
                         "committed there first", 3)
    durable = tasklog.frontmatter(r.stdout).get("status")
    if durable != "dropped":
        raise QueueError(f"{tid} is {durable or 'no status'} in its task file on origin/{integ}: only a task the "
                         "lead marked dropped (and committed) is dropped here; it edits the task file first", 3)
    st = load_task_state(q, tid)
    if st.get("merge_sha") or st.get("status") == "done":
        raise QueueError(f"{tid} merged ({str(st.get('merge_sha') or '')[:7]}): it is closed, not dropped", 3)
    # a PR merged without close recording it (a close whose reconcile failed, or a merge by hand) is closed too
    prs = {str(x) for x in [st.get("pr"), st.get("merged_by_close"), *[r.get("pr") for r in runs.all_runs(q, tid)]] if x}
    for pr in sorted(prs):
        if _pr_state(cfg, pr).get("state") == "MERGED":
            raise QueueError(f"{tid}'s PR {pr} merged: it is closed (`ccp tasks close {tid} --pr {pr}`), not dropped", 3)
    what = _plan(q, tid, st, "dropped")
    if not what:
        return {"ok": True, "task_id": tid, "changed": [], "note": "already dropped in the queue"}
    who = actor()
    _apply(cfg, q, tid, st, "dropped", source="ccp tasks drop")
    emit(q, cfg, tid, "note", "set", {"message": f"dropped in flight: {reason}", "source": "ccp tasks drop"}, who)
    return {"ok": True, "task_id": tid, "changed": what, "holder": st.get("lease_holder"),
            **({"idle_runners": idle} if (idle := idle_runners(q, but=str(st.get("lease_holder") or ""))) else {}),
            "warnings": [f"its worktree {st['worktree_path']} and branch task/{tid} are kept"]
            if st.get("worktree_path") and Path(st["worktree_path"]).is_dir() else []}


def sync(cfg: Config, dry_run: bool = False) -> dict[str, Any]:
    """The queue follows the log (§4): every queue file whose task is done or dropped in its task
    file loses its wait (through set-waiting-on.sh) and its lease, takes the durable status, and has
    its `queue/<state>/` marker moved. Each change is in the ledger. A second run changes nothing.

    A task still leased in a mid-flight phase is skipped: either `ccp tasks close` is between its
    push and its queue update, or the live runner holds a task the log dropped under it. Close, or
    `ccp tasks drop` (release for a claim with no runs), settles the queue; sync never takes a lease
    from a live runner."""
    from ccp.queue import MID_FLIGHT  # noqa: PLC0415

    q = root()
    durable = durable_statuses(cfg)
    changed, skipped = [], []
    for f in sorted((q / "tasks").glob("*.json")) if (q / "tasks").is_dir() else []:
        tid, want = f.stem, durable.get(f.stem)
        st = load_task_state(q, tid)
        if want not in RESOLVED:
            continue
        what = _plan(q, tid, st, want)
        if not what:
            continue
        if st.get("lease_holder") and st.get("status") in MID_FLIGHT:
            skipped.append({"task_id": tid, "durable_status": want,
                            "reason": f"leased by {st['lease_holder']} and {st.get('status')} in the queue: mid-flight "
                                      "(a close in progress, or a live runner's task); close it, or "
                                      f"`ccp tasks drop {tid} --reason` when its file says dropped"})
            continue
        changed.append({"task_id": tid, "durable_status": want, "changed": what})
        if not dry_run:
            _apply(cfg, q, tid, st, want)
    return {"ok": True, "dry_run": dry_run, "changed": changed, "skipped": skipped}


def _apply(cfg: Config, q: Path, tid: str, st: dict[str, Any], want: str, source: str = "ccp tasks sync") -> None:
    runs.abandon_task_runs(q, cfg, tid, want)  # §11.1: they will never report now
    if st.get("waiting_on"):
        cmd = [str(OBS / "set-waiting-on.sh"), "clear", tid, f"{want}_in_log", "--actor", actor(),
               "--project-id", cfg.project_id, "--task-only"]
        r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)})
        if r.returncode != 0:
            raise QueueError(f"set-waiting-on: {tid}: {(r.stderr or r.stdout).strip()}", 1)
    if st.get("lease_holder"):
        emit(q, cfg, tid, "lease", "clear", {"holder": st["lease_holder"], "note": f"{want} in the task log"})
        save_task_state(q, tid, {"lease_holder": None, "lease_expires_at": None})
    frm = st.get("status")
    if frm != want:
        emit(q, cfg, tid, "durable", "reconcile", {"field": "status", "old": frm, "new": want,
                                                   "note": f"{source}: the queue follows the task file"})
        phase_move(q, cfg, tid, want, f"{source}: {want} in the task log")
    if _markers(q, tid) != [want]:
        set_marker(q, tid, want)
    _leave_work(q, tid)


def _leave_work(q: Path, tid: str) -> None:
    """The task leaves work.json: out of `in_flight`, and, when it was the runner's current task, the
    next one in flight (or none) takes its place, with that one's phase and wait. An old file's
    top-level lease is removed whichever task it names (§16.4: the slots hold the leases)."""
    def leave(w: dict[str, Any]) -> None:  # §16.4: judged on the file as read under its lock
        w.pop(OLD_WORK_LEASE, None)  # an old file's top-level lease goes with any task's leaving
        if not (tid in (w.get("in_flight") or []) or w.get("task_id") == tid):
            return
        flight = [x for x in w.get("in_flight") or [] if x != tid]
        upd: dict[str, Any] = {"in_flight": flight}
        if w.get("task_id") == tid:
            nxt = load_task_state(q, flight[0]) if flight else {}
            upd.update(task_id=flight[0] if flight else None, phase=nxt.get("status"),
                       runtime_status="running" if flight else "idle",
                       phase_since=nxt.get("phase_since") or nxt.get("lease_since"),
                       **{k: nxt.get(k) for k in WAIT_KEYS})
        w.update(upd)

    w = load_work(q)
    if tid in (w.get("in_flight") or []) or w.get("task_id") == tid or OLD_WORK_LEASE in w:
        save_work(q, {}, edit=leave)


RELEASABLE = ("leased", "blocked")
# §16.4: work.json's top-level lease, written before each slot kept its own (`tasks/<id>.json`
# `lease_holder`). Nothing writes it now; claim, release, drop, sync and close remove it from an old file.
OLD_WORK_LEASE = "lease"
# work.json's copy of its current task's wait (set-waiting-on.sh writes them together)
WAIT_KEYS = ("waiting_on", "waiting_on_since", "planned_resume_at", "quota_class")


def holder_teammate_for(q: Path, slot: Any) -> str | None:
    """The bound teammate name of a runner slot (§16.4), the slot itself when it has no record."""
    if not slot:
        return None
    rec = runner_slots(load_work(q)).get(str(slot))
    return str((rec or {}).get("bound_name") or slot)


def idle_runners(q: Path, but: str = "") -> list[str]:
    """§16.5 rule 7: the bound names of the runner slots that hold no task, to message after a slot frees
    (the hook cannot wake a teammate that is already idle); `but`, the slot that freed it, is not among
    them (it goes on itself). [] for one runner."""
    w = load_work(q)
    held = {str(load_task_state(q, str(t)).get("lease_holder") or "") for t in w.get("in_flight") or []}
    return [str(r.get("bound_name") or s) for s, r in sorted(runner_slots(w).items()) if s not in held and s != but]


def runner_worktree(cfg: Config, slot: str) -> dict[str, Any]:
    """§16.5 rule 1: a runner's own merge worktree, made when missing, detached at the integration tip:
    work.json `runners.<slot>.worktree`, else the binding's `runner.worktree` plus `-<slot>`."""
    import re as _re  # noqa: PLC0415
    from ccp.prompt import main_checkout  # noqa: PLC0415
    from ccp.queue import binding_text  # noqa: PLC0415
    q = root()
    slots = runner_slots(load_work(q))
    if slot not in slots:
        raise QueueError(f"{slot!r} is no runner slot ({', '.join(sorted(slots)) or 'none: one runner'}); "
                         "the lead records slots with `team.sh runner spawn --count`", 2)
    path = str(slots[slot].get("worktree") or "")
    if not path:
        m = _re.search(r"^runner:\s*\n(?:[ \t]+.*\n)*?[ \t]+worktree:\s*([^#\n]+)", binding_text(q) + "\n", _re.M)
        if not m:
            raise QueueError("the binding names no runner.worktree to put the runners' worktrees beside (SPEC §12.1)", 2)
        path = m.group(1).strip().strip("'\"") + f"-{slot}"
    main = main_checkout(cfg)
    wt = Path(path) if Path(path).is_absolute() else main / path
    integ = integration_branch(q)
    made = False
    live = (wt / ".git").exists() and git(wt, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
    if not live:
        if wt.exists() and any(wt.iterdir()):
            raise QueueError(f"{wt} exists and is not a working tree of the product: move it away first", 2)
        git(main, "worktree", "prune")  # a worktree removed by hand still registered blocks the add
        git(main, "fetch", "-q", "origin")
        git(main, "worktree", "add", "-q", "--detach", str(wt), f"origin/{integ}", check=True)
        made = True
    return {"ok": True, "slot": slot, "worktree": str(wt), "made": made,
            "next": f"cd {wt} && run every ccp command from there (SPEC §16.5)"}


def release(cfg: Config, task: str, reason: str) -> dict[str, Any]:
    """§10.4 `ccp tasks release`: a claim taken too early is undone, and the task goes back to pending.
    Only a claim with no work behind it: leased (or blocked) with no run at all, so no PR, report or
    merge. Its wait and lease are cleared (each an event, the lease's marked `released`), its phase
    moves to pending, and it leaves work.json. The worktree and branch are kept for a later claim."""
    q = root()
    if not reason:
        raise QueueError("give --reason: one line on why the claim is undone", 2)
    tid = str(task_meta(cfg, task)["task_id"])
    st = load_task_state(q, tid)
    if not st.get("lease_holder"):
        raise QueueError(f"{tid} is {st.get('status') or 'not claimed'} in the queue with no lease: only a claimed "
                         "task is released", 3)
    # pending with a lease: a release that stopped after its phase move, finished by running it again
    if st.get("status") not in (*RELEASABLE, "pending") or st.get("merged_by_close") or st.get("pr"):
        raise QueueError(f"{tid} is {st.get('status')} in the queue: only a claim with no work behind it "
                         f"({' or '.join(RELEASABLE)}, no run) is released; a task in flight is finished, or dropped", 3)
    had = [r["run_id"] for r in runs.all_runs(q, tid)]
    pd = q / "prompts" / tid  # a claim from before run records: its prompt audits are its work
    had += [f"prompts/{tid}/"] if pd.is_dir() and any(pd.rglob("*.json")) else []
    if had:
        raise QueueError(f"{tid} has runs ({', '.join(had)}): a claim that has done work is finished or dropped, "
                         "not released", 3)
    who = actor("design-seat")
    from ccp.health import RELEASE_NOTE  # noqa: PLC0415
    note = f"{RELEASE_NOTE} {reason}"
    # the events are checked before anything is written, so a refused one leaves the task as it was
    for typ, op, body in (("lease", "clear", {"holder": st["lease_holder"], "note": note, "released": True}),
                          ("phase", "transition", {"from": st.get("status"), "to": "pending", "note": note})):
        errs = lib.validate_event({"at": iso(), "project_id": cfg.project_id, "task_id": tid, "actor": who,
                                   "type": typ, "op": op, "payload": body})
        if errs:
            raise QueueError("--reason: " + "; ".join(errs), 2)
    done: list[str] = []
    if st.get("waiting_on"):
        cmd = [str(OBS / "set-waiting-on.sh"), "clear", tid, "released", "--actor", who, "--project-id", cfg.project_id,
               "--task-only"]
        r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)})
        if r.returncode != 0:
            raise QueueError(f"set-waiting-on: {(r.stderr or r.stdout).strip()}", r.returncode if r.returncode in (1, 2) else 1)
        done.append(f"cleared waiting_on {st['waiting_on']}")
    frm = phase_move(q, cfg, tid, "pending", note, who)
    done.append(f"status {frm or 'none'} -> pending")
    # `released` marks the claim undone, and it is the release's last event: the task's time starts at
    # the first event after it, its next claim (ccp/health.py, ccp/drill.py)
    emit(q, cfg, tid, "lease", "clear", {"holder": st["lease_holder"], "note": note, "released": True}, who)
    save_task_state(q, tid, {"lease_holder": None, "lease_expires_at": None, "lease_since": None, "claimed_at": None,
                             "implementation_started_at": None})
    done.append(f"cleared the lease of {st['lease_holder']}")
    set_marker(q, tid, "pending")
    _leave_work(q, tid)
    return {"ok": True, "task_id": tid, "released_from": frm, "changed": done, "holder": st.get("lease_holder"),
            "holder_teammate": holder_teammate_for(q, st.get("lease_holder")),
            # every slot holding nothing now, the released task's own holder too (a lead's release frees it)
            **({"idle_runners": idle} if (idle := idle_runners(q)) else {}),
            "warnings": [f"the worktree {wt} and branch {st.get('branch') or f'task/{tid}'} are kept: a later claim "
                         "resumes in them"] if (wt := st.get("worktree_path")) and Path(wt).is_dir() else []}


# ---------------------------------------------------------------------------------------- close

def _gh() -> str:
    return envvar("CCP_GH_BIN") or "gh"


def _merge(cfg: Config, pr: str, head: str, tid: str) -> subprocess.CompletedProcess[str]:
    """§15.5: the merge pinned to the verified head: plane.json `merge.command` when set (a template
    naming pr, head_sha, task_id), else `gh pr merge <pr> --squash --match-head-commit <head>`."""
    cmd = (cfg.merge or {}).get("command")
    if cmd:
        from ccp.config import fill  # noqa: PLC0415
        return _run(["/bin/sh", "-c", fill(cmd, {"pr": pr, "head_sha": head, "task_id": tid})], cfg.root,
                    for_child({"CCP_GH_BIN": _gh()}))
    return _run([_gh(), "pr", "merge", pr, "--squash", "--match-head-commit", head], cfg.root)


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    except FileNotFoundError as exc:
        raise QueueError(f"{cmd[0]} is not installed", 2) from exc


def _verification_note(q: Path, tid: str, pr: str, head: str, merge: str, today: str) -> str:
    import json  # noqa: PLC0415

    rec = json.loads((q / "verification" / f"{tid}.json").read_text())
    checks = [c for c in rec.get("checks") or [] if isinstance(c, dict)]
    ran = [c for c in checks if c.get("ran", True) is not False]
    passed = [str(c.get("dod_check_id")) for c in ran if c.get("pass") is True]
    unrun = [str(c.get("dod_check_id")) for c in checks if c.get("ran", True) is False]
    gate = ", ".join(f"`{r.get('command')}` exit {r.get('exit_code')}" for r in (rec.get("gate") or {}).get("runs") or []
                     if isinstance(r, dict))
    s = (f"- {today} — verifier, PR #{pr} head `{head[:7]}` (squash `{merge[:7]}`): APPROVE. "
         f"Passed: {', '.join(passed) or 'none'}.")
    if unrun:
        s += f" Not run by the verifier: {', '.join(unrun)}."
    if gate:
        s += f" Gate: {gate}."
    return s + f" Record: verification/{tid}.json."


def review_point_problem(cfg: Config, rp: str) -> str | None:
    """§22.1, §22: why `close` would not stamp this review point, or None when it would: it must be
    R<n>, and one of the register's ids when the product keeps a register (`ccp.reviewpoints`).
    `team.sh runner spawn` refuses on the same answer, so a bad point never reaches a close."""
    from ccp import reviewpoints  # noqa: PLC0415
    return reviewpoints.problem(cfg, rp)


def review_point_stamp(cfg: Config, meta: dict[str, Any], rp: str) -> tuple[str | None, str | None]:
    """§22.1: the review point `close` writes into the task file, and a warning when it writes none
    although the runner has one. A task that already carries a review point keeps it."""
    if not rp or "review_point" in meta:
        return None, None
    problem = review_point_problem(cfg, rp)
    return (None, f"review_point not stamped: work.json's {problem}") if problem else (rp, None)


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text.split("\n", 1)[0] + "\n" else "\n"


def stamp_review_point(text: str, review_point: str) -> str | None:
    """`text` (read with no newline translation) with `review_point: R` as the frontmatter's last
    line, in the file's own line ending; every other byte kept. None when the frontmatter's end is
    not found. The caller checks the value (review_point_problem) and that none is set."""
    nl = _newline(text)
    end = text.find(f"{nl}---{nl}", 3) if text.startswith(f"---{nl}") else -1
    if end == -1:
        return None
    return text[:end + len(nl)] + f"review_point: {review_point}{nl}" + text[end + len(nl):]


def _task_file_done(path: Path, note: str, today: str, review_point: str | None = None) -> bool:
    """The task file's close edit. False when a review point was asked for and the frontmatter's end
    was not found (it is then not stamped). Keeps the file's line ending (LF or CRLF)."""
    with path.open(newline="") as fh:  # no newline translation: a CRLF file stays CRLF
        text = fh.read()
    nl = _newline(text)
    text = re.sub(r"^status:[^\r\n]*", "status: done", text, count=1, flags=re.M)
    text = re.sub(r"^updated:[^\r\n]*", f"updated: {today}", text, count=1, flags=re.M)
    stamped = True
    if review_point:
        done = stamp_review_point(text, review_point)
        stamped = done is not None
        text = done if done is not None else text
    m = re.search(rf"^## {re.escape(tasklog.SEC_VERIFY)}[ \t]*(?=\r?$)", text, re.M)
    if not m:
        raise QueueError(f"{path.name} has no `## {tasklog.SEC_VERIFY}` section", 1)
    nxt = re.search(r"^## ", text[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    section = text[m.end():end]
    if VERIFY_PLACEHOLDER_RE.search(section):
        section = VERIFY_PLACEHOLDER_RE.sub(lambda m: note + ("\r" if m.group(0).endswith("\r") else ""), section, count=1)
    else:
        section = section.rstrip("\r\n") + nl + note + nl + nl
    with path.open("w", newline="") as fh:
        fh.write(text[:m.end()] + section + text[end:])
    return stamped


def _log_entry(cfg: Config, values: dict[str, str]) -> str | None:
    log = cfg.reconcile["log"] if cfg.reconcile else None
    if not log:
        return None
    path = cfg.root / log["path"]
    if not path.is_file():
        raise QueueError(f"reconcile.log.path {log['path']} does not exist", 1)
    try:
        entry = log["entry"].format(**values)
    except (KeyError, IndexError) as e:
        raise QueueError(f"reconcile.log.entry names {e}, which close does not set "
                         f"({', '.join(sorted(values))})", 2) from None
    text = path.read_text()
    m = re.search(log["before"], text, re.M) if log.get("before") else None
    i = m.start() if m else len(text)
    path.write_text(text[:i] + entry.rstrip("\n") + "\n\n" + text[i:])
    return log["path"]


def _changed(cwd: Path) -> list[str]:
    """Paths with changes, as git names them (NUL-separated, so a path with spaces stays whole)."""
    parts = git(cwd, "status", "--porcelain", "-z", "-uall").stdout.split("\0")
    out, i = [], 0
    while i < len(parts):
        e = parts[i]
        if len(e) > 3:
            out.append(e[3:])
            if e[0] in "RC":  # a rename names its source next
                i += 1
        i += 1
    return out


def _pr_state(cfg: Config, pr: str) -> dict[str, Any]:
    import json  # noqa: PLC0415

    r = _run([_gh(), "pr", "view", pr, "--json", "state,headRefOid,mergeCommit"], cfg.root)
    if r.returncode != 0:
        raise QueueError(f"gh pr view {pr}: {(r.stderr or r.stdout).strip()}", 1)
    try:
        facts = json.loads(r.stdout)
    except ValueError:
        raise QueueError(f"gh printed no JSON for PR {pr}", 1) from None
    return facts if isinstance(facts, dict) else {}


def _recovery(cfg: Config, q: Path, tid: str, pr: str, merge: str, what: str, pushed: bool) -> QueueError:
    integ = integration_branch(q)
    if pushed:
        return QueueError(
            f"PR {pr} is merged ({merge[:7]}) and its reconcile is pushed, but finishing the queue failed: {what}\n"
            f"  Fix the cause and run `ccp tasks close {tid} --pr {pr}` again: it sees the task done and only "
            "finishes the queue", 1)
    return QueueError(
        f"PR {pr} is merged ({merge[:7]}), and the reconcile did not finish: {what}\n"
        f"  Nothing of the reconcile was pushed. To finish it: discard the half-done reconcile in {cfg.root} "
        f"(`git -C {cfg.root} rebase --abort` if a rebase is in progress, then "
        f"`git -C {cfg.root} reset -q --hard && git -C {cfg.root} checkout -q --detach origin/{integ}` and remove any new "
        f"file it names), fix the cause, and run `ccp tasks close {tid} --pr {pr}` again: it sees the merge and only "
        "reconciles", 1)


def close(cfg: Config, task: str, pr: str, summary: str) -> dict[str, Any]:
    from ccp import verify  # noqa: PLC0415

    q = root()
    meta = task_meta(cfg, task)
    tid = str(meta["task_id"])
    if not str(pr).isdigit():
        raise QueueError("--pr is the PR number", 2)
    integ = integration_branch(q)
    if git(cfg.root, "rev-parse", "-q", "--verify", "REBASE_HEAD").returncode == 0:
        raise QueueError(f"{cfg.root} is in the middle of a rebase: `git -C {cfg.root} rebase --abort` first", 2)
    if _changed(cfg.root):
        raise QueueError(f"{cfg.root} has changes: close commits only its own, so run it from a clean runner "
                         "worktree (SPEC §12.1)", 2)
    try:
        reasons, body = verify.merge_ok(cfg, q, pr, tid)
    except verify.NoGh as exc:
        raise QueueError(str(exc), 2) from None
    facts = _pr_state(cfg, pr)
    already = facts.get("state") == "MERGED"
    if already:
        # A re-run after a reconcile that failed: the merge stands if the record approved the head that merged.
        # An approval recorded after the merge is not one (§15.5): that refusal stays, unless this
        # command made the merge itself, after merge-ok passed (it noted so before merging).
        ours = str(load_task_state(q, tid).get("merged_by_close") or "") == str(pr)
        reasons = [r for r in reasons if not r.startswith(f"PR {pr} is merged") or ("recorded after it" in r and not ours)]
        head = str(facts.get("headRefOid") or "")
        if not reasons and not verify.heads_match(str(body.get("head_sha") or ""), head):
            reasons.append(f"PR {pr} merged at {head[:12]}, which is not the approved head")
    if reasons:
        raise QueueError("merge refused, nothing merged (SPEC §15.5):\n  " + "\n  ".join(reasons), 1)
    if not already:
        head = body["match_head_commit"]
        # §16.5 rule 4: the verified head must contain the tip, the task log and declared paths aside
        from ccp import parallel  # noqa: PLC0415
        behind = _close_behind_tip(cfg, pr, tid, head, integ) if parallel.enabled(cfg) else []  # one runner: §16
        if behind:
            raise QueueError(f"merge refused, nothing merged: behind_tip: the verified head {head[:7]} lacks "
                             f"{len(behind)} commit(s) on origin/{integ} that change more than the task log "
                             "and merge.behind_tip_ignore "
                             f"({', '.join(behind[:5])}). Have the implementer merge origin/{integ} into task/{tid} "
                             "(a plain push, never a rebase) and resolve any conflict, then verify the new head, then "
                             "close (SPEC §16.5); a head whose own change is unchanged needs no new review (§15.2)", 1)
        save_task_state(q, tid, {"merged_by_close": str(pr), "merge_head": head, "phase_since": iso()})
        r = _merge(cfg, pr, head, tid)
        if r.returncode != 0:
            hint = (" (SPEC §16.5 rule 4: a conflict with what merged since: have the implementer merge the tip in "
                    "and resolve it, then verify again)") if "conflict" in (r.stderr + r.stdout).lower() \
                or "not mergeable" in (r.stderr + r.stdout).lower() else ""
            raise QueueError(f"gh pr merge {pr}: {(r.stderr or r.stdout).strip()}{hint}", 1)
        facts = _pr_state(cfg, pr)
        if facts.get("state") != "MERGED":
            raise QueueError(f"gh pr merge {pr} exited 0 but the PR is {facts.get('state')} (a merge queue or auto-merge?): "
                             f"run `ccp tasks close {tid} --pr {pr}` again once it has merged", 1)
    merge = str((facts.get("mergeCommit") or {}).get("oid") or "")
    if not merge:
        raise QueueError(f"PR {pr} is merged but gh names no merge commit", 1)
    progress: dict[str, bool] = {"pushed": False}
    try:
        return _reconcile(cfg, q, meta, tid, pr, head, merge, summary, integ, already, progress)
    except Exception as exc:  # noqa: BLE001  (after a merge, every failure needs the recovery steps)
        what = str(exc) if isinstance(exc, QueueError) else f"{type(exc).__name__}: {exc}"
        raise _recovery(cfg, q, tid, pr, merge, what, progress["pushed"]) from None


class _Moved(Exception):
    """The integration tip moved under a reconcile: its rebase conflicted or its push was rejected."""


RECONCILE_TRIES = 5  # §16.5 rule 5


def _push(cfg: Config, integ: str) -> None:
    """Rebase onto the integration branch and push. A rebase that conflicts is aborted, and it or a
    rejected push raises _Moved: the reconcile is rebuilt on the fresh tip (SPEC §16.5 rule 5)."""
    r = git(cfg.root, "pull", "-q", "--rebase", "origin", integ)
    if r.returncode != 0:
        git(cfg.root, "rebase", "--abort")
        raise _Moved(f"the rebase onto origin/{integ} conflicted: {(r.stderr or r.stdout).strip()[:200]}")
    r = git(cfg.root, "push", "-q", "origin", f"HEAD:{integ}")
    if r.returncode != 0:
        raise _Moved(f"git push: {(r.stderr or r.stdout).strip()[:200]}")


class Unjudged(Exception):
    """behind_tip could not judge: `what` is "tip" (origin/<integ> could not be fetched) or "head" (the head
    could not be found, locally or fetched)."""

    def __init__(self, what: str, message: str) -> None:
        super().__init__(message)
        self.what = what


def behind_tip(cfg: Config, pr: str | None, tid: str, head: str, integ: str) -> list[str]:
    """§16.5 rule 4: the commits on origin/<integ> that `head` lacks and that change anything outside the
    task log (its task files, INDEX.yaml, the reconcile log) and the product's `merge.behind_tip_ignore`
    paths; [] when there are none. Fetches the tip, and the head when it is not here (the PR's head ref,
    then the task branch). Raises Unjudged when either cannot be read."""
    f = git(cfg.root, "fetch", "-q", "origin", integ)
    if f.returncode != 0:
        raise Unjudged("tip", f"origin/{integ} could not be fetched ({(f.stderr or f.stdout).strip()[:200]})")
    if git(cfg.root, "cat-file", "-e", f"{head}^{{commit}}").returncode != 0:
        for ref in ([f"refs/pull/{pr}/head"] if pr else []) + [f"task/{tid}"]:
            if git(cfg.root, "fetch", "-q", "origin", ref).returncode == 0 \
                    and git(cfg.root, "cat-file", "-e", f"{head}^{{commit}}").returncode == 0:
                break
        else:
            raise Unjudged("head", f"the head {head[:7]} could not be fetched")
    skip = [cfg.rel(cfg.tasks_dir), cfg.rel(cfg.index_path)]
    log = (cfg.reconcile or {}).get("log") or {}
    if isinstance(log, dict) and log.get("path"):
        skip.append(str(log["path"]))
    skip += [str(x) for x in ((cfg.merge or {}).get("behind_tip_ignore") or [])]
    r = git(cfg.root, "log", "--format=%h", f"{head}..origin/{integ}", "--", ".", *[f":!{x}" for x in skip])
    return r.stdout.split() if r.returncode == 0 else []


def _close_behind_tip(cfg: Config, pr: str, tid: str, head: str, integ: str) -> list[str]:
    """behind_tip at close: a tip that cannot be fetched refuses the merge; a head that cannot be fetched
    to judge is a warning, not a refusal (the merge is still pinned to the verified head)."""
    try:
        return behind_tip(cfg, pr, tid, head, integ)
    except Unjudged as exc:
        if exc.what == "tip":
            raise QueueError(f"merge refused, nothing merged: {exc}, so the verified head cannot be checked against "
                             "the tip; run close again", 1) from None
        print(f"ccp tasks close: warning: the verified head {head[:7]} could not be fetched to check it against "
              f"origin/{integ} (SPEC §16.5 rule 4); merging it as verified", file=sys.stderr)
        return []


def _undeclared(cfg: Config, meta: dict[str, Any], merge: str) -> list[str] | None:
    """§16.7, with parallel on: the files the merge changed that the task's Scope In: item did not name
    (none meets a declared path). None when parallel is off or the diff cannot be read. A task that
    says `parallel: true` declares that it changes nothing, so every file counts."""
    from ccp import parallel  # noqa: PLC0415
    if not parallel.enabled(cfg):
        return None
    r = git(cfg.root, "diff", "--name-only", f"{merge}^1", merge)
    if r.returncode != 0:
        return None
    declared = [] if parallel.flag(meta) is True else parallel.paths(cfg, meta)
    # the task log's own files ride along with every task (its task file, INDEX.yaml): never undeclared
    log_dir = cfg.rel(cfg.tasks_dir).rstrip("/") + "/"
    own = {cfg.rel(meta["_file"]), cfg.rel(cfg.index_path)}
    return [f for f in r.stdout.splitlines() if f.strip() and f not in own and not f.startswith(log_dir)
            and not any(parallel.meets(f, p) for p in declared)][:200]


def _reconcile(cfg: Config, q: Path, meta: dict[str, Any], tid: str, pr: str, head: str, merge: str, summary: str,
               integ: str, already: bool, progress: dict[str, bool]) -> dict[str, Any]:
    for attempt in range(1, RECONCILE_TRIES + 1):
        try:
            got = _reconcile_once(cfg, q, meta, tid, pr, head, merge, summary, integ)
            break
        except _Moved as moved:  # §16.5 rule 5: another runner reconciled meanwhile; rebuild on the fresh tip
            if attempt == RECONCILE_TRIES:
                raise QueueError(f"the reconcile could not land after {RECONCILE_TRIES} tries: {moved}", 1) from None
    reconciled, stamp_warnings, undeclared, paths, stamp = got
    progress["pushed"] = True
    return _reconciled(cfg, q, meta, tid, pr, head, merge, already, reconciled, stamp_warnings, undeclared, paths, stamp)


def _reconcile_once(cfg: Config, q: Path, meta: dict[str, Any], tid: str, pr: str, head: str, merge: str,
                    summary: str, integ: str) -> tuple[bool, list[str], list[str] | None, list[str], str | None]:
    """One reconcile on the current tip: the task file, the LOG entry, the hooks and the index, committed
    and pushed. A task file the tip already marks done needs nothing (a retry after it landed)."""
    git(cfg.root, "fetch", "-q", "origin", check=True)
    git(cfg.root, "checkout", "-q", "--detach", f"origin/{integ}", check=True)
    if git(cfg.root, "merge-base", "--is-ancestor", merge, "HEAD").returncode != 0:
        raise QueueError(f"the merge commit {merge[:7]} is not on origin/{integ}", 1)
    undeclared = _undeclared(cfg, meta, merge)
    path = meta["_file"]
    if not path.is_file():
        raise QueueError(f"{cfg.rel(path)} is not on origin/{integ}", 1)
    today = now().strftime("%Y-%m-%d")
    reconciled = tasklog.frontmatter(path.read_text()).get("status") == "done"
    paths: list[str] = []
    stamp_warnings: list[str] = []
    stamp: str | None = None
    if not reconciled:
        # Only what this reconcile breaks stops it: a check that already failed on the branch is not its doing.
        before = {e for e in tasklog.check(cfg) if "stale — run `ccp tasks index`" not in e}
        rp = str(load_work(q).get("review_point") or "")
        stamp, stamp_warning = review_point_stamp(cfg, tasklog.frontmatter(path.read_text().replace("\r\n", "\n")), rp)
        if stamp_warning:
            stamp_warnings.append(stamp_warning)
        if not _task_file_done(path, _verification_note(q, tid, pr, head, merge, today), today, stamp):
            stamp_warnings.append(f"review_point not stamped: {cfg.rel(path)} has no frontmatter block this "
                                  "close can find (SPEC §22)")
            stamp = None
        values = {"date": today, "task_id": tid, "nnnn": refs.ids(cfg).task_number(tid), "pr": pr, "head": head, "head7": head[:7],
                  "merge_sha": merge, "merge7": merge[:7], "summary": summary.strip(),
                  "review_point": rp, "title": str(meta.get("title") or "")}
        _log_entry(cfg, values)
        env = {"TASK_ID": tid, "PR": pr, "HEAD_SHA": head, "MERGE_SHA": merge, "SUMMARY": summary.strip(),
               "QUEUE_ROOT": str(q)}
        for cmd in cfg.reconcile["hooks"] if cfg.reconcile else []:
            h = _run(["/bin/sh", "-c", cmd], cfg.root, env)
            if h.returncode != 0:
                raise QueueError(f"reconcile hook `{cmd}` failed: {(h.stderr or h.stdout).strip()[:400]}", 1)
        tasklog.write_index(cfg)
        errs = [e for e in tasklog.check(cfg) if e not in before]
        if errs:
            raise QueueError("the reconcile fails `ccp tasks check`:\n  " + "\n  ".join(errs[:10]), 1)
        paths = _changed(cfg.root)
        git(cfg.root, "add", "--", *paths, check=True)
        msg = f"Reconcile {refs.ids(cfg).task_number(tid)}: done (PR #{pr}, squash {merge[:7]})"
        if envvar("CCP_COMMIT_TRAILER"):
            msg += "\n\n" + envvar("CCP_COMMIT_TRAILER")
        git(cfg.root, "commit", "-q", "-m", msg, "--", *paths, check=True)
        _push(cfg, integ)
    return reconciled, stamp_warnings, undeclared, paths, stamp


def _reconciled(cfg: Config, q: Path, meta: dict[str, Any], tid: str, pr: str, head: str, merge: str, already: bool,
                reconciled: bool, stamp_warnings: list[str], undeclared: list[str] | None, paths: list[str],
                stamp: str | None) -> dict[str, Any]:
    """After the reconcile landed: cleanup, the queue's record, the actuals; once, whatever the tries."""
    reconcile = git(cfg.root, "rev-parse", "HEAD", check=True).stdout.strip()
    warnings = stamp_warnings + _cleanup(cfg, tid)
    st = load_task_state(q, tid)
    if not reconciled:
        emit(q, cfg, tid, "durable", "reconcile", {"field": "status", "old": meta.get("status"), "new": "done"})
    # The merge record is written even when the queue already says done (a sync, or a hand edit, got
    # there first): only the phase and lease events are the transition's own.
    if st.get("status") != "done" or not st.get("merge_sha"):
        if st.get("status") != "done":
            emit(q, cfg, tid, "phase", "transition", {"from": st.get("status") or "merging", "to": "done",
                                                      "note": f"merged {merge[:7]}, reconciled {reconcile[:7]}"})
        if st.get("status") != "done" or st.get("lease_holder"):
            emit(q, cfg, tid, "lease", "clear", {"holder": st.get("lease_holder") or "runner"})
        save_task_state(q, tid, {"status": "done", "pr": pr, "head_sha": head, "merge_sha": merge,
                                 "reconcile_sha": reconcile, "merged_at": iso(), "lease_holder": None,
                                 **({"undeclared_paths": undeclared} if undeclared is not None else {})})
        if st.get("status") != "done":
            progress_event(q, tid, st.get("status"), "done", f"merged {merge[:7]}")
        set_marker(q, tid, "done")
        def closed(w: dict[str, Any]) -> None:  # §16.4: judged on the file as read under its lock
            flight = [x for x in w.get("in_flight") or [] if x != tid]
            upd: dict[str, Any] = {"in_flight": flight, "runner_tasks_done": int(w.get("runner_tasks_done") or 0) + 1}
            if w.get("task_id") == tid:
                # the next task's own wait, as _leave_work does: the closed task's must not stay on it
                nxt = load_task_state(q, flight[0]) if flight else {}
                upd.update(task_id=flight[0] if flight else None, phase=None, phase_since=None,
                           runtime_status="running" if flight else "idle", **{k: nxt.get(k) for k in WAIT_KEYS})
            w.pop(OLD_WORK_LEASE, None)  # §16.4: an old file's top-level lease does not outlive the close
            slots = runner_slots(w)  # §16.5: the holder's own rotation counter
            if (slot := str(st.get("lease_holder") or "")) in slots:
                slots[slot]["tasks_done"] = int(slots[slot].get("tasks_done") or 0) + 1
                upd["runners"] = slots
            w.update(upd)

        save_work(q, {}, edit=closed)
    # §11.1: a run of the task that never reported will not now; a re-run finds none left
    try:
        abandoned = runs.abandon_task_runs(q, cfg, tid, "done")
    except Exception as exc:  # noqa: BLE001  (the merge and reconcile have landed; this is bookkeeping)
        abandoned = []
        warnings.append(f"could not abandon {tid}'s unreported runs ({exc}); `ccp runs gc` will")
    heartbeat(q, f"closed {tid}", task_id=tid)
    warnings += _estimate_actuals(cfg, q, tid)
    return {"ok": True, "task_id": tid, "pr": pr, "head": head, "merge_sha": merge, "reconcile_sha": reconcile,
            "merged_now": not already, "reconciled_now": not reconciled, "committed": paths, "warnings": warnings,
            **({"idle_runners": idle} if (idle := idle_runners(q, but=str(st.get("lease_holder") or ""))) else {}),
            "review_point_stamped": stamp, "abandoned_runs": abandoned}


def _estimate_actuals(cfg: Config, q: Path, tid: str) -> list[str]:
    """§26.2: the task's actual row, after everything else has landed. Advisory: a failure is a
    warning, never a failed close, and a re-run writes it once (record_actuals skips a task that has one)."""
    try:
        from ccp import estimate  # noqa: PLC0415
        estimate.record_actuals(cfg, q, tid)
        return []
    except Exception as exc:  # noqa: BLE001
        return [f"estimate actuals not recorded ({type(exc).__name__}: {str(exc)[:160]}); "
                "`ccp estimate backfill` records them later (SPEC §26.2)"]


def _cleanup(cfg: Config, tid: str) -> list[str]:
    """The legacy `adapter.post_close` commands, then every worktree of the task (§12.1: env.down and
    env.teardown, then removal), then its branch. Failures are warnings: the merge and the reconcile
    have landed."""
    warnings = []
    main = _main_checkout(cfg)
    nnnn = refs.ids(cfg).task_number(tid)
    vals = {"task_id": tid, "nnnn": nnnn}
    for cmd in cfg.adapter["post_close"] if cfg.adapter else []:
        try:
            line = cmd.format(**vals)
        except (KeyError, IndexError) as e:
            warnings.append(f"post_close `{cmd}` names {e}; it gets task_id and nnnn")
            continue
        r = _run(["/bin/sh", "-c", line], main)
        if r.returncode != 0:
            warnings.append(f"post_close `{line}` exited {r.returncode}: {(r.stderr or r.stdout).strip()[:200]}")
    if (cfg.worktrees or {}).get("dir"):
        from ccp import wt  # noqa: PLC0415
        warnings += wt.remove_task(cfg, root(), tid)
        git(main, "branch", "-D", f"task/{tid}")
        git(main, "push", "-q", "origin", "--delete", f"task/{tid}")
    return warnings

