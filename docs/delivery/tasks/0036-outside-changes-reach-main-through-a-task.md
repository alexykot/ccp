---
task_id: 0036-outside-changes-reach-main-through-a-task
title: Changes made outside the plane reach the integration branch through a task
status: pending
kind: feature
depends_on: []
spec_refs: ["S10", "S15"]
review_point: R3
paths: ["docs/spec/", "ccp/", "plugin/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0036-outside-changes-reach-main-through-a-task

## Intent

Code or docs changed outside the plane's flow (another agent, the operator directly, a tool) reach the integration branch through a task, or get an after-the-fact task when they merged first, so review, verify and the task log cover them.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §10 and §15.
- Every product gets changes from outside its runner; without a defined path they bypass review, verify and the task log.

## Scope

- **In:** §10 describes the path and the after-the-fact task kind; `ccp` can report integration-branch commits since a ref that no task or PR covers (`ccp tasks orphans` or a `health` finding); the lead's orientation says what to do.
- **Out:** blocking pushes on the forge.

## dod_checks

- id: `check-01`
  story: As a lead, an uncovered commit is reported.
  setup: a scratch product with a commit on the integration branch that no task or merged PR names.
  steps:
    1. Run the report.
  expect: it lists the commit; after an after-the-fact task names it, it does not.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, task commits are not reported.
  setup: commits from merged task PRs only.
  steps:
    1. Run the report.
  expect: nothing listed.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
