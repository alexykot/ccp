---
task_id: 0106-test-gaps-from-earlier-tasks
title: Behaviour earlier tasks shipped untested gets the tests that pin it
status: pending
kind: chore
depends_on: []
spec_refs: ["S12", "S13", "S14", "S15", "S19"]
review_point: R6
paths: ["tests/", "ccp/estimator.py", "ccp/cli.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0106-test-gaps-from-earlier-tasks

## Intent

Each behaviour below shipped in an earlier task with no test that fails when it breaks. This task adds
those tests. It changes code only where a new test finds a bug, and then only the smallest fix, named
in the Implementation notes.

## Context (not checked)

- Accepted plane proposals (operator, 2026-11-16: all approved), the follow-ups of earlier tasks. Each
  item names the gap a verifier or reviewer recorded.

## Scope

- **In**, one or more tests each:
  - `ccp tasks index` and `ccp tasks check` with `estimate.auto` off, at the command level. Dropping
    the `estimator.notice` call from either command fails a test.
  - The minor-only re-review skip: a ruling or merge round counting as the fix round, both skip knobs
    on, and an abandoned run ignored.
  - The `Small tasks` line reaches the architect prompt through `health.summary_text`
    (`ccp/architect.py`), not only the CLI text view.
  - The wording of close's dirty-caller refusal.
  - `ccp wt exec`: a SIGTERM during `merge_base` and during `create`, and the "name a worktree or a
    checkout" branch.
  - `drill._old_phases` with merge and ruling reports.
  - §12.1: gc and close leave the baseline worktree alone.
  - The signal test that leaves its `sleep 30` running cleans it up, even when it fails.
- **Out:**
  - Tests the earlier tasks 0099–0105 add for their own changes.
  - Refactoring the tested code.

## dod_checks

- id: `check-01`
  story: As a plane developer, each gap now has a test that fails without the behaviour.
  setup: a checkout of the PR head.
  steps:
    1. For each item in Scope, find the new test. Break the behaviour it pins with a one-line change
       (remove the call, flip the condition) and run that test.
  expect: each test fails on its break and passes on the head.
  dry run: n/a.
- id: `check-02`
  story: As a plane developer, a failing signal test leaves no process behind.
  setup: a checkout of the PR head, with the signal test made to fail by an injected assertion.
  steps:
    1. Run the test, then list processes running `sleep 30` that are children of the test run.
  expect: none.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty. Any non-test change is named in the Implementation
    notes with the test that found it.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 (implementer): tests only; no test found a bug, so no code outside `tests/` changed.
  - `ccp tasks index` and `ccp tasks check` at the command level (`tests/test_estimator.py`): index prints
    the estimator note with `estimate.auto` on and none with it off; with it off, neither command prints a
    note or starts a batch, though each still asks `estimator.notice`.
  - The minor-only skip (`tests/test_review_skip_clean.py`): a merge round and a ruling round each count as
    the fix round; an abandoned fix round opened since is ignored; with `verify.skip_review` and
    `verify.skip_review_after_clean` both on (real commits), the proof is tried first and wins when it
    proves the fix, and a fix it cannot judge, or one whose proof fails, still skips as minor-only.
  - `tests/test_architect.py`: the `Small tasks` line reaches the architect's headless prompt.
  - `tests/test_toolkit.py`: close's dirty-caller refusal names the checkout close runs from and says it
    must be clean (assertions added to the existing dirty-close test); close and then gc leave
    `ver-baseline` alone. `tests/test_wt.py`: gc and a task's worktree cleanup remove the task's
    worktrees and keep `ver-baseline`; `wt.own_ccp` with neither a name nor a checkout refuses (exit 2).
  - `tests/test_board_drill.py`: a pre-run-record task's merge and ruling reports start at their own prompt
    stamps, not at an earlier stamp of another kind or of no round kind.
  - `tests/test_review_skip_provers.py`: the signal test registers a cleanup that kills its `sleep 30`
    whichever check fails; a new test runs it with a sleeper outside the prover's process group and an
    early failure, and checks the sleeper is gone.
  - Not added: a SIGTERM during `merge_base` and during `create` of a base run. Task 0104 already added
    those tests (`tests/test_merge_base.py`), and Out excludes them.

## Verification notes
