---
task_id: 0170-forecast-models-co-scheduling
title: The forecast keeps apart the tasks claim rule 3 keeps apart, through the pairwise co-scheduling predicate
status: pending
kind: feature
depends_on: ["0164-clashes-with-and-schedule"]
spec_refs: ["S16", "S26"]
adr_refs: ["0042 D1", "0042 D2"]
review_point: R11
paths: ["ccp/forecast.py", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "tests/test_parallel_records.py"]
adopt: "none"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0170-forecast-models-co-scheduling
## Intent

With several runner slots, `ccp forecast` no longer draws two tasks running side by side when the
claim rules would never let them. A task starts no earlier than the end of every task ahead of it that
claim rule 3 keeps it from running beside: paths that meet under `parallel.schedule: paths`, a
`clashes_with` under `clashes`. The completion dates a lead reads match how the runners actually
schedule, in both modes. With one slot the forecast is exactly as today.

## Context (not checked)

- ADR-0042 D1 and D2 (accepted 2026-11-19), and its Consequences line "§16.7: the forecast models
  clashes". The shape (`sh-20261119T072530Z-663f`, single source "whether two tasks may run
  together") names `ccp/forecast.py`'s slot model as the third copy of that fact. It should go through
  the one pairwise predicate of 0161-paths-meet-and-parallel-defaults, `parallel.kept_apart`, which 0164-clashes-with-and-schedule makes branch on
  `parallel.schedule`.
- **False premise in the brief.** The brief said "§16.7 today says tasks whose paths meet are not
  modelled". That is not so: the SPEC says nothing about them.
  - §16.7's Forecast bullet (`docs/spec/02-delivery.md`) and §26.4's Throughput bullet
    (`docs/spec/04-observability.md`) model only dependencies, the slots, and lone tasks (no paths and
    no `parallel: true`, or an exclusive path). `git grep -n -i "not modelled" -- docs/spec` at
    `b9e58ce` prints one line, §26.4's "Waits on the operator are not modelled", which is unrelated.
  - The sentence is in the code. `ccp/forecast.py`'s throughput text says "Not modelled: two tasks
    whose paths meet, or work past the 5-hour ceiling, still share slots", and its module docstring
    says "tasks whose paths meet, and the 5-hour ceiling, are not modelled". `git grep -n "paths meet" -- ccp/forecast.py` at `b9e58ce`: 2 lines.
  - So the SPEC is silent, and the model lets meeting tasks overlap.
- **Signed: this changes rules.** Modelling the claim rule changes the meaning of the model §16.7 and §26.4
  state (when a task starts). It also changes forecasts under the default `paths`, not only under
  `clashes`. ADR-0042 names §16.7 but not §26.4. So this task carries `sign_off: brief` with both
  passages, rather than §31.1.
- `forecast.simulate` today: a task starts at the earliest free slot (every slot when it is in
  `alone`), no earlier than the task ahead of it started and than each dependency's end (`dep_ix`).
  The new constraint is a second index list beside `dep_ix`.
  - It draws no random numbers, so with no pair kept apart the draws are identical.
  - `tests/test_parallel_records.py` `Slots` holds the slot model:
    `python3 -m unittest tests.test_parallel_records` at `b9e58ce`: 7 tests, OK.
- The order is `ccp tasks next`'s order, each task marked merged in turn, as today. A task the next
  walk passes over (D2) is still replayed in that order. The constraint only delays its start.
- Exclusive paths (§16.3's exclusive rule) still make a task take every slot, as today.

## Scope

- **In:**
  - `ccp/forecast.py`:
    - `simulate` gains `apart: dict[str, set[str]] | None`: for each task, the tasks ahead of it in
      `order` it may not run beside. Its start is at least each such task's end (in flight or drawn),
      as with a dependency. With `apart` empty or None, every draw and result is as today.
    - `forecast()`, when `slots > 1`, builds `apart` from `parallel.kept_apart` over each pair of tasks in the
      order (the earlier one ahead).
    - The throughput gains `apart_pairs` (the count) and `schedule` (`parallel.schedule`). Its text
      drops "two tasks whose paths meet" from "Not modelled" and says how many pairs are kept apart and
      under which schedule.
    - The module docstring's "tasks whose paths meet ... are not modelled" is corrected.
  - `docs/spec/02-delivery.md` §16.7, the Forecast bullet, one passage. PROPOSED replaces CURRENT in
    place, on one unwrapped line:
    CURRENT (at `b9e58ce`): "dependencies; one without paths and without `parallel: true`, or touching an exclusive path, takes" PROPOSED:
    > dependencies and after every task ahead of it that claim rule 3 keeps it from running beside (§16.3, by `parallel.schedule`: paths that meet, or a clash); one without paths and without `parallel: true`, or touching an exclusive path, takes
  - `docs/spec/04-observability.md` §26.4, the Throughput bullet, one passage, the same way:
    CURRENT (at `b9e58ce`): "free slot after its dependencies merge, never before the task ahead of it started; a task without" PROPOSED:
    > free slot after its dependencies merge and after every task ahead of it that claim rule 3 keeps it from running beside ends (§16.3, by `parallel.schedule`: paths that meet, or a clash), never before the task ahead of it started; a task without
  - `tests/test_parallel_records.py`: the checks below, in `Slots` and a new case beside it. The
    existing `Slots` tests stay unchanged.
  - ADR-0042 D1 and D2: task 0164 marked both built (ruling sm-20261119T113130Z-8831); this task marks nothing.
- **Out:**
  - The order the forecast replays.
  - The 5-hour ceiling.
  - Rule 4 (exclusive paths).
  - The board's forecast card, beyond what it reads from `throughput`.

## dod_checks

- id: `fc-01`
  story: As a lead, two tasks the claim rules keep apart are forecast one after the other even with free slots.
  setup: `forecast.simulate` with order `a`, `b`, `c`, `d`, each lognormal(3600, 5400), no dependencies, 300 trials, seed fixed, two slots.
  steps:
    1. Run it with `apart` None, and with `apart={}`.
    2. Run it with `apart={"b": {"a"}}`, and with `apart` keeping every later task apart from every earlier one.
  expect: step 1's two results equal each other and today's (`slots=2`, no `apart`); in step 2, the first run's median end of target `["a", "b"]` is later than with `apart` None, and the second run's `all` ends equal the one-slot run's ends.
  dry run: n/a — `simulate` has no `apart` argument at `b9e58ce`; `python3 -m unittest tests.test_parallel_records` there ran 7 tests, OK.
- id: `fc-02`
  story: As a lead, the forecast reads rule 3 through the same predicate the claim uses, under either schedule.
  setup: a fenced product with `parallel.max_in_flight` 2 and two pending tasks, A and B, whose declared paths meet and which name no `clashes_with`; a copy with `parallel.schedule: clashes`; and a copy of that with B's `clashes_with: [A]`.
  steps:
    1. Run `ccp forecast --backlog --json` in each.
  expect: `throughput.apart_pairs` is 1 under `paths`, 0 under `clashes` without `clashes_with`, and 1 with it; `throughput.schedule` names the schedule in each; no `throughput.text` holds `paths meet`.
  dry run: n/a — at `b9e58ce` the throughput has no `apart_pairs` and its text says "Not modelled: two tasks whose paths meet".
- id: `suite-01`
  story: As a plane developer, the SPEC carries the signed words and nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0170-forecast-models-co-scheduling --base origin/main`.
    2. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: step 1 exits 0 with both passages found; step 2's commands all pass and the branch list is empty.
  dry run: n/a — the passages are not in the SPEC at `b9e58ce`.

## Implementation notes

*Append-only, newest last.*

## Verification notes
