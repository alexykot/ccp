---
task_id: 0092-list-the-tests-a-change-touches
title: A command lists the test modules that depend on changed paths
status: pending
kind: feature
depends_on: []
spec_refs: ["S14"]
review_point: R5
paths: ["ccp/suite.py", "ccp/cli.py", "docs/cli/", "plugin/agents/delivery-implementer.md", "tests/test_suite*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0092-list-the-tests-a-change-touches

## Intent

After a merge or a fix, a worker picks the part lane from the tests that import or exercise the changed modules, listed by `ccp`, instead of guessing by grep (§14.1).

## Context (not checked)

- Accepted plane proposal: implementers and reviewers each guessed test module names, and one guess named a module that does not exist.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** `ccp suite affected [--since <ref>] [--paths …]` prints the test modules that import a changed module (directly or through one package level), or that name a changed file, for the product's language pack; the implementer brief names it for choosing the part lane after a merge.
- **Out:** running the tests.

## dod_checks

- id: `check-01`
  story: As an implementer, I get the tests a change touches.
  setup: a scratch Python product where `tests/test_a.py` imports `pkg/a.py` and `tests/test_b.py` does not.
  steps:
    1. Change `pkg/a.py` and run `ccp suite affected`.
  expect: it prints `tests.test_a` only.
  dry run: on the merge base the command does not exist.
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
