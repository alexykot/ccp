#!/usr/bin/env bash
# prune-prompts.sh — optional Layer 2 retention. DEFAULT OFF until the operator says prune.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  prune-prompts.sh [--older-than-days N] [--keep-last N] [--apply]

Alpha default: keep all prompt audit files.
This script is a stub until the operator asks to prune.

Safety:
  - Refuses to delete unless PRUNE_PROMPTS=1 AND --apply
  - Default mode is --dry-run (prints what would be removed)
  - Never touches events.jsonl / product git

Options:
  --older-than-days N   candidates older than N days (mtime)
  --keep-last N         keep newest N files per task_id (default: keep all)
  --apply               actually delete (still requires PRUNE_PROMPTS=1)
  -h, --help

Env:
  QUEUE_ROOT        required
  PRUNE_PROMPTS=1   required to delete
EOF
}

OLDER=""
KEEP=""
APPLY=0

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --older-than-days) OLDER="${2:-}"; shift 2 ;;
    --keep-last) KEEP="${2:-}"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "prune-prompts: unknown arg $1" >&2; usage >&2; exit 2 ;;
  esac
done

QUEUE_ROOT="${QUEUE_ROOT:?set QUEUE_ROOT to live queue dir outside product git}"
PROMPT_ROOT="${QUEUE_ROOT}/prompts"

if [[ ! -d "$PROMPT_ROOT" ]]; then
  echo "prune-prompts: no $PROMPT_ROOT (nothing to do)"
  exit 0
fi

if [[ -z "$OLDER" && -z "$KEEP" ]]; then
  echo "prune-prompts: DEFAULT OFF (alpha keep-all)."
  echo "prune-prompts: pass --older-than-days N and/or --keep-last N to list candidates."
  echo "prune-prompts: deletion requires PRUNE_PROMPTS=1 and --apply."
  exit 0
fi

export QUEUE_ROOT OLDER KEEP APPLY
export PRUNE_PROMPTS="${PRUNE_PROMPTS:-}"

python3 <<'PY'
import os, time
from pathlib import Path

root = Path(os.environ["QUEUE_ROOT"]).expanduser() / "prompts"
older = os.environ.get("OLDER") or ""
keep = os.environ.get("KEEP") or ""
apply = os.environ.get("APPLY") == "1"
allow = os.environ.get("PRUNE_PROMPTS") == "1"
now = time.time()

files = sorted(p for p in root.rglob("*.json") if p.is_file())
candidates = []

if older:
    cutoff = now - int(older) * 86400
    for p in files:
        if p.stat().st_mtime < cutoff:
            candidates.append(p)

if keep:
    n = int(keep)
    by_task = {}
    for p in files:
        by_task.setdefault(p.parent.name, []).append(p)
    for tid, plist in by_task.items():
        plist.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        for p in plist[n:]:
            if p not in candidates:
                candidates.append(p)

if not candidates:
    print("prune-prompts: no candidates")
    raise SystemExit(0)

print(f"prune-prompts: {len(candidates)} candidate(s)")
for p in candidates:
    print(f"  {p}")

if not apply:
    print("prune-prompts: dry-run (pass --apply and PRUNE_PROMPTS=1 to delete)")
    raise SystemExit(0)
if not allow:
    print("prune-prompts: refusing delete — set PRUNE_PROMPTS=1 (default off)", flush=True)
    raise SystemExit(2)

for p in candidates:
    p.unlink()
    print(f"prune-prompts: removed {p}")
PY
