---
task_id: 0059-newer-record-fields-verify-and-close
title: Tasks that add a record field can be verified and closed
status: pending
kind: bug
depends_on: []
spec_refs: ["S15", "S29"]
review_point: R4
paths: ["ccp/verify.py", "contracts/", "docs/spec/02-delivery.md", "tests/test_verify*.py"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0059-newer-record-fields-verify-and-close

## Intent

A task whose change adds a field to a record the plane checks (such as the verification record) can be verified and closed before the run checkout moves: the installed `ccp` accepts a record written by the newer `ccp` on the PR head, so close does not refuse it as an unknown key (§15, §29).

## Context (not checked)

- Raised while delivering the separation-of-duties task: the verifier wrote the record with the PR head's `bin/ccp`, and `ccp verify merge-ok` with the run checkout's older `ccp` refused it ('unexpected key'); the close had to use the head's `bin/ccp`. Every task that extends a checked record hits this.

## Scope

- **In:** choose one and state it in §15: (a) `merge-ok` and close read the record against the PR head's contract; or (b) a record carries the schema version of the `ccp` that wrote it, and an older `ccp` accepts unknown keys from a newer version while still refusing a known key's bad value.
- **Out:** relaxing checks on known fields.

## dod_checks

- id: `check-01`
  story: As a runner, a record with a newer field closes.
  setup: a scratch verify record carrying a field the installed contract does not know, written by a newer version.
  steps:
    1. Run `ccp verify merge-ok`.
  expect: it passes.
  dry run: on the merge base it refuses with 'unexpected key'.
- id: `check-02`
  story: As a verifier, a bad known field is still refused.
  setup: a record with a known field holding a bad value.
  steps:
    1. Run `ccp verify merge-ok`.
  expect: it refuses.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
