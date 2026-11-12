---
task_id: 0089-health-and-round-accounting-follow-ups
title: Health and estimates count merge and ruling rounds, and the killed-run rule is pinned
status: pending
kind: bug
depends_on: []
spec_refs: ["S13", "S14", "S23"]
review_point: R5
paths: ["ccp/health.py", "ccp/drill.py", "ccp/estimate.py", "docs/spec/02-delivery.md", "tests/test_gate_time.py", "tests/test_health*.py", "tests/test_estimate*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0089-health-and-round-accounting-follow-ups

## Intent

Merge and ruling rounds are counted as what they are in health, drill and estimates, and the killed-at-the-limit finding's filter and wording are exact (§13.2, §14.6).

## Context (not checked)

- Accepted plane proposals from the reviews of the named-rounds and shell-limit tasks.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** health, drill and estimate give merge and ruling rounds their own buckets (`merge`, `ruling`), so they no longer land in "other" or count as review time; a test pins the open-or-killed filter in `gate_time` with an interrupted run past the limit; §14.6's "Killed at the limit" bullet says the elapsed time runs to the earliest of the run's stop, report or abandonment.
- **Out:** changing what a fix round is.

## dod_checks

- id: `check-01`
  story: As a lead, merge rounds are counted as merges.
  setup: a scratch queue with a task that had a merge round.
  steps:
    1. Run `ccp health --json`.
  expect: the round is in a `merge` bucket, not `other`.
  dry run: on the merge base it is in `other`.
- id: `check-02`
  story: As a plane developer, the killed filter is pinned.
  setup: the test suite at the PR head with the filter removed.
  steps:
    1. Run `tests.test_gate_time`.
  expect: a test fails.
  dry run: on the merge base removing the filter keeps the suite green.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
