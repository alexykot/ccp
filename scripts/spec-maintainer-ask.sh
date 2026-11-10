#!/usr/bin/env bash
# spec-maintainer-ask.sh — SPEC §17 spec questions: the runner raises them, the team lead answers.
# Runtime files only (QUEUE_ROOT/questions/); no secrets.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/observability/spec_maintainer.py"

usage() {
  cat <<'USAGE'
Usage:
  spec-maintainer-ask.sh raise --task-id ID --text TEXT --inconsistency TEXT \
      [--spec-refs JSON|a,b] [--tried TEXT] [--blocks JSON|a,b] \
      [--raised-by task-runner|task-verifier]
        §17: write the question file, set waiting_on=spec_maintainer on each blocked task,
        record question/raised, and print the message to send the lead.

  spec-maintainer-ask.sh <question_file.json | question_id>
  spec-maintainer-ask.sh process <question_file.json | question_id> [--actor SEAT]
        Apply the lead's answer file (clear or move the waits, record question/answered,
        print the durable note, pull and prompt-context actions). Without an answer yet:
        prints the lead message (once) or "skip ahead".

  spec-maintainer-ask.sh blocked [--task-id ID]  Skip-ahead: tasks blocked by open questions
                                                  (blocks + depends_on descendants).

Output: one JSON object on stdout. `actions` lists what the seat must still do itself
(message the lead, durable log note, skip ahead). Exit 0 ok; 2 usage.

Env:
  QUEUE_ROOT     required (live queue, outside product git)
  PROJECT_YAML   project binding (default: the binding naming QUEUE_ROOT, SPEC §8.3)
  PROJECT_ID     optional (default: the binding's project_id)
  ACTOR          raising seat id (task-runner | task-verifier) when --raised-by/--actor omitted
  DURABLE_DOCS   optional product docs/delivery (INDEX.yaml depends_on for `blocked`)

Never: email, message agents, rewrite the binding, or put secrets in files/events.
USAGE
}

case "${1:-}" in
  ""|-h|--help) usage; [[ -n "${1:-}" ]] && exit 0; exit 2 ;;
  raise|process|blocked) exec python3 "$PY" "$@" ;;
  *) exec python3 "$PY" process "$@" ;;
esac
