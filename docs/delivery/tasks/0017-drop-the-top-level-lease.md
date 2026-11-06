---
task_id: 0017-drop-the-top-level-lease
title: Drop work.json's top-level lease
status: pending
kind: feature
depends_on: []
spec_refs: ["S16", "S23"]
adr_refs: []
review_point: R2
paths: ["ccp/lifecycle.py", "ccp/queue.py", "ccp/forecast.py", "scripts/observability/lib.py", "contracts/", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0017-drop-the-top-level-lease

## Intent

`work.json` keeps no top-level `lease`: each runner slot keeps its own, so a closed task's lease never lingers at the top level. An old `work.json` with the field still reads.

## Context (not checked)

- `_leave_work` returns early when the task is neither the current task nor in flight, so the top-level lease survived close.
- One home per fact (ADR-0003): the slots hold the leases.

## Scope

- **In:** writers and readers of the top-level `lease`, the snapshot and board, schemas, tests.
- **Out:** per-slot leases.

## dod_checks

- id: `lease-01`
  story: As a runner, closing a task leaves no lease behind at the top level.
  setup: a temporary queue after a claim and a close.
  steps:
    1. Read `work.json`.
  expect: no top-level `lease` key; the slot's own lease cleared.
  dry run: n/a — built by the task's test.
- id: `code-01`
  story: As a plane developer, nothing writes the top-level lease.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -E "\\[.lease.\\]|\\.get\\(.lease.\\)" -- ccp scripts`.
  expect: only readers that tolerate an old field, each with a comment.
  dry run (`a6dcca1`): 6 hits, incl. the forecast's read of `work["lease"]`.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
