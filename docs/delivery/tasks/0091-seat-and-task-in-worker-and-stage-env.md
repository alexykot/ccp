---
task_id: 0091-seat-and-task-in-worker-and-stage-env
title: Workers and gate stages know their seat, kind and task
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S13", "S14"]
review_point: R5
paths: ["ccp/suite.py", "ccp/prompt.py", "ccp/wt.py", "docs/spec/02-delivery.md", "tests/test_suite_stages.py", "tests/test_prompt*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0091-seat-and-task-in-worker-and-stage-env

## Intent

A product names per-seat resources (a scratch database per implementer, reviewer and verifier) from fields the plane provides, not by parsing a worktree's directory name (§12.1, §13.1, §14.2).

## Context (not checked)

- Accepted plane proposal extending the task that gave gate stages the worktree's fields.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** `prompts.worker_env` templates gain `{{seat}}` and `{{kind}}` (`impl`, `rev`, `ver`, `mut`, `base`); gate stages receive `CCP_TASK_ID`, `CCP_NNNN` and `CCP_WT_KIND` besides the existing `CCP_WT_*` fields; §12.1 and §14.2 list them.
- **Out:** naming any resource for the product.

## dod_checks

- id: `check-01`
  story: As a product, a stage knows its task and seat.
  setup: a scratch product whose gate stage prints `CCP_TASK_ID`, `CCP_NNNN` and `CCP_WT_KIND`, run in a `ver-0001` worktree.
  steps:
    1. Run the gate lane.
  expect: the stage prints the task id, `0001` and `ver`.
  dry run: on the merge base the three are unset.
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
