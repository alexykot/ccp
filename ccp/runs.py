"""Runs (SPEC §11.1): one launch of one worker for one phase of one task, the unit time and tokens
are reported in.

A run id is `<task_id>/<phase>[-<n>]`: the second review of a task is `<task_id>/review-2`. Its
record is `runs/<task_id>/<phase>[-<n>].json` and its report `progress/<task_id>/<phase>[-<n>]-report.md`
(the §2.5 report path). `ccp prompt` opens a run (`pending`); the harness's SubagentStart hook binds
it to the agent that started (`ccp agent start`: the oldest pending run of that agent type); the
SubagentStop hook stops it; the worker's `ccp report` closes it. A run that never reported is
abandoned (§11.1): when a later round of its task and phase is opened, when its task is closed or
dropped, or when the next run of its agent type is opened with `--supersede`. `ccp runs gc` applies
the same rules to records written before them.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ccp import tasklog
from ccp.refs import ANY_TASK_ID
from ccp.config import Config
from ccp.queue import QueueError, actor, emit, iso, read_json, write_json

PHASES = ("implement", "fix", "merge", "ruling", "review", "verify")
# §13.2: the implementer's rounds that push a head of the PR (PR and Head in the report), and of those
# the rounds after the first: review and verify treat a merge or ruling round's head as a fix round's.
CHANGE_PHASES = ("implement", "fix", "merge", "ruling")
REWORK_PHASES = ("fix", "merge", "ruling")
# The agent type each phase launches (SPEC §2.5) and the seat it reports as.
AGENT_TYPE = {"implement": "delivery-implementer", "fix": "delivery-implementer", "merge": "delivery-implementer",
              "ruling": "delivery-implementer", "review": "delivery-reviewer", "verify": "delivery-verifier"}
SEAT = {"implement": "implementer", "fix": "implementer", "merge": "implementer", "ruling": "implementer",
        "review": "reviewer", "verify": "verifier"}
PLUGIN = "ccp"
OPEN = ("pending", "running", "stopped")  # not reported, not abandoned
RESOLVED = ("done", "dropped")
CLOSED_REASON = {"done": "task closed", "dropped": "task dropped"}
RUN_ID_RE = re.compile(rf"^(?P<task>{ANY_TASK_ID})/(?P<phase>implement|fix|merge|ruling|review|verify)(?:-(?P<n>[2-9]|[1-9][0-9]+))?$")


def parse_id(run_id: str) -> tuple[str, str, int]:
    m = RUN_ID_RE.match(run_id or "")
    if not m:
        raise QueueError(f"{run_id!r} is not a run id (<task_id>/<phase>[-<n>], phase one of {', '.join(PHASES)})")
    return m.group("task"), m.group("phase"), int(m.group("n") or 1)


def make_id(task_id: str, phase: str, n: int) -> str:
    return f"{task_id}/{phase}" + (f"-{n}" if n > 1 else "")


def path(q: Path, run_id: str) -> Path:
    task, phase, n = parse_id(run_id)
    return q / "runs" / task / (f"{phase}-{n}.json" if n > 1 else f"{phase}.json")


def report_path(q: Path, run_id: str) -> Path:
    task, phase, n = parse_id(run_id)
    return q / "progress" / task / (f"{phase}-{n}-report.md" if n > 1 else f"{phase}-report.md")


def load(q: Path, run_id: str) -> dict[str, Any]:
    rec = read_json(path(q, run_id), None)
    if not isinstance(rec, dict):
        raise QueueError(f"no run {run_id}: `ccp prompt` opens a run before its worker is launched", 1)
    return rec


def save(q: Path, rec: dict[str, Any]) -> None:
    write_json(path(q, rec["run_id"]), rec)


def all_runs(q: Path, task_id: str | None = None) -> list[dict[str, Any]]:
    base = q / "runs"
    if not base.is_dir():
        return []
    dirs = [base / task_id] if task_id else sorted(d for d in base.iterdir() if d.is_dir())
    out = []
    for d in dirs:
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            rec = read_json(f, None)
            if isinstance(rec, dict) and rec.get("run_id"):
                out.append(rec)
    return sorted(out, key=lambda r: str(r.get("opened_at") or ""))


def state(rec: dict[str, Any]) -> str:
    if rec.get("abandoned_at"):
        return "abandoned"
    if rec.get("reported_at"):
        return "reported"
    if rec.get("stopped_at"):
        return "stopped"
    if rec.get("agent_id"):
        return "running"
    return "pending"


def abandon(q: Path, cfg: Config, rec: dict[str, Any], reason: str) -> dict[str, Any]:
    """Mark a run that will never report abandoned (§11.1): who, when and why, and a `run abandoned` event."""
    rec.update(abandoned_at=iso(), abandoned_reason=reason, abandoned_by=actor())
    save(q, rec)
    emit(q, cfg, rec["task_id"], "run", "abandoned", {"run_id": rec["run_id"], "reason": reason})
    return rec


def resolution(q: Path, durable: dict[str, str], task_id: str) -> str | None:
    """`done` or `dropped` when the task is, in its task file (§4, the source of truth) or in the queue."""
    st = durable.get(task_id)
    if st in RESOLVED:
        return st
    from ccp.queue import load_task_state  # noqa: PLC0415
    st = load_task_state(q, task_id).get("status")
    return st if st in RESOLVED else None


def abandon_task_runs(q: Path, cfg: Config, task_id: str, status: str) -> list[str]:
    """Every open run of a task that is done or dropped (`ccp tasks close`, `ccp tasks sync`)."""
    open_ = sorted((r for r in all_runs(q, task_id) if state(r) in OPEN), key=lambda r: str(r.get("run_id")))
    return [abandon(q, cfg, r, CLOSED_REASON[status])["run_id"] for r in open_]  # in run-id order, whatever the filesystem lists


def open_on_live_tasks(q: Path, cfg: Config) -> list[dict[str, Any]]:
    """The open runs the board's Now panel and Seats table list: none of a done or dropped task."""
    from ccp.queue import durable_statuses  # noqa: PLC0415
    try:
        durable = durable_statuses(cfg)
    except Exception:  # noqa: BLE001  (a task log that does not load: the queue's status alone)
        durable = {}
    return [r for r in all_runs(q) if state(r) in OPEN and not resolution(q, durable, str(r.get("task_id") or ""))]


def gc_plan(q: Path, cfg: Config) -> list[tuple[dict[str, Any], str]]:
    """The open runs §11.1's rules abandon, with the reason: a later round of the same task and phase
    (superseded by the next one), else a done or dropped task."""
    from ccp.queue import durable_statuses  # noqa: PLC0415
    try:
        durable = durable_statuses(cfg)
    except Exception:  # noqa: BLE001  (an unreadable task log: fall back to the queue's own statuses)
        durable = {}
    rs = all_runs(q)
    out = []
    for r in rs:
        if state(r) not in OPEN:
            continue
        tid = str(r.get("task_id") or "")
        later = sorted((x for x in rs if x.get("task_id") == tid and x.get("phase") == r.get("phase")
                        and int(x.get("round") or 1) > int(r.get("round") or 1)), key=lambda x: int(x.get("round") or 1))
        res = resolution(q, durable, tid)
        if later:
            out.append((r, f"superseded by {later[0]['run_id']}"))
        elif res:
            out.append((r, CLOSED_REASON[res]))
    return out


def gc(cfg: Config, dry_run: bool = False) -> dict[str, Any]:
    """`ccp runs gc`: §11.1's abandonment rules over the records already written."""
    from ccp.queue import root  # noqa: PLC0415
    q = root()
    changed = []
    for r, reason in gc_plan(q, cfg):
        changed.append({"run_id": r["run_id"], "state": state(r), "reason": reason})
        if not dry_run:
            abandon(q, cfg, r, reason)
    return {"ok": True, "dry_run": dry_run, "abandoned": changed}


def next_round(q: Path, task_id: str, phase: str) -> int:
    return 1 + sum(1 for r in all_runs(q, task_id) if r.get("phase") == phase)


def unscoped(agent_type: str) -> str:
    """`ccp:delivery-implementer` and `delivery-implementer` are the same seat (SPEC §9.1)."""
    return agent_type.split(":", 1)[1] if agent_type.startswith(PLUGIN + ":") else agent_type


def definition(cfg: Config, agent_type: str) -> tuple[str, Path | None]:
    """The agent type to launch and the file that defines it: the product's own managed copy while it
    has one (before §4), else the plugin's (`ccp:<type>`)."""
    own = cfg.root / ".claude" / "agents" / f"{agent_type}.md"
    if own.is_file():
        return agent_type, own
    from ccp.queue import PLANE  # noqa: PLC0415
    f = PLANE / "plugin" / "agents" / f"{agent_type}.md"
    return f"{PLUGIN}:{agent_type}", (f if f.is_file() else None)


def agent_frontmatter(text: str) -> dict[str, Any]:
    """An agent definition's frontmatter: top-level scalars and inline lists, as `tasklog.frontmatter`
    reads them, plus one level of nested map (`experimental:` then indented `cacheTtl: 1h`, §2).
    A nested key never shadows a top-level one of the same name."""
    if not text.startswith("---\n") or text.find("\n---\n", 4) == -1:
        return {}
    out: dict[str, Any] = {}
    block: str | None = None
    for line in text[4:text.find("\n---\n", 4)].splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        one = tasklog.frontmatter(f"---\n{line.strip()}\n---\n")
        if line[:1] in " \t":
            if block is not None:
                out[block].update(one)
            continue
        k = next(iter(one), None)
        if k is not None and one[k] == "":
            out[k], block = {}, k
        else:
            out.update(one)
            block = None
    return out


def expected(cfg: Config, agent_type: str) -> tuple[str | None, str | None]:
    """The model and effort the agent definition pins (SPEC §2.4)."""
    _, f = definition(cfg, agent_type)
    if f is None:
        return None, None
    fm = agent_frontmatter(f.read_text())
    return (str(fm["model"]) if fm.get("model") else None), (str(fm["effort"]) if fm.get("effort") else None)


SUPERSEDE_GRACE_S = 120  # §16.4: another runner's run this fresh is about to be launched, never superseded


def check_pending(q: Path, agent_type: str, supersede: bool, by: str | None = None) -> list[dict[str, Any]]:
    """The pending runs of this agent type; refuses while there is one, unless superseding. Even
    superseding, another runner's (`opened_by`) run opened in the last SUPERSEDE_GRACE_S is refused
    (exit 3): with several runners it is a launch seconds away, not a lost one (SPEC §16.4)."""
    pending = [r for r in all_runs(q) if r.get("agent_type") == agent_type and state(r) == "pending"]
    if supersede and by:
        import time  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415
        for r in pending:
            try:
                age = time.time() - datetime.fromisoformat(str(r.get("opened_at")).replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            if r.get("opened_by") and r.get("opened_by") != by and age < SUPERSEDE_GRACE_S:
                raise QueueError(f"{r['run_id']} was opened {age:.0f} s ago by {r['opened_by']}, another runner, and is "
                                 "about to be launched: wait a few seconds and run `ccp prompt` again (SPEC §16.4)", 3)
    if pending and not supersede:
        names = ", ".join(r["run_id"] for r in pending)
        raise QueueError(f"{names} is still pending (opened, its agent not started): a second pending run of "
                         f"{agent_type} could not be told apart when one starts (SPEC §11.1). Launch it, or open "
                         "this one with --supersede to mark it abandoned", 3)
    return pending


def check_running_rounds(q: Path, task_id: str, phase: str, by: str | None, supersede: bool) -> None:
    """§16.4: a new round never abandons a running round of this task's phase that another slot
    opened, unless the lease holder (`by`) supersedes it explicitly (exit 3)."""
    if not by:
        return
    for r in all_runs(q, task_id):
        if r.get("phase") == phase and state(r) == "running" and r.get("opened_by") and r.get("opened_by") != by \
                and not supersede:
            raise QueueError(f"{r['run_id']} is running, opened by {r['opened_by']}: a new round would abandon "
                             "another slot's worker. The slot holding the lease may supersede it with --supersede "
                             "(SPEC §16.4)", 3)


def open_run(q: Path, cfg: Config, task_id: str, phase: str, *, prompt_ref: str | None, note: str | None,
             supersede: bool, extra: dict[str, Any] | None = None, warnings: list[str] | None = None,
             by: str | None = None) -> dict[str, Any]:
    """Open the next round of a task's phase. Every earlier round of it still open is abandoned,
    superseded by this one (§11.1); one that was running adds a line to `warnings`."""
    agent_type = AGENT_TYPE[phase]
    from ccp.queue import load_task_state  # noqa: PLC0415
    if by is None:  # §16.4: the runner opening it (the lease holder, when the caller is not named)
        by = str(load_task_state(q, task_id).get("lease_holder") or "") or None
    check_running_rounds(q, task_id, phase, by, supersede)
    pending = check_pending(q, agent_type, supersede, by)
    n = next_round(q, task_id, phase)
    run_id = make_id(task_id, phase, n)
    for r in pending:
        if r.get("task_id") != task_id or r.get("phase") != phase:
            abandon(q, cfg, r, f"superseded by {run_id}, a new launch of its agent type")
    model, effort = expected(cfg, agent_type)
    rec = {"schema_version": 1, "run_id": run_id, "project_id": cfg.project_id,
           "task_id": task_id, "phase": phase, "round": n, "seat": SEAT[phase], "agent_type": agent_type,
           "expected_model": model, "expected_effort": effort, "prompt_ref": prompt_ref,
           "note": note or None, "opened_at": iso(), "agent_id": None, "session_id": None,
           "started_at": None, "stopped_at": None, "reported_at": None, "outcome": None, "opened_by": by,
           **(extra or {})}
    save(q, rec)
    emit(q, cfg, task_id, "run", "opened", {k: rec[k] for k in ("run_id", "phase", "round", "agent_type",
                                                                  "expected_model", "expected_effort", "prompt_ref")})
    for r in all_runs(q, task_id):
        if r.get("phase") == phase and r["run_id"] != run_id and (was := state(r)) in OPEN:
            abandon(q, cfg, r, f"superseded by {run_id}")
            if was == "running" and warnings is not None:
                warnings.append(f"{r['run_id']} was still running (bound to agent {r.get('agent_id')}, no stop yet): "
                                f"abandoned, superseded by {run_id}; a report from it will be refused")
    return rec


def bind(q: Path, cfg: Config, agent_type: str, agent_id: str, session_id: str | None) -> dict[str, Any] | None:
    """SubagentStart: the oldest pending run of this agent type is this agent's. None when there is
    no such run (an agent the toolkit did not launch); the hook records it as unbound."""
    agent_type = unscoped(agent_type)
    if any(r.get("agent_id") == agent_id for r in all_runs(q)):
        return None  # a resumed agent: already bound
    pending = [r for r in all_runs(q) if r.get("agent_type") == agent_type and state(r) == "pending"]
    if not pending:
        return None
    rec = pending[0]
    rec.update(agent_id=agent_id, session_id=session_id, started_at=iso())
    save(q, rec)
    emit(q, cfg, rec["task_id"], "run", "bound", {"run_id": rec["run_id"], "agent_id": agent_id,
                                                  "session_id": session_id}, "system")
    return rec


def stop(q: Path, cfg: Config, agent_id: str) -> dict[str, Any] | None:
    for rec in reversed(all_runs(q)):
        if rec.get("agent_id") == agent_id:
            first = not rec.get("stopped_at")
            rec["stopped_at"] = iso()  # the latest stop: SubagentStop fires each time the agent's turn ends
            save(q, rec)
            if first:
                emit(q, cfg, rec["task_id"], "run", "stopped", {"run_id": rec["run_id"], "agent_id": agent_id}, "system")
            return rec
    return None


def latest_open(q: Path, task_id: str, phase: str) -> dict[str, Any] | None:
    """The newest run of this phase that has not reported or been abandoned."""
    for rec in reversed(all_runs(q, task_id)):
        if rec.get("phase") == phase and state(rec) in ("pending", "running", "stopped"):
            return rec
    return None


def same_change(q: Path, a: str, b: str) -> bool:
    """§13: heads `a` and `b` carry the same change of their own: the
    diff from each one's merge base with the integration branch to it has the same patch id. A head that
    only merged the integration branch in (§16.5 rule 4) is the reviewed change on a newer base. False
    when anything cannot be judged (no product checkout, a head not fetched): the gate stays strict."""
    import subprocess  # noqa: PLC0415
    from ccp.queue import binding_scalar, integration_branch  # noqa: PLC0415
    root = binding_scalar(q, "product_root")
    if not root or not Path(root).is_dir():
        return False
    integ = integration_branch(q)

    import os  # noqa: PLC0415

    def g(*args: str, data: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, input=data, timeout=60,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})  # never wait on a credential prompt

    try:
        return _same_patch(g, a, b, integ)
    except subprocess.TimeoutExpired:
        return False


def _same_patch(g: Any, a: str, b: str, integ: str) -> bool:
    g("fetch", "-q", "origin")
    ids = []
    for sha in (a, b):
        mb = g("merge-base", sha, f"origin/{integ}")
        if mb.returncode != 0:
            return False
        d = g("diff", "--binary", mb.stdout.strip(), sha)
        if d.returncode != 0:
            return False
        pid = g("patch-id", "--stable", data=d.stdout)
        if pid.returncode != 0:
            return False
        if not pid.stdout.split():
            return False  # no change of its own (a head the integration branch already holds): nothing to match
        ids.append(pid.stdout.split()[0])
    return ids[0] == ids[1]


def unreviewed_fix(q: Path, task_id: str, head: str | None = None) -> str | None:
    """§15.2 (the runner brief's step 7: a fix round, then review again): why verifying `head` now
    would skip a review, or None. Refused when the task's latest fix, merge or ruling run (not
    abandoned, §13.2) was opened after its latest review run that reported done, or when `head` is not
    the head that review judged (commits pushed since). Rounds since that review that are all merge
    rounds pass when `head` carries the reviewed change unchanged (the integration-merge rule). A task
    with no runs (one before the toolkit, a PR that is not a task's) has nothing to compare and passes."""
    from ccp.verify import heads_match  # noqa: PLC0415

    rs = [r for r in all_runs(q, task_id) if state(r) != "abandoned"]
    reviews = [r for r in rs if r.get("phase") == "review" and state(r) == "reported" and r.get("outcome") == "done"]
    last = reviews[-1] if reviews else None
    judged = str((last or {}).get("head") or "").strip()
    # a tie (one second) counts the round as newer: a fix opens only once a report exists to fix from
    since = [r for r in rs if r.get("phase") in REWORK_PHASES
             and (last is None or str(last.get("opened_at") or "") <= str(r.get("opened_at") or ""))]
    merged_only = bool(since and head and judged) and all(r.get("phase") == "merge" for r in since) \
        and (heads_match(judged, head.strip()) or same_change(q, judged, head.strip()))  # type: ignore[union-attr]
    if since and not merged_only:
        r = since[-1]
        return (f"{r['phase']} round {r['run_id']} is newer than the last review {last['run_id'] if last else '(none)'}: "
                "run `ccp prompt review` first (runner brief step 7)")
    if head and judged and not heads_match(judged, head.strip()) and not same_change(q, judged, head.strip()):
        return (f"head {head.strip()[:12]} is not {judged[:12]}, the head the last review {last['run_id']} judged: "  # type: ignore[index]
                "run `ccp prompt review` first (runner brief step 7)")
    return None
