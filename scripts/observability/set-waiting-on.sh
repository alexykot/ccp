#!/usr/bin/env bash
# set-waiting-on.sh — single-writer for waiting_on.
# ALWAYS emit waiting_on set/clear FIRST, then update work.json / tasks/<id>.json.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  set-waiting-on.sh set <task_id> <reason> [options]
  set-waiting-on.sh clear <task_id> <reason> [options]

Single-writer rule: append the observability event, then mutate work.json / task JSON.
Do not edit waiting_on on those files without this script.

Reasons (set): quota | reauth | operator_decision | runner | steerer | spec_maintainer | design_seat | null-class |
                operator_step
  design_seat = (SPEC §17.9): blocked on a gate the design seat
                has not decided yet; pass --detail <escalation_id>.
  spec_maintainer = blocked on an open spec-maintainer question (SPEC §17);
                    pass --detail <question_id>. steerer stays for projects
                    without a spec_maintainer block. A question escalated to the operator
                    uses reason operator_decision with --detail <question_id>.
  operator_step = a step only the operator's machine can do: a live upgrade or creating
          a database role. Pass --detail naming the step. The code-only change can
          merge; the step is a follow-up for the operator or the lead.
Clear reason: what cleared (e.g. quota_reset, runner_resumed, spec_resolved,
  not_a_spec_question).

Options:
  --resets-at RFC3339     planned resume / quota reset (stored as planned_resume_at)
  --planned-resume-at RFC3339
                          the planned resume when it differs from the reset (SPEC §25.4: the
                          5-hour park resumes at the window's reset plus a margin)
  --quota-class CLASS     session | credit
  --detail TEXT
  --actor ACTOR           default: $ACTOR or system
  --project-id ID         default: $PROJECT_ID or task.project_id
  --task-only             leave work.json alone unless it names this task (a sweep of
                          other tasks, e.g. `ccp tasks sync`, must not move the runner's)
  -h, --help

Env:
  QUEUE_ROOT   required
  PROJECT_ID   optional
  ACTOR        optional

Watchdog precedence: do not set waiting_on=reauth in a way that SIGTERMs a live
prepaid Claude session if that session does not need the failed check (e.g. ADC).
Record auth degraded via emit-event.sh --type auth and rebuild-now.sh instead.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "" ]]; then
  usage
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && exit 0
  exit 2
fi

ACTION="${1:-}"
TASK_ID="${2:-}"
REASON="${3:-}"
shift 3 || true

RESETS_AT=""
PLANNED_AT=""
QUOTA_CLASS=""
DETAIL=""
ACTOR_IN="${ACTOR:-}"
PROJECT_IN="${PROJECT_ID:-}"
TASK_ONLY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resets-at) RESETS_AT="${2:-}"; shift 2 ;;
    --planned-resume-at) PLANNED_AT="${2:-}"; shift 2 ;;
    --quota-class) QUOTA_CLASS="${2:-}"; shift 2 ;;
    --detail) DETAIL="${2:-}"; shift 2 ;;
    --actor) ACTOR_IN="${2:-}"; shift 2 ;;
    --project-id) PROJECT_IN="${2:-}"; shift 2 ;;
    --task-only) TASK_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "set-waiting-on: unknown arg $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$ACTION" != "set" && "$ACTION" != "clear" ]]; then
  echo "set-waiting-on: first arg must be set or clear" >&2
  usage >&2
  exit 2
fi
[[ -n "$TASK_ID" ]] || { echo "set-waiting-on: task_id required" >&2; exit 2; }
[[ -n "$REASON" ]] || { echo "set-waiting-on: reason required" >&2; exit 2; }

QUEUE_ROOT="${QUEUE_ROOT:?set QUEUE_ROOT to live queue dir outside product git}"
command -v python3 >/dev/null || { echo "set-waiting-on: python3 required" >&2; exit 1; }

export QUEUE_ROOT ACTION TASK_ID REASON RESETS_AT PLANNED_AT QUOTA_CLASS DETAIL ACTOR_IN PROJECT_IN TASK_ONLY
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

python3 <<'PY'
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.environ.get("PYTHONPATH", ".").split(":")[0])
from lib import append_event, die, fmt_dt, looks_like_secret, work_lock, write_json

root = Path(os.environ["QUEUE_ROOT"]).expanduser()
action = os.environ["ACTION"]
task_id = os.environ["TASK_ID"]
reason = os.environ["REASON"]
resets_at = os.environ.get("RESETS_AT") or None
planned_at = os.environ.get("PLANNED_AT") or resets_at
resets_at = resets_at or planned_at
quota_class = os.environ.get("QUOTA_CLASS") or None
detail = os.environ.get("DETAIL") or None
actor = os.environ.get("ACTOR_IN") or "system"
now_s = fmt_dt(datetime.now(timezone.utc))

task_path = root / "tasks" / f"{task_id}.json"
work_path = root / "work.json"
task = {}
if task_path.is_file():
    task = json.loads(task_path.read_text())
    if not isinstance(task, dict):
        die(f"invalid task JSON {task_path}")
work = {}
if work_path.is_file():
    try:
        loaded = json.loads(work_path.read_text())
        if isinstance(loaded, dict):
            work = loaded
    except json.JSONDecodeError:
        work = {}

was = task.get("waiting_on")
if was is None and work.get("task_id") == task_id:  # work.json's wait is its own task's only
    was = work.get("waiting_on")

project_id = (
    os.environ.get("PROJECT_IN")
    or task.get("project_id")
    or work.get("project_id")
    or os.environ.get("PROJECT_ID")
    or ""
)
if not project_id:
    die("project_id required (--project-id, $PROJECT_ID, or task JSON)")

if action == "set" and reason not in ("quota", "reauth", "operator_decision", "runner", "steerer", "spec_maintainer",
                                     "design_seat", "null-class", "operator_step"):
    die(f"invalid waiting_on reason {reason!r}")
if quota_class and quota_class not in ("session", "credit"):
    die("quota-class must be session or credit")

payload = {"reason": reason}
if action == "clear":
    payload["was"] = was
if action == "set":
    if resets_at:
        payload["resets_at"] = resets_at
        payload["planned_resume_at"] = planned_at
    if quota_class:
        payload["quota_class"] = quota_class
if detail:
    payload["detail"] = detail

ev = {
    "at": now_s,
    "project_id": project_id,
    "task_id": task_id,
    "actor": actor,
    "type": "waiting_on",
    "op": action,
    "payload": payload,
}
if looks_like_secret(json.dumps(ev)):
    die("refusing secret-like value")

# 1) Event first (canonical ledger).
written = append_event(root, ev)

# 2) Then operational files.
if action == "set":
    waiting = reason
    since = now_s
    planned = planned_at
    qclass = quota_class
else:
    waiting = None
    since = None
    planned = None
    qclass = None

if task_path.is_file() or task:
    task["waiting_on"] = waiting
    task["waiting_on_since"] = since
    task["planned_resume_at"] = planned
    task["quota_class"] = qclass
    task["updated_at"] = now_s
    if "task_id" not in task:
        task["task_id"] = task_id
    write_json(task_path, task)

# SPEC §16.4: work.json is read again and written under its lock, and a wait on one task never
# repoints the runner's current task to it: work.json carries the wait only for its own task_id, or,
# without TASK_ONLY, when it names no task yet. Other tasks' waits live in their task files.
with work_lock(root):
    work = {}
    if work_path.is_file():
        try:
            loaded = json.loads(work_path.read_text())
            if isinstance(loaded, dict):
                work = loaded
        except json.JSONDecodeError:
            work = {}
    if work.get("task_id") != task_id and (os.environ.get("TASK_ONLY") or work.get("task_id")):
        print(json.dumps({"ok": True, "event": written, "task_file": str(task_path) if task_path.is_file() else None,
                          "work_file": None, "waiting_on": waiting, "planned_resume_at": planned}, separators=(",", ":")))
        sys.exit(0)
    work["task_id"] = task_id
    if project_id:
        work["project_id"] = project_id
    work["waiting_on"] = waiting
    work["waiting_on_since"] = since
    work["planned_resume_at"] = planned
    if planned:
        work["resets_at"] = resets_at
    elif "resets_at" in work and action == "clear":
        work["resets_at"] = None
    work["quota_class"] = qclass
    if detail:
        work["waiting_on_detail"] = detail
    work["updated_at"] = now_s
    write_json(work_path, work)

print(json.dumps({
    "ok": True,
    "event": written,
    "task_file": str(task_path) if task_path.is_file() else None,
    "work_file": str(work_path),
    "waiting_on": waiting,
    "planned_resume_at": planned,
}, separators=(",", ":")))
PY
