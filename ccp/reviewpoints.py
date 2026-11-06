"""The review-point register (SPEC §22.1, §22.4): what each review point is for, and the tools that
keep tasks, ADRs and the queue on it.

  ccp review-points [list] [--json]                       every point: name, status, progress
  ccp review-points show R8 [--json]                      one point: its goal, tasks and ADRs
  ccp review-points tag R8 [ID ...] [--from-work] [--dry-run] [--json]
                                                          set `review_point: R8` on tasks (planning)
  ccp review-points migrate --from PM --to R8 [--dry-run] [--merge] [--json]
                                                          rename a legacy point in the task files and
                                                          the queue's work.json

The operator, 2026-10-22: "Review points are points at which I get in and review the progress at a high
level, at a functional level. … Review points need to have a name and description apart from a
number. The number scheme needs to be strict: R<number> … The tasks and ADRs need to be attached to
a review point so that we have a clear arrangement of scope." And: "we should not invent review
point names out of the air." So the register is the product's file, written by the task-log owner
with the operator; the plane reads it and never makes up an entry.

**The register** is `review_points.file` in plane.json (default `docs/delivery/review-points.yaml`):

    review_points:
      - id: R8
        name: pre-beta
        goal: |-
          After this point's tasks are done we run the beta test.
        status: current        # planned | current | closed
        opened: 2026-10-22     # optional, YYYY-MM-DD
        closed: …              # optional, only with status closed

Ids are `R<n>` (no leading zero), unique; a name is one line of at most 40 characters; a goal is
required; at most one point is `current`. The plane takes no YAML dependency: each entry is read with
the ADR frontmatter reader (`ccp.adr.parse`: plain, quoted, `|-` blocks), and a line it cannot read
is a `ccp docs check` failure.

**Strict ids, once the register exists.** With the register, a review point is `R<n>` and one of its
ids, and `task_log.review_point_pattern` is ignored (with a warning). Without it nothing changes from
before the register: the pattern rule holds, and each checking command warns once that there is no
register. `ccp tasks check` (and so `ccp docs check` and the verifier's gate), `ccp tasks close`'s stamp,
the backfill and `team.sh runner spawn` all ask `problem()`.

**Tag and migrate write the working tree only** (as the backfill, §22.6): every other byte of a task
file is kept (CRLF too), a target file with uncommitted changes is refused, `ccp tasks check` runs
before and after, nothing is committed, and the exact `git commit` is printed for the lead. Migrate
also moves the queue's work.json off the old name (through the queue's writers)
and records the rename in the ledger, so the backfill reads the old name in history as the new one.
The ledger itself and the product log are history: listed, never rewritten.
"""
from __future__ import annotations

import json
import re
import shlex
from datetime import date
from pathlib import Path
from typing import Any

from ccp import refs
from ccp.config import Config

ID_RE = refs.DEFAULT.review_point_re  # the default; a product may set ids.review_point (refs.py)
TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")  # a legacy value `migrate --from` accepts
STATUSES = ("planned", "current", "closed")
KEYS = ("id", "name", "goal", "status", "opened", "closed")
NAME_MAX = 40
OPEN = ("pending", "in_progress", "blocked")
ITEM_RE = re.compile(r"^(\s*)- (.*)$")


class RegisterError(Exception):
    """A command cannot act on the register: the message says why, `code` is the exit code."""

    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


def path(cfg: Config) -> Path:
    return cfg.root / ((cfg.review_points or {}).get("file") or "docs/delivery/review-points.yaml")


def number(rp: Any, ids: refs.Ids = refs.DEFAULT) -> int | None:
    return ids.review_point_number(rp)


def sort_key(rp: Any, ids: refs.Ids = refs.DEFAULT) -> tuple[int, int, str]:
    n = number(rp, ids)
    return (0, n, "") if n is not None else (1, 0, str(rp))


# ---------------------------------------------------------------- reading

def parse(text: str) -> list[dict[str, Any]]:
    """A YAML list of mappings, top level or under `review_points:`. Each item's lines are read by
    the ADR frontmatter reader, so the scalars it knows are the ones allowed here."""
    from ccp.adr import ParseError, parse as parse_map  # noqa: PLC0415

    lines = text.replace("\r\n", "\n").split("\n")
    i, ind = 0, None
    while i < len(lines):
        ln = lines[i]
        if not ln.strip() or ln.lstrip().startswith("#"):
            i += 1
            continue
        if ln.rstrip() in ("review_points:", "review_points: []") and ind is None:
            if ln.rstrip().endswith("[]"):
                rest = [x for x in lines[i + 1:] if x.strip() and not x.lstrip().startswith("#")]
                if rest:
                    raise ParseError(f"line {i + 2}: nothing may follow `review_points: []`")
                return []
            i += 1
            continue
        m = ITEM_RE.match(ln)
        if not m:
            raise ParseError(f"line {i + 1} is not a list item (`- id: R<n>`): {ln[:60]!r}")
        ind = len(m.group(1))
        break
    items: list[list[str]] = []
    start_line: list[int] = []
    while i < len(lines):
        ln = lines[i]
        m = ITEM_RE.match(ln)
        if m and len(m.group(1)) == ind:
            items.append([" " * (ind + 2) + m.group(2)])
            start_line.append(i + 1)
        elif not ln.strip() or ln.lstrip().startswith("#"):
            if items:
                items[-1].append("")
        elif len(ln) - len(ln.lstrip(" ")) >= ind + 2 and items:
            items[-1].append(ln)
        else:
            raise ParseError(f"line {i + 1} is outside a list item: {ln[:60]!r}")
        i += 1
    out = []
    for body, at in zip(items, start_line):
        cut = ind + 2
        try:
            meta = parse_map("\n".join(x[cut:] if x.strip() else "" for x in body) + "\n")
        except ParseError as e:
            raise ParseError(f"the item at line {at}: {e}") from None
        meta["_line"] = at
        out.append(meta)
    return out


def validate(entries: list[dict[str, Any]], rel: str, ids: refs.Ids = refs.DEFAULT) -> list[str]:
    errs: list[str] = []
    seen: dict[str, int] = {}
    current = []
    for e in entries:
        where = f"{rel}:{e.get('_line', '?')}"
        unknown = sorted(set(k for k in e if not k.startswith("_")) - set(KEYS))
        if unknown:
            errs.append(f"{where}: unknown key(s) {', '.join(unknown)} (the keys are {', '.join(KEYS)})")
        rid = e.get("id")
        if not isinstance(rid, str) or not ids.is_review_point(rid):
            errs.append(f"{where}: id {rid!r} is not {ids.review_point_shape}; SPEC §22)")
        elif rid in seen:
            errs.append(f"{where}: id {rid} is also at line {seen[rid]}")
        else:
            seen[rid] = e.get("_line", 0)
        name = e.get("name")
        if not isinstance(name, str) or not name.strip():
            errs.append(f"{where}: {rid or '?'} has no name")
        elif "\n" in name or len(name) > NAME_MAX:
            errs.append(f"{where}: {rid}'s name is {len(name)} characters or several lines; a name is one short "
                        f"line (at most {NAME_MAX}), like \"pre-beta\": the goal says the rest")
        if not isinstance(e.get("goal"), str) or not e["goal"].strip():
            errs.append(f"{where}: {rid or '?'} has no goal (what the point's scope is trying to achieve)")
        st = e.get("status")
        if st not in STATUSES:
            errs.append(f"{where}: {rid or '?'}'s status {st!r} is not one of {', '.join(STATUSES)}")
        elif st == "current":
            current.append(str(rid))
        days = {}
        for k in ("opened", "closed"):
            if k in e:
                try:
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(e[k])):
                        raise ValueError
                    days[k] = date.fromisoformat(str(e[k]))
                except ValueError:
                    errs.append(f"{where}: {rid or '?'}'s {k} {e[k]!r} is not a date (YYYY-MM-DD)")
        if "closed" in e and st != "closed":
            errs.append(f"{where}: {rid or '?'} has a closed date but its status is {st!r}")
        if len(days) == 2 and days["closed"] < days["opened"]:
            errs.append(f"{where}: {rid or '?'} closes before it opens")
    if len(current) > 1:
        errs.append(f"{rel}: {len(current)} review points are current ({', '.join(current)}); at most one is")
    return errs


def load(cfg: Config) -> tuple[list[dict[str, Any]] | None, list[str]]:
    """(entries, problems). Entries is None when the product keeps no register (then a review point
    need only be R<n>), and [] when the file cannot be read (every point is then unknown)."""
    from ccp.adr import ParseError  # noqa: PLC0415

    p = path(cfg)
    if not p.is_file():
        return None, []
    rel = cfg.rel(p)
    try:
        entries = parse(p.read_text(errors="replace"))
    except ParseError as e:
        return [], [f"{rel}: {e}"]
    return entries, validate(entries, rel, refs.ids(cfg))


def known(entries: list[dict[str, Any]] | None, ids: refs.Ids = refs.DEFAULT) -> set[str] | None:
    return None if entries is None else {str(e.get("id")) for e in entries if ids.is_review_point(e.get("id"))}


def problem(cfg: Config, rp: Any, entries: Any = ...) -> str | None:
    """Why `rp` is not a review point this product accepts, or None. With a register (§22): strict
    `R<n>`, one of its ids. Without one, the rule before the register, unchanged: a plain token
    matching `task_log.review_point_pattern` (§22.1). `entries` is load()'s, when the caller has it."""
    entries = load(cfg)[0] if entries is ... else entries
    if entries is None:
        pat = cfg.task_log["review_point_pattern"]
        if not isinstance(rp, str) or not re.match(pat, rp) or not TOKEN_RE.match(rp):
            return f"review point {rp!r} does not match task_log.review_point_pattern ({pat}, SPEC §22.1)"
        return None
    ids = refs.ids(cfg)
    if not isinstance(rp, str) or not ids.is_review_point(rp):
        return f"review point {rp!r} is not {ids.review_point_shape}; SPEC §22.1, §22.7)"
    if rp not in (known(entries, ids) or set()):
        return (f"review point {rp} is not in the register {cfg.rel(path(cfg))}: add it there first, with a "
                "name and a goal (SPEC §22)")
    return None


def notes(cfg: Config, entries: Any = ...) -> list[str]:
    """The one warning a command prints about the register: none yet while tasks carry review points
    (they then follow the old pattern rule), or an ignored `review_point_pattern` beside it."""
    entries = load(cfg)[0] if entries is ... else entries
    if entries is None:
        try:  # a product that uses no review point hears nothing about a register
            from ccp import tasklog  # noqa: PLC0415
            if not any("review_point" in t for t in tasklog.load(cfg)):
                return []
        except Exception:  # noqa: BLE001  (an unreadable log: the check itself says so)
            return []
        return [f"no review-point register: {cfg.rel(path(cfg))}; review points are unchecked — create it (SPEC §22.1)"]
    if cfg.review_point_pattern_set:
        return [f"docs/delivery/plane.json: task_log.review_point_pattern is ignored now that the review-point "
                f"register {cfg.rel(path(cfg))} exists: review points are R<number> in it (SPEC §22); "
                "remove the key"]
    return []


def current(entries: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    return next((e for e in entries or [] if e.get("status") == "current"), None)


def public(e: dict[str, Any]) -> dict[str, Any]:
    return {k: e.get(k) for k in KEYS}


# ---------------------------------------------------------------- progress

def summary(rows: list[dict[str, Any]], work: dict[str, Any], entries: list[dict[str, Any]] | None,
            in_scope=None, ids: refs.Ids = refs.DEFAULT) -> list[dict[str, Any]]:
    """Per review point, in number order: the register's entry (name, goal, status, dates) and its
    tasks: done, open (pending / in progress / blocked), dropped. `rows` need task_id, status,
    review_point and done_at. The runner's point (work.json) also counts the tasks of its scope that
    carry no point yet (`unstamped`). `current` is the register's current point; without one in the
    register, the runner's."""
    runner = str(work.get("review_point") or "") or None
    scope = [str(s) for s in work.get("scope") or []]
    reg = {str(e.get("id")): e for e in entries or [] if e.get("id")}
    cur = (current(entries) or {}).get("id") or (runner if not entries else None)
    groups: dict[str, dict[str, Any]] = {}

    def group(rp: str) -> dict[str, Any]:
        if rp not in groups:
            e = reg.get(rp) or {}
            groups[rp] = {"id": rp, "name": e.get("name"), "goal": e.get("goal"), "status": e.get("status"),
                          "opened": e.get("opened"), "closed": e.get("closed"), "in_register": rp in reg,
                          "current": rp == cur, "runner": rp == runner, "tasks": 0, "done": 0, "remaining": 0,
                          "open": {"pending": 0, "in_progress": 0, "blocked": 0}, "dropped": 0, "unstamped": 0,
                          "first_done_at": None, "last_done_at": None, "ids": [], "open_ids": []}
        return groups[rp]

    for rp in reg:
        group(rp)
    for r in rows:
        rp = r.get("review_point") or (runner if runner and scope and in_scope and in_scope(r["task_id"], scope) else None)
        if not rp:
            continue
        g = group(str(rp))
        if r["status"] == "dropped":
            g["dropped"] += 1
            continue
        g["tasks"] += 1
        g["ids"].append(r["task_id"])
        g["unstamped"] += 0 if r.get("review_point") else 1
        if r["status"] == "done":
            g["done"] += 1
            d = r.get("done_at")
            if d:
                g["first_done_at"] = min(filter(None, [g["first_done_at"], d]))
                g["last_done_at"] = max(filter(None, [g["last_done_at"], d]))
        else:
            g["remaining"] += 1
            if r["status"] in g["open"]:
                g["open"][r["status"]] += 1
            g["open_ids"].append(r["task_id"])
    for rp in (runner, cur):
        if rp:
            group(rp)
    out = sorted(groups.values(), key=lambda g: sort_key(g["id"], ids))
    for g in out:
        g["ids"] = g["ids"][:200]
        g["open_ids"] = g["open_ids"][:200]
    return out


def task_rows(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The few fields summary() needs, straight from the task files (the CLI's view; the board's rows
    carry the queue's done times too)."""
    return [{"task_id": str(t.get("task_id") or t["_file"].stem), "status": t.get("status"),
             "review_point": t.get("review_point") or None, "title": t.get("title"),
             "done_at": (str(t.get("updated")) if t.get("status") == "done" and t.get("updated") else None)}
            for t in tasks]


# ---------------------------------------------------------------- task-file edits

def retag(text: str, old: str, new: str) -> str | None:
    """`text` with the frontmatter's `review_point: <old>` line saying <new>, every other byte kept
    (quotes, a trailing comment, the line ending). None when the frontmatter has no such line."""
    nl = "\r\n" if text.startswith("---\r\n") else "\n"
    if not text.startswith(f"---{nl}"):
        return None
    end = text.find(f"{nl}---{nl}", 3)
    if end == -1:
        return None
    head = text[:end]
    rx = re.compile(r"^(review_point:[ \t]*)([\"']?)" + re.escape(old) + r"\2([ \t]*(?:#[^\r\n]*)?)(?=\r?$)", re.M)
    new_head, n = rx.subn(lambda m: m.group(1) + m.group(2) + new + m.group(2) + m.group(3), head, count=1)
    return new_head + text[end:] if n else None


def _read(p: Path) -> str:
    with p.open(newline="") as fh:  # no newline translation: a CRLF file stays CRLF
        return fh.read()


def _write(p: Path, text: str) -> None:
    with p.open("w", newline="") as fh:
        fh.write(text)


def _commit_cmd(cfg: Config, msg: str, files: list[str]) -> str | None:
    if not files:
        return None
    return (f"git -C {shlex.quote(str(cfg.root))} commit -m {shlex.quote(msg)} -- "
            + " ".join(shlex.quote(f) for f in files))


def _guard_dirty(cfg: Config, files: list[str]) -> None:
    from ccp.lifecycle import _changed  # noqa: PLC0415
    dirty = set(_changed(cfg.root))
    busy = [f for f in files if f in dirty]
    if busy:
        raise RegisterError("these task files have uncommitted changes; commit or discard them first, so this "
                            "diff is its own:\n  " + "\n  ".join(busy), 2)


def _need_register(cfg: Config, rp: str, what: str) -> list[dict[str, Any]]:
    entries, errs = load(cfg)
    if entries is None:
        raise RegisterError(f"{what}: there is no review-point register ({cfg.rel(path(cfg))}); write it first, "
                            "with each point's name and goal from the product's plan (SPEC §22)", 2)
    if errs:
        raise RegisterError(f"{what}: the register has problems; fix them first:\n  " + "\n  ".join(errs), 2)
    why = problem(cfg, rp, entries)
    if why:
        raise RegisterError(f"{what}: {why}", 2)
    return entries


def tag(cfg: Config, rp: str, ids: list[str], from_work: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Attach tasks to a review point at planning time (§22.4): `review_point: R` as the
    frontmatter's last line of each named task that has none. A task already on another point is
    refused (re-planning it is an edit the lead makes on purpose, or `migrate`)."""
    from ccp import tasklog  # noqa: PLC0415
    from ccp.lifecycle import stamp_review_point  # noqa: PLC0415

    _need_register(cfg, rp, "tag")
    if from_work:
        from ccp.queue import load_work, root  # noqa: PLC0415
        ids = list(ids) + [str(x) for x in load_work(root()).get("scope") or []]
    if not ids:
        raise RegisterError("tag: name the tasks (ids or NNNN), or --from-work for work.json's scope", 2)
    tasks = tasklog.load(cfg)
    rows, missing = [], []
    for want in dict.fromkeys(ids):
        t = next((x for x in tasks if tasklog.in_scope(str(x.get("task_id") or x["_file"].stem), [want])), None)
        if t is None:
            missing.append(want)
            continue
        tid = str(t.get("task_id") or t["_file"].stem)
        have = t.get("review_point")
        action = "already" if have == rp else ("refused" if have else "tag")
        rows.append({"task_id": tid, "file": cfg.rel(t["_file"]), "status": t.get("status"), "action": action,
                     **({"has": have} if have and have != rp else {})})
    if missing:
        raise RegisterError("tag: no task " + ", ".join(missing), 2)
    refused = [r for r in rows if r["action"] == "refused"]
    if refused:
        raise RegisterError("tag: these tasks are on another review point already: "
                            + ", ".join(f"{r['task_id']} ({r['has']})" for r in refused)
                            + ". Move them by hand on purpose, or with `ccp review-points migrate`", 2)
    targets = [r for r in rows if r["action"] == "tag"]
    body: dict[str, Any] = {"review_point": rp, "dry_run": dry_run, "tasks": rows, "written": [], "warnings": []}
    if dry_run or not targets:
        return body
    _guard_dirty(cfg, [r["file"] for r in targets])
    before = set(tasklog.check(cfg))
    for r in targets:
        p = cfg.root / r["file"]
        new = stamp_review_point(_read(p), rp)
        if new is None:
            body["warnings"].append(f"{r['file']}: no frontmatter block to tag")
            r["action"] = "skipped"
            continue
        _write(p, new)
        body["written"].append(r["file"])
    body["warnings"] += [e for e in tasklog.check(cfg) if e not in before]
    body["commit"] = _commit_cmd(cfg, f"Task log: {len(body['written'])} task(s) attached to review point {rp} "
                                      "(ccp review-points tag)", body["written"])
    return body


def _ledger(q: Path, old: str, new: str) -> dict[str, Any]:
    from ccp.backfill import _events  # noqa: PLC0415
    all_events = _events(q)
    evs = [e for e in all_events if e.get("type") == "runner" and e["payload"].get("review_point") == old]
    return {"events": len(evs), "first": evs[0]["at"] if evs else None, "last": evs[-1]["at"] if evs else None,
            "renamed": renames(all_events).get(old) == new}


def _log_mentions(cfg: Config, old: str) -> dict[str, Any] | None:
    log = cfg.reconcile["log"] if cfg.reconcile else None
    if not log:
        return None
    from ccp.backfill import log_points  # noqa: PLC0415
    n = sum(1 for pts in log_points(cfg).values() if old in pts)
    return {"path": log["path"], "tasks": n}


def migrate(cfg: Config, old: str, new: str, dry_run: bool = False, merge: bool = False) -> dict[str, Any]:
    """Rename a review point the product used before the register (e.g. `PM`) to its `R<n>`: the
    task files' `review_point`, and the queue's work.json when QUEUE_ROOT is set. Idempotent: a second
    run finds nothing to change."""
    from ccp import tasklog  # noqa: PLC0415

    if not TOKEN_RE.match(old or ""):
        raise RegisterError(f"migrate: --from {old!r} is not a review-point token", 2)
    if old == new:
        raise RegisterError("migrate: --from and --to are the same", 2)
    _need_register(cfg, new, "migrate")
    tasks = tasklog.load(cfg)
    olds = [t for t in tasks if t.get("review_point") == old]
    used = [str(t.get("task_id")) for t in tasks if t.get("review_point") == new]
    if olds and used and not merge:
        raise RegisterError(f"migrate: {len(used)} task(s) already carry {new} ({', '.join(used[:8])}"
                            f"{', …' if len(used) > 8 else ''}); renaming {old} into it would merge two points. "
                            "Run the migration before tagging new tasks, or pass --merge when merging is meant", 2)
    rows = [{"task_id": str(t.get("task_id")), "file": cfg.rel(t["_file"]), "status": t.get("status")} for t in olds]
    body: dict[str, Any] = {"from": old, "to": new, "dry_run": dry_run, "tasks": rows, "written": [],
                            "queue": None, "product_log": _log_mentions(cfg, old), "warnings": []}
    body["warnings"] += notes(cfg)
    import os  # noqa: PLC0415
    q = Path(os.environ["QUEUE_ROOT"]) if os.environ.get("QUEUE_ROOT") and Path(os.environ["QUEUE_ROOT"]).is_dir() else None
    if q is not None:
        from ccp.queue import load_work  # noqa: PLC0415
        w = load_work(q)
        body["queue"] = {"path": str(q), "work_json": {"review_point": w.get("review_point"),
                                                         "change": w.get("review_point") == old},
                         "ledger": _ledger(q, old, new), "board": "board/board.json follows at the next build"}
    else:
        body["warnings"].append("QUEUE_ROOT is not set: the queue's work.json is not read or changed")
    if dry_run:
        return body
    if rows:
        _guard_dirty(cfg, [r["file"] for r in rows])
        before = set(tasklog.check(cfg))
        for r in rows:
            p = cfg.root / r["file"]
            new_text = retag(_read(p), old, new)
            if new_text is None:
                body["warnings"].append(f"{r['file']}: no `review_point: {old}` line in its frontmatter")
                continue
            _write(p, new_text)
            body["written"].append(r["file"])
        after = tasklog.check(cfg)
        body["warnings"] += [e for e in after if e not in before]
        body["commit"] = _commit_cmd(cfg, f"Task log: review point {old} is {new} (ccp review-points migrate)",
                                     body["written"])
    qb = body["queue"]
    if q is not None and (qb["work_json"]["change"] or (qb["ledger"]["events"] and not qb["ledger"]["renamed"])):
        from ccp.queue import emit, save_work  # noqa: PLC0415
        # One rename event: a re-run that finds it already recorded adds none.
        if not qb["ledger"]["renamed"]:
            emit(q, cfg, "", "runner", "set", {"field": "review_point", "from": old, "to": new,
                                               "why": "ccp review-points migrate (SPEC §22)"}, who="design-seat")
        if qb["work_json"]["change"]:
            save_work(q, {"review_point": new})
        qb["written"] = ["work.json"] if qb["work_json"]["change"] else []
        qb["event"] = None if qb["ledger"]["renamed"] else "runner/set review_point"
    return body


def renames(events: list[dict[str, Any]]) -> dict[str, str]:
    """old -> new, from the ledger's `runner`/`set` review-point renames (migrate's), chained."""
    out: dict[str, str] = {}
    for e in events:
        p = e.get("payload") or {}
        if e.get("type") == "runner" and e.get("op") == "set" and p.get("field") == "review_point" \
                and isinstance(p.get("from"), str) and isinstance(p.get("to"), str):
            out[p["from"]] = p["to"]
            for k, v in list(out.items()):
                if v == p["from"]:
                    out[k] = p["to"]
    return out


def dumps(body: Any) -> str:
    return json.dumps(body, indent=2, ensure_ascii=False, default=str)
