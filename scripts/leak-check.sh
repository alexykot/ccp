#!/usr/bin/env bash
# leak-check.sh — no managed product's specifics in tracked files (docs/ENGINEERING.md E3).
#
# The patterns live in a local, untracked denylist (one Perl-compatible regex per line, so `\b` word
# boundaries and a leading `(?i)` for a case-insensitive pattern work; # comments allowed), because
# the list itself names what must not appear. It sits beside the installation's bindings as
# leak-denylist.txt. The first of these finds it:
#   1. CCP_LEAK_DENYLIST, a file path; set but missing, the check exits 2.
#   2. CCP_BINDINGS_DIR, when set, is authoritative: leak-denylist.txt in it, or no denylist (step 3
#      does not run, so a fenced test never reads the real installation).
#   3. `ccp --root <this repo> where`, run from PATH: leak-denylist.txt in the directory of its
#      `binding`, or in <plane>/projects when it names no binding. A missing ccp, a non-zero exit or
#      output that does not parse falls through quietly.
# Stdout names the source, never the path. With no denylist the check passes vacuously; a bad
# pattern exits 2. Exit 1 lists each match as path:line.
#
# The root LICENSE, and only it, is not scanned: a copyright notice names its holder by design.
set -euo pipefail
cd "$(dirname "$0")/.."
list=""
src=""
if [ -n "${CCP_LEAK_DENYLIST:-}" ]; then
  list="$CCP_LEAK_DENYLIST"
  src="CCP_LEAK_DENYLIST"
  [ -f "$list" ] || { echo "leak-check: CCP_LEAK_DENYLIST names a file that does not exist" >&2; exit 2; }
elif [ -n "${CCP_BINDINGS_DIR:-}" ]; then
  if [ -f "$CCP_BINDINGS_DIR/leak-denylist.txt" ]; then
    list="$CCP_BINDINGS_DIR/leak-denylist.txt"
    src="bindings dir"
  fi
else
  dir="$( (ccp --root "$PWD" where 2>/dev/null || true) | python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
    b = d.get("binding")
    print(os.path.dirname(b) if b else os.path.join(d["plane"], "projects"))
except Exception:
    pass
' 2>/dev/null || true)"
  if [ -n "$dir" ] && [ -f "$dir/leak-denylist.txt" ]; then
    list="$dir/leak-denylist.txt"
    src="bindings dir"
  fi
fi
if [ -z "$list" ]; then
  echo "leak-check: no denylist found (CCP_LEAK_DENYLIST, the bindings directory): nothing checked"
  exit 0
fi
echo "leak-check: denylist found ($src)"
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
