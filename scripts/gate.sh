#!/usr/bin/env bash
# gate.sh — the plane's own test gate (docs/ENGINEERING.md E1, E2), run through `ccp suite run`.
#
# Runs the full suite, then checks that no test left a `state/*` branch behind. When `ccp suite run`
# sets CCP_SUITE_RESULT, writes the gate-result JSON there (contracts/suite_result.schema.json).
set -uo pipefail
cd "$(dirname "$0")/.."
log="$(mktemp)"; trap 'rm -f "$log"' EXIT
start=$(date +%s)
python3 -m unittest discover -s tests -t . 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
secs=$(( $(date +%s) - start ))
left="$(git branch --list 'state/*')"
if [ -n "$left" ]; then
  echo "gate: tests left state/* branches behind: $left" >&2
  [ "$rc" -eq 0 ] && rc=1
fi
if [ -n "${CCP_SUITE_RESULT:-}" ]; then
  python3 "$(dirname "$0")/gate_result.py" "$log" "$secs" > "$CCP_SUITE_RESULT"
fi
exit "$rc"
