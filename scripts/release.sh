#!/usr/bin/env bash
# release.sh [worktree] — the release after a merge to main (a merge to main is a release).
#
#   1. fast-forwards the dev checkout (the repo's main worktree);
#   2. moves the run checkout to origin/main (run-checkout.sh update; it restarts the telemetry receiver);
#   3. checks the telemetry receiver is up, and says how to restart it when it is not;
#   4. removes the given merged worktree and its local branch.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
MAIN="$(git -C "$HERE" worktree list --porcelain | awk 'NR==1 {print $2}')"
RUN="${CCP_RUN_CHECKOUT:-$(dirname "$MAIN")/control-plane-run}"
die() { echo "release: $*" >&2; exit "${2:-1}"; }
# From the run checkout, the pull below would be a plain merge with nothing keeping its local
# projects/: run this from the dev checkout or one of its worktrees.
[ "$(cd "$MAIN" && pwd -P)" != "$(cd "$RUN" 2>/dev/null && pwd -P)" ] || die "run this from the dev checkout or a worktree of it, not from the run checkout"

git -C "$MAIN" pull -q --ff-only
echo "release: dev checkout at $(git -C "$MAIN" rev-parse --short HEAD)"
CCP_RUN_CHECKOUT="$RUN" "$MAIN/scripts/run-checkout.sh" update

if [ -x "$RUN/bin/ccp" ]; then
  sleep 3   # the receiver restarts under launchd's KeepAlive
  if ! "$RUN/bin/ccp" otel status 2>/dev/null | python3 -c 'import json,sys; sys.exit(0 if (json.load(sys.stdin).get("receiver") or {}).get("ok") else 1)' 2>/dev/null; then
    echo "release: the telemetry receiver is not up. A Claude Code shell cannot reach the login session's" >&2
    echo "  launchd: from a normal terminal run  launchctl kickstart -k gui/\$(id -u)/<the otel label>" >&2
  fi
fi

if [ $# -ge 1 ]; then
  wt="$(cd "$1" && pwd -P)" || die "no worktree at $1"
  branch="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  git -C "$MAIN" worktree remove "$wt"
  [ -n "$branch" ] && [ "$branch" != main ] && git -C "$MAIN" branch -D -q "$branch" || true
  echo "release: removed $wt"
fi
