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

## Verification notes

*Append-only.*
