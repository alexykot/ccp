---
task_id: 0104-command-edge-fixes
title: suite affected, sign-off --at, wt exec and main_of handle their edge cases
status: pending
kind: fix
depends_on: []
spec_refs: ["S3", "S12", "S14"]
review_point: R6
paths: ["ccp/cli.py", "ccp/suite.py", "ccp/lifecycle.py", "ccp/wt.py", "ccp/refs.py", "docs/spec/01-model.md", "tests/test_suite_affected.py", "tests/test_sign_off.py", "tests/test_wt.py", "tests/test_merge_base.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0104-command-edge-fixes

## Intent

Commands that misread an input or crash on one now handle it. Each fix below has a test that fails
without it.

## Context (not checked)

- Accepted plane proposals (operator, 2026-11-16: all approved), the follow-ups of earlier tasks.
- `ccp suite affected`:
  - Git reads a `--since` that starts with a dash as an option.
  - The basename-only name match lists nearly every test for an extension-less path or a directory.
  - `--paths` is not normalised.
- `ccp tasks sign-off --at` compares a date-only value with the local date, but a time with an offset
  with UTC now.
- `ccp wt exec`:
  - A malformed `--timeout` gives a traceback.
  - A SIGTERM before the worktree exists exits with no result JSON.
  - Between `create` returning and its record being bound in `run_on_base` there is a small window
    where a worktree can leak.
- `main_of`, from a linked worktree of a repository with a separate git dir, returns the checkout
  itself.

## Scope

- **In:**
  - `suite affected`:
    - pass `--since` after `--` (or as `--since=<ref>` resolved with `rev-parse --verify`);
    - match a test by name only for a path that has an extension and is not a directory;
    - normalise `--paths` (strip `./`, collapse `..`, relative to the root).
  - `sign-off --at`: one rule. A date-only value is a UTC date, compared with today's UTC date, and the
    SPEC §3.5 sentence says so.
  - `wt exec`:
    - a malformed `--timeout` refuses with exit 2 and a message;
    - a SIGTERM before the worktree exists emits the result JSON with `signal: 15` and no worktree;
    - the leak window in `run_on_base` is closed by binding the record before anything can be
      interrupted, or by cleaning up on the signal.
  - `main_of` returns the main checkout for a linked worktree of a separate-git-dir repository.
- **Out:**
  - New flags, or any rule beyond what Scope names.

## dod_checks

- id: `check-01`
  story: As a worker, `suite affected` lists the tests a change touches, and no more.
  setup: a throwaway product with tests named after modules, a `Makefile` at the root, and a
    directory `pkg/`.
  steps:
    1. Run `ccp suite affected --since -x`.
    2. Run it with `--paths Makefile`, `--paths pkg/`, and `--paths ./pkg/../pkg/mod.py`.
  expect: (1) refuses as an unknown ref, not as an option error. (2) The first two do not list every
    test whose name contains the basename. The third lists what `--paths pkg/mod.py` lists.
  dry run: n/a.
- id: `check-02`
  story: As a lead, `--at` means one thing.
  setup: a task with a sign-off due, and the local zone set to UTC-10 late in the day, so that the
    local date is behind the UTC date.
  steps:
    1. Record with `--at <today's UTC date>`.
  expect: accepted. A date after today's UTC date is refused.
  dry run: n/a.
- id: `check-03`
  story: As a runner, `wt exec` fails cleanly.
  setup: a throwaway product.
  steps:
    1. Run `ccp wt exec --timeout abc …`.
    2. Send SIGTERM to `ccp wt exec` before its worktree is made (a test hook or a slow `merge_base`).
  expect: (1) exit 2 with a message and no traceback. (2) Exit 143 and a result JSON with `signal:
    15`, with no worktree or record left.
  dry run: n/a.
- id: `check-04`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
