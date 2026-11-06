#!/usr/bin/env bash
# emit-event.sh — append one JSON object to $QUEUE_ROOT/observability/events.jsonl
# Append-only. Never rewrite history. No secrets.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  emit-event.sh --type TYPE --op OP [options]
  emit-event.sh --json '{"at":"...","type":"phase",...}'
  echo '{...}' | emit-event.sh --json -

Append one JSONL line to $QUEUE_ROOT/observability/events.jsonl (mkdir -p as needed).

Required event fields: at, project_id, task_id, actor, type, op, payload

Options:
  --type TYPE           phase|waiting_on|lease|claude|auth|seat|durable|note
  --op OP               set|clear|transition|launch|exit|heartbeat|reconcile
  --task-id ID          task id (empty allowed for seat/auth)
  --actor ACTOR         default: $ACTOR or system
  --project-id ID       default: $PROJECT_ID
  --payload JSON        object; default {}
  --at RFC3339          default: now UTC
  --json JSON|-         full event object (overrides flags)
  -h, --help            this help

Env:
  QUEUE_ROOT    required — live queue dir (e.g. $HOME/projects/.delivery-queue/<project_id>)
  PROJECT_ID    default project_id
  ACTOR         default actor

Examples:
  emit-event.sh --type phase --op transition --task-id ex-0001 \
    --payload '{"from":"leased","to":"implementing"}'
  emit-event.sh --type seat --op heartbeat --actor delivery-watchdog \
    --payload '{"seat_id":"delivery-watchdog","wake_kind":"cron","action_summary":"tick"}'
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "" ]]; then
  usage
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && exit 0
  exit 2
fi

QUEUE_ROOT="${QUEUE_ROOT:?set QUEUE_ROOT to live queue dir outside product git}"
command -v python3 >/dev/null || { echo "emit-event: python3 required" >&2; exit 1; }

TYPE=""
OP=""
TASK_ID=""
ACTOR_IN="${ACTOR:-}"
PROJECT_IN="${PROJECT_ID:-}"
PAYLOAD="{}"
AT=""
JSON_IN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --type) TYPE="${2:-}"; shift 2 ;;
    --op) OP="${2:-}"; shift 2 ;;
    --task-id) TASK_ID="${2:-}"; shift 2 ;;
    --actor) ACTOR_IN="${2:-}"; shift 2 ;;
    --project-id) PROJECT_IN="${2:-}"; shift 2 ;;
    --payload) PAYLOAD="${2:-}"; shift 2 ;;
    --at) AT="${2:-}"; shift 2 ;;
    --json) JSON_IN="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "emit-event: unknown arg $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$JSON_IN" == "-" ]]; then
  JSON_IN="$(cat)"
fi

export QUEUE_ROOT TYPE OP TASK_ID ACTOR_IN PROJECT_IN PAYLOAD AT JSON_IN
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

python3 <<'PY'
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.environ.get("PYTHONPATH", ".").split(":")[0])
from lib import append_event, die, events_path, fmt_dt, looks_like_secret

raw = os.environ.get("JSON_IN") or ""
if raw:
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"invalid --json: {exc}")
    if not isinstance(ev, dict):
        die("--json must be an object")
else:
    payload_raw = os.environ.get("PAYLOAD") or "{}"
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError as exc:
        die(f"invalid --payload: {exc}")
    if not isinstance(payload, dict):
        die("--payload must be an object")
    ev = {
        "at": os.environ.get("AT") or fmt_dt(datetime.now(timezone.utc)),
        "project_id": os.environ.get("PROJECT_IN") or "",
        "task_id": os.environ.get("TASK_ID") or "",
        "actor": os.environ.get("ACTOR_IN") or "system",
        "type": os.environ.get("TYPE") or "",
        "op": os.environ.get("OP") or "",
        "payload": payload,
    }

if looks_like_secret(json.dumps(ev)):
    die("refusing secret-like value in event (API key / token / private key)")

if not ev.get("at"):
    ev["at"] = fmt_dt(datetime.now(timezone.utc))
if not ev.get("project_id"):
    ev["project_id"] = os.environ.get("PROJECT_IN") or os.environ.get("PROJECT_ID") or ""
if "task_id" not in ev:
    ev["task_id"] = os.environ.get("TASK_ID") or ""
if not ev.get("actor"):
    ev["actor"] = os.environ.get("ACTOR_IN") or os.environ.get("ACTOR") or "system"
ev.setdefault("payload", {})

root = Path(os.environ["QUEUE_ROOT"]).expanduser()
written = append_event(root, ev)
print(json.dumps({"ok": True, "path": str(events_path(root)), "event": written}, separators=(",", ":")))
PY
