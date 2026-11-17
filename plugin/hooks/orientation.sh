#!/usr/bin/env bash
# Control-plane orientation (SPEC §9): a SessionStart hook that gives the session the plane's
# role-neutral orientation (plugin/orientation.md) as additional context, in projects the plane
# manages (their docs/delivery/plane.json names a project_id). In the plane's own repo it says one
# line pointing at CLAUDE.md instead. Anywhere else it says nothing.
# After the orientation it lists the product's pending notices (SPEC §3.6, `ccp notify pending`), so the
# lead finds what fired while it was away, an `upgrade` notice a release left (§29.3) among them. It asks
# the `ccp` beside the plugin (the plane checkout it is in), else `ccp` on PATH; no queue, no notices.
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
pending=""
[ -n "$ccp" ] && pending="$("$ccp" --root "$root" notify pending 2>/dev/null </dev/null)" || pending=""
python3 - "$doc" "$pending" <<'PY' || true
import json, re, sys
text = open(sys.argv[1]).read()
text = re.sub(r"^<!--.*?-->\s*", "", text, flags=re.S)
try:
    rows = json.loads(sys.argv[2]).get("pending") or []
except (ValueError, AttributeError):
    rows = []
notes = ""
if rows:
    head = ("\n\n## Pending notices\n\nFired and not yet sent (plane SPEC §3.6). The lead sends each over the "
            "product's channel and records it with the `ccp notify sent` call shown; `ccp notify pending` "
            "lists them in full.\n")
    lines = []
    for r in rows:
        reason = str(r.get("reason") or "")
        reason = f" — {reason[:500]}…" if len(reason) > 500 else (f" — {reason}" if reason else "")
        lines.append(f"- {r.get('subject') or r.get('trigger')}{reason}. Record: `{r.get('record', '')}`")
    body, cap = "", 2400
    for i, ln in enumerate(lines):
        if len(body) + len(ln) + 1 > cap:
            body += f"- … {len(lines) - i} more: `ccp notify pending`\n"
            break
        body += ln + "\n"
    notes = head + body
text = text[:9500 - len(notes)].rstrip("\n") + notes if notes else text[:9500]
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
PY
exit 0
