---
task_id: 0020-cold-gate-and-mutation-lane
title: A gate run with nothing cached counts as cold; the verify prompt names the mutation lane
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S15"]
adr_refs: []
review_point: R2
paths: ["ccp/verify.py", "templates/prompts/verify.md", "templates/prompts/review.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0020-cold-gate-and-mutation-lane

## Intent

`ccp verify record` treats a recorded gate run with `cached == 0` as cold, so a cold task's approve is not refused for a missing `cold: true`; the review and verify prompts name the lane a mutation run goes through.

## Context (not checked)

- `ran` and `cached` already fill from the gate's `suite_id`; `cold` never did, so every cold task's approve needed a hand edit.

## Scope

- **In:** the cold inference, the prompt wording, tests.
- **Out:** the cache rules themselves.

## dod_checks

- id: `cold-01`
  story: As a verifier on a cold task, my approve is accepted from the recorded gate run.
  setup: a temporary queue with a gate suite record with `cached: 0`.
  steps:
    1. Record an approve citing that `suite_id` with no `cold` field.
  expect: accepted; the record shows the run as cold.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
