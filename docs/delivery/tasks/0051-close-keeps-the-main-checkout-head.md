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

- 2026-11-11 (implementer): `close` now commits and pushes the reconcile from the task's own merge
  worktree, `merge-<nnnn>` under `worktrees.dir` (`ccp/lifecycle.py` `_merge_checkout`), made detached at
  `origin/<integration>` after the merge, or reused with an earlier failed close's half-done reconcile
  discarded (rebase abort, hard reset, clean); it is removed once the reconcile lands. The checkout close
  runs from keeps its branch, HEAD and index; a detached checkout other than the main checkout (a runner
  worktree) is then moved to the reconcile commit, as when it made the reconcile itself, so the board built
  from it still shows the merge. The recovery message on a failed reconcile names the merge worktree and
  says the re-run discards it. Choices (the task leaves them open): the merge worktree is lifecycle's own,
  not a `ccp wt` kind (no record, no env.setup); a product with no `worktrees.dir` reconciles in the
  checkout close runs from, as before; the refusal of a dirty or mid-rebase caller checkout stays.
  Tests: `tests/test_tasks_close.py`; `tests/test_toolkit.py`'s failed-reconcile test now re-detaches the
  runner worktree at the fresh tip before committing its fix, since close no longer moves it on a failure.
- 2026-11-11 (implementer, fix round 1): the merge worktree now gets the `worktrees.links` paths linked
  in (`wt._link`, as `ccp wt create` does), so a reconcile hook that reads a linked path (a venv, an
  `.env`) works there as it did in the runner worktree; env.setup still does not run in it. The
  `review_point_done` notification now runs with the caller's checkout as its cwd (§3.6, "the checkout
  the call came from"), not the merge worktree close removes next; the task-log read that decides it
  stays on the reconciled tree. A failure before the merge worktree is ready (its path taken by a
  foreign directory, a failed `worktree add`) now gets its own recovery message, which says nothing of
  the reconcile was made and does not call that directory close's own. Tests:
  `tests/test_tasks_close.py` (a hook reads a linked path), `tests/test_notify.py` (the channel's cwd).
- 2026-11-11 (implementer, fix round 1, SPEC per the lead's §31.1 ruling): §10.5 step 1 refuses a
  dirty caller checkout, not "the runner worktree"; step 2 says the reconcile is made, hooked and pushed
  in the `merge-<nnnn>` worktree, which close removes, and that a product with no `worktrees.dir` still
  reconciles in the caller; §12.1 lists `merge-<nnnn>` and says close, run from any checkout, moves only
  a detached runner worktree (to the reconcile); 01-model's plane.json example says the hooks run in
  close's merge worktree.

## Verification notes

*Append-only.*
