#!/usr/bin/env bash
# write-prompt-audit.sh — Layer 2: write QUEUE_ROOT/prompts/<task_id>/<UTC>_<phase>.json
# Prints the relative prompt_ref. Never commit these files to git.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  write-prompt-audit.sh --task-id ID --phase PHASE --prompt-file FILE [options]
  write-prompt-audit.sh --task-id ID --phase PHASE --prompt-file -

Write a Layer 2 alpha prompt audit file (full prompt_body + sha256) under
$QUEUE_ROOT/prompts/<task_id>/<UTC>_<phase>.json and print the relative path
(prompt_ref) for the matching claude/launch event.

Call this BEFORE every plane-owned Claude invocation:
  claude -p, --resume, /mk-pr, /review.

Options:
  --task-id ID
  --phase PHASE           implement | fix-review | mk-pr | review | …
  --prompt-file FILE|-    full prompt body (required, non-empty)
  --session-id UUID
  --resume                mark resume=true
  --argv JSON             JSON array of argv strings
  --actor ACTOR           default $ACTOR or task-runner
  --project-id ID
  --git-head SHA
  --worktree PATH
  --durable-task-path PATH
  --spec-refs JSON        JSON array of strings
  --notes TEXT
  -h, --help

Env:
  QUEUE_ROOT   required
  PROJECT_ID   optional

Rules: no API keys, ADC tokens, or .env contents. Runtime queue only — not git.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "" ]]; then
  usage
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && exit 0
  exit 2
fi

QUEUE_ROOT="${QUEUE_ROOT:?set QUEUE_ROOT to live queue dir outside product git}"
command -v python3 >/dev/null || { echo "write-prompt-audit: python3 required" >&2; exit 1; }

TASK_ID=""
PHASE=""
PROMPT_FILE=""
SESSION_ID=""
RESUME="false"
ARGV='["claude","-p"]'
ACTOR_IN="${ACTOR:-task-runner}"
PROJECT_IN="${PROJECT_ID:-}"
GIT_HEAD=""
WORKTREE=""
DURABLE=""
SPEC_REFS="[]"
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-id) TASK_ID="${2:-}"; shift 2 ;;
    --phase) PHASE="${2:-}"; shift 2 ;;
    --prompt-file) PROMPT_FILE="${2:-}"; shift 2 ;;
    --session-id) SESSION_ID="${2:-}"; shift 2 ;;
    --resume) RESUME="true"; shift ;;
    --argv) ARGV="${2:-}"; shift 2 ;;
    --actor) ACTOR_IN="${2:-}"; shift 2 ;;
    --project-id) PROJECT_IN="${2:-}"; shift 2 ;;
    --git-head) GIT_HEAD="${2:-}"; shift 2 ;;
    --worktree) WORKTREE="${2:-}"; shift 2 ;;
    --durable-task-path) DURABLE="${2:-}"; shift 2 ;;
    --spec-refs) SPEC_REFS="${2:-}"; shift 2 ;;
    --notes) NOTES="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "write-prompt-audit: unknown arg $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$TASK_ID" ]] || { echo "write-prompt-audit: --task-id required" >&2; exit 2; }
[[ -n "$PHASE" ]] || { echo "write-prompt-audit: --phase required" >&2; exit 2; }
[[ -n "$PROMPT_FILE" ]] || { echo "write-prompt-audit: --prompt-file required" >&2; exit 2; }

PROMPT_TMP=""
if [[ "$PROMPT_FILE" == "-" ]]; then
  PROMPT_TMP="$(mktemp "${TMPDIR:-/tmp}/prompt-audit.XXXXXX")"
  cat > "$PROMPT_TMP"
  PROMPT_FILE="$PROMPT_TMP"
fi
[[ -f "$PROMPT_FILE" ]] || { echo "write-prompt-audit: missing prompt file" >&2; exit 2; }

export QUEUE_ROOT TASK_ID PHASE PROMPT_FILE SESSION_ID RESUME ARGV ACTOR_IN PROJECT_IN
export GIT_HEAD WORKTREE DURABLE SPEC_REFS NOTES
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

cleanup() {
  if [[ -n "${PROMPT_TMP:-}" && -f "${PROMPT_TMP:-}" ]]; then
    rm -f "$PROMPT_TMP"
  fi
}
trap cleanup EXIT

python3 <<'PY'
import hashlib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.environ.get("PYTHONPATH", ".").split(":")[0])
from lib import die, fmt_dt, looks_like_secret, write_json

path_in = Path(os.environ["PROMPT_FILE"])
try:
    body = path_in.read_text()
except OSError as exc:
    die(f"cannot read prompt file: {exc}")
if not body.strip():
    die("prompt_body is empty")
if looks_like_secret(body):
    die("refusing secret-like value in prompt_body")

try:
    argv = json.loads(os.environ.get("ARGV") or "[]")
except json.JSONDecodeError as exc:
    die(f"invalid --argv: {exc}")
if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
    die("--argv must be a JSON array of strings")

try:
    spec_refs = json.loads(os.environ.get("SPEC_REFS") or "[]")
except json.JSONDecodeError as exc:
    die(f"invalid --spec-refs: {exc}")
if not isinstance(spec_refs, list) or not all(isinstance(x, str) for x in spec_refs):
    die("--spec-refs must be a JSON array of strings")

now = datetime.now(timezone.utc)
now_s = fmt_dt(now)
stamp = now.strftime("%Y%m%dT%H%M%SZ")
phase = os.environ["PHASE"]
safe_phase = re.sub(r"[^A-Za-z0-9._-]+", "-", phase)
task_id = os.environ["TASK_ID"]
rel = f"prompts/{task_id}/{stamp}_{safe_phase}.json"
root = Path(os.environ["QUEUE_ROOT"]).expanduser()
path = root / rel

project_id = os.environ.get("PROJECT_IN") or os.environ.get("PROJECT_ID") or ""
if not project_id:
    tpath = root / "tasks" / f"{task_id}.json"
    if tpath.is_file():
        try:
            project_id = json.loads(tpath.read_text()).get("project_id") or ""
        except json.JSONDecodeError:
            project_id = ""
if not project_id:
    die("project_id required (--project-id, $PROJECT_ID, or task JSON)")

digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
obj = {
    "schema_version": 1,
    "at": now_s,
    "project_id": project_id,
    "task_id": task_id,
    "phase": phase,
    "actor": os.environ.get("ACTOR_IN") or "task-runner",
    "session_id": os.environ.get("SESSION_ID") or None,
    "resume": os.environ.get("RESUME") == "true",
    "argv": argv,
    "env_stripped": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
    "wallet": "prepaid_oauth",
    "git_head": os.environ.get("GIT_HEAD") or None,
    "worktree": os.environ.get("WORKTREE") or None,
    "durable_task_path": os.environ.get("DURABLE") or None,
    "spec_refs": spec_refs,
    "prompt_body": body,
    "prompt_sha256": digest,
}
notes = os.environ.get("NOTES") or ""
if notes:
    obj["notes"] = notes

if looks_like_secret(json.dumps(obj)):
    die("refusing secret-like value in audit file")

write_json(path, obj)
print(rel)
PY
