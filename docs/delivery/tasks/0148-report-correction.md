---
task_id: 0148-report-correction
title: A worker corrects a recorded report before the task's next run opens, the earlier one kept as superseded
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S11"]
review_point: R9
paths: ["ccp/report.py", "ccp/runs.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "templates/prompts/_common.md", "tests/test_report_correction.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0148-report-correction
## Intent

A worker that finds a mistake in the report it already recorded can record the corrected one, so the
run's figures (outcome, verdict, severity, passages beyond intent, suite numbers, declared fields) are the
corrected ones, as long as nothing has acted on the report yet; the earlier report is kept, marked
superseded.

## Context (not checked)

- `submit` in `ccp/report.py` refuses a run already reported (`"is already {state}: a new launch needs a
  new run"`). Seen on task 0119: a review recorded one spec-beyond-intent passage, the worker corrected it
  to none in its file, and the resubmission was refused, so the run kept the stale count.
- The SPEC states no rule against a second submission: `git grep -n -i 'already reported\|second report' -- docs/spec` at `921507e` finds nothing. §11.1 refuses a report from an abandoned run, which stays.
- "Before anything acts on it": the runner reads a report and then opens the task's next run (the next
  phase, or the next round). So a correction is allowed while no run of the same task was opened after
  the reported one.
- §31.1: the §13.4 sentence below describes this task's own feature.

## Scope

- **In:**
  - `ccp/report.py` `submit`: a run in state `reported` takes a new report when no run of the same task
    was opened after it (`ccp/runs.py` gives the test). The new report goes through every check a first
    one does. The earlier stored report is kept beside it as `<report stem>.superseded-<k>.md` (`k` from 1),
    the run record gets `corrections`, a list of `{at, superseded}`, and its parsed fields are replaced by
    the new report's. A `run` `reported` event is written again with `corrected: true`; a review's
    `review` `recorded` event is written again with the new severity.
  - Friction lines and the suite filing (§27.2) are recorded from the first submission only; a correction
    does not add them again.
  - A run reported after which a later run of the task opened is still refused, the message saying a
    later run exists; an abandoned run is refused as before.
  - §31.1: `docs/spec/02-delivery.md` §13.4, after its first paragraph, one sentence describing the
    correction and its limit; `docs/cli/02-delivery.md`'s `ccp report` row says the same in one clause.
  - `templates/prompts/_common.md`: one sentence: to correct a report already recorded, run `ccp report`
    again with the corrected file, before telling the runner.
  - `tests/test_report_correction.py` (new).
- **Out:**
  - Correcting a verify report's verdict (it must still match `ccp verify record`'s, as today).
  - Editing a report after the task's next run opened.

## dod_checks

- id: `rep-01`
  story: As a reviewer, my corrected report replaces the stale count.
  setup: a scratch queue with a review run reported with one `## Spec beyond intent` passage, and no later run of the task.
  steps:
    1. Run `ccp report <run_id> <file>` with the same report corrected to `none`.
  expect: exit 0; the run record's `spec_beyond_intent` is 0 and `corrections` has one entry; the first report exists as `<stem>.superseded-1.md`; the ledger has a second `run` `reported` event with `corrected: true`.
  dry run: n/a.
- id: `rep-02`
  story: As a runner, a report I have acted on is not changed under me.
  setup: the queue of rep-01 before the correction, then a fix run of the same task opened with `ccp prompt fix`.
  steps:
    1. Run `ccp report <review run_id> <file>` with a corrected report.
  expect: exit 1; the message names the later run; the stored report and the run record are unchanged.
  dry run: n/a.
- id: `rep-03`
  story: As the health record, a correction does not count friction twice.
  setup: a reported implement run whose report has two `## Friction` lines, no later run.
  steps:
    1. Run `ccp report <run_id> <file>` again with the same friction and a corrected `Outcome:` line.
  expect: the friction notes for that run still number two; the run's `outcome` is the corrected one.
  dry run: n/a.
- id: `rep-04`
  story: As a worker, a correction is checked like a first report.
  setup: a reported implement run, no later run.
  steps:
    1. Run `ccp report <run_id> <file>` with a report missing its `Prompt:` token.
  expect: exit 2; nothing written; the run record and the stored report are unchanged.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 (implementer): `runs.opened_after` gives the test: a run of the same task, any phase or
  state, opened after the reported one. Record times are to the second, so a run opened in the same
  second counts as after it (the conservative side: never correct under a runner that may have acted).
- The earlier report is kept by copying the stored one to `<stem>.superseded-<k>.md`, `k` the first free
  from 1. A worker that edits the stored file in place and submits it again has already overwritten the
  earlier text: the correction still goes through, the `corrections` entry has `superseded: null` and
  a warning says so. The `_common.md` sentence therefore tells the worker to write the corrected report
  to a new file, not over the recorded one.
- A correction keeps the run's `reported_at` (the time it closed); its fields from the report (`PR`,
  `Head`, verdict, severity, spec_beyond_intent, suite numbers, declared fields) are removed and set from
  the corrected report, so none stays from the earlier one, except a verify run's `verdict` and `head`,
  which are `ccp verify record`'s. `friction_count` is the corrected report's; the health notes and the
  suite filing are the first submission's.
- `tests/test_toolkit.py`'s double-report check now opens a later run first: a second report on a run with
  no later run is a correction now.

## Verification notes
