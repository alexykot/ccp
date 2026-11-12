---
task_id: 0078-refactor-tasks-do-not-rerun-the-gate
title: ccp tasks check refuses a refactor task whose check re-runs the gate
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S21"]
review_point: R5
paths: ["ccp/tasklog.py", "docs/spec/03-quality.md", "plugin/skills/writing-tasks/", "tests/test_tasklog*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0078-refactor-tasks-do-not-rerun-the-gate

## Intent

A `kind: refactor` task proves itself by its own checks, not by re-running the whole gate, and `ccp tasks check` refuses one that does (§21.1), since the plane knows each product's lanes.

## Context (not checked)

- Accepted plane proposal. Its triage records the operator's ruling of 11 Nov 2026, "if some gates can be skipped on that, they should be", as the acceptance.
- §31: this task adds or changes a § rule beyond describing its own feature, so its merge waits on the operator's approval of the final text at its merge gate (§31.1).

## Scope

- **In:** `ccp tasks check` refuses a `kind: refactor` task whose dod_check steps run the product's gate or full lane command (as declared in `suite.lanes`), naming the check and the lane; §21.1 lists the refusal (CURRENT: no such refusal; PROPOSED: "a `kind: refactor` task whose dod_check runs the gate or full lane (named)"); the writing-tasks skill says it.
- **Out:** judging other task kinds.

## dod_checks

- id: `check-01`
  story: As a lead, a refactor task that re-runs the gate is refused.
  setup: a scratch product whose `suite.lanes.gate` is `scripts/gate.sh`, with a refactor task whose check step runs `scripts/gate.sh`.
  steps:
    1. Run `ccp tasks check`.
  expect: it fails, naming the task, the check and the gate lane.
  dry run: on the merge base it passes.
- id: `check-02`
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
