---
task_id: 0055-merge-and-ruling-rounds
title: Merge-only and ruling rounds are rounds of their own
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S15"]
review_point: R4
paths: ["ccp/prompt.py", "ccp/runs.py", "templates/prompts/", "plugin/agents/delivery-runner.md", "docs/spec/02-delivery.md", "tests/test_prompt*.py", "tests/test_runs*.py"]
created: 2026-11-10
updated: 2026-11-11
---

# Task: 0055-merge-and-ruling-rounds

## Intent

The runner can launch a round that only merges the integration tip into a task branch, or only applies a lead's spec ruling, as a named round (`ccp prompt merge`, `ccp prompt ruling` or one `--kind`), so the run record and the prompt say what the round was instead of an `implement-N` run with a note file (§13, §15).

## Context (not checked)

- Today only `ccp prompt fix` counts as a fix round; tip merges and rulings ran as `implement-N` with `--note-file`, which mislabels the run and its prompt.
- §31: this task's SPEC text describes its own feature. If the operator's standing ruling for such text (given for R3, 2026-11-10) is not extended to R4, the merge waits on their approval.
- From later proposals: `ccp prompt fix` refuses when no review or verify report exists yet, so a lead ruling applied before review also runs as an implement round; and a pure merge-from-main catch-up still needs a review round before verify. Both belong to the round kinds this task adds.

## Scope

- **In:** the new round kind(s) with their own prompt template, run name and phase; the runner brief uses them; review and verify treat their heads like a fix round's; §13 lists them.
- **Out:** changing what a fix round is.

## dod_checks

- id: `check-01`
  story: As a runner, a tip merge is recorded as one.
  setup: a scratch product with a task in review.
  steps:
    1. Run the merge round prompt and record the run.
  expect: the run's kind is the merge round, not `implement`.
  dry run: on the merge base no such kind exists.
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
