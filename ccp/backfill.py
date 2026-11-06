"""`ccp tasks backfill-review-points [--dry-run]` (SPEC §22, §22.6): the review point of each done
task closed before `ccp tasks close` stamped one, rebuilt from the queue's history.

The ledger's `runner` events are the runner's history: each `spawn` carries the review point and the
scope, each `scope` event the scope after a change, each `stop` ends that runner. A task's claim is
its first claim in the ledger (`lease`/`set`, or a `phase` move to `leased` or `implementing`), else
the queue file's `claimed_at` or `implementation_started_at`. A task belongs to:

1. the point its close wrote into the product log, when `reconcile.log.entry` names both
   `{review_point}` and `{nnnn}` (or `{task_id}`) and one entry matches the task (`log`): it is the
   value `close` stamps today, work.json's point at the close;
2. else the runner live at its claim, when that runner's scope listed it (`scope`);
3. else the latest runner spawned before the claim whose scope listed it, else the first one
   spawned after the claim and before the task was done (`scope`, a claim made outside the runner);
4. else the runner live at the claim, when one was (`time`).

A task claimed before the first recorded spawn, or between runners with no scope naming it, stays
unset. So does one whose point the product does not accept: with the review-point register, an R<n>
it lists (§22); without it, one matching `task_log.review_point_pattern`. A point that `ccp review-points migrate` renamed (a ledger `runner`/`set` event)
reads as its new name, in the ledger and the log alike.

It writes only the working tree: `review_point: R` as the frontmatter's last line of each task file
that has none (the same edit `close` makes, CRLF kept), never a value already set, and it commits
nothing. The design seat reads the diff and commits it as one change (§22 says why). Nothing is
written to the queue.
"""
from __future__ import annotations

from ccp.queue import events_path as _events_path

import json
import re
import shlex
from pathlib import Path
from typing import Any

from ccp import refs, tasklog
from ccp.config import Config
from ccp.health import released
from ccp.lifecycle import _changed, stamp_review_point
from ccp.queue import QueueError, load_task_state, root

CLAIM_PHASES = ("leased", "implementing")


def _events(q: Path) -> list[dict[str, Any]]:
    p = _events_path(q)
    out = []
    for line in p.read_text().splitlines() if p.is_file() else []:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and isinstance(e.get("at"), str) and isinstance(e.get("payload"), dict):
            out.append(e)
    return sorted(out, key=lambda e: e["at"])  # ISO UTC strings sort as times; stable for ties


def runners(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per `runner`/`spawn`: its review point, start, end (the next spawn or a stop) and
    the tasks its scope named, at the spawn or after a `scope` change."""
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for e in events:
        if e.get("type") != "runner":
            continue
        op, p = e.get("op"), e["payload"]
        if op == "spawn":
            if cur and cur["end"] is None:
                cur["end"] = e["at"]
            scope = [str(x) for x in p.get("scope") or []]
            cur = {"review_point": str(p.get("review_point") or ""), "start": e["at"], "end": None,
                   "at_spawn": set(scope), "added": set()}
            out.append(cur)
        elif op == "scope" and cur and cur["end"] is None:
            cur["added"] |= {str(x) for x in p.get("scope") or []} - cur["at_spawn"]
        elif op == "stop" and cur and cur["end"] is None:
            cur["end"] = e["at"]
    return out


def _times(events: list[dict[str, Any]], q: Path, tid: str) -> tuple[str | None, str, str | None]:
    """The task's claim time and where it came from, and its done time."""
    claim = done = None
    for e in events:
        if e.get("task_id") != tid:
            continue
        typ, op, p = e.get("type"), e.get("op"), e["payload"]
        if released(e):  # §10.4: an undone claim; the task's claim is the next one
            claim = None
            continue
        if claim is None and ((typ == "lease" and op == "set") or (typ == "phase" and p.get("to") in CLAIM_PHASES)):
            claim = e["at"]
        if done is None and ((typ == "phase" and p.get("to") == "done") or typ == "durable"):
            done = e["at"]
    if claim:
        return claim, "ledger", done
    st = load_task_state(q, tid)
    for key in ("claimed_at", "implementation_started_at"):
        if isinstance(st.get(key), str) and st[key]:
            return st[key], f"tasks/{tid}.json {key}", done or st.get("merged_at") or None
    return None, "none", done


def log_points(cfg: Config) -> dict[str, set[str]]:
    """NNNN -> the review points the product log's close entries give it (reconcile.log). Built from
    the entry template's first line: `{review_point}` and `{nnnn}`/`{task_id}` captured, every other
    field matched loosely. Empty when there is no log or the template does not name both."""
    log = cfg.reconcile["log"] if cfg.reconcile else None
    if not log:
        return {}
    first = log["entry"].split("\n", 1)[0]
    if "{review_point}" not in first or not ("{nnnn}" in first or "{task_id}" in first):
        return {}
    pat, seen, w = "", set(), refs.ids(cfg).task_width
    for part in re.split(r"(\{\w+\})", first):
        name = part[1:-1] if re.fullmatch(r"\{\w+\}", part) else None
        if name is None:
            pat += re.escape(part)
        elif name in ("review_point", "nnnn", "task_id") and name not in seen:
            seen.add(name)
            pat += {"review_point": r"(?P<review_point>[A-Za-z0-9._-]{1,32})", "nnnn": rf"(?P<nnnn>[0-9]{{{w}}})",
                    "task_id": rf"(?P<task_id>[0-9]{{{w}}}[A-Za-z0-9._-]*)"}[name]
        else:
            pat += r".*?"
    rx = re.compile(pat)
    path = cfg.root / log["path"]
    out: dict[str, set[str]] = {}
    for line in path.read_text().splitlines() if path.is_file() else []:
        m = rx.match(line)
        if m:
            nnnn = refs.ids(cfg).task_number(m.groupdict().get("nnnn") or m.groupdict().get("task_id") or "")
            out.setdefault(nnnn, set()).add(m.group("review_point"))
    return out


def _member(r: dict[str, Any], tid: str) -> bool:
    return tid in r["at_spawn"] or tid in r["added"]


def assign(rs: list[dict[str, Any]], tid: str, claim: str | None, done: str | None) -> dict[str, Any]:
    """The review point for one task, with the evidence (module doc)."""
    if not claim:
        return {"review_point": None, "why": "no claim time in the ledger or the queue file"}
    if not rs or claim < rs[0]["start"]:
        return {"review_point": None, "why": "claimed before the first recorded runner spawn"}
    before = [r for r in rs if r["start"] <= claim]
    live = before[-1] if before and (before[-1]["end"] is None or claim <= before[-1]["end"]) else None

    def ev(r: dict[str, Any], how: str) -> dict[str, Any]:
        hit = "at spawn" if tid in r["at_spawn"] else ("added later" if tid in r["added"] else None)
        return {"review_point": r["review_point"] or None, "how": how, "spawn_at": r["start"], "scope_hit": hit}

    if live and _member(live, tid):
        return ev(live, "scope")
    hits = [r for r in before if _member(r, tid)]
    if hits:
        return ev(hits[-1], "scope")
    later = [r for r in rs if r["start"] > claim and (not done or r["start"] <= done) and _member(r, tid)]
    if later:
        return ev(later[0], "scope")
    if live:
        return ev(live, "time")
    return {"review_point": None, "why": "claimed between runners, and no runner's scope named it"}


def plan(cfg: Config, q: Path) -> dict[str, Any]:
    from ccp import reviewpoints  # noqa: PLC0415
    events = _events(q)
    renamed = reviewpoints.renames(events)  # §22.9: what `ccp review-points migrate` renamed
    rs = runners(events)
    for r in rs:
        r["review_point"] = renamed.get(r["review_point"], r["review_point"])
    logged = {k: {renamed.get(v, v) for v in vs} for k, vs in log_points(cfg).items()}
    register = reviewpoints.load(cfg)[0]
    rows, kept = [], 0
    for t in tasklog.load(cfg):
        if t.get("status") != "done":
            continue
        if "review_point" in t:
            kept += 1
            continue
        tid = str(t.get("task_id") or t["_file"].stem)
        claim, source, done = _times(events, q, tid)
        a = assign(rs, tid, claim, done)
        got = logged.get(refs.ids(cfg).task_number(tid)) or set()
        if len(got) == 1:
            rp = next(iter(got))
            ledger = a.get("review_point")
            a = {"review_point": rp, "how": "log", "log": cfg.reconcile["log"]["path"],
                 **({"ledger_says": ledger} if ledger != rp else {})}
        elif len(got) > 1:
            a["log_conflict"] = sorted(got)  # the log disagrees with itself: the ledger decides
        row = {"task_id": tid, "file": cfg.rel(t["_file"]), "claim_at": claim, "claim_from": source, "done_at": done, **a}
        rp = a["review_point"]
        if rp and (problem := reviewpoints.problem(cfg, rp, register)):
            row.update(action="skip", why=problem)
        else:
            row["action"] = "stamp" if rp else "unset"
        rows.append(row)
    counts: dict[str, int] = {}
    for r in rows:
        key = r["review_point"] or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return {"runners": [{"review_point": r["review_point"], "start": r["start"], "end": r["end"],
                         "scope": len(r["at_spawn"] | r["added"])} for r in rs],
            "tasks": rows, "counts": dict(sorted(counts.items())), "already_set": kept,
            "to_stamp": sum(r["action"] == "stamp" for r in rows),
            "skipped_pattern": sum(r["action"] == "skip" for r in rows)}


def backfill(cfg: Config, dry_run: bool = False) -> dict[str, Any]:
    q = root()
    from ccp import reviewpoints  # noqa: PLC0415
    body = plan(cfg, q)
    body["dry_run"] = dry_run
    body["notes"] = reviewpoints.notes(cfg)
    targets = [r for r in body["tasks"] if r["action"] == "stamp"]
    if dry_run or not targets:
        body["written"] = []
        body["warnings"] = list(body["notes"])
        return body
    dirty = set(_changed(cfg.root))
    busy = [r["file"] for r in targets if r["file"] in dirty]
    if busy:
        raise QueueError("these task files have uncommitted changes; commit or discard them first, so the "
                         "backfill's diff is its own:\n  " + "\n  ".join(busy), 2)
    before = set(tasklog.check(cfg))
    written, warnings = [], []
    for r in targets:
        path = cfg.root / r["file"]
        with path.open(newline="") as fh:  # no newline translation: a CRLF file stays CRLF
            text = fh.read()
        new = stamp_review_point(text, r["review_point"])
        if new is None:
            warnings.append(f"{r['file']}: no frontmatter block to stamp")
            r["action"] = "unset"
            continue
        with path.open("w", newline="") as fh:
            fh.write(new)
        written.append(r["file"])
    errs = [e for e in tasklog.check(cfg) if e not in before]
    body.update(written=written, warnings=body["notes"] + warnings + errs,
                commit=(f"git -C {shlex.quote(str(cfg.root))} commit -m 'Task log: review points backfilled "
                        "(ccp tasks backfill-review-points)' -- " + " ".join(shlex.quote(f) for f in written)
                        if written else None))
    return body
