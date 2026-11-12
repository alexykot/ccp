---
task_id: 0081-mutate-follow-ups
title: ccp mutate takes one test method, reverts a hunk, stops cleanly and runs from the reviewer's worktree
status: pending
kind: feature
depends_on: []
spec_refs: ["S20"]
review_point: R5
paths: ["ccp/mutate.py", "ccp/wt.py", "docs/spec/03-quality.md", "docs/cli/", "tests/test_mutate*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0081-mutate-follow-ups

## Intent

Proving a test bites is quick and recorded for every seat: `ccp mutate` targets a single test method, can revert named hunks of the task's change as a mutant, runs from the reviewer's or verifier's own worktree, and its stop on a signal is pinned (§20.6).

## Context (not checked)

- Accepted plane proposals: mutating against one new test ran its whole class; seats hand-edited copies to revert hunks; a reviewer had to make a second worktree to mutate; and the end-of-run signal checks are untested.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.
- Ruling (spec question sm-20261112T085010Z-03f9, commit 93bdcf0): the pin is enough. The plane
  passes `--test` through to the product's `mutate.command`, and a unittest method id already ran
  only that method, so item 1 needs no code change: a test that pins single-method behaviour plus
  the §20.6 and `--test` help wording satisfies check-01's expectation. Read check-01's `dry run`
  line as "n/a: the behaviour already held on the merge base, now pinned" (a clarification of the
  dry-run note; setup, steps and expectation unchanged). Do not refuse a repeated `--test` or check
  test counts.

## Scope

- **In:** `--test` accepts a single test method id; `--revert <path>[:<line-range>]` builds a mutant that restores the merge base's version of that file or range; `ccp mutate` runs in a `rev-` or `ver-` worktree as well as `mut-`; a test sends SIGTERM during the save of a one-mutant run and asserts exit 143 and no `run`/`recorded` event; one long docstring line is wrapped; §20.6 states the options.
- **Out:** choosing mutants automatically.

## dod_checks

- id: `check-01`
  story: As a verifier, I mutate against one test method.
  setup: a scratch product with a test class of two methods, one of which checks the mutated line.
  steps:
    1. Run `ccp mutate --test <module>.<Class>.<method> --mutant …`.
  expect: only that method runs; the mutant is recorded killed.
  dry run: on the merge base a method id is refused or runs the whole class.
- id: `check-02`
  story: As a reviewer, I revert a hunk from my own worktree.
  setup: a `rev-` worktree of a task whose change adds a guard in `src/a.py`.
  steps:
    1. Run `ccp mutate --revert src/a.py:10-12 --test <test>`.
  expect: the guard is reverted for the run, the test fails, and the record says killed; the tree is restored.
  dry run: on the merge base `--revert` does not exist and a `rev-` worktree is refused.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12 (implementer): `--test` was already passed whole to `mutate.command`, so a method id
  ran that method alone on the merge base too (check-01's dry-run premise does not hold for a
  unittest command); a test now pins it and §20.6 says so. `--revert PATH[:N[-M]]` (repeatable) is
  a mutant of kind `revert`: the merge base (HEAD's with `origin/<integration>`, `wt.merge_base`)
  version of the file, a file the change added removed; with a range, every change whose lines in
  the worktree's file overlap N..M, plus a deletion inside or next to it, is put back. A revert that
  changes nothing, a range outside the file, a directory or a path outside the worktree is refused
  (exit 2). The `--mutant`s are numbered first, then the `--revert`s; `--mutant` is no longer
  required, but one of the two is. `ccp mutate` takes `mut`, `rev` and `ver` worktrees. Wrapped the
  long docstring and message lines in `ccp/mutate.py`. `ccp/cli.py` (outside `paths`) gained the
  flag; `ccp/wt.py` did not change.
- 2026-11-12 (implementer, ruling round 1): wrote the lead's ruling on check-01 into Context. It
  confirms the existing pin (`test_a_method_id_runs_that_method_alone`), the §20.6 sentence and the
  `--test` help as item 1's whole delivery, and reads check-01's dry run as n/a; no code, test or doc
  change followed. No refusal of a repeated `--test` and no test-count check were added.

## Verification notes

*Append-only.*
