---
task_id: 0091-seat-and-task-in-worker-and-stage-env
title: Workers and gate stages know their seat, kind and task
status: done
kind: feature
depends_on: []
spec_refs: ["S12", "S13", "S14"]
review_point: R5
paths: ["ccp/suite.py", "ccp/prompt.py", "ccp/wt.py", "docs/spec/02-delivery.md", "tests/test_suite_stages.py", "tests/test_prompt*.py"]
created: 2026-11-12
updated: 2026-11-13
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

- 2026-11-13: `prompts.worker_env` takes `{{kind}}` and `{{seat}}` (`config.WORKER_ENV_FIELDS`, the
  plane.json schema). `ccp prompt` fills them from the phase: `impl` for implement, fix, merge and
  ruling, `rev` for review, `ver` for verify; the seat is that kind's default seat (`wt.KINDS`), which
  is what `ccp wt create` records, since no plane step passes `--seat`. A lane's stages in a recorded
  worktree also get `CCP_TASK_ID` and `CCP_NNNN` from its record (`suite.worktree_env`); the record
  holds the full id, because `ccp wt create` resolves `--task` through the task log, and both are
  empty in `ver-baseline`. `CCP_WT_KIND` was already given to stages (task 0054), so it needed no
  change. SPEC: §12.1 gains a bullet listing the fields, §14.2's environment item names the two new
  variables, and §8.1's `worker_env` field list (01-model.md) names `kind` and `seat`.

## Verification notes

- 2026-11-13 — verifier, PR #92 head `3efb46a` (squash `ac7f9dc`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0091-seat-and-task-in-worker-and-stage-env.json.
