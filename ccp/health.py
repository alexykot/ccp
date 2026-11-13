"""Delivery measurements (SPEC §27.1): how long each task took, where the time went, what it touched.

Everything comes from data the plane already holds; nothing here is a target or part of a DoD.

- **git:** the task merges on the first-parent history of HEAD (the board reads the integration
  branch's remote ref instead, so a checkout that has not pulled still shows a merge). A merge is a merge commit, or a
  commit whose subject ends in a pull-request number `(#N)` (a squash merge); it names a task when
  its subject starts with the task's NNNN (`Task 0136: …`, `0133: …`) or it merged a `task/NNNN-…`
  branch. Its files and lines are split by the `architect.areas` globs.
- **the queue** (QUEUE_ROOT, optional), from the times it records: a task starts at its first prompt
  audit, lease, phase or progress event (none recorded: no wall time); each phase ends when the next
  is launched (prompt-audit stamps) and verifying ends at the verifier's `checked_at`. Where a phase
  end is not recorded, its `progress/<task>/*-report.md` modification time stands in, and the row
  says so (`times`).
  Report and audit counts give the fix, merge, ruling, review and verify rounds, each kind its own
  count (a merge or ruling round is neither a fix round nor review time); prompt audits give prompt
  sizes.
- **what workers add:** friction notes (`health/notes.jsonl`, `ccp health note`) and numbers
  (`health/metrics.jsonl`, `ccp health record`), both written by the runner from worker reports.
- **suite time** (§27.2, §14.1): `ccp report` files each passing `ccp suite run` of the run it closes
  from `runs/_suites.jsonl`, never from the report's prose. A run in the `full` or `gate` role's lane
  with nothing cached is the suite's size and time (`suite_seconds`, `suite_tests`); one with any
  unit cached is `suite_seconds_warm`, a run in any other lane `suite_seconds_part`, and one that
  cannot be shown cold or warm `suite_seconds_unverified`. Only a run with no suite record falls back
  to its `Suite:` line.
- **gate time** (§14.6): the latest cold run of the gate role's lane, from `runs/_suites.jsonl`, against
  plane.json `gate`'s cut line and shell limit; over the line it is reported with its slowest stage as
  an advisory finding, over the limit as a breach. Warm and unverified runs are not judged. A gate run
  with no end whose elapsed time reached the shell limit, started after the latest gate run that passed
  or failed, is reported as killed at the limit.

- **runner rotation** (§10.2 step 4): the runner slots due for rotation and not rotated, and the ledger's
  rotations against tasks done.

- **uncovered commits** (§10.7, `ccp tasks orphans`): the commits on the integration branch's
  first-parent history since a ref that no task covers: not a task's merge (the rule above, a squash
  naming its task only as `Task NNNN: …`, the form the implementer is asked for), not a
  reconcile commit naming a task, not named in a task's `covers:`, and changing more than the task log.

A task's **active time** is its wall time less the time it waited (`waits_s`): every `waiting_on`
interval, set to clear, whatever it waited on (§23.3's waits; an open one runs to the merge), and its
suite runs' waits on an exclusive lane (§16.6: a `started` row's `wait_s`, a `busy` row's `waited_s`
in `runs/_suites.jsonl`), each instant counted once and only inside the task's wall time. The trend
is the median active time of the last 5 timed tasks against the 10 before them; above
`architect.drift_ratio` is drift, one of the architect's triggers (§19.6), so time spent waiting
never reads as slower work.
"""
from __future__ import annotations

from ccp.queue import events_path as _events_path

import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccp import refs, tasklog
from ccp.config import ARCHITECT_DEFAULTS, Config
from ccp.queue import QueueError
from ccp.rules import budget_failures, glob_re

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "observability"))
from lib import looks_like_secret  # noqa: E402

def _merge_task_re(width: int) -> re.Pattern[str]:
    """A squash subject naming a task by number: `0042 …`, `task 0042 …`."""
    return re.compile(rf"^(?:task\s+)?(\d{{{width}}})(?!\d)", re.I)


def _branch_task_re(width: int) -> re.Pattern[str]:
    return re.compile(rf"\btask/(\d{{{width}}})-")


MERGE_TASK_RE, BRANCH_TASK_RE = _merge_task_re(4), _branch_task_re(4)  # the defaults (refs.py ids.task)
PR_SUFFIX_RE = re.compile(r"\(#\d+\)\s*$")
STAMP_RE = re.compile(r"^(\d{8}T\d{6}Z)_(.*)\.json$")
SUITE_KINDS = ("cold", "warm", "part", "unverified")
COLD_ROLES = ("full", "gate")  # §27.2: runs in these roles' lanes (plane.json suite.roles) can be cold or warm


def cold_lanes(cfg: Config | None) -> tuple[str, ...]:
    from ccp.config import lane_for  # noqa: PLC0415
    return tuple(lane_for(cfg, r) for r in COLD_ROLES)
LAST, BEFORE = 5, 10


def suite_metric(kind: str, what: str = "seconds") -> str:
    """The metric a suite run of this kind is filed under: `suite_seconds` for a cold one, else `suite_seconds_<kind>`."""
    return f"suite_{what}" + ("" if kind == "cold" else f"_{kind}")


BUILTIN_METRICS = tuple(suite_metric(k, w) for k in SUITE_KINDS for w in ("seconds", "tests"))


def _ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(at: str) -> float | None:
    """RFC3339 (`Z` or an offset) or a prompt-audit stamp (`20261014T120000Z`), as epoch seconds."""
    try:
        return datetime.strptime(at, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def _git(root: Path, *a: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _written_task_re(width: int) -> re.Pattern[str]:
    """A squash subject in the form the implement prompt asks for: `Task 0042: …` (§10.7)."""
    return re.compile(rf"^Task (\d{{{width}}}): ")


def merges(cfg: Config, tasks: list[dict[str, Any]] | None = None, rev: str = "HEAD",
           written: bool = False) -> list[dict[str, Any]]:
    """Task merges on the first-parent history of `rev` (HEAD, or a range), oldest first. With
    `written`, a squash names its task only in the form the plane writes (`Task 0042: …`)."""
    tasks = tasks if tasks is not None else tasklog.load(cfg)
    by_num = {refs.ids(cfg).task_number(t.get("task_id")): str(t.get("task_id")) for t in tasks}
    w = refs.ids(cfg).task_width
    merge_re, branch_re = (_written_task_re(w) if written else _merge_task_re(w)), _branch_task_re(w)
    out = []
    for rec in _git(cfg.root, "log", "--first-parent", "--reverse", "--format=%x01%H%x1f%P%x1f%ct%x1f%s%x1f%b",
                    rev).split("\x01")[1:]:
        sha, parents, ct, subject, body = (rec.split("\x1f") + [""] * 5)[:5]
        if len(parents.split()) < 2 and not PR_SUFFIX_RE.search(subject):
            continue
        m = merge_re.match(subject) or branch_re.search(subject + "\n" + body)
        if m and m.group(1) in by_num:
            out.append({"sha": sha, "task_id": by_num[m.group(1)], "at": int(ct), "subject": subject.strip()})
    return out


COVERS_RE = re.compile(r"^[0-9a-f]{7,40}$")  # a `covers:` entry: a commit's sha or a prefix of it (§10.7)


def _covers(tasks: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """The commit prefixes the log's tasks name in `covers:` (a dropped task covers nothing), and the
    entries that are not a sha, as warnings."""
    named, bad = [], []
    for t in tasks:
        for e in tasklog._as_list(t.get("covers")):
            e = str(e).strip()
            if not COVERS_RE.match(e):
                bad.append(f"{t.get('task_id')}: covers {e!r} is not a commit sha (7 to 40 hex digits)")
            elif t.get("status") != "dropped":
                named.append(e)
    return named, bad


def _resolve(cfg: Config, ref: str) -> str | None:
    sha = _git(cfg.root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}").strip()
    return sha or None


def integration_tip(cfg: Config, q: Path | None) -> str:
    """§10.7: `origin/<integration branch>` when that ref is here, else the local branch; the branch is
    the binding's (QUEUE_ROOT), else `main`. Nothing is fetched."""
    from ccp.queue import integration_branch  # noqa: PLC0415
    integ = integration_branch(q) if q else "main"
    return f"origin/{integ}" if _resolve(cfg, f"origin/{integ}") else integ


def uncovered(cfg: Config, since: str, tip: str) -> dict[str, Any]:
    """§10.7: the commits on `tip`'s first-parent history after `since` that no task covers, oldest
    first. Covered: a task's merge (`merges`), a reconcile commit naming a task of the log, a commit a
    task not dropped names in `covers:`, and one that changes nothing outside the task log. Raises
    ValueError for a ref that does not resolve."""
    from ccp.lifecycle import reconcile_re, task_log_paths  # noqa: PLC0415
    for ref in (since, tip):
        if not _resolve(cfg, ref):
            raise ValueError(f"{ref!r} is not a commit here")
    tasks = tasklog.load(cfg)
    rng = f"{since}..{tip}"
    merged = {m["sha"] for m in merges(cfg, tasks, rng, written=True)}
    nums = {refs.ids(cfg).task_number(t.get("task_id")) for t in tasks}
    rec_re = reconcile_re(cfg)
    named, warnings = _covers(tasks)
    log = task_log_paths(cfg)

    def in_log(path: str) -> bool:
        return any(path == x or path.startswith(x.rstrip("/") + "/") for x in log)

    out = []
    for rec in _git(cfg.root, "log", "--first-parent", "-m", "--reverse", "--name-only",
                    "--format=%x01%H%x1f%s%x1f", rng).split("\x01")[1:]:
        sha, subject, files = (rec.split("\x1f") + [""] * 3)[:3]
        if sha in merged or any(sha.startswith(n) for n in named):
            continue
        m = rec_re.match(subject.strip())
        if m and m.group(1) in nums:
            continue
        if all(in_log(f) for f in files.split("\n") if f.strip()):
            continue
        out.append({"sha": sha, "subject": subject.strip()})
    return {"since": since, "tip": tip, "uncovered": out, "warnings": warnings}


def orphans_main(cfg: Config, a: Any) -> int:
    """`ccp tasks orphans --since REF [--json]` (§10.7): exit 0 with nothing listed, 1 with a commit
    listed, 2 for a ref that does not resolve."""
    try:
        r = uncovered(cfg, a.since, integration_tip(cfg, _queue(False)))
    except ValueError as e:
        print(f"ccp tasks orphans: {e}", file=sys.stderr)
        return 2
    for w in r["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        for c in r["uncovered"]:
            print(f"{c['sha'][:7]} {c['subject']}")
        if not r["uncovered"]:
            print(f"no uncovered commits on {r['tip']} since {r['since']}")
    return 1 if r["uncovered"] else 0


def numstat(cfg: Config, shas: set[str], rev: str = "HEAD") -> dict[str, list[tuple[str, int]]]:
    """{merge sha: [(path, lines added + deleted)]}, each against its first parent, on `rev`'s history."""
    out: dict[str, list[tuple[str, int]]] = {}
    cur = None
    for line in _git(cfg.root, "log", "--first-parent", "-m", "--numstat", "--format=%x01%H", rev).splitlines():
        if line.startswith("\x01"):
            cur = line[1:] if line[1:] in shas else None
            if cur:
                out.setdefault(cur, [])
        elif cur and line.strip():
            parts = line.split("\t")
            if len(parts) == 3:
                a, d, p = parts
                out[cur].append((p, (int(a) if a.isdigit() else 0) + (int(d) if d.isdigit() else 0)))
    return out


def _area(path: str, areas: list[tuple[str, list[re.Pattern[str]]]]) -> str:
    for name, pats in areas:
        if any(p.match(path) for p in pats):
            return name
    return "other"


def _jsonl(p: Path) -> list[dict[str, Any]]:
    if not p.is_file():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def notes(q: Path | None, since: str | None = None) -> list[dict[str, Any]]:
    """Friction notes, oldest first; only those after `since` (RFC3339) when given."""
    if q is None:
        return []
    s = _epoch(since) if since else None
    return [n for n in _jsonl(q / "health" / "notes.jsonl") if s is None or (_epoch(n.get("at", "")) or 0) > s]


def _append(p: Path, rec: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _metrics_path(q: Path) -> Path:
    return q / "health" / "metrics.jsonl"


@contextmanager
def _metrics_lock(q: Path) -> Iterator[None]:
    """An exclusive flock on `health/metrics.jsonl.lock`, held by every metrics append."""
    from ccp.queue import file_lock  # noqa: PLC0415  (the same lock file: metrics.jsonl.lock)
    with file_lock(_metrics_path(q)):
        yield


def add_note(q: Path, text: str, task_id: str | None = None, by: str | None = None, source: str = "worker") -> dict[str, Any]:
    if looks_like_secret(text):
        raise ValueError("the note looks like it holds a secret; say it without the value")
    rec = {"at": _ts(datetime.now(timezone.utc).timestamp()), "task_id": task_id or None, "by": by or None,
           "source": source, "text": text.strip()}
    from ccp.queue import append_jsonl  # noqa: PLC0415  (under the lock the sync's merge takes)
    append_jsonl(q / "health" / "notes.jsonl", rec)
    return rec


def add_metrics(cfg: Config, q: Path, task_id: str, pairs: list[str]) -> list[dict[str, Any]]:
    """`ccp health record`. A suite number typed by hand (`suite_seconds`, `suite_tests`) has no
    `ccp suite` record behind it: it is filed as unverified, never into the cold series (§27.2)."""
    allowed = set(BUILTIN_METRICS) | set((cfg.architect or ARCHITECT_DEFAULTS)["metrics"])
    recs = []
    for pair in pairs:
        name, _, value = pair.partition("=")
        name = name.strip()
        if name not in allowed:
            raise ValueError(f"metric {name!r} is not one of {', '.join(sorted(allowed))} (architect.metrics adds names)")
        try:
            v = float(value)
        except ValueError:
            raise ValueError(f"metric {name}: {value!r} is not a number") from None
        rec: dict[str, Any] = {"at": _ts(datetime.now(timezone.utc).timestamp()), "task_id": task_id, "metric": name,
                               "value": int(v) if v.is_integer() else v}
        if name in ("suite_seconds", "suite_tests"):
            rec.update(metric=suite_metric("unverified", name.split("_", 1)[1]), kind="unverified", source="record")
        recs.append(rec)
    with _metrics_lock(q):
        for r in recs:
            _append(_metrics_path(q), r)
    return recs


def line_kind(line: str | None) -> str | None:
    """What a `Suite:` line says of its own run: `cold`, `warm` (units cached), or None. Its counts
    decide (`ran 3, cached 90`, or the older `57 modules ran, 3 cached`); else the word warm or cold."""
    if not line:
        return None
    from ccp.report import cache_counts  # noqa: PLC0415
    c = cache_counts(line)
    if c is not None:
        return "warm" if c[1] > 0 else "cold"
    if re.search(r"\bwarm\b", line, re.I):
        return "warm"
    if re.search(r"(?<!not )\bcold\b", line, re.I):
        return "cold"
    return None


def _mentions_cache(line: str) -> bool:
    from ccp.report import cache_counts  # noqa: PLC0415
    return cache_counts(line) is not None or bool(re.search(r"\b(?:warm|cached)\b", line, re.I))


def cache_start(cfg: Config | None, q: Path, suites: list[dict[str, Any]], first: bool = True) -> float | None:
    """When the product's test cache began (epoch seconds): the earlier of the first recorded suite
    run that gave a `cached` count and the first report whose `Suite:` line names cached units
    (counts, `cached` or `warm`). With `verify.accept_cache` set and no such evidence,
    0 (always). None: no cache seen. `first=False` stops at any evidence (whether one exists now)."""
    from ccp import runs  # noqa: PLC0415
    from ccp.verify import cache_rule  # noqa: PLC0415
    times = [e for s in suites if s.get("cached") is not None
             and (e := _epoch(str(s.get("started_at") or ""))) is not None]
    if times and not first:
        return min(times)
    for r in runs.all_runs(q):
        e = _epoch(str(r.get("reported_at") or ""))
        if e is None or (times and e >= min(times)):
            continue
        line = _report_line(q, r)
        if line and _mentions_cache(line):
            times.append(e)
            if not first:
                break
    if times:
        return min(times)
    return 0.0 if cfg is not None and cache_rule(cfg) else None


def classify(s: dict[str, Any], cache: bool, said: str | None = None,
             lanes: tuple[str, ...] = COLD_ROLES) -> str | None:
    """Which suite series a recorded `ccp suite run` belongs to (§27.2); None when it did not pass.
    A run in a cold-capable lane (`lanes`: the full and gate roles') is warm when any unit was cached
    (`cached` > 0); cold when it counted tests and either says nothing was cached (`cached` 0) or the
    product had no test cache then (`cache` False: before cache_start); else unverified. A run in any
    other lane is part. `said` is the report's own word for it (line_kind), used only where the record
    has no `cached` count."""
    if s.get("state") != "passed":
        return None
    if s.get("lane") not in lanes:
        return "part"
    mc = s.get("cached")
    said = said if mc is None else None
    if (isinstance(mc, int) and mc > 0) or said == "warm":
        return "warm"
    counted = isinstance(s.get("tests"), int) and s["tests"] > 0
    if counted and (mc == 0 or said == "cold" or not cache):
        return "cold"
    return "unverified"


def _target(mine: list[dict[str, Any]], tests: Any = None, suite_from: str | None = None,
            lanes: tuple[str, ...] = COLD_ROLES) -> dict[str, Any] | None:
    """The recorded run a report's `Suite:` line describes: the one it cites, else the latest passing
    one with its test count, else the run's latest passing `full` or `gate` run."""
    passed = [s for s in mine if s.get("state") == "passed"]
    return (next((s for s in mine if suite_from and s.get("suite_id") == suite_from), None)
            or next((s for s in reversed(passed) if tests is not None and s.get("tests") == tests), None)
            or next((s for s in reversed(passed) if s.get("lane") in lanes), None))


def _seconds(v: Any) -> float | int:
    sec = float(v or 0)
    return round(sec) if sec >= 10 else round(sec, 1)


def _tally(s: dict[str, Any] | None, line: str | None) -> dict[str, Any]:
    """The units ran and cached behind an entry, from its record, else its report's line: shown, so
    an `effectively cold` run (58 ran, 1 cached) reads as what it was. It stays warm."""
    from ccp.report import cache_counts  # noqa: PLC0415
    if s and s.get("cached") is not None:
        # the cached units' tests beside the ran count, so an all-cached gate does not read as 0 tests
        return {"ran": s.get("ran"), "cached": s.get("cached"),
                **({"cached_tests": s["cached_tests"]} if s.get("cached_tests") is not None else {})}
    c = cache_counts(line) if line else None
    return {"ran": c[0], "cached": c[1]} if c else {}


def _entries(task_id: str, at: str, kind: str, tests: Any, seconds: Any, **extra: Any) -> list[dict[str, Any]]:
    out = []
    if isinstance(tests, int) and not isinstance(tests, bool):
        out.append({"at": at, "task_id": task_id, "metric": suite_metric(kind, "tests"), "value": tests, "kind": kind, **extra})
    if seconds is not None:
        out.append({"at": at, "task_id": task_id, "metric": suite_metric(kind), "value": _seconds(seconds), "kind": kind,
                    **extra})
    return out


def _folded(q: Path, now: float | None = None) -> list[dict[str, Any]]:
    from ccp import suite  # noqa: PLC0415
    try:
        return suite.fold(q, now=now)
    except Exception:  # noqa: BLE001  (a damaged suites file: no records)
        return []


def _filed_ids(entries: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for m in entries:
        if m.get("kind") and m.get("kind") != "duplicate":
            out.update(str(x) for x in ([m.get("suite_id")] + list(m.get("suite_ids") or [])) if x)
    return out


def file_suites(cfg: Config | None, q: Path, run_id: str, task_id: str, parsed: dict[str, Any],
                line: str | None) -> list[dict[str, Any]]:
    """`ccp report`, for a report whose outcome is done (a verify: approve): file the run's suite time
    for `ccp health` (§27.2). Each passing `full` or `gate` run recorded against the run goes under
    its kind (classify), once; its passing part-lane runs go in as one `part` entry for the run, their
    seconds and tests summed (`runs` says how many). A run with no ended suite record falls back to
    the report's `Suite:` numbers, once per (task, run, tests, seconds): warm when the line says so;
    once the product has a test cache, cold only when the line says so, else unverified."""
    rows = _folded(q)
    mine = [s for s in rows if s.get("run_id") == run_id and s.get("state") != "open"]
    cache = cache_start(cfg, q, rows, first=False) is not None  # any evidence by now: the run is after it
    at = _ts(datetime.now(timezone.utc).timestamp())
    said = line_kind(line)
    lanes = cold_lanes(cfg)
    recs: list[dict[str, Any]] = []
    with _metrics_lock(q):
        existing = _jsonl(_metrics_path(q))
        if mine:
            filed = _filed_ids(existing)
            target = _target(mine, parsed.get("suite_tests"), parsed.get("suite_from"), lanes)
            parts = []
            for s in mine:
                if s.get("suite_id") in filed:
                    continue
                k = classify(s, cache, said if s is target else None, lanes)
                if k == "part":
                    parts.append(s)
                elif k:
                    recs += _entries(task_id, at, k, s.get("tests"), s.get("seconds"), run_id=run_id,
                                     suite_id=s.get("suite_id"), lane=s.get("lane"),
                                     **_tally(s, line if s is target else None))
            if parts:
                counts = [s["tests"] for s in parts if isinstance(s.get("tests"), int)]
                recs += _entries(task_id, at, "part", sum(counts) if counts else None,
                                 sum(float(s.get("seconds") or 0) for s in parts), run_id=run_id,
                                 suite_ids=[s.get("suite_id") for s in parts], runs=len(parts), lane="part")
        elif "suite_seconds" in parsed and parsed.get("suite_passed") is not False:
            k = "warm" if said == "warm" else "cold" if said == "cold" or not cache else "unverified"
            tests, secs = parsed.get("suite_tests"), _seconds(parsed.get("suite_seconds"))
            if not any(m.get("source") == "report" and m.get("task_id") == task_id and m.get("run_id") == run_id
                       and m.get("reported_tests") == tests and m.get("value") == secs
                       and str(m.get("metric", "")).startswith("suite_seconds") for m in existing):
                recs = _entries(task_id, at, k, tests, secs, run_id=run_id, source="report", reported_tests=tests,
                                **_tally(None, line))
        for r in recs:
            _append(_metrics_path(q), r)
    return recs


def suite_view(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The metrics as readers take them: an untagged `suite_seconds`/`suite_tests` entry (no `kind`)
    is cold only when it predates the first tagged one (written before §27's records); one written
    after that is unverified."""
    tagged = [e for m in entries if m.get("kind") and (e := _epoch(str(m.get("at") or ""))) is not None]
    first = min(tagged) if tagged else None
    out = []
    for m in entries:
        if (first is not None and not m.get("kind") and m.get("metric") in ("suite_seconds", "suite_tests")
                and (_epoch(str(m.get("at") or "")) or 0) >= first):
            m = {**m, "metric": suite_metric("unverified", str(m["metric"]).split("_", 1)[1]), "kind": "unverified"}
        out.append(m)
    return out


def suite_trend(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Each suite series' entries, latest and median of the last 5 seconds. The cold one is the suite's
    time; warm, part (one entry per run) and unverified ones never enter it, nor duplicates."""
    out: dict[str, Any] = {}
    view = suite_view(entries)
    for k in SUITE_KINDS:
        xs = [m["value"] for m in view if m.get("metric") == suite_metric(k)
              and isinstance(m.get("value"), (int, float)) and not isinstance(m.get("value"), bool)]
        out[k] = {"runs": len(xs), "latest_s": xs[-1] if xs else None, "median_last5_s": _median(xs[-LAST:])}
    return out


def gate_time(cfg: Config | None, q: Path, rows: list[dict[str, Any]] | None = None,
              now: float | None = None) -> dict[str, Any]:
    """The gate's time against the agent's shell limit (§14.6): the latest cold run of the gate role's
    lane (cold as §27.2 decides: passed, counted tests, nothing cached or no test cache yet), judged
    against plane.json `gate`'s cut line and limit. `finding` is that run when it took longer than the
    line (`over_limit` when longer than the limit, a health breach), with its slowest stage; else None:
    an advisory finding, never a filed task. Warm and unverified runs are never judged. `killed` lists,
    oldest first, the gate role's runs with no `ended` row whose elapsed time reached the limit (to the
    earliest of their run's stop, report or abandonment when fold knows it, else to `now`), started
    after the latest gate run that passed or failed: killed at the shell limit. A run that stopped
    earlier, or one with an `ended` row (an interrupted run included), is not listed."""
    from ccp.config import gate_limits, lane_for  # noqa: PLC0415
    limit, line = gate_limits(cfg)
    lane = lane_for(cfg, "gate")
    now = time.time() if now is None else now
    rows = _folded(q, now) if rows is None else rows
    mine = [s for s in rows if s.get("lane") == lane and s.get("state") == "passed"]
    start = cache_start(cfg, q, rows) if mine else None

    def cache_then(s: dict[str, Any]) -> bool:
        return start is not None and (_epoch(str(s.get("started_at") or "")) or 0) >= start

    cold = [s for s in mine if classify(s, cache_then(s), lanes=(lane,)) == "cold"
            and isinstance(s.get("seconds"), (int, float)) and not isinstance(s.get("seconds"), bool)]
    latest = cold[-1] if cold else None
    finding = None
    if latest is not None and latest["seconds"] > line:
        stages = [st for st in latest.get("stages") or [] if isinstance(st, dict)
                  and isinstance(st.get("seconds"), (int, float)) and not isinstance(st.get("seconds"), bool)]
        slow = max(stages, key=lambda st: st["seconds"], default=None)
        finding = {"suite_id": latest.get("suite_id"), "task_id": latest.get("task_id"), "run_id": latest.get("run_id"),
                   "started_at": latest.get("started_at"), "seconds": _seconds(latest["seconds"]),
                   "over_limit": latest["seconds"] > limit,
                   "slowest_stage": {"name": slow.get("name"), "seconds": _seconds(slow["seconds"])} if slow else None}
    ours = [s for s in rows if s.get("lane") == lane]
    since = max((i + 1 for i, s in enumerate(ours) if s.get("state") in ("passed", "failed")), default=0)
    killed = [{k: s.get(k) for k in ("suite_id", "task_id", "run_id", "started_at")} for s in ours[since:]
              if s.get("state") in ("open", "killed") and (t0 := _epoch(str(s.get("started_at") or ""))) is not None
              and _elapsed(s, t0, now) >= limit]
    return {"lane": lane, "limit_s": limit, "line_s": line, "cold_runs": len(cold),
            "latest": {"suite_id": latest.get("suite_id"), "seconds": _seconds(latest["seconds"])} if latest else None,
            "finding": finding, "killed": killed}


def _elapsed(s: dict[str, Any], t0: float, now: float) -> float:
    """A no-end suite run's elapsed seconds: to the earliest of its run's stop, report or abandonment
    when fold knows it, else to now."""
    secs = s.get("seconds")
    return secs if isinstance(secs, (int, float)) and not isinstance(secs, bool) else now - t0


def gate_text(g: dict[str, Any] | None) -> str | None:
    """One line for a gate-time finding (§14.6), or None when there is none."""
    f = (g or {}).get("finding")
    if not f:
        return None
    slow = f.get("slowest_stage")
    where = f"slowest stage {slow['name']} {slow['seconds']:g} s" if slow else "no stage timings recorded"
    head = (f"Gate over the shell limit (a health breach): cold gate run {f['suite_id']}" if f["over_limit"]
            else f"Gate over the cut line: cold gate run {f['suite_id']}")
    return (f"{head} ({f.get('task_id') or 'no task'}, {f.get('started_at') or '-'}) took {f['seconds']:g} s;"
            f" cut line {g['line_s']:g} s, shell limit {g['limit_s']:g} s; {where}."
            " Advisory: the task-log owner decides whether to file a refactor task (§14.6).")


def killed_text(g: dict[str, Any] | None) -> str | None:
    """One line for the gate runs killed at the shell limit (§14.6), or None when there are none."""
    k = (g or {}).get("killed") or []
    if not k:
        return None
    last = k[-1]
    return (f"Gate killed at the shell limit: {len(k)} gate run(s) with no end ran {g['limit_s']:g} s or longer"
            f" since the latest gate run that passed or failed; latest {last.get('suite_id')}"
            f" ({last.get('task_id') or 'no task'}, {last.get('started_at') or '-'}) (§14.6).")


def _report_line(q: Path, run: dict[str, Any]) -> str | None:
    """The `Suite:` line of a run's stored report, if any."""
    from ccp import runs  # noqa: PLC0415
    from ccp.report import SUITE_ANY_RE  # noqa: PLC0415
    try:
        text = Path(run.get("report") or runs.report_path(q, run["run_id"])).read_text(errors="replace")
    except (OSError, ValueError, KeyError):
        return None
    m = SUITE_ANY_RE.search(text)
    return m.group(0) if m else None


RELEASE_NOTE = "ccp tasks release:"  # the note on a release's phase move and progress entry (ccp/lifecycle.py)


def released(ev: dict[str, Any]) -> bool:
    """A lease clear written by `ccp tasks release` (§10.4): the claim before it was undone."""
    return ev.get("type") == "lease" and ev.get("op") == "clear" and bool((ev.get("payload") or {}).get("released"))


def after_release(evs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A task's events (in ledger order) after its last release: an undone claim is no start."""
    last = max((i for i, e in enumerate(evs) if released(e)), default=-1)
    return evs[last + 1:]


def _queue_view(q: Path) -> dict[str, dict[str, Any]]:
    """Per task: start candidates and verify transitions from the event log."""
    view: dict[str, dict[str, Any]] = {}
    for ev in _jsonl(_events_path(q)):
        tid = ev.get("task_id")
        if tid and ev.get("type") == "waiting_on":  # the waits active time leaves out (`waits_s`)
            view.setdefault(tid, {"first": None, "verify_moves": 0}).setdefault("waiting", []).append(ev)
            continue
        if not tid or ev.get("type") not in ("phase", "lease", "claude"):
            continue
        at = _epoch(ev.get("at", ""))
        v = view.setdefault(tid, {"first": None, "verify_moves": 0})
        if released(ev):  # §10.4: the claim before it was undone; the task starts again at its next claim
            v["first"], v["released"] = None, True
            continue
        if v.get("released"):
            if (ev.get("type"), ev.get("op")) != ("lease", "set"):
                continue  # in the gap before the next claim (a sync, a maintainer call): no start
            v["released"] = False
        if at is not None and (v["first"] is None or at < v["first"]):
            v["first"] = at
        if ev.get("type") == "phase" and str((ev.get("payload") or {}).get("to")) in ("verifying", "verify"):
            v["verify_moves"] += 1
    return view


def rotation(q: Path) -> dict[str, Any]:
    """§10.2 step 4: the runner slots due for rotation and not rotated (`lifecycle.rotation_due`), and the
    ledger's count of rotations (`runner`/`rotate` events) against tasks done (distinct tasks moved to
    `done`), so a runner kept past its threshold shows."""
    from ccp.lifecycle import rotation_due  # noqa: PLC0415
    from ccp.queue import load_work, runner_slots  # noqa: PLC0415
    rotations, done = 0, set()
    for ev in _jsonl(_events_path(q)):
        if (ev.get("type"), ev.get("op")) == ("runner", "rotate"):
            rotations += 1
        elif ev.get("type") == "phase" and ev.get("task_id") and (ev.get("payload") or {}).get("to") == "done":
            done.add(str(ev["task_id"]))
    try:
        w = load_work(q)
    except QueueError:  # a damaged work.json never breaks health
        w = {}
    due = [d for s in (sorted(runner_slots(w)) or [""]) if (d := rotation_due(q, s, w))]
    return {"rotations": rotations, "tasks_done": len(done), "due": due}


def rotation_text(r: dict[str, Any] | None) -> list[str]:
    if not r:
        return []
    return ([f"Runner rotations: {r['rotations']} against {r['tasks_done']} task(s) done"]
            + [f"Rotation due, not rotated: {d['slot']} ({d['why']}); `{d['rotate']}`" for d in r["due"]])


def lane_waits(q: Path) -> dict[str, list[tuple[float, float]]]:
    """Per task, its suite runs' waits on an exclusive lane (§16.6) as (start, end) epochs: a `started`
    row's `wait_s` ends at its `at` (the run's start), a `busy` row's `waited_s` at its own `at`."""
    from ccp import suite  # noqa: PLC0415
    out: dict[str, list[tuple[float, float]]] = {}
    for row in _jsonl(suite.path(q)):
        key = {"started": "wait_s", "busy": "waited_s"}.get(str(row.get("op")))
        w = row.get(key) if key else None
        at = _epoch(str(row.get("at") or ""))
        if not row.get("task_id") or at is None or isinstance(w, bool) or not isinstance(w, (int, float)) or w <= 0:
            continue
        out.setdefault(str(row["task_id"]), []).append((at - w, at))
    return out


def waits_s(waiting: list[dict[str, Any]], lanes: list[tuple[float, float]], lo: float, hi: float) -> int:
    """The seconds of [lo, hi] a task spent waiting: its `waiting_on` events' set → clear intervals (one
    still set runs to `hi`) and its lane waits, each instant counted once."""
    from ccp import drill  # noqa: PLC0415  (drill reads health; the wait and interval rules are its)
    iv = [(w["start"], w["end"]) for w in drill._waits(waiting, None, hi)] + list(lanes)
    return round(drill.length(drill.clip(drill.union(iv), lo, hi)))


ROUND_KINDS = ("implement", "review", "fix", "merge", "ruling", "verify")  # runs.PHASES, each its own bucket


def _phase(name: str) -> str:
    """The round kind a report or prompt-audit name starts with (§13.2's kinds), else "other"."""
    return next((k for k in ROUND_KINDS if name.startswith(k)), "other")


def _task_queue(q: Path, tid: str, ev: dict[str, Any], bodies: bool = True) -> dict[str, Any]:
    """A task's timing from the times the queue records: prompt-audit launch stamps (each phase's
    start), `progress/<task>.json` events, the event log, and the verifier's `checked_at`. A phase end
    with no recorded time falls back to its report file's modification time, and `times` says so; a
    task with no recorded start has no wall time."""
    launches: dict[str, list[float]] = {k: [] for k in (*ROUND_KINDS, "other")}
    reports: dict[str, list[float]] = {k: [] for k in (*ROUND_KINDS, "other")}
    d = q / "progress" / tid
    if d.is_dir():
        for f in d.glob("*-report.md"):
            reports[_phase(f.name)].append(f.stat().st_mtime)
    prompt_chars, impl_chars, n_prompts = 0, 0, 0
    pd = q / "prompts" / tid
    if pd.is_dir():
        for f in pd.rglob("*.json"):
            m = STAMP_RE.match(f.name)
            if not m:
                continue
            n_prompts += 1
            if (e := _epoch(m.group(1))) is not None:
                launches[_phase(m.group(2))].append(e)
            if not bodies:
                continue
            try:  # §23.8: the audit's length; an audit from before it, its body
                rec = json.loads(f.read_text())
                n = rec.get("prompt_chars")
                n = n if isinstance(n, int) and not isinstance(n, bool) else len(str(rec.get("prompt_body") or ""))
            except (OSError, ValueError, AttributeError):
                n = 0
            prompt_chars += n
            if m.group(2).startswith("implement"):
                impl_chars = max(impl_chars, n)
    recorded = [x for x in (ev.get("first"), min([t for v in launches.values() for t in v], default=None)) if x]
    try:
        prog = json.loads((q / "progress" / f"{tid}.json").read_text()).get("events") or []
        cut = max((i for i, x in enumerate(prog) if x.get("to") == "pending"
                   and str(x.get("note") or "").startswith(RELEASE_NOTE)), default=-1)
        recorded += [e for x in prog[cut + 1:] if (e := _epoch(str(x.get("at") or ""))) is not None]
    except (OSError, ValueError, AttributeError):
        pass
    try:
        verdict = _epoch(str(json.loads((q / "verification" / f"{tid}.json").read_text()).get("checked_at") or ""))
    except (OSError, ValueError, AttributeError):
        verdict = None
    used_mtime = False

    def pick(rec: float | None, fallback: float | None) -> float | None:
        nonlocal used_mtime
        if rec is None and fallback is not None:
            used_mtime = True
        return rec if rec is not None else fallback

    # A report is written when a phase ends, so it never stands in for the start: no recorded start, no wall.
    start = min(recorded, default=None)
    # Each phase ends when the next one is launched; the last ends at the verdict.
    impl_end = pick(min(launches["review"] or launches["verify"], default=None), min(reports["implement"], default=None))
    rev_end = pick(min(launches["verify"], default=None), max(reports["review"] + reports["fix"], default=None))
    ver_end = pick(verdict, max(reports["verify"], default=None))

    def span(a: float | None, b: float | None) -> float | None:
        return round(b - a) if a is not None and b is not None and b >= a else None

    return {"start": start, "implementing_s": span(start, impl_end), "reviewing_s": span(impl_end, rev_end),
            "verifying_s": span(max([x for x in (impl_end, rev_end) if x is not None], default=None), ver_end),
            "fix_rounds": max(len(reports["fix"]), len(launches["fix"])),
            "merge_rounds": max(len(reports["merge"]), len(launches["merge"])),
            "ruling_rounds": max(len(reports["ruling"]), len(launches["ruling"])),
            "review_rounds": max(len(reports["review"]), len(launches["review"])),
            "verify_rounds": max(len(reports["verify"]), len(launches["verify"]), ev.get("verify_moves", 0)),
            "times": "recorded, some file mtimes" if used_mtime else "recorded",
            "prompts": n_prompts, "prompt_chars": prompt_chars, "implement_prompt_chars": impl_chars}


def _median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def trend(rows: list[dict[str, Any]], ratio: float) -> dict[str, Any]:
    """The drift (§19.6) on active time: the median `active_s` of the last 5 timed tasks against the 10
    before them. `median_wall_s` stays beside it, for reading."""
    walls = [r["wall_s"] for r in rows if r.get("wall_s") is not None]
    active = [r["active_s"] for r in rows if r.get("active_s") is not None]
    last, before = active[-LAST:], active[-(LAST + BEFORE):-LAST]
    m_last, m_before = _median(last), _median(before)
    r = round(m_last / m_before, 2) if m_last is not None and m_before and len(before) == BEFORE else None
    return {"timed_tasks": len(active), "median_wall_s": _median(walls), "median_active_s": _median(active),
            "median_last5_s": m_last, "median_before10_s": m_before, "drift_ratio": r, "drift_limit": ratio,
            "drift": r is not None and r > ratio}


def collect(cfg: Config, q: Path | None, since: str | None = None, files: bool = True,
            rev: str = "HEAD") -> dict[str, Any]:
    """Per-task rows (one per merged task on `rev`'s first-parent history, oldest merge first) and the
    trend over them. Without `files`, only what the trend needs: no per-file lines and no prompt sizes."""
    a = cfg.architect or ARCHITECT_DEFAULTS
    tasks = tasklog.load(cfg)
    ms = merges(cfg, tasks, rev)
    if since:
        s = _epoch(since + ("T00:00:00Z" if len(since) == 10 else ""))
        if s is None:
            raise ValueError(f"--since {since!r}: give a date (YYYY-MM-DD) or YYYY-MM-DDTHH:MM:SSZ")
        ms = [m for m in ms if m["at"] >= s]
    stats = numstat(cfg, {m["sha"] for m in ms}, rev) if files else {}
    areas = [(n, [glob_re(g) for g in gs]) for n, gs in a["areas"].items()]
    ev = _queue_view(q) if q else {}
    lanes = lane_waits(q) if q else {}
    metrics: dict[str, dict[str, Any]] = {}
    entries = suite_view(_jsonl(_metrics_path(q))) if q else []
    for m in entries:  # a task's latest of each; the suite's are filed per kind (file_suites)
        metrics.setdefault(str(m.get("task_id")), {})[str(m.get("metric"))] = m.get("value")
    rows: dict[str, dict[str, Any]] = {}
    for m in ms:
        r = rows.pop(m["task_id"], None) or {"task_id": m["task_id"], "merges": 0, "files": 0, "lines": 0, "areas": {}}
        r.update(merged_at=_ts(m["at"]), merge_sha=m["sha"][:7], _at=m["at"])
        r["merges"] += 1
        for path, n in stats.get(m["sha"], []):
            r["files"] += 1
            r["lines"] += n
            k = _area(path, areas)
            r["areas"][k] = r["areas"].get(k, 0) + n
        rows[m["task_id"]] = r  # re-inserted: a task merged twice sorts by its last merge
    for r in rows.values():
        if q:
            qd = _task_queue(q, r["task_id"], ev.get(r["task_id"], {}), bodies=files)
            start = qd.pop("start")
            r["wall_s"] = round(r["_at"] - start) if start is not None and start <= r["_at"] else None
            if r["wall_s"] is not None:
                r["waits_s"] = waits_s(ev.get(r["task_id"], {}).get("waiting") or [], lanes.get(r["task_id"], []),
                                       start, r["_at"])
                r["active_s"] = r["wall_s"] - r["waits_s"]
            else:
                r["waits_s"] = r["active_s"] = None
            r.update(qd)
        r["metrics"] = metrics.get(r["task_id"], {})
        del r["_at"]
    out_rows = list(rows.values())
    out: dict[str, Any] = {"tasks": out_rows, "trend": trend(out_rows, a["drift_ratio"]), "suite": suite_trend(entries),
                           "queue": str(q) if q else None}
    if files:
        out["budget_failures"] = budget_failures(cfg)  # diagnostics; `ccp architect due` makes them a trigger
        try:  # §14.6: a damaged suites file or report never breaks health
            out["gate_time"] = gate_time(cfg, q) if q else None
        except Exception:  # noqa: BLE001
            out["gate_time"] = None
        out["rotation"] = rotation(q) if q else None  # §10.2 step 4
    return out


def _h(s: float | None) -> str:
    return "-" if s is None else f"{s / 3600:.1f}h"


def summary_text(report: dict[str, Any], n: int = 10) -> str:
    """A compact view for the architect's prompt."""
    t = report["trend"]
    lines = [f"Timed tasks: {t['timed_tasks']}; median wall {_h(t['median_wall_s'])}, active {_h(t.get('median_active_s'))};"
             f" active time of the last 5 {_h(t['median_last5_s'])} vs the 10 before {_h(t['median_before10_s'])}"
             f" (ratio {t['drift_ratio'] if t['drift_ratio'] is not None else '-'}, drift above {t['drift_limit']})."]
    st = report.get("suite") or {}
    if any((st.get(k) or {}).get("runs") for k in SUITE_KINDS):
        def one(k: str, label: str) -> str:
            v = st.get(k) or {}
            m = v.get("median_last5_s")
            return f"{label} {v.get('runs', 0)} run(s), median of the last 5 {'-' if m is None else f'{m:g} s'}"
        lines.append("Suite time (ccp suite records): " + "; ".join(
            [one("cold", "cold (the suite's time)"), one("warm", "warm (units cached)"), one("part", "part lane")])
            + f"; {(st.get('unverified') or {}).get('runs', 0)} unverified, in no series.")
    if gt := gate_text(report.get("gate_time")):
        lines.append(gt)
    if kt := killed_text(report.get("gate_time")):
        lines.append(kt)
    for r in report["tasks"][-n:] if n else []:
        lines.append(f"- {r['task_id']}: merged {r['merged_at']}, wall {_h(r.get('wall_s'))}, active {_h(r.get('active_s'))}"
                     f" (impl {_h(r.get('implementing_s'))},"
                     f" review {_h(r.get('reviewing_s'))}, verify {_h(r.get('verifying_s'))}), fix rounds {r.get('fix_rounds', '-')},"
                     f" verify rounds {r.get('verify_rounds', '-')}, {r['files']} files / {r['lines']} lines {r['areas']},"
                     f" prompts {r.get('prompt_chars', '-')} chars" + (f", {r['metrics']}" if r.get("metrics") else ""))
    return "\n".join(lines)


def _table(report: dict[str, Any]) -> str:
    rows = report["tasks"]
    w = max([28] + [len(r["task_id"]) for r in rows])
    out = [f"{'TASK':<{w}} {'MERGED':<17} {'WALL':>6} {'IMPL':>6} {'REVIEW':>6} {'VERIFY':>6} {'FIX':>3} {'VER':>3}"
           f" {'FILES':>5} {'LINES':>6}  AREAS"]
    for r in rows:
        out.append(f"{r['task_id']:<{w}} {r['merged_at'][:16]:<17} {_h(r.get('wall_s')):>6} {_h(r.get('implementing_s')):>6}"
                   f" {_h(r.get('reviewing_s')):>6} {_h(r.get('verifying_s')):>6} {str(r.get('fix_rounds', '-')):>3}"
                   f" {str(r.get('verify_rounds', '-')):>3} {r['files']:>5} {r['lines']:>6}  "
                   + " ".join(f"{k}={v}" for k, v in sorted(r["areas"].items())))
    return "\n".join(out)


def _queue(required: bool) -> Path | None:
    q = os.environ.get("QUEUE_ROOT")
    if q and Path(q).is_dir():
        return Path(q)
    if required:
        raise SystemExit("ccp health: set QUEUE_ROOT to this project's runtime queue (SPEC §27)")
    return None


def main(cfg: Config, a: Any) -> int:
    if a.action == "note":
        if not (a.text or "").strip():
            print("ccp health note: give --text", file=sys.stderr)
            return 2
        try:
            rec = add_note(_queue(True), a.text, a.task, a.by or os.environ.get("ACTOR"))
        except ValueError as e:
            print(f"ccp health note: {e}", file=sys.stderr)
            return 2
        print(json.dumps(rec))
        return 0
    if a.action == "record":
        if not a.task or not a.metric:
            print("ccp health record: give --task and at least one --metric name=value", file=sys.stderr)
            return 2
        try:
            recs = add_metrics(cfg, _queue(True), a.task, a.metric)
        except ValueError as e:
            print(f"ccp health record: {e}", file=sys.stderr)
            return 2
        print(json.dumps(recs))
        return 0
    q = _queue(False)
    try:
        report = collect(cfg, q, a.since)
    except ValueError as e:
        print(f"ccp health: {e}", file=sys.stderr)
        return 2
    report["notes"] = len(notes(q))
    if a.json:
        print(json.dumps(report, indent=2))
        return 0
    if not q:
        print("(QUEUE_ROOT not set: git figures only, no wall times)")
    print(_table(report))
    print(summary_text(report, 0))
    for b in report["budget_failures"]:
        print(f"Budget over: {b}")
    for line in rotation_text(report.get("rotation")):
        print(line)
    print(f"Friction notes on record: {report['notes']}")
    return 0
