---
task_id: 0096-bundle-follow-ups-by-area
title: Follow-ups, leftovers and findings are bundled by area into fewer, larger tasks
status: pending
kind: chore
depends_on: []
spec_refs: ["S5", "S19"]
review_point: R5
paths: ["plugin/skills/writing-tasks/", "plugin/skills/review-triage/", "ccp/health.py", "tests/test_health*.py", "tests/test_plugin.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0096-bundle-follow-ups-by-area

## Intent

The task-log owner turns follow-ups, review leftovers and architect findings into one task per area,
up to a size target, so each task's fixed cost (claim, worker start-up, review, verify, merge,
reconcile) is paid once per area rather than once per finding (§5, §19.8).

## Context (not checked)

- Accepted plane proposal. A managed product's delivery data showed small tasks costing many times
  more wall time per changed line than tasks of a few hundred lines, and a large share of tasks were
  small follow-ups. The writing-tasks skill tells writers to give a follow-up its own small task.
- §31.1: this changes skill guidance and adds a health figure describing its own feature; no § rule
  changes, so no merge gate.

## Scope

- **In:**
  - The writing-tasks and review-triage skills tell the task-log owner to bundle follow-ups,
    leftovers and findings (code, tests and docs alike) by area into one task per area, aiming at a
    few hundred changed lines, with the union of the paths declared and one dod_check per finding;
    every finding is still fixed.
  - `ccp health` reports the share of tasks merged in its window whose diff is under a small-task
    line (`health.small_task_lines`, default 100).
- **Out:** splitting large tasks.

## dod_checks

- id: `check-01`
  story: As a task-log owner, the skills tell me to bundle.
  setup: a checkout of the PR head.
  steps:
    1. Read the writing-tasks and review-triage skills' follow-up guidance.
  expect: both say to bundle by area up to a size target with a dod_check per finding; neither says a
    follow-up gets a small task of its own.
  dry run: on the merge base the writing-tasks skill says a follow-up gets its own small task.
- id: `check-02`
  story: As a lead, I see small-task drift.
  setup: a scratch product with three merged tasks of 20, 50 and 400 changed lines.
  steps:
    1. Run `ccp health --json`.
  expect: it reports two of three tasks under the small-task line.
  dry run: n/a — the figure does not exist yet.
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
