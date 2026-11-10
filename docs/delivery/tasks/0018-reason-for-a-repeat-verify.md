---
task_id: 0018-reason-for-a-repeat-verify
title: Enforce a reason for a verify round with no fix since the last
status: done
kind: feature
depends_on: []
spec_refs: ["S15"]
adr_refs: []
review_point: R2
paths: ["ccp/prompt.py", "ccp/verify.py", "tests/"]
created: 2026-11-06
updated: 2026-11-10
---

# Task: 0018-reason-for-a-repeat-verify

## Intent

`ccp prompt verify` refuses a second verify round with no fix round since the last verify unless `--note` gives the reason, as SPEC §15.6 already requires; the reason reaches the verifier's record.

## Context (not checked)

- The rule exists in the SPEC; nothing enforces it.

## Scope

- **In:** the check in `ccp prompt verify`, its message, tests.
- **Out:** changing the rule.

## dod_checks

- id: `verify-01`
  story: As a runner, I cannot re-verify without saying why.
  setup: a temporary queue with a verify round and no fix round after it.
  steps:
    1. Run `ccp prompt verify <task>` without `--note`.
  expect: exit non-zero naming the rule; with `--note "…"` it opens the round.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): `ccp prompt verify` refuses, exit 4 and nothing opened, when the task's
  latest verify run that reported has no fix run (not abandoned) opened at or after it, unless
  `--note` or `--note-file` gives the reason (SPEC §15.6 rule 4; `prompt.repeat_gate`,
  `verify.repeat_round`). A verify run that never reported (abandoned or still open) is no round, so
  relaunching one needs no note; a fix opened in the same second counts as newer, as in the §15.2
  gate. The opened run records `repeat_verify: {"after": <prior verify run id>}` beside its `note`,
  and `ccp verify record` adds the note to the record's `findings` when that run carries
  `repeat_verify` and no finding already holds it (`verify.fill_reason`). One existing test that
  opened a second verify round with no fix (`tests/test_suite.py`) now passes `--note`; its
  expectations are unchanged.

## Verification notes

- 2026-11-10 — verifier, PR #14 head `91f9ea8` (squash `5f66d3c`): APPROVE. Passed: verify-01. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0018-reason-for-a-repeat-verify.json.
