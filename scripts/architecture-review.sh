#!/usr/bin/env bash
# architecture-review.sh — SPEC §19 architecture review: due check, isolated reviewer, triage hand-off.
# The Task Runner runs it; runtime files only (QUEUE_ROOT); no secrets.
# SPEC §19: when the product's docs/delivery/plane.json has an `architect` block, every action is
# `ccp architect <action>` instead (a thin alias). Without one it runs as below, with the product's
# `architect` skill (structure lens) once the sync has replaced the `architecture-review` skill.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/observability/architecture_review.py"

usage() {
  cat <<'USAGE'
Usage:
  architecture-review.sh due
        Is a review due? Exit 0 due, 3 not due. Due when architecture_review.enabled and either
        every_n_tasks durable tasks reached done since the last review, or max_days passed with at
        least one done. Never due while a review is running or a report awaits triage.

  architecture-review.sh run [--force] [--actor SEAT]
        Launch a FRESH (never resumed) Claude session in product_root, read-only
        (--allowedTools read tools + architecture_review.probes; --disallowedTools Edit,Write,...),
        prompt `/architecture-review review_id=... head=... base=...`, under architecture-review.lock,
        with the Layer 2 prompt audit (task architecture-review, phase architecture-review) and
        prepaid OAuth (env -u ANTHROPIC_API_KEY ...). Parses the final JSON report, validates it
        (contracts/architecture_review.schema.json) and writes QUEUE_ROOT/reviews/<review_id>.json + .md.
        --force = on demand (the operator or the owner asked); still refused while a review is running or untriaged.

  architecture-review.sh triage <review_id> [--actor SEAT]
        Hand the report to the task-log owner, the team lead (SPEC §19.8): prints the message for
        the lead. Applies QUEUE_ROOT/reviews/<review_id>.triage.json when present (on a later wake)
        and prints the actions left to the seat: register the new durable tasks in the runtime
        queue; the lead asks the operator any question_for_operator in its own session.

  architecture-review.sh status
        State, last review and every review's status.

Output: one JSON object on stdout; `actions` lists what the seat must still do itself.
Exit 0 ok; 1 failed (retry per actions); 2 usage/config; 3 not due / locked / blocked.

Env:
  QUEUE_ROOT     required (live queue, outside product git)
  PROJECT_YAML   project binding (default $QUEUE_ROOT/project.yaml): architecture_review, product_root,
                 spec_maintainer, seats, email
  ACTOR          acting seat (default task-runner)
  DURABLE_DOCS   optional product docs/delivery (INDEX.yaml statuses for `due`)
  AR_CLAUDE_BIN  optional claude binary override (tests only)

Never: edit the product, email, message agents, rewrite project.yaml, or put secrets in files/events.
USAGE
}

case "${1:-}" in
  ""|-h|--help) usage; [[ -n "${1:-}" ]] && exit 0; exit 2 ;;
  due|run|triage|status) exec python3 "$PY" "$@" ;;
  *) usage; exit 2 ;;
esac
