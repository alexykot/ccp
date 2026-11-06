#!/usr/bin/env bash
# install-git-hooks.sh — point this clone (and all its worktrees) at scripts/git-hooks.
set -euo pipefail
git -C "$(cd "$(dirname "$0")/.." && pwd)" config core.hooksPath scripts/git-hooks
echo "install-git-hooks: core.hooksPath = scripts/git-hooks"
