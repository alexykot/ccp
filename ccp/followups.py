"""Worker follow-ups (SPEC §13.4, ADR-0044 D2 and D4): the lead records what became of each follow-up a
worker report states (`ccp tasks follow-up`), and `ccp tasks follow-ups` lists them across tasks.

A follow-up lives on its run record (`follow_ups`, each with its id `<run_id>#<n>`, refs.py) beside the
lead's `outcome`. `undecided` and `listing` work on plain run records; `undecided` is the one list of open
follow-ups that every reader counts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ccp import health, plane, queue, refs, runs, tasklog
from ccp.config import Config
from ccp.queue import QueueError

LEAD = "design-seat"  # §2: the actor the lead's commands record as, and the only one that decides a follow-up
KINDS = ("task", "proposal", "drop")  # an outcome: a task in the log, a plane proposal, or dropped with a reason


def _rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every follow-up on `records`, in their order and each report's: its id, task, run, text and outcome
    (None while undecided). A record without the field, or an entry that is not one, adds nothing."""
    out = []
    for rec in records:
        items = rec.get("follow_ups") if isinstance(rec, dict) else None
        for fu in items if isinstance(items, list) else []:
            if not isinstance(fu, dict) or not fu.get("id"):
                continue
            outcome = fu.get("outcome")
            out.append({"id": str(fu["id"]), "task_id": str(rec.get("task_id") or ""),
                        "run_id": str(rec.get("run_id") or ""), "text": str(fu.get("text") or ""),
                        "outcome": outcome if isinstance(outcome, dict) and outcome else None})
    return out


def undecided(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The follow-ups on `records` with no outcome recorded, as `listing` gives them."""
    return [r for r in _rows(records) if r["outcome"] is None]


def listing(records: list[dict[str, Any]], open_only: bool) -> list[dict[str, Any]]:
    """Every follow-up on `records`, or with `open_only` the undecided ones."""
    return undecided(records) if open_only else _rows(records)


def outcome_word(outcome: dict[str, Any] | None) -> str:
    """How a listing line names an outcome: `open`, `task:<id>`, `proposal:<id>` or `drop`."""
    if not outcome:
        return "open"
    kind = str(outcome.get("kind") or "?")
    return f"{kind}:{outcome['ref']}" if outcome.get("ref") else kind


def line(row: dict[str, Any]) -> str:
    """One listing line: `<id> <task_id> <outcome or open>: <text>`."""
    return f"{row['id']} {row['task_id']} {outcome_word(row['outcome'])}: {row['text']}"


def resolve_task(given: str, present: list[str], ids: refs.Ids) -> str | None:
    """The task id `given` names among the ids `present` (its full id, or its number when exactly one task
    has it); None when it names none."""
    given = given.strip()
    if given in present:
        return given
    hits = [t for t in present if given != t and ids.same_task(t, given)]
    return hits[0] if len(hits) == 1 else None


def _find(rec: Any, fid: str) -> dict[str, Any] | None:
    """The follow-up `fid` on run record `rec`, or None."""
    items = rec.get("follow_ups") if isinstance(rec, dict) else None
    return next((fu for fu in items if isinstance(fu, dict) and fu.get("id") == fid), None) \
        if isinstance(items, list) else None


def decide(q: Path, cfg: Config, fid: str, kind: str, ref_or_reason: str, by: str) -> dict[str, Any]:
    """§13.4, ADR-0044 D2: record follow-up `fid`'s outcome on its run record, replacing any earlier one, and a
    `run` `decided` event. Refused (exit 2, nothing written) for a caller other than the lead, an id that
    resolves to no follow-up, a task not in the task log at `origin/<integration>`, a proposal not in
    `plane/proposals.jsonl`, and an empty or secret-like drop reason."""
    if by != LEAD:
        raise QueueError(f"only the lead records a follow-up's outcome (ACTOR is {by}): tell the lead", 2)
    if kind not in KINDS:
        raise QueueError(f"an outcome is one of {', '.join(KINDS)}", 2)
    parsed = refs.parse_follow_up_id(fid)
    if parsed is None:
        raise QueueError(f"{fid!r} is not a follow-up id (<run_id>#<n>; `ccp tasks follow-ups` lists them)", 2)
    run_id, _ = parsed
    try:
        rec = queue.read_json(runs.path(q, run_id), None)
    except QueueError as e:
        raise QueueError(f"{fid}: {e}", 2) from e
    fid = refs.follow_up_id(run_id, parsed[1])
    fu = _find(rec, fid)
    if fu is None:
        raise QueueError(f"no follow-up {fid}: `ccp tasks follow-ups` lists them", 2)
    value = ref_or_reason.strip()
    if kind == "task":
        rev = f"origin/{queue.integration_branch(q)}"
        tid = resolve_task(value, tasklog.task_ids_at(cfg, rev), refs.ids(cfg))
        if tid is None or tid not in tasklog.statuses_at(cfg, rev, [tid]):
            raise QueueError(f"--task {value!r} names no task in the task log at {rev}: write and push the task "
                             "first (fetch, if it was pushed from elsewhere)", 2)
        value = tid
    elif kind == "proposal":
        if value not in plane.proposals(q):
            raise QueueError(f"--proposal {value!r} names no row of plane/proposals.jsonl (`ccp plane list`)", 2)
    elif not value:
        raise QueueError("give --drop a reason: why the work is not worth doing", 2)
    elif health.looks_like_secret(value):
        raise QueueError("the --drop reason looks like a secret: write it without one", 2)
    outcome = {"kind": kind, ("reason" if kind == "drop" else "ref"): value, "at": queue.iso(), "by": by}
    replaced = fu.get("outcome") or None
    fu["outcome"] = outcome
    runs.save(q, rec)
    task_id = str(rec.get("task_id") or runs.parse_id(run_id)[0])
    queue.emit(q, cfg, task_id, "run", "decided",
               {"run_id": run_id, "follow_up": fid, "kind": kind, **({"ref": value} if kind != "drop" else {})}, by)
    return {"ok": True, "id": fid, "task_id": task_id, "outcome": outcome, "replaced": replaced}


__all__ = ["KINDS", "LEAD", "decide", "line", "listing", "outcome_word", "resolve_task", "undecided"]
