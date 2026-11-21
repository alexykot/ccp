#!/usr/bin/env python3
"""The event ledger shared by `ccp` and the observability scripts: QUEUE_ROOT/observability/events.jsonl.

It validates and appends events, holds the work.json lock, the shared constants and the alias table
for values renamed over time, and folds a task's events into its timers. The board (`ccp board`,
SPEC §28) is the status; the older snapshot and its scripts are retired (SPEC §23.4).

Timer formula (stable — see README.md):

  wall_hours  = now − implementation_started_at  (null if never started)
  wait_hours  = sum of waiting_on set→clear intervals + open wait if still waiting
  work_hours  = sum of intervals where ALL of:
                  • phase ∈ WORK_PHASES
                  • waiting_on is null
                  • a Claude launch is open (launch without matching exit)

Do not change this formula without a SPEC + README note.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
from contextlib import contextmanager, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEAT_IDS = ("task-runner", "task-verifier", "delivery-watchdog", "design-seat")
ACTORS = SEAT_IDS + ("adapter", "operator", "system", "plane-session")  # plane-session: §31.5 triage
# §17.8 adds question + spec_maintainer types and their ops; §19.10 adds architecture_review;
# §21 adds docs_audit (same ops and payloads: both are §19 review kinds); §23.7 adds gate + runner
# (gate opened/decided, runner spawn/scope/rotate/stop) and the design-seat actor;
# §19 adds architect (a third review kind: passes and shapes). The first two are retired (§19.12):
# their types stay so an older ledger still reads; nothing writes them any more.
# §23.2 adds the toolkit's ledger: run (a worker launch: opened, bound, stopped, reported, abandoned;
# recorded: the counts of one `ccp mutate` call, §20.6),
# review and verify (recorded verdicts), allowance (samples) and plane (ccp proposals). None of them
# moves a task phase or a timer: the `phase` events ccp writes beside them do that. §14.1 adds suite
# (one `ccp suite run`, recorded when it ends). §10.4 adds prefer (the lead's next tasks for the runner,
# work.json `next_tasks`: set by `ccp tasks prefer`, cleared by it; the claim that takes one removes it), and
# hold (the lead's hold on a task, work.json `held`: `ccp tasks hold`, `next` passes over it). §3.5 adds
# sign_off (the operator's sign-off on a task's text, recorded by `ccp tasks sign-off`; claim and close read it).
# §3.6 adds notify (pending: a trigger fired; sent: a notice sent, by `ccp` over the command or by the lead).
REVIEW_EVENT_TYPES = ("architecture_review", "docs_audit", "architect")
TEAM_EVENT_TYPES = ("gate", "runner")
TOOLKIT_EVENT_TYPES = ("run", "review", "verify", "allowance", "plane", "suite", "prefer", "hold", "sign_off",
                       "ruling", "notify")
# Read-only legacy types (E9's alias): the schema still allows them, so an old ledger validates; ccp writes none.
LEGACY_EVENT_TYPES = ("hosting",)  # an old ledger's hosting switch (Grok hosting is gone)
EVENT_TYPES = ("phase", "waiting_on", "lease", "claude", "auth", "seat", "durable", "note", "question", "spec_maintainer",
               *REVIEW_EVENT_TYPES, *TEAM_EVENT_TYPES, *TOOLKIT_EVENT_TYPES)
EVENT_OPS = (
    "set",
    "clear",
    "transition",
    "launch",
    "exit",
    "heartbeat",
    "reconcile",
    "raised",
    "answered",
    "escalated",
    "resolved_by_operator",
    "rebound",
    "opened",
    "decided",
    "spawn",
    "scope",
    "rotate",
    "stop",
    "switch",
    "bound",
    "stopped",
    "reported",
    "abandoned",
    "recorded",
    "sample",
    "proposed",
    "again",
    "triaged",
    "built",
    "armed",
    "fired",
    "pending",
    "sent",
    "adopted",
    "archived",
)
WAIT_REASONS = ("quota", "reauth", "operator_decision", "runner", "steerer", "spec_maintainer", "design_seat", "null-class",
                "operator_step")

OPEN_GATE_STATUSES = ("open", "waiting_operator")


STATUS_ENUM = (
    "pending",
    "leased",
    "implementing",
    "implemented",
    "reviewing",
    "fixing",
    "reviewed",
    "submitted",
    "verifying",
    "merging",
    "done",
    "blocked",
    "failed",
    "dropped",
)
MID_FLIGHT = {
    "leased",
    "implementing",
    "reviewing",
    "fixing",
    "implemented",
    "reviewed",
    "submitted",
    "verifying",
    "merging",
}
WORK_PHASES = {
    "implement",
    "implementing",
    "mk_pr",
    "mk-pr",
    "mkpr",
    "review",
    "reviewing",
    "fixing",
    "fix-review",
    "fix_review",
    "verify",
    "verifying",
    "merge",
    "merging",
}
REQUIRED_PAYLOAD = {
    ("phase", "transition"): ("from", "to"),
    ("waiting_on", "set"): ("reason",),
    ("waiting_on", "clear"): ("reason", "was"),
    ("lease", "set"): ("holder",),
    ("lease", "clear"): ("holder",),
    ("sign_off", "recorded"): ("stage", "by", "words", "head"),
    ("ruling", "recorded"): ("id", "n", "words"),
    ("notify", "pending"): ("trigger", "project", "task", "id", "reason"),
    ("notify", "sent"): ("trigger", "project", "task", "id", "via", "by", "ok"),
    ("claude", "launch"): ("phase", "prompt_ref"),
    ("claude", "exit"): ("exit_code",),
    ("auth", "transition"): ("overall",),
    ("seat", "heartbeat"): ("seat_id", "wake_kind", "action_summary"),
    ("durable", "reconcile"): ("field", "old", "new"),
    ("note", "set"): ("message",),
    # §17.8 spec maintainer
    ("question", "raised"): ("question_id", "raised_by", "blocks", "route", "spec_refs"),
    ("question", "answered"): ("question_id", "verdict", "answered_by"),
    ("question", "escalated"): ("question_id", "blocks", "email_sent"),
    ("question", "resolved_by_operator"): ("question_id", "commit_sha"),
    ("spec_maintainer", "set"): ("holder", "reason"),
    ("spec_maintainer", "clear"): ("holder", "reason"),
    ("spec_maintainer", "rebound"): ("old_session_id", "new_session_id", "alias"),
    # §23.7: gates (task-scoped) and the runner teammate (project-level)
    ("gate", "opened"): ("escalation_id", "class", "standing"),
    ("gate", "decided"): ("escalation_id", "decision", "decided_by", "authority"),
    ("gate", "escalated"): ("escalation_id",),
    ("runner", "spawn"): ("name", "scope", "prompt_ref"),
    ("runner", "scope"): ("name", "scope", "prompt_ref"),
    ("runner", "rotate"): ("name", "reason"),
    ("runner", "stop"): ("name", "reason"),
    ("runner", "bound"): ("name", "previous"),
    # §23.2 the toolkit's ledger
    ("run", "opened"): ("run_id", "phase", "round", "agent_type", "expected_model", "expected_effort"),
    ("run", "bound"): ("run_id", "agent_id"),
    ("run", "stopped"): ("run_id", "agent_id"),
    ("run", "reported"): ("run_id", "outcome"),
    ("run", "abandoned"): ("run_id", "reason"),
    ("run", "recorded"): ("run_id", "mutants", "killed", "unbuilt", "survived"),  # §20.6 `ccp mutate`
    ("review", "recorded"): ("run_id", "verdict", "severity"),
    ("verify", "recorded"): ("run_id", "verdict", "head_sha"),
    ("allowance", "sample"): ("five_hour", "seven_day", "resets_at"),
    ("allowance", "decided"): ("to", "reason", "resets_at"),
    # §25.4 the session wake: the lead armed one (`session-wake --armed`), and it fired (`--fire`)
    ("allowance", "armed"): ("five_hour_resets_at", "wake_at"),
    ("allowance", "fired"): ("five_hour", "unparked"),
    ("plane", "proposed"): ("proposal_id", "need"),
    ("plane", "again"): ("proposal_id",),
    ("plane", "triaged"): ("proposal_id", "decision"),
    ("plane", "built"): ("proposal_id", "built_task"),
    # §4.5: `ccp init` adopted the product (the plane checkout's HEAD; the binding `written` or `kept`)
    ("plane", "adopted"): ("plane", "binding"),
    # §31.3: `ccp plane check --archive` moved or failed to move queue entries (counts only, no paths)
    ("plane", "archived"): ("day", "archived", "not_moved"),
    ("suite", "recorded"): ("suite_id", "exit_code", "seconds"),
    ("prefer", "set"): ("by", "reason"),
    ("prefer", "clear"): ("was", "reason"),
    # The retired architecture review and docs audit (§19.12): readers of old records only.
    # Review events are project-level: task_id is empty; they never touch task timers.
    ("architecture_review", "launch"): ("review_id", "phase", "prompt_ref"),
    ("architecture_review", "exit"): ("review_id", "phase", "exit_code"),
    ("architecture_review", "transition"): ("review_id", "from", "to"),
    ("architecture_review", "set"): ("holder", "reason"),
    ("architecture_review", "clear"): ("holder", "reason"),
    ("docs_audit", "launch"): ("review_id", "phase", "prompt_ref"),
    ("docs_audit", "exit"): ("review_id", "phase", "exit_code"),
    ("docs_audit", "transition"): ("review_id", "from", "to"),
    ("docs_audit", "set"): ("holder", "reason"),
    ("docs_audit", "clear"): ("holder", "reason"),
    ("architect", "launch"): ("review_id", "phase", "prompt_ref"),
    ("architect", "exit"): ("review_id", "phase", "exit_code"),
    ("architect", "transition"): ("review_id", "from", "to"),
    ("architect", "set"): ("holder", "reason"),
    ("architect", "clear"): ("holder", "reason"),
}
DEFAULT_CRON = "*/10 * * * *"
# Seat cadence (operator, 2026-09-24, token-burn reduction):
#   delivery-watchdog  */30 24/7 (was */10)
#   task-verifier      event-only — NO routine; the runner's subagent
#   task-runner        unchanged default (*/10) unless its heartbeat says otherwise
# These are only the heartbeat's recorded `cron_expected` defaults: every seat is event-only
# (§18.3).
EVENT_ONLY = "event"
SEAT_DEFAULT_CRON = {
    "task-runner": DEFAULT_CRON,
    "task-verifier": EVENT_ONLY,
    "delivery-watchdog": "*/30 * * * *",
    "design-seat": EVENT_ONLY,
}
# §18.3: no seat runs on a routine (the team lead sees idle and failure notices directly), so
# every seat is event-only: there is no stale rule for seats and no verifier-progress timer.
SECRET_VALUE_RE = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{8,}"
    r"|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
    r"|(?:ANTHROPIC_API_KEY|CLAUDE_API_KEY|ANTHROPIC_AUTH_TOKEN)\s*[:=]\s*\S+"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|ghp_[A-Za-z0-9]{20,})",
    re.I,
)


def die(msg: str, code: int = 1) -> None:
    print(f"observability: {msg}", file=sys.stderr)
    raise SystemExit(code)


def utcnow() -> datetime:
    raw = os.environ.get("OBS_NOW") or os.environ.get("NOW")
    if raw:
        return parse_dt(raw)
    return datetime.now(timezone.utc)


def fmt_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not value:
        raise ValueError("empty datetime")
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def looks_like_secret(text: str) -> bool:
    return bool(SECRET_VALUE_RE.search(text or ""))


def queue_root() -> Path:
    raw = os.environ.get("QUEUE_ROOT")
    if not raw:
        die("set QUEUE_ROOT to live queue dir outside product git")
    return Path(raw).expanduser().resolve()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


@contextmanager
def work_lock(root: Path):
    """SPEC §16.4: the lock every writer of QUEUE_ROOT/work.json holds across its read and write (the
    same `work.json.lock` as ccp's `file_lock`), so two writers at once cannot lose each other's change."""
    import fcntl  # noqa: PLC0415

    lp = Path(root) / "work.json.lock"
    lp.parent.mkdir(parents=True, exist_ok=True)
    with lp.open("a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n")
    tmp.replace(path)


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError as exc:
            die(f"events.jsonl line {i}: {exc}")
        if not isinstance(ev, dict):
            die(f"events.jsonl line {i}: not an object")
        out.append(ev)
    out.sort(key=lambda e: str(e.get("at") or ""))
    return out


def validate_event(ev: dict[str, Any], *, require_payload: bool = True) -> list[str]:
    errors: list[str] = []
    for key in ("at", "project_id", "task_id", "actor", "type", "op", "payload"):
        if key not in ev:
            errors.append(f"missing {key}")
    if ev.get("actor") not in ACTORS:
        errors.append(f"invalid actor {ev.get('actor')!r}")
    if ev.get("type") not in EVENT_TYPES:
        errors.append(f"invalid type {ev.get('type')!r}")
    if ev.get("op") not in EVENT_OPS:
        errors.append(f"invalid op {ev.get('op')!r}")
    if not ev.get("project_id"):
        errors.append("project_id empty")
    try:
        parse_dt(ev.get("at"))
    except Exception:
        errors.append("at is not RFC3339")
    payload = ev.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be object")
        payload = {}
    needed = REQUIRED_PAYLOAD.get((ev.get("type"), ev.get("op")))
    if require_payload and needed:
        for k in needed:
            if k not in payload:
                errors.append(f"payload missing {k}")
    dumped = json.dumps(ev, default=str)
    if looks_like_secret(dumped):
        errors.append("refusing secret-like value (API key / token / private key)")
    return errors


def events_path(root: Path) -> Path:
    """The ledger this queue root writes and reads: observability/events.jsonl."""
    return root / "observability" / "events.jsonl"


def append_event(root: Path, ev: dict[str, Any]) -> dict[str, Any]:
    errors = validate_event(ev)
    if errors:
        die("invalid event: " + "; ".join(errors))
    ev = {
        "at": ev["at"],
        "project_id": ev["project_id"],
        "task_id": ev.get("task_id") or "",
        "actor": ev["actor"],
        "type": ev["type"],
        "op": ev["op"],
        "payload": ev.get("payload") or {},
    }
    dest = events_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(ev, separators=(",", ":"), ensure_ascii=False)
    with dest.open("a") as fh:
        fh.write(line + "\n")
    return ev


def new_task_state(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "durable_status": None,
        "runtime_status": None,
        "phase": None,
        "waiting_on": None,
        "waiting_on_since": None,
        "planned_resume_at": None,
        "quota_class": None,
        "implementation_started_at": None,
        "wait_seconds": 0.0,
        "work_seconds": 0.0,
        "cursor": None,
        "claude_open": False,
        "claude_pid": None,
        "pr_url": None,
        "head_sha": None,
        "lease_holder": None,
        "lease_expires_at": None,
        "prompt_last_ref": None,
        "wait_detail": None,
        "wait_by_reason": {},
        "wait_by_qid": {},
    }


def is_work_phase(phase: str | None) -> bool:
    return bool(phase) and phase in WORK_PHASES


def accrue(state: dict[str, Any], until: datetime) -> None:
    cursor = state.get("cursor")
    if not cursor:
        state["cursor"] = until
        return
    if until <= cursor:
        state["cursor"] = until
        return
    delta = (until - cursor).total_seconds()
    if state.get("waiting_on"):
        state["wait_seconds"] += delta
        reason = str(state["waiting_on"])
        by_reason = state.setdefault("wait_by_reason", {})
        by_reason[reason] = by_reason.get(reason, 0.0) + delta
        detail = str(state.get("wait_detail") or "")
        if detail.startswith("sm-"):
            by_qid = state.setdefault("wait_by_qid", {})
            key = f"{detail}|{reason}"
            by_qid[key] = by_qid.get(key, 0.0) + delta
    elif is_work_phase(state.get("phase")) and state.get("claude_open"):
        state["work_seconds"] += delta
    state["cursor"] = until


def apply_event(
    tasks: dict[str, dict[str, Any]],
    seats: dict[str, dict[str, Any]],
    auth: dict[str, Any],
    ev: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> None:
    at = parse_dt(ev["at"])
    typ, op = ev.get("type"), ev.get("op")
    payload = ev.get("payload") or {}
    task_id = ev.get("task_id") or ""

    if typ in ("question", "spec_maintainer"):
        # §17.8: question + lock ledger. Never touches task timers.
        if extra is not None:
            apply_spec_maintainer_event(extra, ev)
        return

    if typ in LEGACY_EVENT_TYPES:
        return  # read past it

    if typ in TOOLKIT_EVENT_TYPES:
        # §23.2: the toolkit's own ledger. The phase, lease and waiting_on events ccp writes beside
        # these move the task; these never do.
        return

    if typ in TEAM_EVENT_TYPES:
        # §23.7: gate + runner ledger. Project-level; never moves a task phase,
        # opens a work interval or starts the wall timer. waiting_on for gates goes through
        # set-waiting-on.sh as for every other wait.
        if extra is not None:
            led = extra.setdefault(typ, {})
            led["last_op"] = op
            led["updated_at"] = ev["at"]
            for k in ("escalation_id", "decision", "scope", "reason", "name"):
                if payload.get(k) is not None:
                    led[k] = payload[k]
        return

    if typ in REVIEW_EVENT_TYPES:
        # §19.10 / §21: project-level review ledger (reviewer + triage calls, review lock). Not
        # implementer work: never moves a task phase, opens a work interval or starts the wall timer.
        if extra is not None:
            ar = extra.setdefault(typ, {})
            if op == "transition":
                ar["last_review_id"] = payload.get("review_id")
                ar["status"] = payload.get("to")
                ar["updated_at"] = ev["at"]
        return

    if typ == "seat" and op == "heartbeat":
        sid = payload.get("seat_id") or task_id
        if sid:
            seats.setdefault(sid, empty_seat(sid))
            seats[sid]["last_wake_at"] = ev["at"]
            seats[sid]["wake_kind"] = payload.get("wake_kind")
            seats[sid]["last_action"] = payload.get("action_summary") or ""
            if payload.get("cron_expected"):
                seats[sid]["cron_expected"] = payload["cron_expected"]
        return

    if typ == "auth" and op == "transition":
        auth["overall"] = payload.get("overall") or auth.get("overall") or "ok"
        auth["checked_at"] = ev["at"]
        failed = payload.get("failed_checks") or []
        if isinstance(failed, list):
            auth["failed_checks"] = [str(x) for x in failed]
        if "ambient_api_key" in payload:
            auth["ambient_api_key"] = bool(payload["ambient_api_key"])
        return

    if not task_id:
        return

    st = tasks.setdefault(task_id, new_task_state(task_id))
    accrue(st, at)

    if typ == "phase" and op == "transition":
        dest = payload.get("to")
        st["phase"] = dest
        if dest in STATUS_ENUM:
            st["runtime_status"] = dest
        if dest in ("implementing", "implement") and not st["implementation_started_at"]:
            st["implementation_started_at"] = ev["at"]
    elif typ == "waiting_on" and op == "set":
        st["waiting_on"] = payload.get("reason")
        st["waiting_on_since"] = ev["at"]
        st["planned_resume_at"] = payload.get("resets_at") or payload.get("planned_resume_at")
        st["quota_class"] = payload.get("quota_class")
        st["wait_detail"] = payload.get("detail")
        if st["waiting_on"] == "blocked":
            st["runtime_status"] = "blocked"
    elif typ == "waiting_on" and op == "clear":
        st["waiting_on"] = None
        st["waiting_on_since"] = None
        st["planned_resume_at"] = None
        st["quota_class"] = None
        st["wait_detail"] = payload.get("detail")
    elif typ == "lease" and op == "set":
        st["lease_holder"] = payload.get("holder")
        st["lease_expires_at"] = payload.get("expires_at")
        if st["runtime_status"] in (None, "pending"):
            st["runtime_status"] = "leased"
            st["phase"] = st["phase"] or "leased"
    elif typ == "lease" and op == "clear":
        st["lease_holder"] = None
        st["lease_expires_at"] = None
    elif typ == "claude" and payload.get("phase") == "spec-maintainer":
        # A headless call is audited like any plane launch, but it is not
        # implementer work — it must not move the task phase, open a work interval,
        # or start the wall timer.
        if op == "launch":
            st["prompt_last_ref"] = payload.get("prompt_ref") or st.get("prompt_last_ref")
    elif typ == "claude" and op == "launch":
        st["claude_open"] = True
        st["claude_pid"] = payload.get("pid")
        st["prompt_last_ref"] = payload.get("prompt_ref")
        if payload.get("phase"):
            st["phase"] = payload["phase"]
        if not st["implementation_started_at"]:
            st["implementation_started_at"] = ev["at"]
            if not st["runtime_status"] or st["runtime_status"] in ("pending", "leased"):
                st["runtime_status"] = "implementing"
    elif typ == "claude" and op == "exit":
        st["claude_open"] = False
        st["claude_pid"] = None
    elif typ == "durable" and op == "reconcile":
        field = payload.get("field")
        if field in ("status", "durable_status", "INDEX status", "INDEX.yaml status", "meta.status"):
            st["durable_status"] = payload.get("new")
        if field in ("pr_url", "pr"):
            st["pr_url"] = payload.get("new")
        if field in ("head_sha", "merge_sha"):
            st["head_sha"] = payload.get("new")
    elif typ == "note" and op == "set":
        pass

    if payload.get("pr_url"):
        st["pr_url"] = payload["pr_url"]
    if payload.get("head_sha"):
        st["head_sha"] = payload["head_sha"]


def apply_spec_maintainer_event(extra: dict[str, Any], ev: dict[str, Any]) -> None:
    typ, op = ev.get("type"), ev.get("op")
    payload = ev.get("payload") or {}
    if typ == "spec_maintainer":
        if op == "set":
            extra["lock"] = {
                "holder": payload.get("holder"),
                "since": ev.get("at"),
                "question_id": payload.get("question_id"),
            }
        elif op == "clear":
            extra["lock"] = None
        elif op == "rebound":
            extra["rebound"] = {"at": ev.get("at"), **payload}
        return
    qid = payload.get("question_id")
    if not qid:
        return
    q = extra.setdefault("questions", {}).setdefault(
        qid,
        {
            "question_id": qid,
            "task_id": ev.get("task_id") or None,
            "status": "open",
            "verdict": None,
            "route": None,
            "dispatch": None,
            "raised_by": None,
            "blocks": [],
            "since": ev.get("at"),
        },
    )
    if op == "raised":
        q["raised_by"] = payload.get("raised_by")
        q["blocks"] = list(payload.get("blocks") or [])
        q["route"] = payload.get("route")
        q["since"] = ev.get("at")
        q["task_id"] = ev.get("task_id") or q.get("task_id")
    elif op == "answered":
        q["verdict"] = payload.get("verdict")
        q["status"] = "escalated" if payload.get("verdict") == "needs_operator" else "answered"
    elif op == "escalated":
        q["status"] = "escalated"
        q["verdict"] = q.get("verdict") or "needs_operator"
    elif op == "resolved_by_operator":
        q["status"] = "answered"
        q["verdict"] = "resolved"


def _pid_alive_raw(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False


def lock_is_stale(lock: dict[str, Any], now: datetime | None = None, host: str | None = None) -> bool:
    """§11.2 stale rule.

    Plane holder: stale when its pid is dead on this host (even inside the TTL), or when
    the TTL has passed and the pid cannot be checked (other host). Operator: stale only after TTL.
    """
    import socket

    now = now or datetime.now(timezone.utc)
    try:
        since = parse_dt(lock.get("since"))
        ttl = int(lock.get("ttl_seconds") or 0)
        expired = (now - since).total_seconds() > ttl
    except Exception:
        expired = True
    if lock.get("holder") == "operator":
        return expired
    local = host or socket.gethostname()
    lock_host = str(lock.get("host") or "")
    same_host = not lock_host or lock_host.split(".")[0].lower() == local.split(".")[0].lower()
    if same_host and lock.get("pid"):
        return not _pid_alive_raw(lock.get("pid"))
    return expired


def default_cron(sid: str | None) -> str:
    return SEAT_DEFAULT_CRON.get(sid or "", DEFAULT_CRON)


def empty_seat(sid: str | None = None) -> dict[str, Any]:
    return {
        "last_wake_at": None,
        "wake_kind": None,
        "last_action": "",
        "cron_expected": default_cron(sid),
    }


def resolve_durable_docs_dir(root: Path) -> Path | None:
    """The product's task-log directory for the queue `root` (§8.3): the `DURABLE_DOCS` environment variable
    when set, else `task_log.dir` of the product's plane.json (`docs/delivery` unless it sets one) under
    the binding's `product_root`; None when there is none."""
    env = os.environ.get("DURABLE_DOCS")
    if env:
        return Path(env).expanduser()
    product_root = binding_str(binding_data(root), "product_root")
    if not product_root:
        return None
    base = Path(product_root).expanduser()
    cfg = _product_config(base)
    rel = cfg.task_log["dir"] if cfg is not None else _config().TASK_LOG_DEFAULTS["dir"]
    return (base / str(rel)).resolve()


_BINDING_LINE = re.compile(r"^([ \t]*)([^\s#:-][^:#]*?):(?:[ \t]+(.*))?$")


def read_binding(text: str) -> dict[str, Any]:
    """SPEC §8.3: the one parser of a binding's text. The `key: value` lines as nested objects by
    indentation: a scalar is its string (quotes and an ` #` comment dropped), a key with no value on its
    line is a dict of what is indented under it (empty when nothing is). List items are not read."""
    out: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, out)]
    for line in text.splitlines():
        m = _BINDING_LINE.match(line.split(" #", 1)[0].rstrip())
        if not m:
            continue
        depth = len(m.group(1).expandtabs(2))
        while stack[-1][0] >= depth:
            stack.pop()
        node: dict[str, Any] = {}
        stack[-1][1][m.group(2).strip()] = (m.group(3) or "").strip().strip("'\"") or node
        stack.append((depth, node))
    return out


def binding_str(data: dict[str, Any], *path: str) -> str | None:
    """The scalar at `path` in a `read_binding` dict (`binding_str(d, "runner", "name")`), or None when
    the key is absent, has no value or holds a block."""
    node: Any = data
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, str) and node else None


def _yaml_block_scalars(text: str, block: str) -> dict[str, str]:
    """The scalars directly under a top-level `block:` of the binding, by `read_binding`."""
    node = read_binding(text).get(block)
    return {k: v for k, v in node.items() if isinstance(v, str)} if isinstance(node, dict) else {}


def bindings_dir() -> Path:
    """SPEC §8.3: this plane's bindings, `projects/` beside its code (`CCP_BINDINGS_DIR` overrides it)."""
    return Path(os.environ.get("CCP_BINDINGS_DIR") or Path(__file__).resolve().parents[2] / "projects")


MACHINE_FILE = "machine.json"


def machine_path() -> Path:
    """SPEC §8.3: the machine file, `machine.json` in the bindings directory (so `CCP_BINDINGS_DIR` moves it
    with the bindings). Its name does not match the bindings' `*.yaml` glob. Contract
    `contracts/machine.schema.json`."""
    return bindings_dir() / MACHINE_FILE


def read_machine() -> dict[str, Any]:
    """The machine file's keys; empty when it is missing, unreadable or not a JSON object."""
    try:
        data = json.loads(machine_path().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _same_dir(a: str, b: Path) -> bool:
    try:
        return Path(a).expanduser().resolve() == b.resolve()
    except (OSError, RuntimeError):
        return False


def binding_path(root: Path) -> Path | None:
    """SPEC §8.3: the one resolver every binding reader goes through, for the queue `root`.

    1. `PROJECT_YAML` (or `PLANE_PROJECT_YAML`), when it names a file: an explicit choice;
    2. the binding in `bindings_dir()` whose `queue_root` is this queue;
    3. `QUEUE_ROOT/project.yaml`, the retired queue copy, read only when no binding names the queue
       (a queue set up before the copy was retired).
    """
    for key in ("PROJECT_YAML", "PLANE_PROJECT_YAML"):
        v = os.environ.get(key)
        if v and Path(v).expanduser().is_file():
            return Path(v).expanduser()
    d = bindings_dir()
    for b in sorted(d.glob("*.yaml")) if d.is_dir() else []:
        try:
            queue = binding_str(read_binding(b.read_text()), "queue_root")
        except OSError:
            continue
        if queue and _same_dir(queue, root):
            return b
    p = root / "project.yaml"
    return p if p.is_file() else None


def product_binding(project_id: str, roots: Any) -> Path | None:
    """SPEC §8.3, §9.2: the binding of the product `project_id` (the caller checks the id is well formed):
    the file `PROJECT_YAML` names, when it is set, ahead of `<bindings_dir()>/<project_id>.yaml` (a
    sandbox's binding sits outside the bindings directory, §29.3); either only when its `product_root` is
    one of `roots` (real paths: the checkout and its main checkout). A scratch clone or a fork that names
    a live project's id gets nothing."""
    explicit = os.environ.get("PROJECT_YAML")
    for b in ([Path(explicit).expanduser()] if explicit else []) + [bindings_dir() / f"{project_id}.yaml"]:
        if not b.is_file():
            continue
        root = binding_str(read_binding(b.read_text()), "product_root")
        if root and Path(root).expanduser().resolve() in roots:
            return b
    return None


def binding_where(root: Path) -> str:
    """How a warning names the binding of the queue `root`: its path (`binding_path`), else `the binding`."""
    p = binding_path(root)
    return str(p) if p else "the binding"


def binding_data(root: Path) -> dict[str, Any]:
    """The binding of the queue `root` (`binding_path`), parsed by `read_binding`, with one warning for each
    key it sets that the plane no longer reads (`warn_binding`); empty when there is none."""
    data = read_binding(project_yaml_text(root))
    warn_binding(data, binding_where(root))
    return data


# §8.3: what a binding holds, and what became of the rest. The runner's agent, name and worktree and the
# task-log directory are derived; the runner's limits are constants (§29.3); the lead's compaction window
# moved to the product's own settings.
BINDING_KEPT = ("project_id", "integration_branch", "product_root", "queue_root", "ci", "notes")
RUNNER_AGENT = "ccp:delivery-runner"
RUNNER_NAME = "runner"
# The constants' short names, as callers read them, and the binding key each was set under.
RUNNER_LIMITS = {"after_tasks": "runner.rotate_after_tasks", "at_context_tokens": "runner.rotate_at_context_tokens",
                 "idle_limit": "runner.idle_block_limit"}
WINDOW_KEY = "lead.auto_compact_window"
DERIVED_KEYS = {
    "runner.agent_type": f"the runner's agent is {RUNNER_AGENT}",
    "runner.name": f"the runner's name is {RUNNER_NAME}",
    "runner.worktree": "the runner's worktree is <product_root>/<worktrees.dir>/runner",
    "durable_docs_path": "the task log is plane.json task_log.dir, docs/delivery unless it sets one",
}
MOVED_KEYS = {WINDOW_KEY: "the product's .claude/settings.json autoCompactWindow, which `ccp init` writes when it is absent"}


def _config() -> Any:
    """`ccp.config`, for the constant mechanism (`constant_override`); importable from a script here too."""
    try:
        from ccp import config  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from ccp import config  # noqa: PLC0415
    return config


def binding_constants() -> dict[str, Any]:
    """The runner's constants (§29.3) as `config.constant_override`'s registry: each `RUNNER_LIMITS` key with
    its value (`rotate_at_context_tokens` is None, shown as off)."""
    c = _config()
    return {"runner.rotate_after_tasks": c.Outcome(c.CONSTANT, value=4),
            "runner.rotate_at_context_tokens": c.Outcome(c.CONSTANT, value=None, shown="off"),
            "runner.idle_block_limit": c.Outcome(c.CONSTANT, value=3)}


def _leaves(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Each dotted key of a `read_binding` dict that holds a value (a scalar, or a block with nothing in it)."""
    out: list[tuple[str, Any]] = []
    for k, v in data.items():
        out += _leaves(v, f"{prefix}{k}.") if isinstance(v, dict) and v else [(f"{prefix}{k}", v)]
    return out


def _limit_value(raw: str, constant: Any) -> tuple[bool, Any]:
    """A limit as the binding wrote it: (True, the whole number), (True, None) for `null` where the constant is
    off (None), else (False, None): not a value the limit takes."""
    if raw.strip().lower() in ("null", "~") and constant is None:
        return True, None
    if re.fullmatch(r"[0-9]+", raw.strip()) and int(raw) >= 1:
        return True, int(raw)
    return False, None


def binding_findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    """§8.3, §29.3: each key a `read_binding` dict sets that the plane no longer reads, as `{key, outcome, set}`:
    `removed` (ignored: any key `BINDING_KEPT` does not hold, `why` for a derived one), `constant` (a runner
    limit: `constant`, `differs`, and `use`, the value that applies: the binding's when it is a valid other
    value) or `moved` (`replacement`: the lead's compaction window)."""
    consts = binding_constants()
    out: list[dict[str, Any]] = []
    for key, given in _leaves(data):
        if key.split(".")[0] in BINDING_KEPT:
            continue
        f: dict[str, Any] = {"key": key, "set": given}
        if key in consts:
            const = consts[key].value
            ok, value = _limit_value(given, const) if isinstance(given, str) else (False, None)
            f.update(outcome="constant", constant=const, valid=ok, use=value if ok else const,
                     differs=not (ok and value == const))
        elif key in MOVED_KEYS:
            f.update(outcome="moved", replacement=MOVED_KEYS[key])
        else:
            f.update(outcome="removed", why=DERIVED_KEYS.get(key, ""))
        out.append(f)
    return out


def warn_binding(data: dict[str, Any], where: str) -> None:
    """One warning on stderr for each key `binding_findings` lists (once per `where` and process): a removed key
    is ignored, a limit set to another value still applies, the lead's window is used by `ccp init`."""
    c = _config()
    consts = binding_constants()
    for f in binding_findings(data):
        key = f["key"]
        if f["outcome"] == "removed":
            c._warn_once(where, f"{where}: {key} is removed and ignored" + (f": {f['why']}" if f["why"] else "")
                         + "; delete it (SPEC §29.3)")
        elif f["outcome"] == "moved":
            c._warn_once(where, f"{where}: {key} moved to {f['replacement']}; `ccp init` writes the binding's value "
                         "there while it is set: set it there and delete the key (SPEC §29.3)")
        elif f["valid"]:
            c.constant_override(key, f["use"], where=where, registry=consts)
        else:
            c._warn_once(where, f"{where}: {key} is {f['set']!r}, which is no value it takes; the constant "
                         f"{f['constant']!r} applies: delete the key (SPEC §29.3)")


def runner_limits(root: Path) -> dict[str, int | None]:
    """§8.3, §29.3: the runner's limits for the queue `root`, by `RUNNER_LIMITS`' short names: the constants
    (rotation after 4 tasks, no rotation by context, 3 idle blocks), or the value the binding still sets
    (warned, `warn_binding`)."""
    findings = {f["key"]: f for f in binding_findings(binding_data(root))}
    consts = binding_constants()
    return {short: findings[key]["use"] if key in findings else consts[key].value
            for short, key in RUNNER_LIMITS.items()}


def _product_config(product_root: Path) -> Any:
    """The product's `ccp.config` Config (E16: the one reader of plane.json), or None when plane.json is missing
    or does not load. The load's warnings are not printed."""
    cfg = _config()
    try:
        with redirect_stderr(io.StringIO()):
            return cfg.load(product_root)
    except Exception:  # noqa: BLE001  (no plane.json, invalid JSON, a ConfigError: the defaults, as before)
        return None


def runner_worktree(root: Path) -> str | None:
    """§8.3, §16: the runner's worktree for the queue `root`, derived: `<product_root>/<worktrees.dir>/runner`
    (`.plane-runtime` while plane.json names no directory); with several runners each slot's is this plus
    `-<slot>`. None when the binding has no `product_root`."""
    product_root = binding_str(binding_data(root), "product_root")
    if not product_root:
        return None
    base = Path(product_root).expanduser()
    cfg = _product_config(base)
    wdir = ((cfg.worktrees or {}).get("dir") if cfg is not None else None) or _config().WORKTREES_DIR
    return os.path.normpath(base / str(wdir) / RUNNER_NAME)


def project_yaml_text(root: Path) -> str:
    """The binding's text for the queue `root` (`binding_path`), or "" when there is none."""
    p = binding_path(root)
    if p is None:
        return ""
    try:
        return p.read_text()
    except OSError:
        return ""


def main(argv: list[str]) -> int:
    """`lib.py binding <file>`: the top-level scalars of a binding file (`read_binding`) as one JSON
    object, for the shell that reads a binding (SPEC §8.3: no second parser). A block is not printed."""
    if len(argv) != 2 or argv[0] != "binding":
        print("usage: lib.py binding <binding file>", file=sys.stderr)
        return 2
    try:
        text = Path(argv[1]).read_text()
    except OSError as e:
        print(f"lib.py: cannot read {argv[1]}: {e.strerror or e}", file=sys.stderr)
        return 1
    print(json.dumps({k: v for k, v in read_binding(text).items() if isinstance(v, str)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
