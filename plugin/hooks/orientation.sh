#!/usr/bin/env bash
# Control-plane orientation (SPEC §9): a SessionStart hook that gives the session the plane's
# role-neutral orientation (plugin/orientation.md) as additional context, in projects the plane
# manages (their docs/delivery/plane.json names a project_id). In the plane's own repo it says one
# line pointing at CLAUDE.md instead. Anywhere else it says nothing.
# After the orientation it appends what `ccp orientation --tail` prints (SPEC §9.3): the product's pending
# notices (§3.6), an `upgrade` notice a release left (§29.3) among them, and the allowance warning (§25.1: no
# usage is read and nothing bounds spend); `ccp` builds that text. It asks the `ccp` beside the plugin (the
# plane checkout it is in), else `ccp` on PATH; no queue, no tail. That one call gets 3 s: a slow queue drops
# the tail, never the orientation (the hook's own limit is 10 s).
# It always exits 0.
set -u
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
[ -f "$root/docs/delivery/plane.json" ] || exit 0
# The plane's own repo (it manages its own development): a plane development session, not a seat.
if [ -f "$root/ccp/refs.py" ] && grep -q '"name": *"ccp"' "$root/.claude-plugin/marketplace.json" 2>/dev/null; then
  printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "Control-plane development session: this repo is the plane itself. Follow CLAUDE.md; the seat orientation does not apply here."}}'
  exit 0
fi
plugin="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
doc="$plugin/orientation.md"
[ -f "$doc" ] || exit 0
ccp="$plugin/../bin/ccp"
[ -x "$ccp" ] || ccp="$(command -v ccp 2>/dev/null || true)"
python3 - "$doc" "$ccp" "$root" <<'PY' || true
import json, re, subprocess, sys
text = open(sys.argv[1]).read()
text = re.sub(r"^<!--.*?-->\s*", "", text, flags=re.S)
notes = ""
if sys.argv[2]:
    try:
        res = subprocess.run([sys.argv[2], "--root", sys.argv[3], "orientation", "--tail"], capture_output=True,
                             text=True, stdin=subprocess.DEVNULL, timeout=3)
        notes = res.stdout if res.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError, ValueError):
        notes = ""
text = text[:9500 - len(notes)].rstrip("\n") + notes if notes else text[:9500]
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
PY
exit 0
