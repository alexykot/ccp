---
task_id: 0018-reason-for-a-repeat-verify
title: Enforce a reason for a verify round with no fix since the last
status: pending
kind: feature
depends_on: []
spec_refs: ["S15"]
adr_refs: []
review_point: R2
paths: ["ccp/prompt.py", "ccp/verify.py", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0018-reason-for-a-repeat-verify

## Intent

`ccp prompt verify` refuses a second verify round with no fix round since the last verify unless `--note` gives the reason, as SPEC §15.6 already requires; the reason reaches the verifier's record.

## Context (not checked)

- The rule exists in the SPEC; nothing enforces it.

## Scope

- **In:** the check in `ccp prompt verify`, its message, tests.
- **Out:** changing the rule.

## dod_checks

- id: `verify-01`
  story: As a runner, I cannot re-verify without saying why.
  setup: a temporary queue with a verify round and no fix round after it.
  steps:
    1. Run `ccp prompt verify <task>` without `--note`.
  expect: exit non-zero naming the rule; with `--note "…"` it opens the round.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
