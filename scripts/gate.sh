#!/usr/bin/env bash
# gate.sh — the plane's own test gate (docs/ENGINEERING.md E1, E2), run through `ccp suite run`.
#
# Runs every test module in its own process, GATE_WORKERS at a time (scripts/gate_parallel.py), then
# checks that no test left a `state/*` branch behind. Given module names (`tests.test_x`), it runs only
# those (the part lane, SPEC §14.7): its arguments go to gate_parallel.py. A module whose inputs are unchanged since it last
# passed is served from the test cache (GATE_CACHE_DIR) instead of run; gate_parallel.py records a pass
# only when its run left no `state/*` branch, so a leaking module is never served. GATE_COLD=1 is the cold option,
# no cache read or written (SPEC §15.3); CCP_SUITE_COLD, which `ccp suite run --cold` sets, is read the same
# way (SPEC §14.2). When `ccp suite run` sets CCP_SUITE_RESULT, writes the
# gate-result JSON there, with each module's seconds and tests and the modules ran and cached
# (contracts/suite_result.schema.json).
set -uo pipefail
cd "$(dirname "$0")/.."
case "${CCP_SUITE_COLD:-}" in ""|0) ;; *) export GATE_COLD=1 ;; esac
log="$(mktemp)"; trap 'rm -f "$log"' EXIT
start=$(date +%s)
python3 scripts/gate_parallel.py "$@" 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
secs=$(( $(date +%s) - start ))
left="$(git branch --list 'state/*')"
if [ -n "$left" ]; then
  echo "gate: tests left state/* branches behind: $left" >&2
  [ "$rc" -eq 0 ] && rc=1
fi
if [ -n "${CCP_SUITE_RESULT:-}" ]; then
  python3 scripts/gate_result.py "$log" "$secs" > "$CCP_SUITE_RESULT"
fi
exit "$rc"
