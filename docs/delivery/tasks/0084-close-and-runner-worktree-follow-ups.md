---
task_id: 0084-close-and-runner-worktree-follow-ups
title: Close and runner worktrees leave no stale messages, leftovers or wrong paths
status: pending
kind: bug
depends_on: []
spec_refs: ["S10", "S12", "S16"]
review_point: R5
paths: ["ccp/lifecycle.py", "ccp/wt.py", "ccp/board.py", "contracts/project.schema.json", "plugin/agents/delivery-runner.md", "scripts/observability/team.py", "tests/test_tasks_close*.py", "tests/test_wt.py", "tests/test_team*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0084-close-and-runner-worktree-follow-ups

## Intent

Closing a task and making a runner's worktree leave nothing stale behind: refusal messages give the real reason, a failed close's merge worktree is found and removed, the board sees merges without a pull, and a single runner is told how to make its worktree (§10.5, §12.1, §16).

## Context (not checked)

- Accepted plane proposals from the reviews of the close-in-its-own-worktree and single-runner-worktree tasks.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** the dirty-caller refusal says the checkout close runs from must be clean (no longer "a clean runner worktree"); `contracts/project.schema.json`'s `runner.worktree` description drops "reconciles"; `ccp wt list` and `gc` show and remove leftover `merge-<nnnn>` worktrees, and removing a task's worktrees removes its merge worktree; the board reads merges from the remote integration branch; the runner brief's single-runner part says to run `ccp tasks worktree` when the spawn could not make the worktree; `team.py`'s "before any write" wording is made exact; the main checkout is found with `git rev-parse --git-common-dir` (works with a separate git dir).
- **Out:** the reconcile itself.

## dod_checks

- id: `check-01`
  story: As a lead, a failed close leaves no hidden worktree.
  setup: a scratch product with a leftover `merge-0001` worktree from a close that failed.
  steps:
    1. Run `ccp wt list`, then `ccp wt gc`.
  expect: the list shows it; gc removes it.
  dry run: on the merge base it is not listed.
- id: `check-02`
  story: As a runner, the brief tells me how to make my worktree.
  setup: a checkout of the PR head.
  steps:
    1. Read the runner brief's single-runner part.
  expect: it names `ccp tasks worktree` for when the spawn could not make the worktree.
  dry run: on the merge base only the several-runners part names it.
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
