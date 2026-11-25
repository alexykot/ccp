"""The runner seat's decisions at a spawn, on plain values (SPEC §16.5, §20.4, §22, §22.5; house rules E7, E15).

Which tasks a spawn or respawn takes, which slots it makes, which tasks no slot holds, and whether the plan is
ready. The caller (`scripts/observability/team.py`) reads work.json, the task states, the task log, the review-point
register and the runner worktree, and prints and writes; each function here takes what it read as lists, dicts and
strings, touches no file, git, config or process, and prints nothing. A refusal is a `QueueError` with exit 2 and the
message the caller prints, which it turns into its own `die`.
"""
from __future__ import annotations

from typing import Any

from ccp import tasklog
from ccp.queue import QueueError

# `readiness_checks`'s runner worktree states: a working tree of the product; nothing there (or an empty directory),
# so the spawn makes it; a non-empty directory that is not a working tree.
WORKTREE, ABSENT, OCCUPIED = "worktree", "absent", "occupied"


def tagged_open(tasks: list[dict[str, Any]], rp: str) -> list[str]:
    """§22.4: the tasks attached to the point at planning time that are still open, in task order."""
    return [str(t.get("task_id")) for t in tasks
            if t.get("review_point") == rp and t.get("status") in ("pending", "in_progress", "blocked")]


def respawn_scope(tagged: list[str], kept: list[str], pending: list[str]) -> list[str]:
    """§22.5: the scope of a respawn on work.json's review point: the point's open tagged tasks, then each
    entry of work.json's scope (`kept`, its review point's refactors left to `refactor_scope`) that names a
    still-pending task not among them, in work.json's order."""
    return tagged + [s for s in kept if any(tasklog.in_scope(p, [s]) for p in pending)
                     and not any(tasklog.in_scope(t, [s]) for t in tagged)]


def scope_warnings(tasks: list[dict[str, Any]], rp: str, scope: list[str]) -> list[str]:
    """§22: a given --scope against the tasks tagged with the point. The refactors §20 puts on
    top are not the point's own tasks, so they are not named."""
    by_id = {str(t.get("task_id")): t for t in tasks}
    out = []
    untagged = [s for s in scope
                if (t := next((by_id[k] for k in by_id if tasklog.in_scope(k, [s])), None)) is not None
                and t.get("review_point") != rp and t.get("kind") != "refactor"]
    if untagged:
        out.append(f"{len(untagged)} scope task(s) are not tagged {rp}: {', '.join(untagged)}. Set "
                   f"`review_point: {rp}` on them (`ccp review-points tag {rp} …`) if they belong to it")
    missing = [t for t in tagged_open(tasks, rp) if not tasklog.in_scope(t, scope)]
    if missing:
        out.append(f"{len(missing)} open task(s) tagged {rp} are not in the scope: {', '.join(missing)}")
    return out


def point_scope(tasks: list[dict[str, Any]], entries: Any, scope: list[str], review_point: str | None,
                scope_given: bool, work_point: str | None, work_scope: list[Any] | None,
                work_refactors: list[Any] | None, problem_given: str | None,
                problem_for: str | None) -> tuple[list[str], list[str]]:
    """§22, at spawn: (the scope, the review-point warnings). `scope` is the caller's own (`--scope`, else work.json's),
    `review_point` the `--review-point` value and `scope_given` whether `--scope` was; `work_point`, `work_scope`
    and `work_refactors` are work.json's `review_point`, `scope` and `review_point_refactors`. `problem_given` is
    `reviewpoints.problem` for the `--review-point` value and `problem_for` for the point the scope is for
    (`--review-point`, else work.json's), each a message or None, both with `entries` (the register's, or None
    for a product without one).

    With a register: `--review-point` must pass (exit 2), and without `--scope` the scope is the point's open
    tagged tasks, and on work.json's own point the tasks work.json's scope still holds pending too (§22.5,
    `respawn_scope`). Without a register, a point the pattern refuses is a warning (close will not stamp it)."""
    if entries is None:
        return scope, ([f"{problem_for}: `ccp tasks close` will not stamp it into the tasks it closes. Widen the "
                        "pattern in docs/delivery/plane.json, or name the review point to fit it"]
                       if problem_for else [])
    if review_point:
        if problem_given:
            raise QueueError(f"runner spawn --review-point: {problem_given}", 2)
        if scope_given:
            return scope, scope_warnings(tasks, review_point, scope)
        scope = tagged_open(tasks, review_point)
        if review_point == work_point:  # §22.5: a respawn keeps the tasks the lead added
            kept = [str(s) for s in work_scope or [] if s not in (work_refactors or [])]
            scope = respawn_scope(scope, kept, [str(t.get("task_id")) for t in tasks if t.get("status") == "pending"])
        if not scope:
            raise QueueError(f"no open task is tagged review_point: {review_point}; tag the point's tasks "
                             f"(`ccp review-points tag {review_point} …`) or pass --scope (SPEC §22)", 2)
        return scope, []
    if problem_for:
        return scope, [f"work.json's {problem_for}; `ccp tasks close` will not stamp it. Respawn with --review-point "
                       "R<n> (`ccp review-points migrate` renames it, SPEC §22.4)"]
    return scope, []


def refactor_scope(new_point: bool, waiting: list[str], pending: list[str] | None, work_refactors: list[Any] | None,
                   scope: list[str]) -> tuple[list[str], list[str], list[str]]:
    """§20.4 at a spawn: (the scope, the refactors put on top, the review point's refactor list). A new
    review point (`new_point`: not work.json's last one) starts with every `waiting` refactor on top, and
    work.json keeps that list for the review point. A respawn of the same review point puts back the ones of
    `work_refactors` still in `pending` (the pending task ids); it never looks for new ones: a refactor filed
    mid-cycle waits for the next review point. `pending` is None when the product runs no refactor
    placement (no task log to read): nothing is added."""
    if pending is None:
        added, rp_refactors = [], ([] if new_point else [str(r) for r in work_refactors or []])
    elif new_point:
        added = list(waiting)
        rp_refactors = added
    else:
        rp_refactors = [str(r) for r in work_refactors or []]
        added = [r for r in rp_refactors if r in pending and r not in scope]
    return added + [t for t in scope if t not in added], added, rp_refactors


def slots_of(w: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """§16.4: work.json `runners`, slot -> record; {} for one runner."""
    r = w.get("runners")
    return {str(k): dict(v) if isinstance(v, dict) else {} for k, v in r.items()} if isinstance(r, dict) else {}


def slot_tasks(in_flight: list[Any] | None, states: dict[str, Any], slot: str) -> list[str]:
    """The tasks in flight (work.json's `in_flight`) a slot holds: their `lease_holder`, and not done. `states`
    is each readable task's state by task id; a task whose state did not read holds nothing."""
    out = []
    for tid in [str(x) for x in in_flight or []]:
        st = states.get(tid)
        if isinstance(st, dict) and st.get("lease_holder") == slot and st.get("status") != "done":
            out.append(tid)
    return out


def new_slots(recorded: list[str], name: str, slot: str | None, count: int | None, cap: int) -> list[str]:
    """§16.5: the slots a spawn makes. `--slot` (a respawn, after a rotation or a lead restart) names a recorded
    one; else `--count` slots (default: the recorded ones, else one) `<name>-<n>` not recorded yet, at most `cap`
    (parallel.max_in_flight). Refuses (exit 2) a `--slot` that is none, a count above the cap, and no slot left."""
    if slot:
        if slot not in recorded:
            raise QueueError(f"--slot {slot}: no such slot ({', '.join(sorted(recorded)) or 'none'})", 2)
        return [slot]
    want = count or len(recorded) or 1
    if want > cap:
        raise QueueError(f"--count {want} is above parallel.max_in_flight {cap} (SPEC §16.5)", 2)
    new = [f"{name}-{i}" for i in range(1, want + 1) if f"{name}-{i}" not in recorded]
    if not new:
        raise QueueError(f"{want} slot(s) are recorded already; respawn one with --slot", 2)
    return new


def orphans(in_flight: list[Any] | None, states: dict[str, Any], recorded: list[str], new: list[str]) -> None:
    """§16.5: refuses (exit 2) when a task the single runner still holds would belong to no slot and stall: an
    in-flight task, not done, whose `lease_holder` is neither a recorded slot nor one of the `new` ones."""
    held = []
    for t in [str(x) for x in in_flight or []]:
        st = states.get(t)
        h = st.get("lease_holder") if isinstance(st, dict) else None
        if h and st.get("status") != "done" and h not in recorded and h not in new:
            held.append(f"{t} (held by {h})")
    if held:
        raise QueueError(f"{', '.join(held)}: held by no runner slot. Drain or stop the single runner first "
                         "(`team.sh runner stop --drain`), or `ccp tasks release` it (SPEC §16.5)", 2)


def readiness_checks(scope: list[str], ids: list[str], errors: list[str], held: list[str] | None,
                     worktree: tuple[str, str] | None) -> list[dict[str, Any]]:
    """SPEC §16.5, `runner spawn --dry-run`: the §10.2 readiness checks a machine can answer, as {check, ok, detail}:
    every `scope` entry names a task id of the log (`ids`), `ccp tasks check` is clean (`errors`), no closed review
    point holds an undecided follow-up (`held`, §22.2), and (one runner) the runner worktree is a working tree or
    can be made. `held` is None when the product's task log does not read: that is the one check then. `worktree` is
    (path, WORKTREE | ABSENT | OCCUPIED), or None when there is none to check (several slots, or no worktree)."""
    checks: list[dict[str, Any]] = []
    if held is None:
        checks.append({"check": "task_log", "ok": False,
                       "detail": "the product's task log does not read (no plane.json at the product root, or a "
                                 "bad task file): `ccp tasks check` names it"})
    else:
        missing = [s for s in scope if not any(tasklog.in_scope(t, [s]) for t in ids)]
        checks.append({"check": "scope_tasks_exist", "ok": not missing,
                       "detail": f"not in the task log: {', '.join(missing)}" if missing
                       else f"{len(scope)} scope task(s) in the task log"})
        checks.append({"check": "tasks_check", "ok": not errors,
                       "detail": f"`ccp tasks check`: {len(errors)} failure(s): " + "; ".join(errors[:5]) if errors
                       else "`ccp tasks check` is clean"})
        checks.append({"check": "closed_points", "ok": not held,
                       "detail": f"`ccp tasks check --closed-points`: {len(held)} failure(s): " + "; ".join(held[:5])
                       if held else "no closed review point holds an undecided follow-up"})
    if worktree:
        path, state = worktree
        if state == WORKTREE:
            checks.append({"check": "runner_worktree", "ok": True, "detail": f"{path} exists"})
        elif state == OCCUPIED:
            checks.append({"check": "runner_worktree", "ok": False,
                           "detail": f"{path} exists and is not a working tree of the product: the spawn could "
                                     "not make it (SPEC §12.1)"})
        else:
            checks.append({"check": "runner_worktree", "ok": True, "detail": f"{path} would be made by the spawn"})
    return checks
