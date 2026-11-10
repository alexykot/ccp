---
task_id: 0054-stages-get-worktree-fields
title: Gate stages receive the worktree's fields
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S14"]
review_point: R4
paths: ["ccp/suite.py", "ccp/wt.py", "docs/spec/02-delivery.md", "tests/test_suite_stages.py"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0054-stages-get-worktree-fields

## Intent

A gate stage run in a task worktree gets that worktree's `CCP_WT_*` fields (its name, kind, task and the values its env hooks set up, such as a scratch resource's name), so a staged lane can reach per-worktree resources without each caller exporting them by hand (§12, §14).

## Context (not checked)

- Raised by a managed product: a per-worktree resource (a scratch database, a port, a cache dir) set up by the worktree's env hook was unreachable from a staged gate lane unless the caller set a variable by hand.
- Env hooks already receive `CCP_WT_*`; stages do not.
- §31: this task's SPEC text describes its own feature. If the operator's standing ruling for such text (given for R3, 2026-11-10) is not extended to R4, the merge waits on their approval.

## Scope

- **In:** `ccp suite run` in a worktree `ccp wt` made passes the same `CCP_WT_*` fields to every stage command; outside such a worktree nothing is added; §14 says so in one sentence.
- **Out:** new fields beyond those the hooks already get.

## dod_checks

- id: `check-01`
  story: As a product, a stage sees its worktree's fields.
  setup: a scratch product with a two-stage gate whose second stage prints `$CCP_WT_NAME`, run in a `ccp wt create` worktree.
  steps:
    1. Run the gate there.
  expect: the stage prints the worktree's name.
  dry run: on the merge base it prints nothing.
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
