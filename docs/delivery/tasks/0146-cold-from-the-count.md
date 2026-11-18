---
task_id: 0146-cold-from-the-count
title: A suite run is recorded cold from its own count alone, so a gate that ignores the cold signal never records cold, and verify record reads the same value
status: done
kind: feature
depends_on: []
spec_refs: ["S14", "S15"]
review_point: R9
sign_off: brief
paths: ["ccp/suite.py", "ccp/verify.py", "ccp/cli.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_suite_cold.py", "tests/test_verify_cache.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-18
---

# Task: 0146-cold-from-the-count
## Intent

A run's `cold` says what the run did, never only what was asked: a `--cold` run is recorded cold when
its own count shows nothing cached, warm when it shows units cached, and unknown when it gives no
count; `ccp verify record` fills a cited run's `cold` from that same recorded value, so the suite record
and the verdict never disagree.

## Context (not checked)

- Follow-up from task 0124. Today `_finish` in `ccp/suite.py` sets `cold = True` for a `--cold` run whose
  output gives no `cached` count (`"if asked_cold and cold is None"`). So a gate that ignores
  `CCP_SUITE_COLD` and prints no cached count is still recorded cold.
- `fill_gate` in `ccp/verify.py` fills a cited run's `cold` only from `cached == 0`
  (`"row.get(\"cached\") == 0"`), so for such a run the suite record says cold and the verdict says
  nothing.
- This is what 0124's signed text says: §14.2 "record `cold: true` unless the run's own count shows units
  cached (§14.6)" and §14.6 "null when it gave no `cached` count (`true` for a `--cold` run, §14.2)". With no
  count, the count does not show units cached, so the text requires `cold: true` on the ask alone. Changing
  it is a rule change, carried below for signing.
- A gate with no cache at all loses nothing: §27.2 judges a run whose `cold` is null by the product's cache
  start (before it, a passing gate run is cold).
- The scripts doc half of that follow-up is in task 0141.

## Scope

- **In:**
  - `ccp/suite.py` `_finish`: `cold` is `run_cold(cached)` whatever was asked; `asked_cold` no longer
    changes it. The module docstring and the `--cold` help in `ccp/cli.py` say "recorded cold only when its own count shows nothing cached".
  - `ccp/verify.py` `fill_gate`: an entry that leaves `cold` out takes the cited row's recorded `cold` when
    it is `true` (the row's `cold` now is `cached == 0` exactly); an explicit value still wins.
  - `docs/cli/02-delivery.md`: the `--cold` wording, if it states the old rule.
  - `docs/spec/02-delivery.md` §14.2. CURRENT (at `921507e`): "and the `ended` row and its event record `cold: true` unless the run's own count shows units cached (§14.6)." PROPOSED:
    > and the `ended` row and its event record `cold` from the run's own count alone (§14.6): asking for a cold run does not make it one.
  - `docs/spec/02-delivery.md` §14.6. CURRENT (at `921507e`): "null when it gave no `cached` count (`true` for a `--cold` run, §14.2)." PROPOSED:
    > null when it gave no `cached` count, a `--cold` run included (§14.2).
  - Each PROPOSED passage goes in on lines of its own, unwrapped, the line holding its first word part
    of the diff, so `ccp verify spec-text` finds it.
  - `tests/test_suite_cold.py`: the tests that expect `cold: true` from a `--cold` run with no count
    change (the change breaks them).
- **Out:**
  - `CCP_SUITE_COLD` itself and `scripts/gate.sh`, unchanged.
  - §27.2's judgement of a null `cold`.

## dod_checks

- id: `cold-01`
  story: As an operator, a gate that ignores the cold signal is not recorded cold.
  setup: a scratch product (`tests/helpers.py`) whose gate lane's stage prints a test count and no cached count.
  steps:
    1. Run `ccp suite run --lane gate --cold`.
  expect: the stage's environment holds `CCP_SUITE_COLD=1`; the `ended` row and its `suite` event have `cold` null.
  dry run: n/a.
- id: `cold-02`
  story: As an operator, a run's own count still decides.
  setup: the same product with two lanes, one whose stage prints `ran 3, cached 0` and one printing `ran 1, cached 2`.
  steps:
    1. Run `ccp suite run --lane <first> --cold`, then `ccp suite run --lane <second> --cold`, then the first lane without `--cold`.
  expect: `cold` is `true`, `false` and `true` in that order.
  dry run: n/a.
- id: `ver-01`
  story: As a verifier, the verdict's cold agrees with the suite record.
  setup: a scratch queue with an open verify run and two suite runs bound to it: one recorded `cached: 0`, one with no cached count made with `--cold`.
  steps:
    1. Run `ccp verify record` on a verdict citing each as a gate run by `suite_id`, `cold` left out.
  expect: the first gate run is filled `cold: true`; the second has no `cold`, matching its row's null.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Run `ccp verify spec-text 0146-cold-from-the-count`, and compare the §14.2 and §14.6 edits with the PROPOSED text above.
  expect: exit 0, both match word for word, and no other § rule changes.
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

- 2026-11-18 (implementer): `_finish` takes `cold` from `run_cold(cached)` alone; the `asked_cold`
  parameter is gone. `fill_gate` fills `cold: true` when the cited row's `cold` is `true` and the entry's
  `cached` (its own, or the one filled from the row) is 0, the guard the code already had. So a row recorded
  `cold: true` with no count at all (a `--cold` run recorded before this change) is not filled, and neither
  is a row with `cached` 0 whose `cold` is null. For rows written from now on the two conditions coincide.
  `docs/cli/02-delivery.md` names `--cold` only in its usage line and states no rule, so it is unchanged.
  The verifier brief (`templates/prompts/verify.md`) says verify record "marks a run with nothing cached as
  cold", which stays true.

## Verification notes
- 2026-11-18 — verifier, PR #163 head `6c77529` (squash `63c4de7`): APPROVE. Passed: cold-01, cold-02, ver-01, check-01, suite-01. Gate: `ccp suite run --lane gate -- gate.sh (0 args)` exit 0, `ccp tasks check && ccp docs check && ccp adr check` exit 0. Record: verification/0146-cold-from-the-count.json.

