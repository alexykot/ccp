#!/usr/bin/env bash
# status.sh — human ops-board summary. Exit non-zero if open blockers.

set -euo pipefail
echo "note: superseded by \`ccp board status|build\` (SPEC §28.3); this still prints the §23 snapshot" >&2

HERE="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  status.sh [--no-rebuild]

Print a one-screen digest of $QUEUE_ROOT/observability/now.json
(tasks, blockers, work/wait hours, seats, auth).

Exit 0 if no open blockers.
Exit 1 if any open blocker (cron wrappers). Seats are never stale (SPEC §18.3).

Spec maintainer (SPEC §17): also lists spec-maintainer questions (status,
verdict, dispatch, blocked tasks), the lock holder, and wait timers split
into spec_maintainer vs operator_decision (per question and per task wait_hours_by_reason).
Tasks with waiting_on=spec_maintainer are open blockers (kind spec_maintainer).
Exit 2 on usage / missing QUEUE_ROOT.

By default rebuilds the snapshot first (events + live probes).
--no-rebuild reads an existing now.json (rebuilds if missing).

This output is the email digest for /status and blocker-set alerts.
No secrets.

Env:
  QUEUE_ROOT    required — e.g. $HOME/projects/.delivery-queue/<project_id>
  PROJECT_ID    optional
  DURABLE_DOCS  optional
  OBS_NOW       optional RFC3339 pin
  OBS_SKIP_PS=1 skip pid probe
  PROJECT_YAML  optional project.yaml (else $QUEUE_ROOT/project.yaml) — spec_maintainer block

  -h, --help
EOF
}

REBUILD=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-rebuild) REBUILD=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "status: unknown arg $1" >&2; usage >&2; exit 2 ;;
  esac
done

QUEUE_ROOT="${QUEUE_ROOT:?set QUEUE_ROOT to live queue dir outside product git}"
command -v python3 >/dev/null || { echo "status: python3 required" >&2; exit 1; }

args=(status --queue-root "$QUEUE_ROOT")
if [[ "$REBUILD" -eq 0 ]]; then
  args+=(--no-rebuild)
fi
exec python3 "$HERE/lib.py" "${args[@]}"
