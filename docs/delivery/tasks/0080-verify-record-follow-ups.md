---
task_id: 0080-verify-record-follow-ups
title: The verifier's packet and the record's version and ruling checks are complete
status: pending
kind: bug
depends_on: []
spec_refs: ["S15"]
review_point: R5
paths: ["templates/prompts/", "plugin/agents/delivery-verifier.md", "contracts/", "ccp/verify.py", "tests/test_verify*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0080-verify-record-follow-ups

## Intent

A verifier writes a valid record on its first try, and the record's version and ruling checks hold against every way they can be broken (§15.4).

## Context (not checked)

- Accepted plane proposals: a verifier discovered `produced_by` only from the refusal; and reviews of the record-version and producer-rule tasks left gaps.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** the verify prompt template and the verifier brief state `produced_by` and the three `rests_on` forms, with a valid example check, replacing "whose claim it rests on" (and the test that pins that sentence); `contracts/verification.example.json` carries `schema_version`; the record-version test also requires raising `schema_version` when a key is added; a cited spec question needs its question file as well as its answer; a cited gate file must name the gate it is filed as (`escalation_id`) and the task.
- **Out:** changing the three forms.

## dod_checks

- id: `check-01`
  story: As a verifier, the packet shows a valid check.
  setup: a checkout of the PR head.
  steps:
    1. Render a verify prompt with `ccp prompt verify` for a scratch task.
  expect: it states `produced_by` and the three `rests_on` forms and shows a valid example check.
  dry run: on the merge base it says "whose claim it rests on" and no `produced_by`.
- id: `check-02`
  story: As a lead, a ruling id without its question is refused.
  setup: a scratch queue with an answer file whose question file is missing, cited in `rests_on`.
  steps:
    1. Record a verdict citing it.
  expect: it is refused, naming the id.
  dry run: on the merge base it is accepted.
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
