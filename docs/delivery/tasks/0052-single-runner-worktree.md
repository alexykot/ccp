---
task_id: 0052-single-runner-worktree
title: ccp creates a single runner's worktree
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S16"]
review_point: R4
paths: ["ccp/wt.py", "scripts/observability/team.py", "tests/test_wt.py", "tests/test_team*.py", "docs/spec/02-delivery.md"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0052-single-runner-worktree

## Intent

A product starting its first single runner gets the runner's worktree from the plane (`team.sh runner spawn`, or `ccp tasks worktree` without a slot), as slotted runners already do, so no runner makes it by hand with `git worktree add` (§12, §16).

## Context (not checked)

- The plane's own first single runner found `.plane-runtime/runner` missing and made it by hand; `ccp tasks worktree` only makes slotted worktrees.

## Scope

- **In:** the spawn (or the runner's first `ccp tasks worktree`) creates the binding's `runner.worktree` detached at the integration tip when it is missing and leaves an existing one alone; §12 or §16 says who creates it.
- **Out:** slotted runners' worktrees, which already work.

## dod_checks

- id: `check-01`
  story: As a lead starting a first runner, its worktree exists.
  setup: a scratch product with a binding naming `runner.worktree`, no such worktree.
  steps:
    1. Run `team.sh runner spawn --scope <task>`.
  expect: the worktree exists, detached at the integration tip.
  dry run: on the merge base it does not exist.
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
