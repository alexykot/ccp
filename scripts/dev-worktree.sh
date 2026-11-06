#!/usr/bin/env bash
# dev-worktree.sh <branch> [dir] — a git worktree for plane development, on a new branch from origin/main.
#
# Develop only in such a worktree, never in the dev checkout or the run checkout (CLAUDE.md).
# dir defaults to $CCP_WORKTREES/<branch> (CCP_WORKTREES defaults to $TMPDIR/ccp-worktrees).
# Prints the worktree's path.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
[ $# -ge 1 ] || { sed -n '2,7p' "$0"; exit 2; }
branch="$1"
dir="${2:-${CCP_WORKTREES:-${TMPDIR:-/tmp}/ccp-worktrees}/$branch}"
git -C "$HERE" fetch -q origin
git -C "$HERE" worktree add -q -b "$branch" "$dir" origin/main
echo "$dir"
