---
task_id: 0118-leftovers-and-pr-body-guard
title: SPEC and test leftovers from R6 are closed, and a PR whose body names another task is caught before review
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S13", "S14"]
review_point: R7
paths: ["ccp/prompt.py", "ccp/wt.py", "ccp/suite.py", "plugin/agents/delivery-runner.md", "templates/prompts/_common.md", "docs/spec/02-delivery.md", "docs/design/toolkit.md", "tests/test_prompt*.py", "tests/test_suite_affected.py", "tests/test_merge_base.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0118-leftovers-and-pr-body-guard
## Intent

The small leftovers R6's reviews recorded are closed, and a pull request whose body was overwritten
with another task's is caught before a reviewer reads it.

## Context (not checked)

- From an accepted plane proposal listing R6 leftovers.
- During a parallel run a PR's body was once overwritten with another task's PR body; the cause is unknown. Two guards close it: workers always pass the PR number to `gh pr edit`, and the review prompt refuses a PR whose body does not name its task.
- All describe the accepted follow-ups (§31.1); no rule changes.

## Scope

- **In:**
  - §13.2 and `docs/design/toolkit.md`: the parenthesis on prompt rendering lists only examples, and says so; the three SPEC passages task 0101 re-wrapped badly are re-wrapped (text unchanged).
  - `ccp/wt.py`: the SIGTERM hold across `git worktree add` is bounded (30 s), after which the signal is acted on and the partial worktree removed.
  - `ccp suite affected --since`: a range (`A..B`) is accepted and means the files changed in it; §14.7 says so. A test pins the §14.7 dotfile rule.
  - `templates/prompts/_common.md`: `gh pr edit` and `gh pr view` always take the PR number.
  - `ccp prompt review` (`ccp/prompt.py`): refuses (exit 2) when the PR's body does not contain the task id, naming both; the runner brief says to repair the body before review.
- **Out:**
  - Finding the cause of the overwrite.

## dod_checks

- id: `cmd-01`
  story: As a runner, a PR body naming another task is caught.
  setup: a scratch task T whose PR body (stubbed `gh`) names task U only; then one naming T.
  steps:
    1. Run `ccp prompt review T` in each case.
  expect: (1) exit 2 naming T and the PR. (2) renders the prompt.
  dry run: n/a.
- id: `cmd-02`
  story: As a worker, `--since` takes a range.
  setup: a scratch repository with commits A, B, C, where B..C changes one module.
  steps:
    1. Run `ccp suite affected --since B..C`.
  expect: lists the tests for that module only; exit 0.
  dry run: n/a.
- id: `code-01`
  story: As a runner, a hung worktree add cannot hold a signal forever.
  setup: a test whose `git worktree add` is stubbed to hang, with a SIGTERM sent during it.
  steps:
    1. Run the test through `ccp suite run`.
  expect: the process exits 143 within 40 s and no worktree is left registered.
  dry run: n/a.
- id: `check-01`
  story: As a reader, the leftovers are fixed without new rules.
  setup: the PR diff.
  steps:
    1. Read every changed SPEC line.
  expect: each one describes behaviour this task builds or re-wraps text unchanged; the verdict's `spec_beyond_intent` is empty.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
