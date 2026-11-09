---
task_id: 0046-test-fence-clears-queue-root
title: The test fence clears an inherited QUEUE_ROOT
status: pending
kind: bug
depends_on: []
spec_refs: ["S14"]
review_point: R1
paths: ["tests/__init__.py", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0046-test-fence-clears-queue-root

## Intent

The plane's own suite passes under `ccp suite run` in a seat that has `QUEUE_ROOT` set. The test
fence clears an inherited `QUEUE_ROOT`, so no test reads a live queue (§14).

## Context (not checked)

- A runner working on the plane itself exports `QUEUE_ROOT` (the plane's own queue). The fence in
  `tests/__init__.py` does not clear it, so a test that runs `ccp tasks next` without its own queue
  reads the live one and gets exit 3. On `9d06bcd`, `tests.test_pkgdocs_config.ConfigTest.test_cli_exit_codes`
  fails this way, which turns every task's gate red.

## Scope

- **In:** `tests/__init__.py` pops `QUEUE_ROOT` (and `PROJECT_YAML` if a test path reads it) next to
  the other fenced variables, with a one-line comment; tests that need a queue already set their own.
- **Out:** any change to how `ccp` resolves the queue outside tests.

## dod_checks

- id: `check-01`
  story: As a runner on the plane itself, the gate passes with my queue exported.
  setup: a checkout of the PR head; `QUEUE_ROOT` set to any existing directory holding a queue with a
    ready task.
  steps:
    1. Run `QUEUE_ROOT=<that dir> python3 -m unittest tests.test_pkgdocs_config`.
  expect: it passes; on the merge base the same command fails `test_cli_exit_codes`.
  dry run: on 9d06bcd with the plane's own queue exported, `test_cli_exit_codes` fails (exit 3).
- id: `check-02`
  story: As a plane developer, the whole suite still passes.
  setup: a checkout of the PR head, `QUEUE_ROOT` set as in check-01.
  steps:
    1. Run `python3 -m unittest discover -s tests -t .`, then `git branch --list 'state/*'`.
  expect: the suite passes and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
