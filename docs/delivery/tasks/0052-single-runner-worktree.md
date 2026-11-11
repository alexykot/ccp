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
- §31: this task's SPEC text describes its own feature. If the operator's standing ruling for such text (given for R3, 2026-11-10) is not extended to R4, the merge waits on their approval.

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

- 2026-11-11 (implementer): the creation moved into `ccp/wt.py` `runner_worktree(main, path, integ)`
  (made detached at `origin/<integ>` when missing, left alone when it is a working tree, a non-empty
  non-worktree directory refused with exit 2), with `main_of(checkout)` for a caller with no plane.json.
  `ccp/lifecycle.py` `runner_worktree` uses it for both cases: with `--runner <slot>` as before, and
  without it (now optional in `ccp/cli.py`) the binding's `runner.worktree` itself for one runner;
  without a slot beside recorded slots, or with no `runner.worktree` in the binding, it refuses (exit 2).
  `team.py` `single_runner_worktree` runs in the single-runner spawn after the scope checks and before
  any write: no `runner.worktree` or no `product_root` makes nothing; its output carries
  `runner_worktree: {path, made}`. A worktree it cannot make is a warning (`made: false` with `error`),
  not a refusal: `ccp init` writes `runner.worktree` into every binding, and a product with no `origin`
  yet must still spawn (`tests/test_init.py` `OneBinding` pins that); the runner's `ccp tasks worktree`
  makes it once the cause is fixed. A relative
  `runner.worktree` is the main checkout's. Slotted spawns are unchanged. SPEC §12.1 now says who makes
  it; `docs/cli/02-delivery.md` shows `--runner` as optional. Tests: `tests/test_wt.py`
  `SingleRunnerWorktree`. Paths beyond the declared ones: `ccp/lifecycle.py`, `ccp/cli.py`,
  `docs/cli/02-delivery.md`.

## Verification notes

*Append-only.*
