---
task_id: 0063-sign-off-follow-ups-and-plane-mutate-command
title: The sign-off refusals are pinned, the brief-staleness rule is in the writing guide, and the plane sets a mutate command
status: pending
kind: chore
depends_on: []
spec_refs: ["S3", "S20"]
review_point: R4
paths: ["tests/test_sign_off.py", "plugin/skills/writing-tasks/", "docs/delivery/plane.json"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0063-sign-off-follow-ups-and-plane-mutate-command

## Intent

Every fail-closed branch of the brief-staleness check has a test that fails when the branch is removed; the writing-tasks skill tells task writers that editing a task file after its brief sign-off makes the sign-off stale; and the plane's own `plane.json` sets `mutate.command`, so its verifiers use `ccp mutate` instead of applying mutations by hand.

## Context (not checked)

- From task 0039's review: three branches have no test (no commit for the task file, a head that is not a sha, a head that is not a commit in the checkout); one survives mutation.
- The plane's own verifiers applied mutations by hand on two tasks because `plane.json` sets no `mutate.command`.

## Scope

- **In:** three tests, one per branch; one sentence in the writing-tasks skill; `mutate.command` in the plane's `plane.json`, running one test module in the form §20.6 gives.
- **Out:** the sign-off rule itself.

## dod_checks

- id: `check-01`
  story: As a plane developer, each staleness refusal is pinned.
  setup: the PR head with each of the three branches removed in turn from the staleness check.
  steps:
    1. Run `tests.test_sign_off` after each removal.
  expect: a test fails each time.
  dry run: on the merge base at least one removal keeps the suite green.
- id: `check-02`
  story: As a verifier on the plane, `ccp mutate` runs.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp mutate` with one mutant against a test in `tests/test_sign_off.py`.
  expect: it runs the test and records the mutant killed or survived.
  dry run: on the merge base it refuses: no `mutate.command`.
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
