#!/usr/bin/env bash
# Control-plane run binding (SPEC §11.1). SubagentStart and SubagentStop hooks.
#
#   run-binding.sh start|stop                              from the control-plane plugin (SPEC §9.1)
#   run-binding.sh start|stop <queue root> <plane checkout> from a product's managed copy (before §4)
#
# It hands the hook's JSON to `ccp agent start|stop`, which binds the oldest pending run of the
# agent's type (opened by `ccp prompt`) to the agent, or stops it. Without arguments `ccp` finds the
# project's queue itself (`--root` is the session's project directory, and QUEUE_ROOT comes from the
# plane's binding for the project in its docs/delivery/plane.json). It always exits 0: a hook never
# blocks or fails the agent it watches. Errors land in <queue>/runs/_unbound.jsonl.
set -u
action="${1:-}"; queue="${2:-}"; plane="${3:-}"
case "$action" in start|stop) ;; *) exit 0 ;; esac
input="$(cat)"
root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
if [ -n "$queue" ]; then
  [ -d "$queue" ] && [ -x "$plane/bin/ccp" ] || exit 0
  printf '%s' "$input" | QUEUE_ROOT="$queue" "$plane/bin/ccp" --root "$root" agent "$action" >/dev/null 2>&1 || true
else
  command -v ccp >/dev/null 2>&1 || exit 0
  printf '%s' "$input" | ccp --root "$root" agent "$action" >/dev/null 2>&1 || true
fi
exit 0
