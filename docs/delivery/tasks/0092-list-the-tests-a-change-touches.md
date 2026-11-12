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

- 2026-11-12 — `ccp suite affected [--since REF | --paths PATH …]` (ccp/suite.py, wired in ccp/cli.py),
  described in SPEC §14.7 under §31.1 and listed in docs/cli/02-delivery.md; the implementer brief names
  it for the part lane after a merge. Choices where the task left room, each the narrowest reading:
  the change without `--paths` is `git diff REF` against the working tree (default `HEAD`) plus
  untracked, not-ignored files, renames as both paths; `--since` and `--paths` do not mix; the reader
  is keyed by `package_docs.language` (the knob's default `python` when the block is absent; `none`
  exits 2) and lives in ccp/suite.py, inside the task's declared paths, rather than in ccp/doclang;
  Python test modules are `test*.py` files (unittest's default pattern) git tracks or does not
  ignore; "one package level" is a package the test imports whose `__init__.py` imports the changed
  module, and importing `p.m` counts as importing `p`; "names a changed file" is the file's name
  appearing in the test's text; a changed test module lists itself. Output is plain lines, so it
  can feed `python3 -m unittest` directly.

## Verification notes

*Append-only.*
