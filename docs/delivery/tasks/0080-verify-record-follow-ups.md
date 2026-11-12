---
task_id: 0080-verify-record-follow-ups
title: The verifier's packet and the record's version and ruling checks are complete
status: done
kind: bug
depends_on: []
spec_refs: ["S15"]
review_point: R5
paths: ["templates/prompts/", "plugin/agents/delivery-verifier.md", "contracts/", "ccp/verify.py", "tests/test_verify*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0080-verify-record-follow-ups

## Intent

A verifier writes a valid record on its first try, and the record's version and ruling checks hold against every way they can be broken (§15.4).

## Context (not checked)

- Accepted plane proposals: a verifier discovered `produced_by` only from the refusal; and reviews of the record-version and producer-rule tasks left gaps.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.
- Ruling, spec question sm-20261112T104634Z-0923 (round 1):
  (1) check-02's dry run is n/a: the behaviour already held on the merge base (refusal of an answer
  whose question file is missing, since 0062) and is now pinned. Clarification of the dry-run note
  only; setup, steps and expectation unchanged.
  (2) The new cited-gate-file refusal is §31.1 only as an integrity check: the cited gate file must be
  the gate it is cited as, i.e. its escalation_id and task_id match the cited gate. If the code also
  requires the gate to belong to the task being verified, drop that part (it would otherwise need a
  gate). The §15.4 wording must match what the code does, and no more.
  (3) No digest in the record-version test: pin each version's key set as an explicit sorted list in
  the test (a visible, reviewable expectation), not a sha256.

## Scope

- **In:** the verify prompt template and the verifier brief state `produced_by` and the three `rests_on` forms, with a valid example check, replacing "whose claim it rests on" (and the test that pins that sentence); `contracts/verification.example.json` carries `schema_version`; the record-version test also requires raising `schema_version` when a key is added; a cited spec question needs its question file as well as its answer; a cited gate file must name the gate it is filed as (`escalation_id`) and the task.
- **Out:** changing the three forms.

## dod_checks

- id: `check-01`
  story: As a verifier, the packet shows a valid check.
  setup: a checkout of the PR head.
  steps:
    1. Render a verify prompt with `ccp prompt verify` for a scratch task.
  expect: it states `produced_by` and the three `rests_on` forms and shows a valid example check.
  dry run: on the merge base it says "whose claim it rests on" and no `produced_by`.
- id: `check-02`
  story: As a lead, a ruling id without its question is refused.
  setup: a scratch queue with an answer file whose question file is missing, cited in `rests_on`.
  steps:
    1. Record a verdict citing it.
  expect: it is refused, naming the id.
  dry run: on the merge base it is accepted.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12, implementer: the verify prompt template replaces "whose claim it rests on" with a pointer
  to a new closing paragraph stating `produced_by`, the three `rests_on` forms and two valid example
  checks (one run, one not run, operator form, so it needs no queue state); the verifier brief shows
  the same two checks; a test records each example check shown in either through `ccp verify record`.
  `contracts/verification.example.json` carries `schema_version: 1`, and its test holds it to
  `RECORD_VERSION`. The record-version test keeps a per-version key history, each version's keys
  pinned by a sha256 digest, so a key added under the current version (rather than a raised one)
  changes a pinned expectation; a second test shows the rule refusing that. `_ruling_refusal` refuses
  a cited gate whose file does not name that gate as its `escalation_id` and that task. The
  question-file existence check was already on main (task 0062); this task adds the test that pins
  it, so check-02's dry run (accepted on the merge base) does not hold: flagged in the report. The
  §15.4 text names both citation checks (§31.1), and `record`'s refusals for a missing `rests_on` no
  longer say "whose claim it rests on".
- 2026-11-12, implementer (ruling round 1): (1) check-02's dry run stands as n/a per the ruling;
  its setup, steps and expectation are unchanged. (2) The cited-gate refusal already compared the
  gate file's `task_id` and `escalation_id` with the cited gate id only, never with the task being
  verified, so the code is unchanged; §15.4 and `verify.py`'s docstrings now say exactly that (the
  file is the gate it is cited as), and the gate test also records a correctly filed gate of another
  task as accepted. (3) The record-version test pins each version's keys as an explicit sorted list
  (no sha256); `version_errors` checks that the versions run 1 to `RECORD_VERSION`, that each list is
  sorted without repeats, and that the contract's keys are the current version's. A key slipped into
  a released version's list is now caught by review of that visible expectation, not by the test.

## Verification notes

- 2026-11-12 — verifier, PR #77 head `06ea71a` (squash `c1194ae`): APPROVE. Passed: check-03. Not run by the verifier: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0080-verify-record-follow-ups.json.
