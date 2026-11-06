"""What `ccp tasks next` picks, read from the queue: one function for the command and the board
(SPEC §10.3, §20.3, §22).

`inputs` reads work.json the way `next` always has: a running runner's scope is
the default scope, and its `review_point_refactors` go first; the lead's preference list (`next_tasks`,
`ccp tasks prefer`) comes before everything, each entry in its order once it is ready. `pick` hands them to
`tasklog.ranked`, whose first row is `next`'s answer and whose rest is the order after it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ccp import tasklog
from ccp.config import Config
from ccp.queue import QueueError, load_work, preferred_ids


def _work(q: Path | None) -> dict[str, Any]:
    if q is None or not q.is_dir():
        return {}
    try:
        return load_work(q)
    except QueueError:
        return {}


def inputs(cfg: Config, q: Path | None, scope: list[str] | None = None,
           tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The scope (and whether it came from work.json), the review point's refactors, and the lead's
    preference list: `prefer`, the (task, why) of each entry that is ready or waiting on a dependency,
    in the lead's order (`ranked` takes the ready ones), and `prefer_notes` for the rest."""
    w = _work(q)
    from_work = False
    if scope is None and w.get("status") == "running" and w.get("scope"):
        scope, from_work = [str(s) for s in w["scope"]], True
    first, rp = [], None
    if cfg.architect is not None:
        first = [str(x) for x in w.get("review_point_refactors") or [] if tasklog.in_scope(str(x), scope)]
        rp = w.get("review_point")
    prefer: list[tuple[dict[str, Any], str]] = []
    notes: list[str] = []
    states: list[dict[str, Any]] = []
    ids = preferred_ids(w)
    bits = [str(w.get("next_task_by") or "?"), str(w.get("next_task_at") or "?")]
    if w.get("next_task_reason"):
        bits.append(str(w["next_task_reason"]))
    for k, tid in enumerate(ids, 1):
        t, state = tasklog.preferred(cfg, tid, scope, tasks)
        states.append({"task_id": tid, "state": state})
        if t is not None and (state == "ready" or state.startswith("waiting on")):
            pos = [f"{k} of {len(ids)}"] if len(ids) > 1 else []
            prefer.append((t, f"the lead's preference ({', '.join(pos + bits)}; work.json next_tasks, `ccp tasks prefer`)"))
            if state != "ready":
                notes.append(f"preferred {tid} is {state}: skipped for now, keeping its place")
        else:
            notes.append(f"preferred {tid} is {state}: ignored (`ccp tasks prefer` a new list, or --clear)")
    flight = [str(x) for x in w.get("in_flight") or []]
    if w.get("task_id") and str(w["task_id"]) not in flight:
        flight.append(str(w["task_id"]))
    return {"scope": scope, "scope_from_work": from_work, "first": first, "review_point": rp, "prefer": prefer,
            "prefer_notes": notes, "preferred": states or None, "in_flight": flight}


def holds(q: Path | None) -> dict[str, dict[str, Any]]:
    """§10.4 `ccp tasks hold`: the lead's holds, work.json `held` ({task_id: {by, at, reason}})."""
    h = _work(q).get("held")
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in h.items()} if isinstance(h, dict) else {}


def pick(cfg: Config, q: Path | None, scope: list[str] | None = None,
         tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """`inputs` plus `ranked`: row 0 is what `ccp tasks next` returns now. A held task (a refactor or
    the preference too) is passed over: `ranked` is the order without the holds, `ranked_all` the full
    queue they sit in, and `passed_over` the held tasks that would otherwise be in it."""
    tasks = tasks if tasks is not None else tasklog.load(cfg)
    i = inputs(cfg, q, scope, tasks)
    full = tasklog.ranked(cfg, i["scope"], i["first"], i["prefer"], tasks, i["review_point"])
    held = holds(q)
    i["held"], i["ranked_all"], i["passed_over"] = held, full, []
    if not held:
        i["ranked"] = full
        return i
    # A held task stays in the log (its dependants and the refactors it reaches are unchanged); it is
    # only not pending for this pick.
    live = [{**t, "status": "held"} if str(t.get("task_id")) in held else t for t in tasks]
    prefer = [p for p in i["prefer"] if str(p[0].get("task_id")) not in held]
    for p in i["prefer"]:
        if (tid := str(p[0].get("task_id"))) in held:
            i["prefer_notes"] = [n for n in i["prefer_notes"] if not n.startswith(f"preferred {tid} ")]
            i["prefer_notes"].append(f"preferred {tid} is held: passed over (`ccp tasks hold --clear {tid}`)")
    for st in i["preferred"] or []:
        if st["task_id"] in held and (st["state"] == "ready" or st["state"].startswith("waiting on")):
            st["state"] = "held"
    i["prefer"] = prefer
    first = [x for x in i["first"] if x not in held]
    i["ranked"] = tasklog.ranked(cfg, i["scope"], first, prefer, live, i["review_point"])
    i["passed_over"] = [str(t.get("task_id")) for t, _ in full if str(t.get("task_id")) in held]
    return i
