#!/usr/bin/env bash
# formal-submit.template.sh — certify formal readiness only (no spec judgement).
# Copy beside a project queue and wire adapter unit/lint + PR checks.
#
# Required checks (standing DoD):
#   1. unit + lint pass — wired below. The verifier also runs them itself and records them
#      (SPEC §15.3)
#   2. PR exists
#   3. review artifact present (from same-session /mk-pr + clean /review)
#   4. no open spec escalation
#
# On success: move task → submitted (runner then hands verifier packet).
# Does NOT merge. Does NOT approve.

set -euo pipefail

TASK_ID="${1:?usage: formal-submit.template.sh <task_id>}"
QUEUE_ROOT="${QUEUE_ROOT:?set QUEUE_ROOT to live queue dir outside product git}"
TASK_FILE="${QUEUE_ROOT}/tasks/${TASK_ID}.json"
REVIEW_FILE="${QUEUE_ROOT}/review/${TASK_ID}.json"
ESC_DIR="${QUEUE_ROOT}/escalations/${TASK_ID}"

die() { echo "formal-submit: $*" >&2; exit 1; }

[[ -f "$TASK_FILE" ]] || die "missing task file $TASK_FILE"

# --- project-specific: replace with adapter hooks ---
# run_unit_lint() { (cd "$(adapter worktree_path "$SLUG")" && npm test && npm run lint); }
run_unit_lint() {
  die "wire run_unit_lint to adapter worktree unit+lint"
}

pr_exists() {
  local url
  url="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('pr_url') or '')" "$TASK_FILE")"
  [[ -n "$url" ]] || die "pr_url missing on task (same-session /mk-pr required first)"
  echo "pr_ok $url"
}

review_artifact_present() {
  [[ -f "$REVIEW_FILE" ]] || die "missing review artifact $REVIEW_FILE"
  python3 -c '
import json, sys
r = json.load(open(sys.argv[1]))
sid = r.get("mk_pr_session_id")
if not sid:
    sys.exit("mk_pr_session_id missing — cold /mk-pr is forbidden")
print("review_ok session", sid)
' "$REVIEW_FILE"
}

no_open_spec_escalation() {
  if [[ -d "$ESC_DIR" ]]; then
    python3 -c '
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
open_spec = []
for p in root.glob("*.json"):
    e = json.loads(p.read_text())
    if e.get("class") == "spec" and e.get("status") in ("open", "waiting_operator"):
        open_spec.append(p.name)
if open_spec:
    print("open spec escalations:", ", ".join(open_spec), file=sys.stderr)
    sys.exit(1)
print("escalations_ok")
' "$ESC_DIR"
  else
    echo "escalations_ok (none)"
  fi
}

run_unit_lint
pr_exists
review_artifact_present
no_open_spec_escalation

echo "formal-submit: READY task_id=$TASK_ID → status submitted"
# Caller (runner) updates task status + queue bucket.
