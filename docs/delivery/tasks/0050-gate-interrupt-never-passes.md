---
task_id: 0050-gate-interrupt-never-passes
title: A gate interrupted between stages never exits 0
status: pending
kind: bug
depends_on: []
spec_refs: ["S14"]
review_point: R4
paths: ["ccp/suite.py", "tests/test_suite_stages.py", "docs/spec/02-delivery.md"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0050-gate-interrupt-never-passes

## Intent

A gate run that a signal stops between two stages exits non-zero (128 + the signal) and records the stage it stopped before, so an interrupted gate can never read as passed with later stages unrun (§14).

## Context (not checked)

- Found in the review of the gate-stages task: a SIGTERM or SIGINT between stages can leave the run exiting 0; the row records `interrupted` but `failed_stage` is null.
- §14's text on interrupted runs already treats them as not passed; this makes the exit code agree. If the stage section of §14 needs a sentence, it states only this behaviour.
- §31: this task's SPEC text describes its own feature. If the operator's standing ruling for such text (given for R3, 2026-11-10) is not extended to R4, the merge waits on their approval.

## Scope

- **In:** when the stage loop stops on a signal, the run exits 128 + the signal number and records `failed_stage` (or a `stopped_before` field) naming the first unrun stage; a signal during a stage keeps today's handling; a test sends each signal between stages.
- **Out:** the stages themselves and their order.

## dod_checks

- id: `check-01`
  story: As a runner, an interrupted gate never passes.
  setup: a scratch product with two gate stages, the first sleeping briefly.
  steps:
    1. Run the gate with `ccp suite run`, send SIGTERM after the first stage ends and before the second starts.
  expect: the run exits 143 and its row names the second stage as not run.
  dry run: on the merge base the run exits 0 with `failed_stage` null.
- id: `check-02`
  story: As a runner, SIGINT behaves the same.
  setup: as check-01.
  steps:
    1. Send SIGINT between the stages.
  expect: the run exits 130 and names the unrun stage.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 (implementer): `ccp/suite.py` `run()`: when the stage loop finds a signal before a stage
  starts, it remembers that stage; after the loop the run exits 128 + the first signal's number and
  `failed_stage` names that stage (reused, no new field; `stages` still lists only the stages that
  ran). A signal that ends a stage keeps today's handling (that stage's code and name). A signal a
  stage survives (it exits 0) stops the loop the same way, so it too exits 128 + N naming the next
  stage. A signal after the last stage, with every stage run, is unchanged (recorded `interrupted`,
  exit code the last stage's). SPEC §14.2 gets one sentence and §14.3's `failed_stage` parenthesis
  names the new case; `contracts/suite_result.schema.json`'s `failed_stage` description matches it
  (outside the task's paths, one string). Tests in `tests/test_suite_stages.py`: one runs the stage loop in
  process and sends SIGTERM and SIGINT to itself right after the first stage returns; one runs
  `ccp suite run` with a first stage that ignores the signal it sends to `ccp`.

## Verification notes

*Append-only.*
