---
task_id: 0056-shell-limit-finding-files-a-task
title: A gate over the shell-limit line gets its refactor task
status: done
kind: feature
depends_on: []
spec_refs: ["S14", "S20"]
review_point: R4
paths: ["ccp/health.py", "ccp/suite.py", "docs/spec/02-delivery.md", "tests/test_gate_time.py", "tests/test_health_suite.py"]
created: 2026-11-10
updated: 2026-11-11
---

# Task: 0056-shell-limit-finding-files-a-task

## Intent

When `ccp health` finds the gate's latest cold run over `gate.cut_line_seconds`, a refactor task is filed the way §20 files refactors (or §14.6 says plainly that the finding is advisory and the task-log owner files it), and a run the harness kills at the limit leaves a finding too (§14.6).

## Context (not checked)

- §14.6 says the gate 'gets a refactor task', but nothing files one: the finding only shows in the health and architect summaries.
- A run killed by the harness at the limit records nothing, so the worst case is the one never reported.
- §31: this task changes § text, so its merge waits on the operator's approval of the PROPOSED text.
- Lead ruling, fix round 1 (2026-11-11): (1) a run is labelled "killed at the shell limit" only when
  its elapsed time reached the limit; one that stopped early for another reason is reported as
  stopped, or not at all; both cases are pinned by tests and stated in §14.6's Killed-at-the-limit
  bullet. (2) The killed list is not permanent: it shows only kills newer than the last completed
  gate run, or within the window the existing line already uses, and the bullet says which.
  (3) `gate_time` passes `now` through to `fold`.

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

- 2026-11-11 (implementer): took scope option (b). §14.6 now says the over-the-line finding is
  advisory and the task-log owner decides whether to file a refactor (the PROPOSED text, worked into
  the existing bullet). Option (a) would have had `ccp health`, a reader, write task files. The
  health and architect line now says so in place of "It calls for a refactor task".
- Killed at the limit: `gate_time(..., now=)` lists in `killed` (suite id, task, run, start, oldest
  first) every run of the gate role's lane with no `ended` row (fold state `open` or `killed`) that
  started more than `gate.shell_limit_seconds` before now. It is read literally, so a run whose
  worker run stopped earlier is listed too. `summary_text` adds one `Gate killed at the shell limit`
  line (count, latest). It is not a breach and not judged as a cold run.
- §14.6 gained a "Killed at the limit" bullet describing this (the task gave no PROPOSED text for it).
  §27.2's gate-time pointer and the `cut_line_seconds` schema description were brought in line. Both
  are outside the task's `paths`. `ccp/suite.py` and `tests/test_health_suite.py` needed no change.
- 2026-11-11 (fix round 1, lead ruling above): a no-end gate run is listed in `killed` only when its
  elapsed time reached the limit (`>=`): to its run's stop, report or abandonment when fold knows it
  (fold's estimated `seconds`), else to now. A run that stopped earlier is not listed (not reported
  as stopped). The list holds only runs started after the latest run of the gate lane that passed or
  failed; an interrupted run or another lane's run does not clear it. `gate_time` passes `now` to
  `fold` through `_folded`. The §14.6 bullet and the health text line say both.
- 2026-11-11 (fix round 2): §14.6 text only, no code change. The Killed-at-the-limit bullet now says
  exactly what each output holds: `gate_time.killed` carries each run's suite id, task, run and start;
  the health and architect summaries give one line with the count and the latest to start. The
  "Judged on cold runs only" bullet says killed runs are not judged against the line.

## Verification notes

- 2026-11-11 — verifier, PR #64 head `6852718` (squash `c1e40fd`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0056-shell-limit-finding-files-a-task.json.
