---
task_id: 0011-retire-stale-seat-and-verify-stale
title: Retire the seat stale rule, stale_seat and verify_stale
status: pending
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S18", "S23"]
adr_refs: ["0034 D6"]
review_point: R1
paths: ["scripts/observability/lib.py", "scripts/observability/heartbeat.sh", "scripts/observability/README.md", "contracts/observability_now.schema.json", "contracts/project.schema.json", "ccp/config.py", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0011-retire-stale-seat-and-verify-stale

## Intent

The snapshot raises no `stale_seat` and no `verify_stale` blocker, and the binding has no `cadence.verify_stale_minutes`; heartbeats are still written. Older snapshots and bindings carrying them are still read without error.

## Context (not checked)

- §18.3 states the target rule; ADR-0034 D6 records the ruling.
- `ccp tasks claim` and `close` write heartbeats; keep them.
- A binding that still sets `cadence.verify_stale_minutes` is accepted and ignored.
- Ruling (lead, 2026-11-09, question sm-20261109T214211Z-429f): this task also edits SPEC. §18.3's
  last sentence ("The snapshot code and the binding's `cadence.verify_stale_minutes` still carry both
  until task 0011 removes them; old snapshots holding them stay readable.") becomes "Old snapshots
  that hold `stale_seat` or `verify_stale` stay readable."; §8.3's "(§18.3; code: task 0011)"
  becomes "(§18.3)". §31 approval: the operator's rulings in `docs/spec/RULINGS.md` (rows §20.1.4,
  §12.1, §20.1.8 and §20.6/§25.8, operator, 2026-11-06).

## Scope

- **In:** the blocker kinds, their timers and thresholds, the knob, their renderings, schema entries (kept read-only for old data), tests.
- **Out:** heartbeats; other blockers.

## dod_checks

- id: `code-01`
  story: As a plane developer, no stale-seat or verify-stale logic remains.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -E 'stale_seat|verify_stale' -- ccp scripts contracts`.
  expect: no match apart from readers of old data, each with a comment saying so.
  dry run (`216cda1`): 16 matching lines in scripts/observability/lib.py alone.
- id: `compat-01`
  story: As an operator with an older queue, the snapshot and board rebuild.
  setup: a temporary `QUEUE_ROOT` with an old snapshot carrying both blockers and a binding with `cadence.verify_stale_minutes`.
  steps:
    1. Run `ccp board build` against it.
  expect: it succeeds and shows neither blocker.
  dry run: n/a — the test this task adds builds the queue.

## Implementation notes

*Append-only, newest last.*

- 2026-11-09 (implementer): The snapshot (`scripts/observability/lib.py`) no longer computes either
  blocker. Gone: the seat stale floor and multiplier, `stale_after_seconds`, `cron_interval_seconds`,
  the seat rows' `stale` and `stale_after_seconds` fields, the `stale_seat` loop and its mid-flight
  target list (with `future_resume`, which only it used), `VERIFY_STALE_MINUTES_DEFAULT`,
  `verify_stale_minutes` (the `VERIFY_STALE_MINUTES` env and `cadence.verify_stale_minutes`
  reader), `VERIFY_PHASES`, the task state's `verify_since` / `verifier_last_at` tracking,
  `task_file_updated_at` and `verdict_written_since`. STATUS.md and the status digest drop the
  seat stale column; `status.sh` exits 1 only on a blocker, ignoring an older snapshot's seat
  `stale` flag (`has_blockers`). Heartbeats are untouched and still read.
- Old data stays readable: `BLOCKER_KINDS` keeps both kinds under a read-only comment; the
  now-schema keeps them in the kind enum (described as deprecated, read only) and keeps the seat
  `stale` field as deprecated and no longer required; `contracts/project.schema.json` keeps
  `cadence.verify_stale_minutes` as deprecated and ignored, so an older binding validates.
  Help text (`heartbeat.sh`, `status.sh`), the observability README's seat-liveness section and
  `docs/design/observability.md` updated. ADR-0034 D6 recorded as built.
- New `tests/test_stale_blockers_retired.py`: a queue with a submitted task past the old threshold,
  a ten-hour-silent scheduled seat, a binding setting `verify_stale_minutes: 1` and an old
  `now.json` carrying both blockers and a seat `stale` flag; the rebuild and `ccp board build`
  succeed and show neither, and heartbeats are still written and read.
- Not done, pending a ruling: SPEC §18.3's last sentence ("The snapshot code and the binding's
  `cadence.verify_stale_minutes` still carry both until task 0011 removes them; old snapshots
  holding them stay readable.") and §8.3's "(code: task 0011)" now describe removed code. The task
  gives no SPEC edit, so both are left for the runner or the lead. `ccp/config.py` (in `paths`)
  needed no change: it reads `plane.json`, not the binding.
- 2026-11-09 (implementer, round 2): per the ruling recorded in Context, SPEC §18.3's last sentence
  and §8.3's "(code: task 0011)" are edited; the "Not done, pending a ruling" note above is resolved.
  No other SPEC passage describes the stale rule, `stale_seat` or `verify_stale` as present
  behaviour (the `docs/spec/map/` rows and `RULINGS.md` record old sections and rulings).

## Verification notes

*Append-only.*
