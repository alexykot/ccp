---
task_id: 0012-retire-the-old-snapshot
title: Retire now.json, STATUS.md and their scripts
status: pending
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S23", "S28"]
adr_refs: ["0034 D7"]
review_point: R1
paths: ["scripts/observability/rebuild-now.sh", "scripts/observability/status.sh", "scripts/observability/lib.py", "scripts/observability/README.md", "scripts/queue/README.md", "contracts/observability_now.schema.json", "ccp/", "plugin/", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0012-retire-the-old-snapshot

## Intent

The board is the status: nothing writes or reads `observability/now.json` or `STATUS.md`, and `rebuild-now.sh` and `status.sh` are gone. Whatever still reads the snapshot reads the board instead.

## Context (not checked)

- §23.4 states the target rule; ADR-0034 D7 records the ruling.
- Before deleting, find every reader (hooks, team.py, health, tests) and move it to the board or the ledger.
- Old `now.json` files left in queues are ignored.

## Scope

- **In:** the two scripts, the snapshot writer, readers of the snapshot, schema status (deprecated), READMEs, tests.
- **Out:** the board; the ledger.

## dod_checks

- id: `code-01`
  story: As a plane developer, nothing writes or reads the old snapshot.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -E 'now\.json|STATUS\.md|rebuild-now|status\.sh' -- ccp scripts plugin`.
  expect: no match apart from a comment noting the retirement.
  dry run (`216cda1`): matches in scripts/observability (lib.py, rebuild-now.sh, status.sh, set-waiting-on.sh, prune-prompts.sh, README) and scripts/queue/README.md.
- id: `board-01`
  story: As an operator, the board shows what the snapshot showed.
  setup: a temporary queue with a waiting task, an open question and a gate.
  steps:
    1. Run `ccp board status`.
  expect: it lists all three and exits non-zero.
  dry run: n/a — the test this task adds builds the queue.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
