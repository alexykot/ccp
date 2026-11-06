---
task_id: 0011-retire-stale-seat-and-verify-stale
title: Retire the seat stale rule, stale_seat and verify_stale
status: pending
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S18", "S23"]
adr_refs: ["0034 D6"]
review_point: R1
paths: ["scripts/observability/lib.py", "scripts/observability/heartbeat.sh", "scripts/observability/README.md", "contracts/observability_now.schema.json", "contracts/project.schema.json", "ccp/config.py", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0011-retire-stale-seat-and-verify-stale

## Intent

The snapshot raises no `stale_seat` and no `verify_stale` blocker, and the binding has no `cadence.verify_stale_minutes`; heartbeats are still written. Older snapshots and bindings carrying them are still read without error.

## Context (not checked)

- §18.3 states the target rule; ADR-0034 D6 records the ruling.
- `ccp tasks claim` and `close` write heartbeats; keep them.
- A binding that still sets `cadence.verify_stale_minutes` is accepted and ignored.

## Scope

- **In:** the blocker kinds, their timers and thresholds, the knob, their renderings, schema entries (kept read-only for old data), tests.
- **Out:** heartbeats; other blockers.

## dod_checks

- id: `code-01`
  story: As a plane developer, no stale-seat or verify-stale logic remains.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -E 'stale_seat|verify_stale' -- ccp scripts contracts`.
  expect: no match apart from readers of old data, each with a comment saying so.
  dry run (`216cda1`): 16 matching lines in scripts/observability/lib.py alone.
- id: `compat-01`
  story: As an operator with an older queue, the snapshot and board rebuild.
  setup: a temporary `QUEUE_ROOT` with an old snapshot carrying both blockers and a binding with `cadence.verify_stale_minutes`.
  steps:
    1. Run `ccp board build` against it.
  expect: it succeeds and shows neither blocker.
  dry run: n/a — the test this task adds builds the queue.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
