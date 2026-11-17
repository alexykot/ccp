---
task_id: 0132-model-alias-matches-full-ids
title: A run pinned to a model alias reads as on-pin when telemetry reports a full id of that family
status: done
kind: feature
depends_on: []
spec_refs: ["S2", "S24"]
review_point: R8
paths: ["ccp/models.py", "ccp/usage.py", "ccp/seats.py", "ccp/board.py", "tests/test_model_alias.py", "tests/test_usage*.py", "tests/test_board_seats.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0132-model-alias-matches-full-ids
## Intent

The implementer-model trial can be measured: a run whose expected model is an alias is judged
against the full model ids telemetry reports, so its runs read as on-pin and count in the usage
window.

## Context (not checked)

- Task 0121 let `workers.implementer_model` take the aliases the Agent tool accepts (`sonnet`, `opus`,
  `haiku`, `fable`), so a run's `expected_model` can be an alias.
- Its review found (MAJOR, accepted by the lead's ruling, not fixed before merge) that `ccp usage`
  (the pin check and the window fallback) and `ccp/seats.py` (the mismatch flag, which the board shows)
  compare `expected_model` with the observed full id by equality, so every run pinned to an alias
  reads as a mismatch and the window fallback skips it.
- This describes task 0121's own feature (§31.1): no rule changes.

## Scope

- **In:**
  - One helper, in `ccp/models.py` (new), that says whether an observed model id matches an expected one: equal
    ids match, and an alias matches any full id of its family (`sonnet` matches an id containing
    `-sonnet-`).
  - `ccp/usage.py` and `ccp/seats.py` use it wherever they compare an expected model with an observed
    one.
- **Out:**
  - Which model a task kind gets, and the trial itself.

## dod_checks

- id: `alias-01`
  story: As an operator running the implementer-model trial, a run pinned to an alias reads as on-pin.
  setup: telemetry fixtures for two implement runs whose `expected_model` is `sonnet`, one observed on a full Sonnet id and one on a full Opus id.
  steps:
    1. Run `ccp usage` and the board's seats view over that window.
  expect: the Sonnet run is on-pin and counted by the window fallback; the Opus run is flagged as a mismatch in both.
  dry run: n/a.
- id: `alias-02`
  story: As a plane developer, a full expected id still matches only itself.
  setup: the helper's tests.
  steps:
    1. Run `tests/test_model_alias.py`.
  expect: a full id matches only an equal id; an alias matches its family and no other; an unknown alias matches nothing.
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

- 2026-11-17 (implementer): `ccp/models.py` `matches(observed, expected)`: equal ids match; an
  expected value in `config.WORKER_MODEL_ALIASES` also matches an observed id containing `-<alias>-`;
  anything else (an unknown alias included) is compared by equality only, so it matches no full id.
  Used at every site in `ccp/usage.py` and `ccp/seats.py` that compares an expected model with an
  observed one: the run pin check (a run is flagged when any observed model does not match), the
  window join, the design seat's advice (kept its `startswith` prefix test, alias match added) and
  `seats.mismatch` (the design seat's `[...]`-stripped compare included). `ccp/board.py` needed no
  change: its seats view is `seats.collect`. `ccp/CLAUDE.md` lists the new module.

## Verification notes
- 2026-11-17 — verifier, PR #140 head `9f6e534` (close's catch-up of the approved `8f24b2a`, gate run st-20261117T192557Z-3717ad) (squash `d2dbd16`): APPROVE. Passed: alias-01, alias-02, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0132-model-alias-matches-full-ids.json.

