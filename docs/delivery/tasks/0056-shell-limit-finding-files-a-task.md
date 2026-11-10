---
task_id: 0056-shell-limit-finding-files-a-task
title: A gate over the shell-limit line gets its refactor task
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S20"]
review_point: R4
paths: ["ccp/health.py", "ccp/suite.py", "docs/spec/02-delivery.md", "tests/test_gate_time.py", "tests/test_health_suite.py"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0056-shell-limit-finding-files-a-task

## Intent

When `ccp health` finds the gate's latest cold run over `gate.cut_line_seconds`, a refactor task is filed the way §20 files refactors (or §14.6 says plainly that the finding is advisory and the task-log owner files it), and a run the harness kills at the limit leaves a finding too (§14.6).

## Context (not checked)

- §14.6 says the gate 'gets a refactor task', but nothing files one: the finding only shows in the health and architect summaries.
- A run killed by the harness at the limit records nothing, so the worst case is the one never reported.
- §31: this task changes § text, so its merge waits on the operator's approval of the PROPOSED text.

## Scope

- **In:** choose one and state it: (a) health files the refactor through the §20 mechanism, once per crossing; or (b) §14.6 PROPOSED: 'Over the line, `ccp health` reports the run as an advisory finding; the task-log owner decides whether to file a refactor task.' Either way, a run with no `ended` row older than the shell limit is reported as killed at the limit.
- **Out:** changing the limit or the line.

## dod_checks

- id: `check-01`
  story: As a lead, a killed gate run is reported.
  setup: a scratch queue with a gate run started more than `gate.shell_limit_seconds` ago and no `ended` row.
  steps:
    1. Run `ccp health`.
  expect: it reports the run as killed at the shell limit.
  dry run: on the merge base it reports nothing.
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
