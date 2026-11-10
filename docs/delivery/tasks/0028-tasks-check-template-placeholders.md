---
task_id: 0028-tasks-check-template-placeholders
title: ccp tasks check refuses untouched template placeholders
status: pending
kind: feature
depends_on: []
spec_refs: ["S5"]
review_point: R1
paths: ["ccp/", "docs/spec/01-model.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0028-tasks-check-template-placeholders

## Intent

A task copied from the template and not filled in fails `ccp tasks check` with a message that names
each placeholder still there, so a new user or an agent fixes it before a runner claims it.

## Context (not checked)

- A newcomer following the README copied `TEMPLATE-task.md` and got a terse "cites none of
  spec_refs" error from empty `spec_refs`, while other placeholders passed silently.
- The same applies to `plane.json`: a gate lane left as `<your test command>` runs and fails late.

## Scope

- **In:** `ccp tasks check` refuses a task file holding `NNNN-kebab-slug`, `YYYY-MM-DD`,
  `As a <role>`, `<preconditions`, `<concrete, observable result>` or `One line, imperative`, naming
  the placeholder and the line; an empty `spec_refs` on a feature task gets a message saying to list
  the SPEC sections and cite them in the text; `plane.json` validation refuses a lane command holding
  `<your test command>`; §5 notes the rule.
- **Out:** judging the quality of filled-in text.

## dod_checks

- id: `check-01`
  story: As a new user, an unfilled copy of the template is refused clearly.
  setup: a scratch product with `TEMPLATE-task.md` copied to `tasks/0001-x.md` unchanged.
  steps:
    1. Run `ccp tasks check`.
  expect: it fails and names each placeholder found with its line number.
  dry run: n/a — the check does not exist yet.
- id: `check-02`
  story: As a new user, empty spec_refs tells me what to do.
  setup: a filled task with `spec_refs: []` and `kind: feature`.
  steps:
    1. Run `ccp tasks check`.
  expect: the message says to list the SPEC sections in `spec_refs` and cite them in the text.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, the plane's own task log and examples still pass.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp tasks check` and the full suite.
  expect: both pass; the template itself is exempt (it is not under `tasks/`).
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 — `ccp tasks check` reads each task not yet `done` or `dropped` for the template's
  placeholders (`tasklog.PLACEHOLDERS`) and refuses each one with its file and line. Text inside a
  code span or a fenced block is skipped as quoted, so this task's own Scope passes. A code span
  never runs past a blank line, and an unclosed fence hides nothing. Done and dropped tasks are
  history and are not read, as with the dry-run check.
- A refusal for missing refs, where `spec_refs` is one of the lists the task may cite, now says to
  list the SPEC sections in `spec_refs` and cite them in the text. That covers both the task log's
  `refs_any` and a kind's own `refs_any`.
- `plane.json` validation refuses a `suite.lanes` argv with an item that contains
  `<your test command>`, naming the lane (`config.LANE_PLACEHOLDER`).
- SPEC §5 gets a note on the three refusals. Tests: `tests/test_task_placeholders.py`.

## Verification notes

*Append-only.*
