---
task_id: 0076-sign-off-before-adoption
title: A sign-off the operator gave before it could be recorded can be recorded with its date
status: pending
kind: feature
depends_on: []
spec_refs: ["S3"]
review_point: R5
paths: ["ccp/lifecycle.py", "ccp/cli.py", "docs/spec/01-model.md", "tests/test_sign_off.py"]
created: 2026-11-12
updated: 2026-11-12
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

## Verification notes

*Append-only.*
