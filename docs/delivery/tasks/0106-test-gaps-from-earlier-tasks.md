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

## Verification notes
