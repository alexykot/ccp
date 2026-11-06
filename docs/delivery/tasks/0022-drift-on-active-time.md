---
task_id: 0022-drift-on-active-time
title: Architect drift measured on active time
status: pending
kind: feature
depends_on: []
spec_refs: ["S19", "S27"]
adr_refs: ["0035 D3"]
review_point: R2
paths: ["ccp/health.py", "ccp/architect.py", "docs/spec/03-quality.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0022-drift-on-active-time

## Intent

The architect's drift trigger compares active time (wall time minus time waiting on the operator, the lead or an exclusive lane), so waits do not read as slower work.

## Context (not checked)

- Wall time includes sign-off holds and lane waits, which inflated the drift ratio.

## Scope

- **In:** the active-time measure, the drift trigger, SPEC §19.6 wording, tests.
- **Out:** the trigger's thresholds.

## dod_checks

- id: `drift-01`
  story: As the architect, a task that waited long on a sign-off does not trip drift.
  setup: a temporary queue with tasks whose wall time is mostly a recorded wait.
  steps:
    1. Run the drift computation.
  expect: the ratio uses active time and does not trip.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
