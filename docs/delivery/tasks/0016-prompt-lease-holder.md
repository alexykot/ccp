---
task_id: 0016-prompt-lease-holder
title: cpl prompt checks the lease holder and never abandons another slot's running run
status: done
kind: feature
depends_on: []
spec_refs: ["S10", "S16"]
adr_refs: []
review_point: R1
paths: ["cpl/prompt.py", "cpl/runs.py", "cpl/cli.py", "plugin/agents/delivery-runner.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0016-prompt-lease-holder

## Intent

With several runners, `cpl prompt <phase> <task>` refuses a runner slot that does not hold the task's lease, and opening a run never abandons a run that another slot started and that is still running.

## Context (not checked)

- A slot whose claim lost the race could still open a run for the task; opening it abandoned the winning slot's running worker.
- Urgent: this is a live bug in the released plane. Implemented in its own PR.

## Scope

- **In:** the holder check on `cpl prompt` (a `--holder` argument, defaulting to the caller's slot), the abandon rule in `runs.open_run`, the runner brief's prompt line, tests.
- **Out:** claim rules (already holder-aware).

## dod_checks

- id: `lease-01`
  story: As a runner slot that lost a claim, I cannot open a run for a task another slot holds.
  setup: a temporary queue where slot A holds a task's lease.
  steps:
    1. Run `cpl prompt implement <task> --holder B`.
  expect: exit non-zero naming the holder; no run opened, none abandoned.
  dry run: n/a — the temporary queue is built by the task's test.
- id: `lease-02`
  story: As the holder, a new round never abandons another slot's running run.
  setup: a temporary queue with a running run of the task opened by another slot.
  steps:
    1. Open a run of the same phase as the holder.
  expect: the other slot's running run stays open.
  dry run: n/a — the temporary queue is built by the task's test.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*

- 2026-11-06: delivered in PR #112 (holder check on `cpl prompt`, another slot's running round protected); independently reviewed, suite green.
