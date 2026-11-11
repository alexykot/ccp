---
task_id: 0065-latest-verdict-test-deterministic
title: The review prompt picks the latest implementer verdict deterministically
status: pending
kind: bug
depends_on: []
spec_refs: ["S13"]
review_point: R4
paths: ["ccp/report.py", "ccp/prompt.py", "tests/test_report_fields.py"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0065-latest-verdict-test-deterministic

## Intent

When two implementer reports carry the same timestamp, the review prompt shows the verdict of the later one by a total order (the run number), so the latest-verdict test cannot fail intermittently.

## Context (not checked)

- `tests.test_report_fields.Declared.test_the_review_prompt_shows_the_latest_implementer_verdict` failed once in a full run and passed on rerun; the likely cause is two reports written in the same second, so "latest" by timestamp is a tie.

## Scope

- **In:** the prompt picks the latest report by run number (or another total order the code already has), never by timestamp alone; a test writes two reports with equal timestamps.
- **Out:** the report format.

## dod_checks

- id: `check-01`
  story: As a reviewer, I see the latest verdict even when two reports share a second.
  setup: two implementer reports for one task with the same timestamp and different verdicts, the higher run number second.
  steps:
    1. Render the review prompt.
  expect: it shows the higher run's verdict, every time.
  dry run: on the merge base the choice depends on file order, so the result can flip.
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
