---
task_id: 0019-parallel-doc-checks
title: Run docs.checks and architect.checks in parallel, opt-in
status: pending
kind: feature
depends_on: []
spec_refs: ["S20", "S21"]
adr_refs: []
review_point: R2
paths: ["ccp/rules.py", "ccp/config.py", "contracts/plane_config.schema.json", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0019-parallel-doc-checks

## Intent

`ccp docs check` can run a product's check commands in parallel when the product sets a workers count; the default stays serial and the output order stays stable.

## Context (not checked)

- Checks run serially today; a product with many slow checks waits on their sum.
- Serving checks from a product's own cache is product work.

## Scope

- **In:** a `workers` setting for the shared check runner, ordered output, per-check timeouts kept, tests.
- **Out:** caching check results.

## dod_checks

- id: `par-01`
  story: As a product with slow checks, parallel workers cut the wait.
  setup: a temporary product with two checks that each sleep one second and `workers: 2`.
  steps:
    1. Time `ccp docs check`.
  expect: under two seconds; output in declared order; failures reported as before.
  dry run: n/a — built by the task's test.
- id: `par-02`
  story: As a product with architect checks, they run in parallel too, and the architect gate reads the same results.
  setup: the same product with two `architect.checks` that each sleep one second and `workers: 2`.
  steps:
    1. Time `ccp docs check` with only the architect checks declared.
  expect: under two seconds; each check's `check E<n>` result line unchanged.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
