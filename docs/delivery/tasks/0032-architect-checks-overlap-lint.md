---
task_id: 0032-architect-checks-overlap-lint
title: ccp refuses architect checks that cover the same test twice
status: pending
kind: feature
depends_on: []
spec_refs: ["S19"]
review_point: R3
paths: ["ccp/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0032-architect-checks-overlap-lint

## Intent

`ccp` checks its own `architect.checks` config: two checks that select the same test module or class are refused, so a test is not run twice in one gate and a failure is not blamed on two checks.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §19.
- The config is the plane's, so the plane lints it; without this, each product writes its own test of plane config.

## Scope

- **In:** config validation (or `ccp architect check`) resolves each check's test selectors and fails when two overlap, naming both checks and the shared module or class; §19 notes it.
- **Out:** judging whether a check is useful.

## dod_checks

- id: `check-01`
  story: As a lead, an overlapping config is refused.
  setup: a scratch product with two checks both selecting `tests.test_a`.
  steps:
    1. Validate the config.
  expect: it fails and names both checks and `tests.test_a`.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, disjoint checks pass.
  setup: two checks selecting different modules.
  steps:
    1. Validate the config.
  expect: it passes.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
