---
task_id: 0286-the-spec-states-the-operator-gate-waiver-limit-and-cites-language-packs
title: The SPEC states that an operator gate never waives a marked check, and §20.6 cites the language packs' section for the per-test runner
status: pending
kind: feature
depends_on: []
spec_refs: ["S15", "S20", "S21"]
review_point: R25
paths: ["docs/spec/02-delivery.md", "docs/spec/03-quality.md"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0286-the-spec-states-the-operator-gate-waiver-limit-and-cites-language-packs

## Intent

§15.4 says what the code already enforces: a ruling that waives a marked check must name at least one id
that is not an operator gate, since an operator gate approves running a step, never skipping it. §20.6
cites §21.4, where language packs are defined, for the pack's per-test runner. Text only; no code
changes.

## Context (not checked)

From the triage of architect pass `ar-20261122T055103Z-11aa` (the record is in `docs/delivery/reviews/`):
the lead's deferred question four of `ar-20261121T223646Z-f0a7` (§15.4), asked again in this triage, and
worker follow-ups `0267-mutate-falls-back-to-the-language-pack/review#3` and `…/verify#3` (`…` being
`0267-mutate-falls-back-to-the-language-pack`).

Measured at `76f41dd` (re-measured: neither SPEC file has changed since the first measurement at `072d9f9`, `git diff --stat 072d9f9 76f41dd -- docs/spec/02-delivery.md docs/spec/03-quality.md` at `76f41dd`: empty).

- **§15.4.** `ccp/verify.py` `"def _waiver_texts"`: "An operator gate approves running a step, never
  skipping it, so a text whose only ids are operator gates waives nothing." §15.4 says a waiving ruling
  names "spec question ids, gate ids or lead ruling ids" (`grep -n 'gate ids' docs/spec/02-delivery.md` at `76f41dd`: 1 line),
  with no class limit. ADR-0045 D3 (built) reads as the code does. So the SPEC is the one out of step.
- **§20.6.** Task 0267's signed passage says "the language pack's per-test runner (§14.1)". §14.1 is the
  suite-run rule; language packs, their test command included, are §21.4 (`grep -n '^### 21.4' docs/spec/03-quality.md` at `76f41dd`: "Language packs").
  The passage's second §14.1 citation ("Its test runs are not suite runs (§14.1)") is correct and stays.

## Scope

- **In:** the two SPEC passages below, nothing else.
- **SPEC, signed before the claim (`sign_off: brief`):** one passage in `docs/spec/02-delivery.md` and one
  in `docs/spec/03-quality.md`, each CURRENT at `76f41dd`.

    CURRENT (`docs/spec/02-delivery.md` at `76f41dd`), §15.4, the sentence that starts "A marked check resting on a verdict":
    > A marked check resting on a verdict it may carry needs no run at the new head, and one waived by a ruling is handled as any other.

    PROPOSED:
    > A marked check resting on a verdict it may carry needs no run at the new head, and one waived by a ruling is handled as any other, save that the ruling must name at least one id that is not a gate of class `operator`: an operator gate approves running a step, never skipping it.

    CURRENT (`docs/spec/03-quality.md` at `76f41dd`), §20.6, the sentence on a product with no command:
    > With no command it runs the language pack's per-test runner (§14.1), its test command followed by the test id;

    PROPOSED:
    > With no command it runs the language pack's per-test runner (§21.4), its test command followed by the test id;
- **Out:** any code change (the code already holds the §15.4 limit); the rest of §20.6.

## dod_checks

- id: `spec-01`
  story: As the operator, §15.4 and §20.6 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0286`.
  expect: exit 0, both PROPOSED passages found.
  dry run (simulated at `76f41dd`: this task file committed, then the 2 passages applied, each CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0286 --base HEAD~1`): `"ok": true`, 2 passage(s) found, none missing.
- id: `doc-01`
  story: As a reader, the SPEC's waiver rule matches the code's, and nothing else in the SPEC changed.
  setup: A checkout of the PR head.
  steps:
    1. Run `git diff --name-only origin/main...HEAD -- docs/spec`.
    2. Run `python3 -B -m unittest -q tests.test_verify_later 2>&1 | tail -1`.
  expect: step 1 prints `docs/spec/02-delivery.md` and `docs/spec/03-quality.md` and nothing else; step 2 prints `OK`.
  dry run (`76f41dd`): step 1 printed nothing; step 2 printed `OK`.

## Implementation notes

- Re-measured at `7a2993b4`: `waiver_refusal` in `ccp/verify.py` still refuses a text whose only ids are operator gates; each CURRENT passage is found once (the §15.4 one wraps a line, so the edit keeps the wrap); §21.4 is still "Language packs".
- Applied the two PROPOSED passages as given, in `docs/spec/02-delivery.md` and `docs/spec/03-quality.md`. No code change.
- `ccp verify spec-text 0286 --base HEAD~1` on the commit: ok, 2 passages found, none missing.

## Verification notes
