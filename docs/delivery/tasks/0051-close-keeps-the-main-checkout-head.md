---
task_id: 0051-close-keeps-the-main-checkout-head
title: ccp tasks close never moves the main checkout's HEAD
status: pending
kind: bug
depends_on: []
spec_refs: ["S10"]
review_point: R4
paths: ["ccp/lifecycle.py", "tests/test_tasks_close*.py", "docs/spec/02-delivery.md"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0051-close-keeps-the-main-checkout-head

## Intent

`ccp tasks close` reconciles in a worktree of its own, so running it from the product's main checkout (as an operator does when a harness denies the runner its close) leaves that checkout on its branch with its HEAD unmoved (§10).

## Context (not checked)

- An operator ran `ccp tasks close` from the main checkout: it checked out `origin/<integration>` detached there, committed the reconcile and pushed, leaving the checkout off its branch. Run from the runner's worktree, it did not.
- The reconcile commit itself is right; only where it is made is wrong.

## Scope

- **In:** close makes (or reuses) a merge worktree under the product's worktree dir for the reconcile commit and push, whatever the caller's cwd; the main checkout's HEAD, branch and index are untouched; a test runs close from the main checkout and checks its branch and HEAD before and after.
- **Out:** what the reconcile commits.

## dod_checks

- id: `check-01`
  story: As an operator, closing from the main checkout leaves it as it was.
  setup: a scratch product whose main checkout is on `main`, a merged task PR to reconcile.
  steps:
    1. Run `ccp tasks close <task> --pr <n>` from the main checkout.
  expect: the reconcile is pushed; the main checkout is still on `main` with the same HEAD as before.
  dry run: on the merge base the main checkout ends detached at the reconcile commit.
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
