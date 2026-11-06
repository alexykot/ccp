#!/usr/bin/env bash
# Control-plane orientation (SPEC §9): a SessionStart hook that gives the session the plane's
# role-neutral orientation (plugin/orientation.md) as additional context, in projects the plane
# manages (their docs/delivery/plane.json names a project_id). In the plane's own repo it says one
# line pointing at CLAUDE.md instead. Anywhere else it says nothing.
# It always exits 0.
set -u
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
[ -f "$root/docs/delivery/plane.json" ] || exit 0
# The plane's own repo (it manages its own development): a plane development session, not a seat.
if [ -f "$root/ccp/refs.py" ] && grep -q '"name": *"ccp"' "$root/.claude-plugin/marketplace.json" 2>/dev/null; then
  printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "Control-plane development session: this repo is the plane itself. Follow CLAUDE.md; the seat orientation does not apply here."}}'
  exit 0
fi
doc="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}/orientation.md"
[ -f "$doc" ] || exit 0
python3 - "$doc" <<'PY' || true
import json, re, sys
text = open(sys.argv[1]).read()
text = re.sub(r"^<!--.*?-->\s*", "", text, flags=re.S)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text[:9500]}}))
PY
exit 0
