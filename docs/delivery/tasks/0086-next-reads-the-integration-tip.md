---
task_id: 0086-next-reads-the-integration-tip
title: ccp tasks next never offers a task already done on the integration branch
status: done
kind: bug
depends_on: []
spec_refs: ["S10"]
review_point: R5
paths: ["ccp/selection.py", "ccp/tasklog.py", "tests/test_selection*.py", "tests/test_tasks_next*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0086-next-reads-the-integration-tip

## Intent

A runner whose worktree is behind the integration tip is never offered a task already done there (§10.3).

## Context (not checked)

- Accepted plane proposal: `ccp tasks next` read the task files of the checkout it ran in, so a lagging runner worktree offered a done task (the claim then refused it correctly).

## Scope

- **In:** `ccp tasks next` skips a task whose queue status is `done` or `dropped` whatever the checkout's task file says, and reads statuses from the remote integration branch when the checkout lags it.
- **Out:** changing the ranking.

## dod_checks

- id: `check-01`
  story: As a runner on a lagging worktree, I am not offered a done task.
  setup: a scratch product whose task 0001 is done on the integration branch and in the queue, with a worktree at an older commit where 0001 is pending.
  steps:
    1. Run `ccp tasks next` from that worktree.
  expect: it does not offer 0001.
  dry run: on the merge base it offers 0001.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12 (implementer): `selection.current` is the task log `ccp tasks next` reads (`pick` uses it
  when no task list is passed; the board and the forecast pass their own and are unchanged). When the
  checkout's HEAD lacks a commit of `origin/<integration branch>` (the binding's, else `main`; nothing
  is fetched; `tasklog.lags`), each task the checkout knows takes the status its file has on that tip
  (`tasklog.statuses_at`, one `git cat-file --batch`, legacy statuses read canonically); a task the tip
  lacks keeps its own. Then a task still pending whose queue state (`tasks/<id>.json`) is `done` or
  `dropped` is passed over: its status reads "<status> in the queue", so it is neither offered nor
  counted done for its dependants (they wait for the task log). A lead preference for such a task is
  ignored with the usual stderr note. No ranking change. Tests: `tests/test_tasks_next_tip.py`.

## Verification notes

- 2026-11-12 — verifier, PR #74 head `b9bef72` (squash `21fa219`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0086-next-reads-the-integration-tip.json.
