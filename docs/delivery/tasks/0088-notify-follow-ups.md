---
task_id: 0088-notify-follow-ups
title: Notification records and wording agree everywhere
status: pending
kind: bug
depends_on: []
spec_refs: ["S3"]
review_point: R5
paths: ["ccp/notify.py", "ccp/config.py", "scripts/observability/spec_maintainer.py", "plugin/skills/review-triage/", "tests/test_notify*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0088-notify-follow-ups

## Intent

The notification feature's edges agree with ADR-0039 and §3.6: no skill tells the lead never to email, config refuses what render refuses, and every notice is recorded.

## Context (not checked)

- Accepted plane proposal from the review of the lead-dispatched notices task.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** the review-triage skill's never-do list no longer says "Email anyone" (it says only the lead sends, a plane-rendered notice, §3.6); `notify.lead` values with a carriage return are refused at config load, as render refuses them; the spec maintainer's operator notice is recorded even when the product has no `plane.json`; the vacuous `sent == []` assertion in the ask-operator test becomes a real check.
- **Out:** new triggers.

## dod_checks

- id: `check-01`
  story: As a lead, no skill contradicts the notice rule.
  setup: a checkout of the PR head.
  steps:
    1. `git grep -n 'Email anyone' plugin/`
  expect: no match.
  dry run: on the merge base the review-triage skill matches.
- id: `check-02`
  story: As a product, a bad lead channel is refused at load.
  setup: a scratch `plane.json` whose `notify.lead.to` holds a carriage return.
  steps:
    1. Run `ccp tasks check`.
  expect: it is refused, naming `notify.lead`.
  dry run: on the merge base it loads and only render refuses.
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
