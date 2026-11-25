"""Seats propose `ccp` tools instead of writing their own (SPEC §31.4), and the hooks that bind runs.

The commands are `plane propose`, `plane triage`, `plane built`, `plane list` and `plane check`, and `agent start|stop`,
the SubagentStart and SubagentStop hooks (`docs/cli`). `plane check` lists the queue entries the plane does not
write (§31.3): files in QUEUE_ROOT/scripts/ that are not the plane's, and top-level entries it does not keep;
`--archive` moves them to QUEUE_ROOT/_legacy/<UTC date>/, deleting nothing.

Proposals are `QUEUE_ROOT/plane/proposals.jsonl`, append-only: a `proposed` row, then `again` and
`triaged` rows naming its id, and a `built` row for an accepted one a merged plane task built, carrying
that task's `adopt` step (ADR-0041 D4). The current state is the fold. An open proposal whose last `again` (or
its creation, whichever is later) is STALE_DAYS old or more is flagged `stale` in the list and on the
board.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from ccp import health, runs
from ccp.config import Config
from ccp.queue import (LEGACY_DIR, QueueError, actor, emit, iso, leftover_entries, now, queue_leftovers, root,
                       script_drift, script_findings)

FREQUENCIES = ("per-task", "per-run", "once")
DECISIONS = ("accepted", "merged", "declined")
STALE_DAYS = 7  # §31.4: an open proposal untouched this long is flagged


def _path(q: Path) -> Path:
    return q / "plane" / "proposals.jsonl"


def _append(q: Path, row: dict[str, Any]) -> None:
    from ccp.queue import append_jsonl  # noqa: PLC0415  (under the lock the sync's merge takes)
    append_jsonl(_path(q), row)


def proposals(q: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    p = _path(q)
    for line in p.read_text().splitlines() if p.is_file() else []:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        pid = row.get("id")
        if row.get("op") == "proposed":
            out[pid] = {**row, "status": "open", "again": 0, "last_at": row.get("at")}
        elif pid in out and row.get("op") == "again":
            out[pid]["again"] += 1
            out[pid]["last_at"] = row.get("at")
        elif pid in out and row.get("op") == "triaged":
            out[pid].update(status=row.get("decision"), triaged_at=row.get("at"), reason=row.get("reason"),
                            merged_into=row.get("merged_into"), triaged_by=row.get("by"))
        elif pid in out and row.get("op") == "built":
            out[pid].update(status="built", built_task=row.get("built_task"), adopt=row.get("adopt"),
                            built_at=row.get("at"), built_by=row.get("by"))
    t = now().timestamp()
    for r in out.values():
        r["stale"] = _stale(r, t)
    return out


def _stale(r: dict[str, Any], t: float) -> bool:
    """§31.4: open, and its later of creation and last `again` is STALE_DAYS old or more. An
    unreadable time never flags."""
    if r["status"] != "open":
        return False
    seen = [e for e in (health._epoch(r.get("at")), health._epoch(r.get("last_at"))) if e is not None]
    return bool(seen) and t - max(seen) >= STALE_DAYS * 86400


def _clean(text: str | None, what: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    if health.looks_like_secret(text):
        raise QueueError(f"{what} looks like it holds a secret; say it without the value", 2)
    return text


def propose(cfg: Config, a: Any) -> dict[str, Any]:
    q = root()
    by = actor()
    if a.again:
        cur = proposals(q).get(a.again)
        if not cur:
            raise QueueError(f"no proposal {a.again} (ccp plane list)", 2)
        _append(q, {"op": "again", "id": a.again, "at": iso(), "by": by, "task_id": a.task or None})
        emit(q, cfg, a.task or "", "plane", "again", {"proposal_id": a.again})
        return {"ok": True, "id": a.again, "again": cur["again"] + 1, "status": cur["status"]}
    need = _clean(a.need, "--need")
    if not need:
        raise QueueError("give --need: the step `ccp` does not cover, in one or two sentences", 2)
    generic = _clean(getattr(a, "generic", None), "--generic")
    if not generic:
        raise QueueError("give --generic: why any product would need this, whatever its language, domain or "
                         "conventions (SPEC §31.4). A need only this product has is product work: build it in "
                         "the product repo, wire it through docs.checks, an env hook, architect.checks or "
                         "reconcile.hooks, and ask the lead for a product task", 2)
    freq = a.frequency or "per-task"
    if freq not in FREQUENCIES:
        raise QueueError(f"--frequency is one of {', '.join(FREQUENCIES)}", 2)
    pid = f"pp-{iso().replace('-', '').replace(':', '')}-{secrets.token_hex(2)}"
    row = {"op": "proposed", "id": pid, "at": iso(), "by": by, "task_id": a.task or None, "need": need,
           "generic": generic, "workaround": _clean(a.workaround, "--workaround"), "frequency": freq}
    _append(q, row)
    emit(q, cfg, a.task or "", "plane", "proposed", {"proposal_id": pid, "need": need[:200], "frequency": freq})
    return {"ok": True, "id": pid, "status": "open",
            "next": "Tell the lead in one line. Until the tool exists, do the step by hand and record each "
                    f"repeat with `ccp plane propose --again {pid}`"}


def triage(cfg: Config, a: Any) -> dict[str, Any]:
    q = root()
    cur = proposals(q).get(a.id)
    if not cur:
        raise QueueError(f"no proposal {a.id}", 2)
    if cur["status"] != "open":
        raise QueueError(f"{a.id} is already {cur['status']}", 3)
    picked = [d for d, on in (("accepted", a.accept), ("merged", bool(a.merge_into)), ("declined", a.decline)) if on]
    if len(picked) != 1:
        raise QueueError("give exactly one of --accept, --merge-into ID, --decline", 2)
    reason = _clean(a.reason, "--reason")
    if not reason:
        raise QueueError("give --reason: for an accept, the plane task or PR it becomes", 2)
    if a.merge_into and a.merge_into not in proposals(q):
        raise QueueError(f"--merge-into {a.merge_into}: no such proposal", 2)
    row = {"op": "triaged", "id": a.id, "at": iso(), "by": actor("plane-session"), "decision": picked[0],
           "merged_into": a.merge_into or None, "reason": reason}
    _append(q, row)
    emit(q, cfg, cur.get("task_id") or "", "plane", "triaged",
         {"proposal_id": a.id, "decision": picked[0], "reason": reason[:200]}, actor("plane-session"))
    return {"ok": True, "id": a.id, "status": picked[0]}


def built(cfg: Config, a: Any) -> dict[str, Any]:
    """§29.3, ADR-0041 D4: close an accepted proposal as built by a merged plane task (one `done` in the
    plane's own task log), copying that task's `adopt` step into the proposal's record."""
    from ccp import tasklog, upgrade  # noqa: PLC0415
    q = root()
    cur = proposals(q).get(a.id)
    if not cur:
        raise QueueError(f"no proposal {a.id}", 2)
    if cur["status"] != "accepted":
        raise QueueError(f"{a.id} is {cur['status']}: only an accepted proposal is closed as built", 3)
    task = upgrade.merged_task(a.task)
    if task is None:
        raise QueueError(f"--task {a.task}: no merged plane task by that id (a `done` task in the plane's "
                         "task log)", 2)
    tid = str(task["task_id"])  # the full id, whatever `--task` gave: `upgrade`'s proposals are keyed by it
    step = tasklog.adopt_step(task)
    _append(q, {"op": "built", "id": a.id, "at": iso(), "by": actor("plane-session"), "built_task": tid,
                "adopt": step})
    emit(q, cfg, cur.get("task_id") or "", "plane", "built", {"proposal_id": a.id, "built_task": tid},
         actor("plane-session"))
    return {"ok": True, "id": a.id, "status": "built", "built_task": tid, "adopt": step}


def listing(_cfg: Config, a: Any) -> dict[str, Any]:
    rows = sorted(proposals(root()).values(), key=lambda r: (-r["again"], r["at"]))
    if a.open:
        rows = [r for r in rows if r["status"] == "open"]
    return {"ok": True, "proposals": rows, "stale": [r["id"] for r in rows if r["stale"]]}


def check(cfg: Config, a: Any) -> tuple[dict[str, Any], int]:
    """§31.3: `scripts`, the files in QUEUE_ROOT/scripts/ that are not the plane's copy, and `root`,
    the top-level entries the plane does not keep; exit 1 when either is non-empty. With `--archive`
    it first moves every entry it would list (`archive`), then checks again."""
    q = root()
    moved = archive(q, cfg) if getattr(a, "archive", False) else None
    scripts, left = script_drift(q), queue_leftovers(q)
    body: dict[str, Any] = {"ok": not (scripts or left), "scripts": scripts, "root": left}
    if moved is not None:
        body.update(moved)
    return body, (0 if body["ok"] else 1)


def archive(q: Path, cfg: Config) -> dict[str, list[dict[str, str]]]:
    """§31.3: move each entry `check` lists (the scripts that are unknown, drifted or retired, then the
    top-level entries) to QUEUE_ROOT/_legacy/<YYYY-MM-DD, UTC>/<its path relative to QUEUE_ROOT>. It
    never deletes: an entry whose target already exists, or that cannot be moved, stays where it is and
    is listed under `not_moved` with the reason. Paths are relative to QUEUE_ROOT; a directory's ends
    in `/`. When anything moved or failed to move, it emits one `plane`/`archived` event with the day
    and the two counts, never a path."""
    day = now().strftime("%Y-%m-%d")
    archived: list[dict[str, str]] = []
    not_moved: list[dict[str, str]] = []
    for rel in [path for _, path, _ in script_findings(q)] + leftover_entries(q):
        src, dst = q / rel, q / LEGACY_DIR / day / rel
        slash = "/" if src.is_dir() and not src.is_symlink() else ""
        row = {"path": rel + slash, "target": f"{LEGACY_DIR}/{day}/{rel}{slash}"}
        if os.path.lexists(dst):
            not_moved.append({**row, "reason": f"the target {row['target']} already exists (an earlier "
                                               "archive the same day); nothing was overwritten"})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, dst)
        except OSError as e:
            not_moved.append({**row, "reason": f"could not move it: {e.strerror or e}"})
            continue
        archived.append(row)
    if archived or not_moved:
        emit(q, cfg, "", "plane", "archived", {"day": day, "archived": len(archived), "not_moved": len(not_moved)},
             actor("operator"))
    return {"archived": archived, "not_moved": not_moved}


def agent_hook(cfg: Config, action: str, raw: str) -> dict[str, Any]:
    """SubagentStart binds the oldest pending run of the agent's type; SubagentStop stops it. An
    agent the toolkit did not launch is recorded as unbound. Never raises: a hook must not fail the
    agent it watches."""
    try:
        q = root()
        data = json.loads(raw or "{}")
        agent_id = str(data.get("agent_id") or "")
        agent_type = str(data.get("agent_type") or "")
        if not agent_id:
            return {"ok": True, "skipped": "no agent_id in the hook input"}
        if action == "start":
            if runs.unscoped(agent_type) not in set(runs.AGENT_TYPE.values()):
                return {"ok": True, "skipped": f"agent type {agent_type or '?'} is not a plane worker"}
            rec = runs.bind(q, cfg, agent_type, agent_id, data.get("session_id"))
            if rec is None:
                _unbound(q, {"at": iso(), "agent_id": agent_id, "agent_type": agent_type,
                             "session_id": data.get("session_id"), "why": "no pending run of its type"})
                return {"ok": True, "bound": None}
            return {"ok": True, "bound": rec["run_id"]}
        rec = runs.stop(q, cfg, agent_id)
        return {"ok": True, "stopped": rec["run_id"] if rec else None}
    except Exception as exc:  # noqa: BLE001  (a hook never fails its agent)
        try:
            _unbound(Path(root()), {"at": iso(), "error": f"{type(exc).__name__}: {exc}"[:300], "action": action})
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": str(exc)[:300]}


def _unbound(q: Path, row: dict[str, Any]) -> None:
    p = q / "runs" / "_unbound.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def read_stdin() -> str:
    try:
        return sys.stdin.read() if not sys.stdin.isatty() else ""
    except (OSError, ValueError):
        return ""
