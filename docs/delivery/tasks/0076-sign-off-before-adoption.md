---
task_id: 0076-sign-off-before-adoption
title: A sign-off the operator gave before it could be recorded can be recorded with its date
status: done
kind: feature
depends_on: []
spec_refs: ["S3"]
review_point: R5
paths: ["ccp/lifecycle.py", "ccp/cli.py", "docs/spec/01-model.md", "tests/test_sign_off.py"]
created: 2026-11-12
updated: 2026-11-13
---

# Task: 0076-sign-off-before-adoption

## Intent

A product that adopts mid-life can declare `sign_off` on a task whose text the operator already signed in git, by recording that sign-off with its original date and commit (§3.5), instead of blocking the claim or leaving the text unenforced.

## Context (not checked)

- Accepted plane proposal from an adoption trial.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** `ccp tasks sign-off <id> --by <who> --words "…" --at <date> [--from <commit>]` records a sign-off dated `--at`, its head `--from` (default: the commit that last changed the task file); claim and close judge it as any other; §3.5 says so.
- **Out:** importing sign-offs in bulk.

## dod_checks

- id: `check-01`
  story: As a lead, a past sign-off satisfies the claim.
  setup: a scratch product with a task declaring `sign_off: brief` and no record.
  steps:
    1. Run `ccp tasks sign-off <id> --by operator --words "approved" --at 2026-01-01`.
    2. Run `ccp tasks claim <id>`.
  expect: the record carries the given date and the task file's commit; the claim succeeds.
  dry run: on the merge base `--at` is refused.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-13 (implementer): `ccp tasks sign-off` takes `--at <date>` (`YYYY-MM-DD`, or an RFC 3339
  time with its offset, kept in UTC), stored as the payload's `signed_at`; the event's own `at` stays
  the time it was recorded, so the ledger stays in order. `--at` refuses (exit 2) a value it cannot
  read, a time without an offset, and one later than now. `--from` is another name for the existing
  `--head`: same sha check, same defaults (brief: the task file's last commit; build: the verified
  head). Claim and close read the record as any other: `signed_at` is not consulted. §3.5 says so;
  the CLI table (`docs/cli/02-delivery.md`) and the event contract's `sign_off` description name the
  new flag and key. Tests: `tests/test_sign_off.py`, the "given before it was recorded" group.

## Verification notes

- 2026-11-13 — verifier, PR #90 head `328a0f6` (squash `73e46fc`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0076-sign-off-before-adoption.json.
