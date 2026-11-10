---
task_id: 0022-drift-on-active-time
title: Architect drift measured on active time
status: pending
kind: feature
depends_on: []
spec_refs: ["S19", "S27"]
adr_refs: ["0035 D3"]
review_point: R2
paths: ["ccp/health.py", "ccp/architect.py", "docs/spec/03-quality.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0022-drift-on-active-time

## Intent

The architect's drift trigger compares active time (wall time minus time waiting on the operator, the lead or an exclusive lane), so waits do not read as slower work.

## Context (not checked)

- Wall time includes sign-off holds and lane waits, which inflated the drift ratio.
- Ruling (2026-11-10, on the implementer's open question): "The broader reading is right. Drift
  subtracts every `waiting_on` interval, whatever its reason (operator, lead, quota, reauth, runner),
  plus exclusive-lane waits. Active time is time not spent waiting, and a quota or reauth wait is no
  more the task's work than an operator wait. State it by reference to section 23.3's wait
  definition rather than as a second list of reasons (one home per fact), naming exclusive-lane
  waits as the one addition. Record this in task 0022's Context. The task's Intent listed examples,
  not an exhaustive set. Section 31: this is the task's own feature (ADR-0035 D3, which the operator
  accepted), so the 2026-11-10 ruling covers any SPEC wording. No merge gate."

## Scope

- **In:** the active-time measure, the drift trigger, SPEC §19.6 wording, tests.
- **Out:** the trigger's thresholds.

## dod_checks

- id: `drift-01`
  story: As the architect, a task that waited long on a sign-off does not trip drift.
  setup: a temporary queue with tasks whose wall time is mostly a recorded wait.
  steps:
    1. Run the drift computation.
  expect: the ratio uses active time and does not trip.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): `ccp health` rows gain `waits_s` and `active_s` (wall time less waits), and
  `health.trend` (the drift `ccp architect due` reads) now runs on `active_s`; it also reports
  `median_active_s` beside `median_wall_s`. Waits are the task's `waiting_on` set → clear intervals
  (reusing the board drill's `_waits`, so one rule says what a wait is; an open wait runs to the merge)
  plus its suite runs' exclusive-lane waits from `runs/_suites.jsonl` (`started.wait_s`,
  `busy.waited_s`), unioned and clipped to the task's wall time. Every `waiting_on` reason counts,
  as in §23.3's `wait_hours` and ADR-0035 D3's "waits"; the intent's list (operator, lead, lane) is
  read as examples. SPEC §19.6 item 4 reworded from ADR-0035 D3 (the task gave no CURRENT → PROPOSED
  text). `docs/design/board.md`'s "wall-time drift" became "active-time drift" so the doc stays true
  (outside the declared paths). Thresholds unchanged.
- 2026-11-10 (implementer, round 2): per the ruling in Context, SPEC §19.6 item 4 now defines active
  time by reference to §23.3's `wait_hours` (every `waiting_on` interval, whatever it waited on),
  naming exclusive-lane waits as the one addition, instead of listing reasons. The `health.py`
  module docstring dropped its "operator, the lead or a lane" list the same way. No code change: the
  wait rule (`drill._waits`, read by `health.waits_s`) already took every `waiting_on` event with no
  list of reasons of its own, and the tests already cover a `quota` wait.

## Verification notes

*Append-only.*
