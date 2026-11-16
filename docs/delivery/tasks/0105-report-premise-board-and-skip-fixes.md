---
task_id: 0105-report-premise-board-and-skip-fixes
title: Report fields, the premise check, the board and the minor-only skip handle their edge cases
status: pending
kind: fix
depends_on: []
spec_refs: ["S5", "S13", "S15", "S28"]
review_point: R6
paths: ["ccp/report.py", "ccp/tasklog.py", "ccp/board.py", "ccp/estimate.py", "ccp/prompt.py", "ccp/lifecycle.py", "docs/spec/02-delivery.md", "tests/test_report_fields.py", "tests/test_board*.py", "tests/test_estimate.py", "tests/test_prompt_rounds.py", "tests/test_tasklog*.py", "tests/test_minor*.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0105-report-premise-board-and-skip-fixes

## Intent

A report-field reason is not read as the template, the premise check catches a joined unit, the
board's views agree on rounds, and a failed fix round never skips the re-review. Each fix has a test
that fails without it.

## Context (not checked)

- Accepted plane proposals (operator, 2026-11-16: all approved), the follow-ups of earlier tasks.
- A report-field reason that starts with another declared value (`yes, no downtime needed` on a yes/no
  field) is refused as the template. It fails closed, but the refusal is wrong.
- The unmeasured-premise warning misses sizes and ranges written without a space (`40MB`, `5-10
  sites`, `300ms`).
- `ccp/board.py`'s key whitelist omits `merge_rounds` and `ruling_rounds`. The drill view then falls
  back to run-record counts, while `ccp board task` uses health's count. The estimate bands still
  have four phases.
- The minor-only re-review skip does not check the fix round's own outcome before skipping.

## Scope

- **In:**
  - Report fields: a value is read as the template only when it is exactly the template, or is two
    declared values joined by `|`. A reason after a single declared value is accepted.
  - The premise warning catches a number joined to its unit or a dash range (`40MB`, `300ms`,
    `5-10`).
  - The board whitelist carries `merge_rounds` and `ruling_rounds`, so the drill view and `ccp board
    task` agree. The estimate bands count merge and ruling rounds as the implementer documents
    (inside the fix band, or as their own).
  - The minor-only skip applies only when the fix round's own outcome is `done`. The SPEC's text on
    the skip says whether a second fix round may skip as well, describing the behaviour as built.
- **Out:**
  - New flags, or any rule beyond what Scope names.

## dod_checks

- id: `check-01`
  story: As a worker, a report-field reason is not read as the template.
  setup: a product declaring a field with values `yes|no`.
  steps:
    1. Submit `<field>: yes, no downtime needed`, then `<field>: yes|no`.
  expect: the first is accepted, and the second is refused as the template.
  dry run: n/a.
- id: `check-02`
  story: As a lead, the premise check catches a joined unit.
  setup: a task whose Context states `40MB`, `300ms` and `5-10 sites` with no command.
  steps:
    1. Run `ccp tasks check`.
  expect: it warns about each one.
  dry run: n/a.
- id: `check-03`
  story: As a lead, the board's views agree on rounds.
  setup: a task with a merge round and a ruling round in its health record.
  steps:
    1. Read the board's drill view of the task and `ccp board task`.
  expect: both show the same merge and ruling round counts.
  dry run: n/a.
- id: `check-04`
  story: As a runner, a failed fix round does not skip the re-review.
  setup: a review with only MINOR findings, and a fix round whose outcome is `failed`.
  steps:
    1. Run `ccp prompt verify` without a re-review.
  expect: refused, as for an unreviewed fix. With the fix round `done`, it proceeds as today.
  dry run: n/a.
- id: `check-05`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
