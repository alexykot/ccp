"""The board's Plan and backlog section (SPEC §28.3 priority 5, §22): `board.json`'s `plan`.

  tasks          every task with the fields §5.7 sends here instead of INDEX.yaml: kind, adr_refs,
                 spec_refs, review_point, pr, merge_sha, done_at (plus status, title, depends_on, created)
  adrs           the ADR register: status, in force, review points, and built % (done over the tasks
                 citing it), overall and per review point (its citing tasks tagged that point)
  review_points  per review point, in number order: the register's name, goal, status and dates
                 (§22.4), its tasks (done, open by status), first and last done, and the ADRs it builds
  register       the review-point register: its path, problems, the current point and the runner's
  ready          what `ccp tasks next` would pick, in the order it would pick them
  graph          the open tasks and the open dependencies between them
  burnup         per day: tasks in the log (not dropped) and tasks done

Reads only: the task files, the ADR frontmatter, the queue's task records and work.json, and git's
merges. Each part that fails leaves its error under `errors` and the rest still builds.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ccp import adr, health, refs, reviewpoints, selection, tasklog
from ccp.config import Config
from ccp.queue import load_work, read_json

PR_RE = re.compile(r"\(#(\d+)\)\s*$")
NOTE_PR_RE = re.compile(r"\bPR #(\d+)\b")
NOTE_SQUASH_RE = re.compile(r"\bsquash `([0-9a-f]{7,40})`")
OPEN = ("pending", "in_progress", "blocked")
TITLE_MAX = 140
GRAPH_MAX = 150
BURNUP_DAYS = 180


def _day(s: Any) -> str | None:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(s or ""))
    return m.group(1) if m else None


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:200]


def task_rows(cfg: Config, q: Path, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per task. pr, merge_sha and done_at come from the queue's close record, else git's
    merge of the task (its subject's `(#N)`), else the close's verification note; done_at falls back
    to the task file's `updated` date."""
    try:
        merges = {m["task_id"]: m for m in health.merges(cfg, tasks)}
    except Exception:  # noqa: BLE001  (no git: the queue and the notes still give most of it)
        merges = {}
    rows = []
    for t in tasks:
        tid = str(t.get("task_id") or t["_file"].stem)
        st = read_json(q / "tasks" / f"{tid}.json", {}) if q else {}
        st = st if isinstance(st, dict) else {}
        m = merges.get(tid) or {}
        notes = tasklog._section(t["_text"], tasklog.SEC_VERIFY) or ""
        pr = st.get("pr") or (PR_RE.search(m.get("subject") or "") or [None, None])[1] \
            or (NOTE_PR_RE.search(notes) or [None, None])[1]
        sha = st.get("merge_sha") or m.get("sha") or (NOTE_SQUASH_RE.search(notes) or [None, None])[1]
        done = t.get("status") == "done"
        done_at = None
        if done:
            done_at = st.get("merged_at") or (datetime.fromtimestamp(m["at"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                                              if m.get("at") else None) or _day(t.get("updated"))
        rows.append({"task_id": tid, "title": str(t.get("title") or "")[:TITLE_MAX], "status": t.get("status"),
                     "kind": tasklog.kind_of(t),
                     # an open task's dependencies (the graph's); a closed one's are in INDEX.yaml and its file
                     "depends_on": tasklog._as_list(t.get("depends_on")) if t.get("status") in OPEN else [],
                     "adr_refs": tasklog._as_list(t.get("adr_refs")), "spec_refs": tasklog._as_list(t.get("spec_refs")),
                     "review_point": t.get("review_point") or None, "pr": str(pr) if pr else None,
                     "merge_sha": str(sha)[:12] if sha else None, "done_at": done_at, "created": _day(t.get("created"))})
    return rows


def adr_register(cfg: Config, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """With the `adr` block, every ADR's frontmatter; without it, the ADRs tasks cite, by number only.
    Built % comes from the ADR's recorded decision states (built or live over those not retired, SPEC
    §6) when it records any; otherwise it is done over the tasks that cite the ADR in `adr_refs`,
    dropped ones left out."""
    cites: dict[int, list[dict[str, Any]]] = {}
    for t in tasks:
        if t.get("status") == "dropped":
            continue
        for n in dict.fromkeys(tasklog.adr_number(r, cfg) for r in tasklog._as_list(t.get("adr_refs"))):
            if n is not None:
                cites.setdefault(n, []).append(t)
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if cfg.adr is not None:
        metas, errors = adr.load(cfg)
        by_sup: dict[str, list[str]] = {}
        for m in metas:
            for sb in adr._as_list(m.get("superseded_by")):
                by_sup.setdefault(sb.split()[0], []).append(str(m.get("id")))
        for m in metas:
            items.append({"id": m.get("id") or refs.ids(cfg).adr_id(m["_number"]), "number": m["_number"],
                          "title": str(m.get("title") or "")[:TITLE_MAX], "status": m.get("status"),
                          "date": m.get("date"), "superseded_by": ", ".join(adr._as_list(m.get("superseded_by"))) or None,
                          "supersedes": by_sup.get(str(m.get("id")), []), "archived": bool(m.get("_archived")),
                          "in_force": re.sub(r"\s+", " ", str(m.get("in_force") or ""))[:240] or None,
                          "review_points": [str(x) for x in m.get("review_points") or []
                                            if isinstance(m.get("review_points"), list)][:20],
                          "decisions": [{"id": f"D{d['id']}", "state": d["state"], "by": d["by"]}
                                        for d in adr.decision_states(m)][:40],
                          "_built": adr.built(m),
                          "path": m["_path"]})
    known = {i["number"] for i in items}
    items += [{"id": refs.ids(cfg).adr_id(n), "number": n, "title": None, "status": None, "date": None, "superseded_by": None,
               "supersedes": [], "archived": False, "in_force": None, "path": None} for n in sorted(cites) if n not in known]
    for i in items:
        ts = cites.get(i["number"], [])
        done = [t for t in ts if t.get("status") == "done"]
        i.update(tasks=len(ts), done=len(done), built_pct=round(100 * len(done) / len(ts)) if ts else None,
                 built_from="tasks" if ts else None,
                 open=[str(t.get("task_id")) for t in ts if t.get("status") in OPEN][:20])
        b = i.pop("_built", None)
        if b is not None:   # §6: the ADR's own record of its decisions wins over the task-derived figure
            i.update(built_pct=round(100 * b[0] / b[1]) if b[1] else None, built_from="decisions",
                     built_decisions=b[0], standing_decisions=b[1])
        i.setdefault("decisions", [])
        i.setdefault("review_points", [])
        # §22: built % per review point, over the citing tasks tagged that point.
        per: dict[str, list[dict[str, Any]]] = {}
        for t in ts:
            if t.get("review_point"):
                per.setdefault(str(t["review_point"]), []).append(t)
        i["by_point"] = {rp: {"tasks": len(v), "done": sum(t.get("status") == "done" for t in v),
                              "built_pct": round(100 * sum(t.get("status") == "done" for t in v) / len(v))}
                         for rp, v in sorted(per.items(), key=lambda kv: reviewpoints.sort_key(kv[0], refs.ids(cfg)))}
    items.sort(key=lambda i: i["number"])
    return {"enabled": cfg.adr is not None, "dir": (cfg.adr or {}).get("dir"), "items": items, "errors": errors[:30]}


def review_points(rows: list[dict[str, Any]], work: dict[str, Any],
                  entries: list[dict[str, Any]] | None = None, ids: refs.Ids = refs.DEFAULT) -> list[dict[str, Any]]:
    """Per review point (ccp/reviewpoints.py `summary`): the register's entry and the tasks tagged
    with it. The runner's point (work.json) also counts the tasks of its scope that do not carry it
    yet (`close` stamps them, §22), as `unstamped`."""
    return reviewpoints.summary(rows, work, entries, tasklog.in_scope, ids)


def attach_adrs(groups: list[dict[str, Any]], adrs: dict[str, Any] | None) -> None:
    """Each point's ADRs: the ones whose frontmatter names it, and the ones its tasks cite, with
    built % in that point and overall."""
    items = (adrs or {}).get("items") or []
    for g in groups:
        g["adrs"] = [{"id": i["id"], "title": i.get("title"), "status": i.get("status"),
                      "named": g["id"] in (i.get("review_points") or []),
                      "point": (i.get("by_point") or {}).get(g["id"]), "built_pct": i.get("built_pct")}
                     for i in items if g["id"] in (i.get("review_points") or []) or g["id"] in (i.get("by_point") or {})][:40]


def ready_queue(cfg: Config, q: Path, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """The ready tasks in `ccp tasks next`'s order, from the selection the command itself runs
    (`selection.pick`, `tasklog.ranked`). `next` is what the command returns now (`parallel.next_choice`):
    row 0 without parallel, which may be a task already in flight (its file still says pending: the
    command would resume it); with it (§16.3), the head of the line when it may join what the runner
    holds, else none, and `slots_full` says why. `in_flight` lists work.json's tasks in flight."""
    from ccp import parallel  # noqa: PLC0415
    sel = selection.pick(cfg, q, None, tasks)
    flight = sel["in_flight"]
    choice = parallel.next_choice(cfg, q, sel)  # §16.3: the same answer `ccp tasks next` gives
    rows = [{"task_id": str(t.get("task_id")), "title": str(t.get("title") or "")[:TITLE_MAX],
             "kind": tasklog.kind_of(t), "why": why or "the lowest ready number",
             "review_point": t.get("review_point") or None,
             "in_flight": str(t.get("task_id")) in flight} for t, why in sel["ranked"]]
    return {"scope": sel["scope"], "scope_size": len(sel["scope"]) if sel["scope"] else None, "items": rows,
            "next": str(choice["pick"][0].get("task_id")) if choice["pick"] else None,
            "slots_full": choice["slots_full"], "in_flight": flight, "preferred": sel["preferred"]}


def _depths(deps: dict[str, list[str]]) -> dict[str, int]:
    """Each task's longest chain of the given dependencies under it (0: none). A dependency may have a
    higher number than its dependant (§5), so this walks the graph rather than the file order; a cycle
    (which `ccp tasks check` refuses) is cut where the walk meets it again."""
    depth: dict[str, int] = {}
    for root in deps:
        stack, on_path = [(root, iter(deps[root]))], {root}
        while stack:
            tid, it = stack[-1]
            d = next(it, None)
            if d is None:
                stack.pop()
                on_path.discard(tid)
                depth[tid] = 1 + max((depth.get(x, 0) for x in deps[tid] if x in depth), default=-1)
            elif d in deps and d not in depth and d not in on_path:
                stack.append((d, iter(deps[d])))
                on_path.add(d)
    return depth


def graph(rows: list[dict[str, Any]], ready_ids: set[str], flight: set[str] | None = None,
          scope: list[str] | None = None) -> dict[str, Any]:
    """Open tasks as nodes (with their depth: the longest chain of open dependencies under them) and
    the open dependencies as edges. Done dependencies are counted, not drawn."""
    status = {r["task_id"]: r["status"] for r in rows}
    open_rows = [r for r in rows if r["status"] in OPEN]
    open_deps = {r["task_id"]: [d for d in r["depends_on"] if status.get(d) in OPEN] for r in open_rows}
    depth = _depths(open_deps)
    nodes, edges = [], []
    for r in open_rows:
        deps = open_deps[r["task_id"]]
        nodes.append({"id": r["task_id"], "title": r["title"], "status": r["status"], "kind": r["kind"],
                      "ready": r["task_id"] in ready_ids, "in_flight": r["task_id"] in (flight or set()),
                      "in_scope": tasklog.in_scope(r["task_id"], scope),
                      "depth": depth[r["task_id"]],
                      "review_point": r["review_point"], "waiting_on": deps,
                      "done_deps": sum(1 for d in r["depends_on"] if status.get(d) == "done")})
        edges += [[d, r["task_id"]] for d in deps]
    cut = len(nodes) > GRAPH_MAX
    if cut:
        keep = {n["id"] for n in nodes[:GRAPH_MAX]}
        nodes = nodes[:GRAPH_MAX]
        edges = [e for e in edges if e[0] in keep and e[1] in keep]
    return {"nodes": nodes, "edges": edges, "truncated": cut, "open": len(open_rows)}


def burnup(rows: list[dict[str, Any]], today: str) -> list[dict[str, Any]]:
    """Per day, from the first task's `created` (at most BURNUP_DAYS back): tasks in the log that are not
    dropped (a task with no `created` counts from the start) and tasks done by then (`done_at`)."""
    live = [r for r in rows if r["status"] != "dropped"]
    days = [d for d in ([r["created"] for r in live] + [_day(r["done_at"]) for r in live]) if d]
    if not days:
        return []
    try:
        end = date.fromisoformat(today)
        start = max(date.fromisoformat(min(days)), end - timedelta(days=BURNUP_DAYS - 1))
    except ValueError:
        return []
    # A task is in the log from its `created`, or from its done day if that is earlier (a backdated file).
    created = sorted(min(filter(None, [r["created"] or "0000-00-00", _day(r["done_at"])])) for r in live)
    finished = sorted(d for d in (_day(r["done_at"]) for r in live) if d)
    out, i, j = [], 0, 0
    d = start
    while d <= end:
        s = d.isoformat()
        while i < len(created) and created[i] <= s:
            i += 1
        while j < len(finished) and finished[j] <= s:
            j += 1
        out.append({"date": s, "total": i, "done": j})
        d += timedelta(days=1)
    return out


def collect(cfg: Config, q: Path, work: dict[str, Any] | None = None, today: str | None = None) -> dict[str, Any]:
    work = work if work is not None else load_work(q)
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    errors: dict[str, str] = {}
    out: dict[str, Any] = {"tasks": [], "counts": {}, "adrs": None, "review_points": [], "register": None,
                           "ready": None, "graph": None, "burnup": [], "errors": errors}
    try:
        tasks = tasklog.load(cfg)
        rows = task_rows(cfg, q, tasks)
    except Exception as e:  # noqa: BLE001  (an unreadable task log: nothing below can stand)
        errors["tasks"] = _err(e)
        return out
    out["tasks"] = rows
    counts: dict[str, int] = {}
    for r in rows:
        counts[str(r["status"])] = counts.get(str(r["status"]), 0) + 1
    out["counts"] = counts
    entries: list[dict[str, Any]] | None = None
    try:
        entries, reg_errs = reviewpoints.load(cfg)
        cur = reviewpoints.current(entries)
        runner = str(work.get("review_point") or "") or None
        mismatch = None
        if entries is not None and runner and (problem := reviewpoints.problem(cfg, runner, entries)):
            mismatch = f"the runner's point: {problem}"
        elif cur and runner and runner != cur.get("id"):
            mismatch = f"the runner works on {runner}; the register's current point is {cur.get('id')}"
        out["register"] = {"path": cfg.rel(reviewpoints.path(cfg)), "exists": entries is not None,
                           "errors": reg_errs[:30], "current": cur.get("id") if cur else None,
                           "runner": runner, "mismatch": mismatch}
    except Exception as e:  # noqa: BLE001
        errors["register"] = _err(e)
    for key, fn in (("adrs", lambda: adr_register(cfg, tasks)), ("review_points", lambda: review_points(rows, work, entries, refs.ids(cfg))),
                    ("ready", lambda: ready_queue(cfg, q, tasks)), ("burnup", lambda: burnup(rows, today))):
        try:
            out[key] = fn()
        except Exception as e:  # noqa: BLE001
            errors[key] = _err(e)
    try:
        attach_adrs(out["review_points"], out["adrs"])
    except Exception as e:  # noqa: BLE001
        errors["review_points"] = _err(e)
    try:
        rq = out["ready"] or {}
        out["graph"] = graph(rows, {r["task_id"] for r in rq.get("items") or []}, set(rq.get("in_flight") or []), rq.get("scope"))
    except Exception as e:  # noqa: BLE001
        errors["graph"] = _err(e)
    return out


def status_lines(p: dict[str, Any] | None) -> list[str]:
    """`ccp board status`: one line for the plan."""
    if not p:
        return []
    c = p.get("counts") or {}
    live = sum(v for k, v in c.items() if k != "dropped")
    ready = (p.get("ready") or {}).get("items") or []
    cur = next((g for g in p.get("review_points") or [] if g.get("current")), None)
    waiting = [r for r in ready if not r.get("in_flight")]
    line = f"plan: {c.get('done', 0)}/{live} tasks done, {len(waiting)} ready" + (
        f" (next pick {ready[0]['task_id']}{', in flight' if ready[0].get('in_flight') else ''})" if ready else "")
    if cur:
        line += f"; review point {cur['id']}{' ' + cur['name'] if cur.get('name') else ''} {cur['done']}/{cur['tasks']}"
    out = [line]
    reg = p.get("register") or {}
    if reg.get("errors"):
        out.append(f"plan: {len(reg['errors'])} review-point register problem(s) (ccp docs check)")
    if reg.get("mismatch"):
        out.append(f"plan: {reg['mismatch']}")
    for k, e in sorted((p.get("errors") or {}).items()):
        out.append(f"plan {k} failed: {e}")
    if (p.get("adrs") or {}).get("errors"):
        out.append(f"plan: {len(p['adrs']['errors'])} ADR frontmatter problem(s) (ccp docs check)")
    return out
