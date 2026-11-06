---
task_id: 0001-retire-the-runaway-backstop
title: Retire the twelve-hour runaway backstop
status: done
kind: feature
depends_on: []
spec_refs: ["S18", "S3", "S23"]
adr_refs: ["0032 D2"]
review_point: R1
paths: ["scripts/observability/lib.py", "scripts/observability/README.md", "scripts/queue/README.md", "contracts/observability_now.schema.json", "plugin/agents/delivery-runner.md", "SPEC.md", "tests/"]
created: 2026-11-05
updated: 2026-11-05
---

# Task: 0001-retire-the-runaway-backstop

## Intent

Nothing in the plane stops or flags a task because twelve hours of wall time have passed since its
first launch. A stuck task is noticed through the team's idle and failure signals instead, as
ADR-0032 D2 decides. Queues whose snapshots were written before the change still rebuild without
errors.

## Context (not checked)

- The backstop dates from a time when the system could stall without anyone noticing; the agent
  team's idle hook and failure notices now cover that.
- The `backstop` blocker is derived in the snapshot (`scripts/observability/lib.py`), never written to
  the ledger. Old snapshots (`now.json`) may hold `backstop_hours` / `backstop_breached` fields and a
  `backstop` blocker; readers keep accepting them.
- The rule also appears without the word "backstop": "12h clock", "does not reset", the §14 gate list.
- After merge, record the decision as built: `cpl adr decide 32 D2 built`.

## Scope

- **In:** the snapshot's backstop fields, timer and `backstop` blocker kind and the status and board
  renderings of them (all in `scripts/observability/lib.py`), the now-schema, the runner brief
  (`plugin/agents/delivery-runner.md`: the stop condition and "the 12h clock does not reset"),
  SPEC §13, the §14 gate list, §25's stop condition and seat table, and every other SPEC or README
  reference to the twelve-hour rule; tests.
- **Out:** the wall, work and wait timers themselves (they stay as diagnostics); quota waits.

## dod_checks

- id: `code-01`
  story: As a plane developer, I find no twelve-hour rule left in the plane's code, contracts or briefs.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -i -E 'backstop|12 ?h|twelve-hour|≥ ?12' -- cpl scripts plugin contracts`.
  expect: no match, apart from a reader that accepts an old `backstop` blocker or field, each with a comment saying so.
  dry run (`8207a8b`): 23 matching lines today, all about the twelve-hour rule.
- id: `spec-01`
  story: As a reader of the SPEC, I find no twelve-hour rule.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n -i -E 'backstop|12 ?h|twelve-hour|≥ ?12' SPEC.md`.
  expect: no normative rule remains; at most one line noting the rule's retirement.
  dry run (`8207a8b`): 17 matching lines today, all about the twelve-hour rule.
- id: `compat-01`
  story: As an operator with an older queue, I rebuild the snapshot and the board from a queue whose last snapshot carries backstop data.
  setup: a temporary `QUEUE_ROOT` holding an old `observability/now.json` with `backstop_hours`, `backstop_breached: true` and a `backstop` blocker, and a task (its ledger events and queue state) whose `implementation_started_at` is more than twelve hours old.
  steps:
    1. Run `scripts/observability/rebuild-now.sh` with that `QUEUE_ROOT`.
    2. Run `cpl board build` against the same queue.
  expect: both succeed, and neither reports the task as blocked by a backstop.
  dry run: n/a — the temporary queue is built by the test this task adds.

## Implementation notes

*Append-only, newest last.*

- 2026-11-05 — The snapshot no longer computes a backstop: `BACKSTOP_HOURS`, the `backstop_breached` /
  `backstop_hours` row fields, the `backstop` blocker, the blocked count's backstop term and the STATUS
  and status-line columns are gone from `scripts/observability/lib.py`. `backstop` stays in
  `BLOCKER_KINDS` and the now-schema only as a read-only kind for older snapshots (commented); the two
  row fields stay in the schema as deprecated, not required. SPEC: §13 is now "Quota" with a one-line
  retirement note; the §2 table row, §8's reject/failed notes, the §14 gate, the §16 phase line, §20's
  example, formula and knob, §23's "12h clock", §25.3's stop condition and §25.6's table row are
  removed or reworded. Runner brief: the stop condition and "the 12h clock does not reset" are gone.
  READMEs reworded. ADR-0032 D2 recorded as built. New test `tests/test_backstop_retired.py`.

## Verification notes

*Append-only.*

- 2026-11-05 — `code-01` pass — `git grep -n -i -E 'backstop|12 ?h|twelve-hour|≥ ?12' -- cpl scripts plugin contracts`
  leaves 9 lines, all readers of old data with a note saying so: `scripts/observability/lib.py` 83–85
  (`BLOCKER_KINDS`) and `contracts/observability_now.schema.json` 226–232, 303, 309 (deprecated, read
  only).
- 2026-11-05 — `spec-01` pass — `grep -n -i -E 'backstop|12 ?h|twelve-hour|≥ ?12' SPEC.md` leaves line 401,
  the retirement note, and line 4438, an unrelated estimation rule ("at most 12 hours" per usage
  interval), which is not the backstop.
- 2026-11-05 — `compat-01` pass — `python3 -m unittest tests.test_backstop_retired`: a temporary queue with
  a task started 18 hours earlier and an old `now.json` carrying `backstop_hours`, `backstop_breached`
  and a `backstop` blocker; `rebuild-now.sh` and `cpl board build` both exit 0, and neither the
  snapshot, STATUS.md nor the board reports a backstop.

<!-- spec-refs: historical -->
