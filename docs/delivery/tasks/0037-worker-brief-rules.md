---
task_id: 0037-worker-brief-rules
title: Generic worker rules go into the implementer, reviewer and verifier briefs
status: pending
kind: feature
depends_on: []
spec_refs: ["S13"]
review_point: R3
paths: ["plugin/agents/", "docs/spec/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0037-worker-brief-rules

## Intent

The worker briefs carry three generic rules: a test module that the task's change necessarily breaks is in scope even if the task's Scope does not name it; a test failing under load is rerun alone before it is called a finding; line numbers a task file cites may be stale, so read the code at the merge base.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §13.
- These follow from running agents on shared machines and from briefs written ahead of their tasks; products add them to their own worker prose today.

## Scope

- **In:** the implementer, reviewer and verifier agent files state the rules that apply to each; §13 lists them.
- **Out:** product-specific worker rules.

## dod_checks

- id: `check-01`
  story: As a plane developer, each brief states its rules.
  setup: the PR head.
  steps:
    1. Run the plugin tests.
  expect: a test finds each rule in the brief it belongs to and fails when one is removed.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
