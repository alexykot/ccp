#!/usr/bin/env bash
# leak-check.sh — no managed product's specifics in tracked files (docs/ENGINEERING.md E3).
#
# The patterns live in a local, untracked denylist (one Perl-compatible regex per line, so `\b` word
# boundaries and a leading `(?i)` for a case-insensitive pattern work; # comments allowed)
# named by CCP_LEAK_DENYLIST, because the list itself names what must not appear. With no denylist
# the check passes vacuously; a named but missing denylist, or a bad pattern, exits 2. Exit 1 lists
# each match as path:line.
#
# The root LICENSE, and only it, is not scanned: a copyright notice names its holder by design.
set -euo pipefail
cd "$(dirname "$0")/.."
list="${CCP_LEAK_DENYLIST:-}"
if [ -z "$list" ]; then
  echo "leak-check: no denylist (CCP_LEAK_DENYLIST unset): nothing checked"
  exit 0
fi
[ -f "$list" ] || { echo "leak-check: CCP_LEAK_DENYLIST names $list, which does not exist" >&2; exit 2; }
pats="$(grep -vE '^\s*(#|$)' "$list" || true)"
[ -n "$pats" ] || { echo "leak-check: denylist is empty"; exit 0; }
set +e
hits="$(git grep -nIP -f <(printf '%s\n' "$pats") -- . ':(top,exclude)LICENSE' 2>/dev/null)"  # git's own errors would echo a pattern
rc=$?
set -e
if [ "$rc" -gt 1 ]; then
  echo "leak-check: a denylist pattern is invalid (git grep exit $rc); the patterns are not printed" >&2
  exit 2
fi
if [ -n "$hits" ]; then
  echo "leak-check: managed-product specifics found:" >&2
  printf '%s\n' "$hits" >&2
  exit 1
fi
echo "leak-check: clean"
