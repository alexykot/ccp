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

import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEAT_IDS = ("task-runner", "task-verifier", "delivery-watchdog", "design-seat")
ACTORS = SEAT_IDS + ("adapter", "operator", "system", "plane-session")  # plane-session: §31.5 triage
# §17.8 adds question + spec_maintainer types and their ops; §19.10 adds architecture_review;
# §21 adds docs_audit (same ops and payloads: both are §19 review kinds); §23.7 adds gate + runner
# (gate opened/decided, runner spawn/scope/rotate/stop) and the design-seat actor;
# §19 adds architect (a third review kind: passes and shapes).
# §23.2 adds the toolkit's ledger: run (a worker launch: opened, bound, stopped, reported, abandoned),
# review and verify (recorded verdicts), allowance (samples) and plane (ccp proposals). None of them
# moves a task phase or a timer: the `phase` events ccp writes beside them do that. §14.1 adds suite
# (one `ccp suite run`, recorded when it ends). §10.4 adds prefer (the lead's next tasks for the runner,
# work.json `next_tasks`: set by `ccp tasks prefer`, cleared by it; the claim that takes one removes it), and
# hold (the lead's hold on a task, work.json `held`: `ccp tasks hold`, `next` passes over it).
REVIEW_EVENT_TYPES = ("architecture_review", "docs_audit", "architect")
TEAM_EVENT_TYPES = ("gate", "runner")
TOOLKIT_EVENT_TYPES = ("run", "review", "verify", "allowance", "plane", "suite", "prefer", "hold")
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
    "armed",
    "fired",
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
    ("suite", "recorded"): ("suite_id", "exit_code", "seconds"),
    ("prefer", "set"): ("by", "reason"),
    ("prefer", "clear"): ("was", "reason"),
    # §19.10 architecture review (project-level: task_id is empty; never touches task timers)
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
EVENT_ONLY_VALUES = {"event", "event-only", "none", "null", ""}
EVENT_ONLY_SEATS = {"task-verifier", "design-seat"}
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
    out.sort(key=lambda e: (str(e.get("at") or ""), i_key(e)))
    return out


def i_key(_ev: dict[str, Any]) -> int:
    return 0


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


def event_id(ev: dict[str, Any]) -> str:
    """An event's identity: the sha256 of its canonical JSON. Events carry no id field (the schema is
    closed), and two writes of the same event are the same line, so a re-pulled event is a duplicate."""
    import hashlib  # noqa: PLC0415

    return hashlib.sha256(json.dumps(ev, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode()).hexdigest()


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

    if typ == "hosting":
        return  # an old ledger's hosting switch (Grok hosting is gone): read past it

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


def is_event_only(sid: str | None, cron: str | None) -> bool:
    if sid in EVENT_ONLY_SEATS:
        return True
    return str(cron or "").strip().lower() in EVENT_ONLY_VALUES


def empty_seat(sid: str | None = None) -> dict[str, Any]:
    return {
        "last_wake_at": None,
        "wake_kind": None,
        "last_action": "",
        "cron_expected": default_cron(sid),
    }


def parse_index_statuses(text: str) -> dict[str, str]:
    """Best-effort INDEX.yaml reader (no PyYAML dependency)."""
    out: dict[str, str] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^\s*-\s+id:\s*(\S+)\s*$", line)
        if m:
            current = m.group(1).strip().strip("'\"")
            continue
        m = re.match(r"^\s+status:\s*(\S+)\s*$", line)
        if m and current:
            out[current] = m.group(1).strip().strip("'\"")
            current = None
    return out


def _parse_simple_yaml_scalar_map(text: str) -> dict[str, str]:
    """Tiny YAML subset: top-level `key: value` scalars (no nested structures)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        if s.startswith("-"):
            continue
        if line[:1].isspace():
            continue
        key, _, val = s.partition(":")
        key = key.strip()
        if not key:
            continue
        val = val.strip().strip(chr(34)+chr(39))
        if val:
            out[key] = val
    return out


def resolve_durable_docs_dir(root: Path) -> Path | None:
    """Resolve product docs/delivery for INDEX status mirror.

    Order:
      1. DURABLE_DOCS env
      2. PROJECT_YAML / QUEUE_ROOT/project.yaml / PLANE_PROJECT_YAML
         fields: durable_docs (abs) OR product_root + durable_docs_path
    """
    env = os.environ.get("DURABLE_DOCS")
    if env:
        return Path(env).expanduser()

    yaml_candidates: list[Path] = []
    for key in ("PROJECT_YAML", "PLANE_PROJECT_YAML"):
        v = os.environ.get(key)
        if v:
            yaml_candidates.append(Path(v).expanduser())
    yaml_candidates.append(root / "project.yaml")

    for ypath in yaml_candidates:
        if not ypath.is_file():
            continue
        try:
            data = _parse_simple_yaml_scalar_map(ypath.read_text())
        except OSError:
            continue
        abs_docs = data.get("durable_docs") or data.get("durable_docs_abs")
        if abs_docs:
            return Path(abs_docs).expanduser()
        product_root = data.get("product_root") or data.get("hamlet_root")
        rel = data.get("durable_docs_path") or "docs/delivery"
        if product_root:
            return (Path(product_root).expanduser() / rel).resolve()

    return None


def load_durable_statuses(root: Path) -> dict[str, str]:
    candidates: list[Path] = []
    docs_dir = resolve_durable_docs_dir(root)
    if docs_dir is not None:
        candidates.extend([docs_dir / "INDEX.yaml", docs_dir / "INDEX.yml"])
    candidates.extend(
        [
            root / "durable" / "INDEX.yaml",
            root / "docs" / "delivery" / "INDEX.yaml",
        ]
    )
    for index in candidates:
        if index.is_file():
            try:
                return parse_index_statuses(index.read_text())
            except OSError:
                return {}
    # SPEC §5.7: a product may keep no index; the task files are the record.
    out: dict[str, str] = {}
    tdir = (docs_dir or root / "docs" / "delivery") / "tasks"
    for f in sorted(tdir.glob("*.md")) if tdir.is_dir() else []:
        try:
            m = re.search(r"^status:\s*([^\s#]+)", f.read_text(), re.M)
        except OSError:
            continue
        if m:
            out[f.stem] = m.group(1).strip("'\"")
    return out


def _yaml_block_scalars(text: str, block: str) -> dict[str, str]:
    """Tiny YAML subset: indented `key: value` scalars under a top-level `block:`."""
    out: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not line[:1].isspace():
            inside = line.split("#", 1)[0].strip() == f"{block}:"
            continue
        if inside and ":" in line:
            key, _, val = line.strip().partition(":")
            val = val.split(" #", 1)[0].strip().strip(chr(34) + chr(39))
            if key.strip() and val:
                out[key.strip()] = val
    return out


def project_yaml_text(root: Path) -> str:
    for key in ("PROJECT_YAML", "PLANE_PROJECT_YAML"):
        v = os.environ.get(key)
        if v and Path(v).expanduser().is_file():
            try:
                return Path(v).expanduser().read_text()
            except OSError:
                pass
    p = root / "project.yaml"
    if p.is_file():
        try:
            return p.read_text()
        except OSError:
            return ""
    return ""


def _yaml_nested_map(text: str, block: str, key: str) -> dict[str, str]:
    """Tiny YAML subset: the `k: v` scalars of the map `key:` nested under a top-level `block:`."""
    out: dict[str, str] = {}
    inside = nested = False
    depth = 0
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not line[:1].isspace():
            inside = line.split("#", 1)[0].strip() == f"{block}:"
            nested = False
            continue
        if not inside:
            continue
        indent = len(line) - len(line.lstrip())
        k, _, v = line.strip().partition(":")
        if nested and indent > depth:
            v = v.split(" #", 1)[0].strip().strip(chr(34) + chr(39))
            if k.strip() and v:
                out[k.strip().strip(chr(34) + chr(39))] = v
            continue
        nested = k.strip() == key and not v.split(" #", 1)[0].strip()
        depth = indent
    return out


def email_cfg(root: Path) -> dict[str, str]:
    """The binding's `email` block. A `prefix_by_team` map left from Grok hosting is read for its
    `claude-team` entry, which overrides `subject_prefix`."""
    text = project_yaml_text(root)
    by_team = _yaml_nested_map(text, "email", "prefix_by_team")
    cfg = {k: v for k, v in _yaml_block_scalars(text, "email").items() if k not in by_team}
    if "claude-team" in by_team:
        cfg["subject_prefix"] = by_team["claude-team"]
    return cfg


def project_seat_agent(root: Path, role: str) -> str | None:
    return _yaml_block_scalars(project_yaml_text(root), "seats").get(role)
