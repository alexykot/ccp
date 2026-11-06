#!/usr/bin/env bash
# rebuild-now.sh — fold events.jsonl + live probes into observability/now.json + STATUS.md

set -euo pipefail
echo "note: superseded by \`ccp board status|build\` (SPEC §28.3); this still writes the §23 snapshot" >&2

HERE="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  rebuild-now.sh

Fold $QUEUE_ROOT/observability/events.jsonl + live probes (auth/status.json,
running.json pid, seats/*.json, tasks/*.json, work.json, optional DURABLE_DOCS
INDEX.yaml) into:

  $QUEUE_ROOT/observability/now.json
  $QUEUE_ROOT/observability/STATUS.md

Env:
  QUEUE_ROOT     required
  PROJECT_ID     optional label
  DURABLE_DOCS   optional product docs/delivery path (INDEX.yaml status mirror)
  OBS_NOW        optional RFC3339 pin for deterministic rebuilds / examples
  OBS_SKIP_PS=1  skip pid-alive probe

See README.md for the locked work_hours formula.

  -h, --help
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -gt 0 ]]; then
  echo "rebuild-now: unexpected arg $1" >&2
  usage >&2
  exit 2
fi

QUEUE_ROOT="${QUEUE_ROOT:?set QUEUE_ROOT to live queue dir outside product git}"
command -v python3 >/dev/null || { echo "rebuild-now: python3 required" >&2; exit 1; }
exec python3 "$HERE/lib.py" rebuild --queue-root "$QUEUE_ROOT"
