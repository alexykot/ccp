---
task_id: 0085-release-a-claimed-task-with-no-open-run
title: The lead can release a claimed task with no open worker run, keeping its branch
status: pending
kind: feature
depends_on: []
spec_refs: ["S10"]
review_point: R5
paths: ["ccp/lifecycle.py", "ccp/cli.py", "docs/spec/02-delivery.md", "tests/test_tasks_release*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0085-release-a-claimed-task-with-no-open-run

## Intent

When a claimed task's checks or scope turn out wrong, the lead can release it while no worker run is open, keeping its branch and PR, amend it unleased and have it re-claimed under the same id (§10.5), instead of dropping it and superseding it with a new id.

## Context (not checked)

- Accepted plane proposal from a superseded task: §10.5 routes such a change through releasing or superseding, but `ccp tasks release` refuses any task with a run behind it, so the only route was a new task id and branch.
- §31: this task adds or changes a § rule beyond describing its own feature, so its merge waits on the operator's approval of the final text at its merge gate (§31.1).

## Scope

- **In:** `ccp tasks release <id> --keep-branch --reason R` releases a claimed task whose worker runs are all closed: the lease clears, the queue status returns to `pending`, the branch and PR stay, and a later claim resumes on them; a task with an open run is still refused; §10.5 states it (CURRENT: release undoes only a leased task with no run; PROPOSED: "or, with `--keep-branch`, a claimed task whose runs are all closed, keeping its branch and PR").
- **Out:** releasing a task with an open run.

## dod_checks

- id: `check-01`
  story: As a lead, I release an in-flight task with no open run.
  setup: a scratch product with a claimed task whose implement run is closed and a pushed branch.
  steps:
    1. Run `ccp tasks release <id> --keep-branch --reason fix-check`.
    2. Run `ccp tasks claim <id>`.
  expect: the release succeeds and the branch remains; the re-claim resumes on that branch.
  dry run: on the merge base the release is refused.
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
