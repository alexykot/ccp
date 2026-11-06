#!/usr/bin/env bash
# heartbeat.sh — write seats/<seat_id>.json and append seat/heartbeat event.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  heartbeat.sh <seat_id> [options]

Seat ids: task-runner | task-verifier | delivery-watchdog

task-verifier is event-only: woken by Task Runner (formal-submit) or by the
Watchdog (verify_stale). Heartbeat with --wake-kind priority --task-id <id>.

On every wake (cron, priority, or manual):
  1. Write $QUEUE_ROOT/observability/seats/<seat_id>.json
  2. Append a seat/heartbeat event

Options:
  --wake-kind KIND        cron | priority | manual   (default: cron)
  --action TEXT           last_action / action_summary
  --cron-expected SPEC    default per seat (2026-09-24 cadence):
                            delivery-watchdog '*/30 * * * *' (24/7)
                            task-verifier     'event' (NO routine — event-only)
                            task-runner       '*/10 * * * *'
  --task-id ID            optional; defaults to work.json task_id
  --actor ACTOR           default: seat_id
  --project-id ID
  -h, --help

Env:
  QUEUE_ROOT   required
  PROJECT_ID   optional
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "" ]]; then
  usage
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && exit 0
  exit 2
fi

SEAT_ID="${1:-}"
shift || true

WAKE_KIND="cron"
ACTION=""
CRON_EXPECTED=""
TASK_ID=""
ACTOR_IN=""
PROJECT_IN="${PROJECT_ID:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wake-kind) WAKE_KIND="${2:-}"; shift 2 ;;
    --action) ACTION="${2:-}"; shift 2 ;;
    --cron-expected) CRON_EXPECTED="${2:-}"; shift 2 ;;
    --task-id) TASK_ID="${2:-}"; shift 2 ;;
    --actor) ACTOR_IN="${2:-}"; shift 2 ;;
    --project-id) PROJECT_IN="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "heartbeat: unknown arg $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$SEAT_ID" in
  task-runner|task-verifier|delivery-watchdog) ;;
  *) echo "heartbeat: seat_id must be task-runner|task-verifier|delivery-watchdog" >&2; exit 2 ;;
esac
case "$WAKE_KIND" in
  cron|priority|manual) ;;
  *) echo "heartbeat: --wake-kind must be cron|priority|manual" >&2; exit 2 ;;
esac

if [[ -z "$CRON_EXPECTED" ]]; then
  case "$SEAT_ID" in
    delivery-watchdog) CRON_EXPECTED="*/30 * * * *" ;;
    task-verifier) CRON_EXPECTED="event" ;;
    *) CRON_EXPECTED="*/10 * * * *" ;;
  esac
fi
if [[ "$SEAT_ID" == "task-verifier" ]]; then
  CRON_EXPECTED="event"   # policy: Verifier never runs a recurring routine
fi

QUEUE_ROOT="${QUEUE_ROOT:?set QUEUE_ROOT to live queue dir outside product git}"
command -v python3 >/dev/null || { echo "heartbeat: python3 required" >&2; exit 1; }

export QUEUE_ROOT SEAT_ID WAKE_KIND ACTION CRON_EXPECTED TASK_ID ACTOR_IN PROJECT_IN
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

python3 <<'PY'
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.environ.get("PYTHONPATH", ".").split(":")[0])
from lib import append_event, die, fmt_dt, write_json

root = Path(os.environ["QUEUE_ROOT"]).expanduser()
seat_id = os.environ["SEAT_ID"]
wake_kind = os.environ["WAKE_KIND"]
action = os.environ.get("ACTION") or "wake"
cron = os.environ.get("CRON_EXPECTED") or "*/10 * * * *"
now_s = fmt_dt(datetime.now(timezone.utc))

work = {}
wp = root / "work.json"
if wp.is_file():
    try:
        loaded = json.loads(wp.read_text())
        if isinstance(loaded, dict):
            work = loaded
    except json.JSONDecodeError:
        work = {}

task_id = os.environ.get("TASK_ID") or work.get("task_id") or work.get("task") or ""
project_id = (
    os.environ.get("PROJECT_IN")
    or work.get("project_id")
    or os.environ.get("PROJECT_ID")
    or root.name
)
actor = os.environ.get("ACTOR_IN") or seat_id

seat = {
    "seat_id": seat_id,
    "last_wake_at": now_s,
    "wake_kind": wake_kind,
    "last_action": action,
    "cron_expected": cron,
    "updated_at": now_s,
}
write_json(root / "observability" / "seats" / f"{seat_id}.json", seat)

ev = append_event(root, {
    "at": now_s,
    "project_id": project_id,
    "task_id": task_id,
    "actor": actor,
    "type": "seat",
    "op": "heartbeat",
    "payload": {
        "seat_id": seat_id,
        "wake_kind": wake_kind,
        "action_summary": action,
        "cron_expected": cron,
    },
})
print(json.dumps({"ok": True, "seat": seat, "event": ev}, separators=(",", ":")))
PY
