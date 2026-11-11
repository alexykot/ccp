---
task_id: 0061-mutate-record-and-signal-follow-ups
title: `ccp mutate` keeps code text out of its record and stops cleanly on a signal
status: pending
kind: bug
depends_on: []
spec_refs: ["S20", "S23", "S24"]
review_point: R4
paths: ["ccp/mutate.py", "scripts/observability/lib.py", "docs/spec/03-quality.md", "docs/spec/04-observability.md", "tests/test_mutate*.py"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0061-mutate-record-and-signal-follow-ups

## Intent

A `ccp mutate` run record never carries code text, old or new; a signal between mutants or in the baseline run ends the call with exit 143 and no orphaned child; a restore leaves the tree exactly as it was; and its event is listed where every event is listed.

## Context (not checked)

- From task 0044's review. The record test checks only that a mutant's new text is absent, so its old text could reach the record unnoticed. The plane's records carry numbers and ids only (§24), so this gap matters most.
- A SIGTERM between mutants or during the baseline run exits 1 or leaves a child running, instead of 143.
- A patch that creates a file in a new directory leaves an empty directory after restore.
- The `run`/`recorded` event that `ccp mutate` writes is missing from the §23.2 event table and the `lib.py` payload map.
- §20.6 does not say how `ccp mutate` relates to §14.1: its test runs are not suite runs.

## Scope

- **In:** the record test asserts that neither the old nor the new text of any mutant appears anywhere in the run record or event payloads; a signal at any point of the call kills the running child, restores the tree and exits 143; restore removes directories a patch created; §23.2 and the `lib.py` payload map list the event; one §20.6 sentence states that its test runs are not suite runs (§14.1). These describe the feature and need no separate approval (§31.1).
- **Out:** mutant selection; other commands.

## dod_checks

- id: `check-01`
  story: As an operator, no code text reaches a mutate record.
  setup: a scratch product with `mutate.command` set and one mutant whose old and new texts are distinctive strings.
  steps:
    1. Run `ccp mutate` with that mutant.
    2. Search the run record and the ledger events for both strings.
  expect: neither string appears.
  dry run: n/a — the current test searches only for the new text, so a leak of the old text would pass.
- id: `check-02`
  story: As a runner, an interrupted mutate call leaves nothing behind.
  setup: a mutant whose test command sleeps; a second run interrupted during the baseline.
  steps:
    1. Send SIGTERM during a mutant's test, then during a baseline run.
    2. Check the exit code, running processes and the working tree.
  expect: exit 143 each time, no child left running, the tree as before (no new empty directory).
  dry run: on the merge base the call exits 1 or leaves a child running.
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
