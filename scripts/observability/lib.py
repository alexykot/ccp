#!/usr/bin/env python3
"""Fold QUEUE_ROOT/observability/events.jsonl + live probes into now.json / STATUS.md.

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

import argparse
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SEAT_IDS = ("task-runner", "task-verifier", "delivery-watchdog", "design-seat")
ACTORS = SEAT_IDS + ("adapter", "operator", "system", "plane-session")  # plane-session: §31.5 triage
# §17.8 adds question + spec_maintainer types and their ops; §19.10 adds architecture_review;
# §21 adds docs_audit (same ops and payloads: both are §19 review kinds); §23.7 adds gate + runner
# (gate opened/decided, runner spawn/scope/rotate/stop) and the design-seat actor;
# §19 adds architect (a third review kind: passes and shapes). The first two are retired (§19.12):
# their types stay so an older ledger still reads; nothing writes them any more.
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
BLOCKER_KINDS = ("quota", "reauth", "operator_decision", "spec_maintainer", "design_seat", "operator_step", "stale_seat",
                 "verify_stale", "ambient_key", "other",
                 # read-only: a snapshot written before 2026-11-05 may carry the retired twelve-hour
                 # backstop blocker (ADR-0032 D2); nothing emits it any more.
                 "backstop")
# Waits that surface as their own blocker kind (a question-driven operator_decision wait keeps that kind,
# detail=question_id).
WAIT_BLOCKER_KINDS = ("quota", "reauth", "operator_decision", "spec_maintainer", "design_seat", "operator_step")

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
#   task-verifier      event-only — NO routine; woken by Runner on formal-submit
#                      or by Watchdog on verify_stale. Never time-stale.
#   task-runner        unchanged default (*/10) unless its heartbeat says otherwise
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
# every seat is event-only and never time-stale on the board.
# Stale floor; per-seat threshold = max(floor, 2.5 × cron interval):
#   */10 → 25m (unchanged), */30 → 75m.
STALE_AFTER_SECONDS = 25 * 60
STALE_INTERVAL_MULTIPLIER = 2.5
# verify_stale: task submitted/verifying with no verdict and no verifier progress
# (verifier event or task-scoped heartbeat) for >= this many minutes. Aligned with
# the 30m Watchdog tick → worst-case detection ~60m after submit.
# Override: env VERIFY_STALE_MINUTES or project.yaml cadence.verify_stale_minutes.
VERIFY_STALE_MINUTES_DEFAULT = 30
VERIFY_PHASES = {"submitted", "verifying", "verify"}
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


def hours_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 3600.0)


def round_hours(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 1)


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


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.environ.get("OBS_SKIP_PS") == "1":
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


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
        "verify_since": None,
        "verifier_last_at": None,
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
        if sid == "task-verifier" and task_id:
            tasks.setdefault(task_id, new_task_state(task_id))["verifier_last_at"] = ev["at"]
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
    if ev.get("actor") == "task-verifier":
        st["verifier_last_at"] = ev["at"]

    if typ == "phase" and op == "transition":
        dest = payload.get("to")
        if dest in VERIFY_PHASES:
            if dest == "submitted" or not st.get("verify_since"):
                st["verify_since"] = ev["at"]
        else:
            st["verify_since"] = None
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


def load_question_files(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    qdir = root / "questions"
    if not qdir.is_dir():
        return out
    for path in sorted(qdir.glob("sm-*.json")):
        if path.name.endswith(".answer.json"):
            continue
        try:
            data = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        qid = data.get("question_id") or path.stem
        ans_path = qdir / f"{qid}.answer.json"
        answer = None
        if ans_path.is_file():
            try:
                answer = read_json(ans_path)
            except (OSError, json.JSONDecodeError):
                answer = None
        data["_answer"] = answer if isinstance(answer, dict) else None
        out[qid] = data
    return out


def build_questions(
    root: Path, extra: dict[str, Any], tasks: dict[str, dict[str, Any]], now: datetime
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (extra.get("questions") or {}).items()}
    for qid, data in load_question_files(root).items():
        q = merged.setdefault(qid, {"question_id": qid, "since": data.get("asked_at")})
        ans = data.get("_answer") or {}
        q.update(
            {
                "task_id": data.get("task_id") or q.get("task_id"),
                "status": data.get("status") or q.get("status") or "open",
                "route": data.get("route") or q.get("route"),
                "dispatch": data.get("dispatch") or q.get("dispatch"),
                "raised_by": data.get("raised_by") or q.get("raised_by"),
                "blocks": list(data.get("blocks") or q.get("blocks") or ([data["task_id"]] if data.get("task_id") else [])),
                "since": data.get("asked_at") or q.get("since"),
            }
        )
        if ans.get("verdict"):
            q["verdict"] = ans.get("verdict")
    rows = []
    for qid, q in merged.items():
        blocks = list(q.get("blocks") or [])
        waiting = None
        for tid in blocks:
            st = tasks.get(tid) or {}
            if st.get("waiting_on") in ("spec_maintainer", "operator_decision", "steerer") \
                    and str(st.get("wait_detail") or "") == qid:
                waiting = st["waiting_on"]
                break

        def q_hours(reason: str) -> float | None:
            vals = []
            for tid in [q.get("task_id")] + blocks:
                st = tasks.get(tid or "") or {}
                sec = (st.get("wait_by_qid") or {}).get(f"{qid}|{reason}")
                if sec:
                    vals.append(sec)
                    if tid == q.get("task_id"):
                        break
            return round_hours(max(vals) / 3600.0) if vals else 0.0

        status = q.get("status") or "open"
        if status not in ("open", "answered", "escalated"):
            status = "open"
        verdict = q.get("verdict")
        if verdict not in ("resolved", "needs_operator", "not_a_spec_question"):
            verdict = None
        route = q.get("route") if q.get("route") in ("spec_maintainer", "steerer") else None
        rows.append(
            {
                "question_id": qid,
                "task_id": q.get("task_id"),
                "status": status,
                "verdict": verdict,
                "route": route,
                "dispatch": q.get("dispatch"),
                "raised_by": q.get("raised_by"),
                "blocks": blocks,
                "waiting_on": waiting,
                "since": q.get("since"),
                "maintainer_wait_hours": q_hours("spec_maintainer"),
                "operator_wait_hours": q_hours("operator_decision"),
            }
        )
    rows.sort(key=lambda r: (0 if r["status"] in ("open", "escalated") else 1, str(r.get("since") or "")))
    return rows


def default_cron(sid: str | None) -> str:
    return SEAT_DEFAULT_CRON.get(sid or "", DEFAULT_CRON)


def is_event_only(sid: str | None, cron: str | None) -> bool:
    if sid in EVENT_ONLY_SEATS:
        return True
    return str(cron or "").strip().lower() in EVENT_ONLY_VALUES


def cron_interval_seconds(cron: str | None) -> int | None:
    """Minute-field interval for simple specs (`*/N …` → N min; `M * * * *` → 60 min)."""
    fields = str(cron or "").split()
    if not fields:
        return None
    minute = fields[0]
    m = re.fullmatch(r"\*/(\d+)", minute)
    if m and int(m.group(1)) > 0:
        return int(m.group(1)) * 60
    if re.fullmatch(r"\d+", minute) and len(fields) > 1 and fields[1] == "*":
        return 60 * 60
    return None


def stale_after_seconds(cron: str | None) -> int:
    interval = cron_interval_seconds(cron)
    if not interval:
        return STALE_AFTER_SECONDS
    return max(STALE_AFTER_SECONDS, int(interval * STALE_INTERVAL_MULTIPLIER))


def empty_seat(sid: str | None = None) -> dict[str, Any]:
    return {
        "last_wake_at": None,
        "wake_kind": None,
        "last_action": "",
        "cron_expected": default_cron(sid),
        "stale": False,
    }


def merge_task_file(st: dict[str, Any], task: dict[str, Any]) -> None:
    # Events win for timers / waiting_on / runtime_status. Task JSON fills gaps.
    if st.get("runtime_status") is None and task.get("status"):
        st["runtime_status"] = task.get("status")
    if not st.get("implementation_started_at"):
        st["implementation_started_at"] = task.get("implementation_started_at")
    if st.get("lease_holder") is None:
        st["lease_holder"] = task.get("lease_holder")
    if not st.get("pr_url"):
        st["pr_url"] = task.get("pr_url")
    if not st.get("head_sha"):
        st["head_sha"] = task.get("merge_sha") or task.get("head_sha")
    if st.get("waiting_on") is None and task.get("waiting_on"):
        st["waiting_on"] = task.get("waiting_on")
        st["waiting_on_since"] = task.get("waiting_on_since")
        st["planned_resume_at"] = task.get("planned_resume_at")
        st["quota_class"] = task.get("quota_class")
    if not st.get("phase") and task.get("status"):
        st["phase"] = task.get("status")


def merge_work_json(st: dict[str, Any], work: dict[str, Any]) -> None:
    if work.get("waiting_on") and st.get("waiting_on") is None:
        st["waiting_on"] = work.get("waiting_on")
        st["waiting_on_since"] = work.get("waiting_on_since")
        st["planned_resume_at"] = work.get("planned_resume_at") or work.get("resets_at")
        st["quota_class"] = work.get("quota_class")
    if work.get("pr_url") and not st.get("pr_url"):
        st["pr_url"] = work["pr_url"]


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


def load_auth_file(root: Path) -> dict[str, Any]:
    path = root / "auth" / "status.json"
    auth = {
        "overall": "ok",
        "checked_at": None,
        "ambient_api_key": False,
        "failed_checks": [],
    }
    if not path.is_file():
        return auth
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return auth
    if not isinstance(data, dict):
        return auth
    overall = data.get("overall") or data.get("state") or "ok"
    if overall == "fail":
        overall = "expired"
    if overall not in ("ok", "degraded", "expired"):
        overall = "degraded" if overall != "ok" else "ok"
    failed = data.get("reasons") or data.get("failed_checks") or []
    if isinstance(failed, list):
        auth["failed_checks"] = [str(x) for x in failed]
    checks = data.get("checks") or []
    if isinstance(checks, list):
        for c in checks:
            if isinstance(c, dict) and c.get("status") in ("expired", "missing", "fail"):
                cid = str(c.get("id") or c.get("label") or "check")
                if cid not in auth["failed_checks"]:
                    auth["failed_checks"].append(cid)
    ambient = data.get("ambient_api_key")
    if ambient is None:
        ambient = any("ambient" in str(x).lower() for x in auth["failed_checks"])
    auth["ambient_api_key"] = bool(ambient)
    auth["checked_at"] = data.get("checked_at")
    if auth["ambient_api_key"] and overall == "ok":
        overall = "degraded"
    auth["overall"] = overall
    return auth


def load_running(root: Path) -> dict[str, Any]:
    path = root / "running.json"
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_seat_file(path: Path) -> dict[str, Any]:
    seat = empty_seat(path.stem)
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return seat
    if not isinstance(data, dict):
        return seat
    seat["last_wake_at"] = data.get("last_wake_at")
    seat["wake_kind"] = data.get("wake_kind")
    seat["last_action"] = data.get("last_action") or data.get("action_summary") or ""
    seat["cron_expected"] = data.get("cron_expected") or default_cron(path.stem)
    if path.stem in EVENT_ONLY_SEATS:
        seat["cron_expected"] = EVENT_ONLY  # policy: legacy */10 files do not re-arm a verifier cadence
    return seat


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


def verify_stale_minutes(root: Path) -> int:
    raw = os.environ.get("VERIFY_STALE_MINUTES") or _yaml_block_scalars(
        project_yaml_text(root), "cadence"
    ).get("verify_stale_minutes")
    try:
        val = int(str(raw).strip()) if raw else VERIFY_STALE_MINUTES_DEFAULT
    except ValueError:
        val = VERIFY_STALE_MINUTES_DEFAULT
    return val if val > 0 else VERIFY_STALE_MINUTES_DEFAULT


def task_file_updated_at(root: Path, task_id: str) -> str | None:
    path = root / "tasks" / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        data = read_json(path)
        if isinstance(data, dict) and data.get("updated_at"):
            return str(data["updated_at"])
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return fmt_dt(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))
    except OSError:
        return None


def verdict_written_since(root: Path, task_id: str, since: datetime) -> bool:
    path = root / "verification" / f"{task_id}.json"
    if not path.is_file():
        return False
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) >= since
    except OSError:
        return False


def future_resume(st: dict[str, Any], now: datetime) -> bool:
    raw = st.get("planned_resume_at")
    if not raw or not st.get("waiting_on"):
        return False
    try:
        return parse_dt(raw) > now
    except Exception:
        return False


def build_now(root: Path) -> dict[str, Any]:
    now = utcnow()
    now_s = fmt_dt(now)
    events = load_events(events_path(root))
    tasks: dict[str, dict[str, Any]] = {}
    seats = {sid: empty_seat(sid) for sid in SEAT_IDS}
    auth = load_auth_file(root)

    extra: dict[str, Any] = {"questions": {}, "lock": None}
    for ev in events:
        apply_event(tasks, seats, auth, ev, extra)

    durable = load_durable_statuses(root)
    tasks_dir = root / "tasks"
    if tasks_dir.is_dir():
        for path in sorted(tasks_dir.glob("*.json")):
            try:
                task = read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(task, dict):
                continue
            tid = task.get("task_id") or path.stem
            st = tasks.setdefault(tid, new_task_state(tid))
            merge_task_file(st, task)

    work_path = root / "work.json"
    work: dict[str, Any] = {}
    if work_path.is_file():
        try:
            loaded = read_json(work_path)
            if isinstance(loaded, dict):
                work = loaded
                tid = work.get("task_id") or work.get("task")
                if tid:
                    st = tasks.setdefault(tid, new_task_state(tid))
                    merge_work_json(st, work)
        except (OSError, json.JSONDecodeError):
            work = {}

    running = load_running(root)
    running_tid = running.get("task_id") or running.get("task")
    running_pid = running.get("pid") or running.get("claude_pid")
    try:
        running_pid = int(running_pid) if running_pid is not None else None
    except (TypeError, ValueError):
        running_pid = None

    seats_dir = root / "observability" / "seats"
    if seats_dir.is_dir():
        for path in seats_dir.glob("*.json"):
            sid = path.stem
            file_seat = load_seat_file(path)
            seats.setdefault(sid, empty_seat(sid))
            # Heartbeat files on disk are liveness authority when newer.
            ev_wake = seats[sid].get("last_wake_at")
            file_wake = file_seat.get("last_wake_at")
            use_file = False
            if file_wake and not ev_wake:
                use_file = True
            elif file_wake and ev_wake:
                try:
                    use_file = parse_dt(file_wake) >= parse_dt(ev_wake)
                except Exception:
                    use_file = True
            if use_file:
                seats[sid].update({k: file_seat[k] for k in ("last_wake_at", "wake_kind", "last_action", "cron_expected")})
            elif not seats[sid].get("cron_expected"):
                seats[sid]["cron_expected"] = file_seat.get("cron_expected") or default_cron(sid)

    for tid, st in tasks.items():
        accrue(st, now)
        if not st.get("durable_status"):
            st["durable_status"] = durable.get(tid)
        if running_tid == tid and running_pid:
            st["claude_pid"] = running_pid
            st["claude_open"] = True

    mid_unparked = []
    for st in tasks.values():
        status = st.get("runtime_status")
        if status in MID_FLIGHT and not future_resume(st, now):
            mid_unparked.append(st["task_id"])

    for seat in seats.values():
        # §18.3: every seat is event-only, never time-stale; see verify_stale below.
        seat["cron_expected"] = EVENT_ONLY
        seat["stale_after_seconds"] = None
        seat["stale"] = False

    verify_stale_min = verify_stale_minutes(root)
    verifier_agent = project_seat_agent(root, "verifier") or "task-verifier"
    verify_stale: list[dict[str, Any]] = []
    for tid, st in tasks.items():
        if st.get("runtime_status") not in ("submitted", "verifying"):
            continue
        if st.get("waiting_on"):
            continue  # parked (e.g. waiting_on=runner for a localhost-only packet) — other blockers cover it
        since_raw = st.get("verify_since") or task_file_updated_at(root, tid)
        if not since_raw:
            continue
        try:
            since = parse_dt(since_raw)
        except Exception:
            continue
        if verdict_written_since(root, tid, since):
            continue  # verdict exists; Runner owns next step (Wake B)
        last = since
        if st.get("verifier_last_at"):
            try:
                last = max(last, parse_dt(st["verifier_last_at"]))
            except Exception:
                pass
        age_min = (now - last).total_seconds() / 60.0
        if age_min >= verify_stale_min:
            verify_stale.append(
                {
                    "task_id": tid,
                    "kind": "verify_stale",
                    "since": fmt_dt(last),
                    "detail": (
                        f"runtime_status={st.get('runtime_status')} no verdict and no verifier progress for "
                        f"{int(age_min)}m (threshold {verify_stale_min}m) — Watchdog: wake verifier seat "
                        f"{verifier_agent} with task_id={tid}"
                    ),
                }
            )

    project_id = os.environ.get("PROJECT_ID") or work.get("project_id")
    if not project_id:
        project_id = next((e.get("project_id") for e in events if e.get("project_id")), None)
    if not project_id and (root / "tasks").is_dir():
        for path in sorted((root / "tasks").glob("*.json")):
            try:
                data = read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and data.get("project_id"):
                project_id = data["project_id"]
                break
    project_id = project_id or root.name

    board_tasks = []
    blockers: list[dict[str, Any]] = []
    for tid in sorted(tasks):
        st = tasks[tid]
        started = st.get("implementation_started_at")
        wall = hours_between(parse_dt(started), now) if started else None
        runtime = st.get("runtime_status")
        pid = st.get("claude_pid")
        try:
            pid_i = int(pid) if pid is not None else None
        except (TypeError, ValueError):
            pid_i = None
        alive = pid_alive(pid_i) if pid_i else False
        waiting = st.get("waiting_on") or None
        row = {
            "task_id": tid,
            "durable_status": st.get("durable_status"),
            "runtime_status": runtime,
            "phase": st.get("phase"),
            "waiting_on": waiting,
            "waiting_on_since": st.get("waiting_on_since"),
            "planned_resume_at": st.get("planned_resume_at"),
            "quota_class": st.get("quota_class"),
            "implementation_started_at": started,
            "wall_hours": round_hours(wall),
            "work_hours": round_hours(st.get("work_seconds", 0.0) / 3600.0) or 0.0,
            "wait_hours": round_hours(st.get("wait_seconds", 0.0) / 3600.0) or 0.0,
            "pr_url": st.get("pr_url"),
            "head_sha": st.get("head_sha"),
            "running_pid": pid_i,
            "running_pid_alive": alive,
            "lease_holder": st.get("lease_holder"),
            "prompt_last_ref": st.get("prompt_last_ref"),
        }
        by_reason = {
            r: round_hours(sec / 3600.0) or 0.0
            for r, sec in sorted((st.get("wait_by_reason") or {}).items())
            if sec > 0
        }
        if by_reason:
            row["wait_hours_by_reason"] = by_reason
        board_tasks.append(row)

        if waiting in WAIT_BLOCKER_KINDS:
            blockers.append(
                {
                    "task_id": tid,
                    "kind": waiting,
                    "since": st.get("waiting_on_since") or started or now_s,
                    "detail": st.get("wait_detail") or f"waiting_on={waiting}",
                }
            )
        elif waiting:
            blockers.append(
                {
                    "task_id": tid,
                    "kind": "other",
                    "since": st.get("waiting_on_since") or now_s,
                    "detail": f"waiting_on={waiting}"
                    + (f" {st.get('wait_detail')}" if st.get("wait_detail") else ""),
                }
            )

    for sid, seat in seats.items():
        if seat.get("stale"):
            target = mid_unparked[0] if mid_unparked else ""
            blockers.append(
                {
                    "task_id": target or sid,
                    "kind": "stale_seat",
                    "since": seat.get("last_wake_at") or now_s,
                    "detail": (
                        f"{sid} last_wake_at={seat.get('last_wake_at')} (stale after "
                        f"{int((seat.get('stale_after_seconds') or STALE_AFTER_SECONDS) / 60)}m with mid-flight work; "
                        f"cron_expected={seat.get('cron_expected')})"
                    ),
                }
            )

    blockers.extend(verify_stale)

    if auth.get("ambient_api_key"):
        tid = next((t["task_id"] for t in board_tasks if t.get("runtime_status") in MID_FLIGHT), "")
        blockers.append(
            {
                "task_id": tid,
                "kind": "ambient_key",
                "since": auth.get("checked_at") or now_s,
                "detail": "ambient product API key present; delivery launches stay prepaid-stripped; overall at best degraded",
            }
        )

    active = sum(1 for t in board_tasks if t.get("runtime_status") in MID_FLIGHT)
    done = sum(1 for t in board_tasks if t.get("runtime_status") == "done")
    blocked = sum(1 for t in board_tasks if t.get("waiting_on"))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_s,
        "project_id": project_id,
        "queue_root": str(root),
        "auth": {
            "overall": auth.get("overall") or "ok",
            "checked_at": auth.get("checked_at"),
            "ambient_api_key": bool(auth.get("ambient_api_key")),
            "failed_checks": list(auth.get("failed_checks") or []),
        },
        "seats": {
            sid: {
                "last_wake_at": seats[sid].get("last_wake_at"),
                "wake_kind": seats[sid].get("wake_kind"),
                "last_action": seats[sid].get("last_action") or "",
                "cron_expected": seats[sid].get("cron_expected") or default_cron(sid),
                "stale": bool(seats[sid].get("stale")),
            }
            for sid in sorted(seats)
        },
        "tasks": board_tasks,
        "blockers": blockers,
        "questions": build_questions(root, extra, tasks, now),
        "spec_maintainer": None,  # the headless maintainer and its lock were removed (§17, 2026-11-05)
        "totals": {
            "tasks_active": active,
            "tasks_done": done,
            "tasks_blocked": blocked,
            "open_blockers": len(blockers),
        },
    }


def render_status_md(now: dict[str, Any]) -> str:
    lines = [
        f"# Delivery observability — {now.get('project_id')}",
        "",
        f"Generated: `{now.get('generated_at')}`  ",
        f"Queue: `{now.get('queue_root')}`  ",
        f"Auth: **{now.get('auth', {}).get('overall')}**"
        + (" · ambient API key present" if now.get("auth", {}).get("ambient_api_key") else ""),
        "",
        "## Seats",
        "",
        "| Seat | Last wake | Kind | Stale | Last action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for sid, seat in (now.get("seats") or {}).items():
        lines.append(
            f"| `{sid}` | {seat.get('last_wake_at') or '—'} | {seat.get('wake_kind') or '—'} | "
            f"{'YES' if seat.get('stale') else 'no'} | {seat.get('last_action') or ''} |"
        )
    lines += ["", "## Tasks", ""]
    if not now.get("tasks"):
        lines.append("_No tasks in events or `tasks/*.json`._")
    else:
        lines += [
            "| Task | Runtime | Durable | Phase | Wait | Wall / work / wait | Prompt |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for t in now["tasks"]:
            timers = f"{t.get('wall_hours')} / {t.get('work_hours')} / {t.get('wait_hours')}"
            wait = t.get("waiting_on") or "—"
            if t.get("planned_resume_at"):
                wait += f" → {t['planned_resume_at']}"
            diverge = ""
            if t.get("durable_status") and t.get("runtime_status") and t["durable_status"] != t["runtime_status"]:
                diverge = " · DIVERGE"
            lines.append(
                f"| `{t['task_id']}` | {t.get('runtime_status')}{diverge} | {t.get('durable_status') or '—'} | "
                f"{t.get('phase') or '—'} | {wait} | {timers} | {t.get('prompt_last_ref') or '—'} |"
            )
    lines += ["", "## Blockers", ""]
    if not now.get("blockers"):
        lines.append("_None._")
    else:
        for b in now["blockers"]:
            lines.append(f"- **{b.get('kind')}** `{b.get('task_id')}` since {b.get('since')} — {b.get('detail')}")
    lines += ["", "## Spec questions (§17)", "", "_The team lead answers spec questions._"]
    qs = now.get("questions") or []
    lines += [""]
    if not qs:
        lines.append("_No spec questions._")
    else:
        lines += [
            "| Question | Status | Verdict | Dispatch | Raised by | Blocks | Waiting on | Maintainer h | Operator h |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for q in qs:
            lines.append(
                f"| `{q['question_id']}` | {q.get('status')} | {q.get('verdict') or '—'} | {q.get('dispatch') or '—'} | "
                f"{q.get('raised_by') or '—'} | {', '.join(q.get('blocks') or []) or '—'} | {q.get('waiting_on') or '—'} | "
                f"{q.get('maintainer_wait_hours')} | {q.get('operator_wait_hours')} |"
            )
    tot = now.get("totals") or {}
    lines += [
        "",
        "## Totals",
        "",
        f"active={tot.get('tasks_active')} done={tot.get('tasks_done')} "
        f"blocked={tot.get('tasks_blocked')} open_blockers={tot.get('open_blockers')}",
        "",
        "No secrets.",
        "",
    ]
    return "\n".join(lines)


def print_human(now: dict[str, Any]) -> None:
    auth = now.get("auth") or {}
    tot = now.get("totals") or {}
    print(f"project  {now.get('project_id')}")
    print(f"generated {now.get('generated_at')}")
    print(f"queue    {now.get('queue_root')}")
    print(
        f"auth     {auth.get('overall')}"
        + (" ambient_api_key=true" if auth.get("ambient_api_key") else "")
        + (f" failed={auth.get('failed_checks')}" if auth.get("failed_checks") else "")
    )
    print("")
    print("SEATS")
    for sid, seat in (now.get("seats") or {}).items():
        flag = "STALE" if seat.get("stale") else "ok"
        print(
            f"  {sid:22} wake={seat.get('last_wake_at') or '—':22} "
            f"kind={seat.get('wake_kind') or '—':8} {flag}  {seat.get('last_action') or ''}"
        )
    print("")
    print("TASKS")
    if not now.get("tasks"):
        print("  (none)")
    for t in now.get("tasks") or []:
        diverge = ""
        if t.get("durable_status") and t.get("runtime_status") and t["durable_status"] != t["runtime_status"]:
            diverge = " DIVERGE"
        wait = t.get("waiting_on") or "null"
        resume = f" resume={t['planned_resume_at']}" if t.get("planned_resume_at") else ""
        print(
            f"  {t['task_id']:28} runtime={t.get('runtime_status')} durable={t.get('durable_status')}"
            f"{diverge} phase={t.get('phase')} wait={wait}{resume}"
        )
        print(
            f"  {'':28} wall={t.get('wall_hours')} work={t.get('work_hours')} "
            f"wait_h={t.get('wait_hours')} "
            f"pid={t.get('running_pid')} alive={t.get('running_pid_alive')} prompt={t.get('prompt_last_ref')}"
        )
        if t.get("wait_hours_by_reason"):
            parts = " ".join(f"{k}={v}" for k, v in t["wait_hours_by_reason"].items())
            print(f"  {'':28} wait_by_reason: {parts}")
    print("")
    qs = now.get("questions") or []
    print("QUESTIONS")
    if not qs:
        print("  (none)")
    for q in qs:
        print(
            f"  {q['question_id']:28} status={q.get('status')} verdict={q.get('verdict') or '—'} "
            f"dispatch={q.get('dispatch') or '—'} raised_by={q.get('raised_by') or '—'} "
            f"blocks={','.join(q.get('blocks') or [])} waiting_on={q.get('waiting_on') or '—'}"
        )
        print(
            f"  {'':28} wait: spec_maintainer={q.get('maintainer_wait_hours')}h operator={q.get('operator_wait_hours')}h"
        )
    print("")
    print("BLOCKERS")
    if not now.get("blockers"):
        print("  (none)")
    for b in now.get("blockers") or []:
        print(f"  {b.get('kind'):12} {b.get('task_id')} since {b.get('since')} — {b.get('detail')}")
    print("")
    print(
        f"totals   active={tot.get('tasks_active')} done={tot.get('tasks_done')} "
        f"blocked={tot.get('tasks_blocked')} open_blockers={tot.get('open_blockers')}"
    )


def write_snapshot(root: Path, now: dict[str, Any]) -> None:
    dest_dir = root / "observability"
    dest_dir.mkdir(parents=True, exist_ok=True)
    write_json(dest_dir / "now.json", now)
    (dest_dir / "STATUS.md").write_text(render_status_md(now))


def cmd_rebuild(root: Path) -> dict[str, Any]:
    now = build_now(root)
    write_snapshot(root, now)
    print(f"rebuild-now: wrote {root / 'observability' / 'now.json'}")
    print(f"rebuild-now: wrote {root / 'observability' / 'STATUS.md'}")
    return now


def has_stale_or_blockers(now: dict[str, Any]) -> bool:
    if now.get("blockers"):
        return True
    return any(s.get("stale") for s in (now.get("seats") or {}).values())


def cmd_status(root: Path, rebuild: bool) -> int:
    now = cmd_rebuild(root) if rebuild else None
    if now is None:
        path = root / "observability" / "now.json"
        if not path.is_file():
            now = cmd_rebuild(root)
        else:
            now = read_json(path)
    print_human(now)
    return 1 if has_stale_or_blockers(now) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Control-plane observability fold/status")
    parser.add_argument("command", choices=("rebuild", "status"))
    parser.add_argument("--queue-root", default=None)
    parser.add_argument("--no-rebuild", action="store_true")
    args = parser.parse_args(argv)
    if args.queue_root:
        os.environ["QUEUE_ROOT"] = args.queue_root
    root = queue_root()
    if args.command == "rebuild":
        cmd_rebuild(root)
        return 0
    return cmd_status(root, rebuild=not args.no_rebuild)


if __name__ == "__main__":
    raise SystemExit(main())
