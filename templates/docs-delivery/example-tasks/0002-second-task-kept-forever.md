---
task_id: 0002-second-task-kept-forever
title: EXAMPLE — a second task that depends on the first
status: pending
depends_on: ["0001-hello-delivery-log"]
spec_refs: ["docs/SPEC.md#overview"]
created: 2026-09-15
updated: 2026-09-30
---

# Task: 0002-second-task-kept-forever

> EXAMPLE only — demonstrates `depends_on` pointing at `0001-…`.

## Intent

EXAMPLE second task kept forever; depends on the first EXAMPLE task.

## Context (not checked)

The dependency is declared in the frontmatter, not repeated as a check.

## Scope

- **In:** demonstrate `depends_on`
- **Out:** real product

## dod_checks

- id: `other-01`
  story: As a runner, I ask for the next task so I know claim order.
  setup: Both EXAMPLE tasks present, neither done.
  steps:
    1. Run `ccp tasks next`.
  expect: It names `0001-hello-delivery-log`, not this task.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
