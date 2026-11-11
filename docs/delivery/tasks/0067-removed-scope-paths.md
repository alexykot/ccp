---
task_id: 0067-removed-scope-paths
title: A task can name a path it removes without a scope warning
status: pending
kind: feature
depends_on: []
spec_refs: ["S5"]
review_point: R4
paths: ["ccp/tasklog.py", "docs/spec/01-model.md", "plugin/skills/writing-tasks/", "tests/test_tasklog*.py"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0067-removed-scope-paths

## Intent

`ccp tasks check` does not warn about a declared path the task deletes or replaces when the task marks it as removed, so a task that retires a file can name it in `paths:` without a standing warning.

## Context (not checked)

- `ccp tasks check` warns when a Scope or `paths:` entry names a file that does not exist and is not marked new. A task that deletes a file names a path that stops existing once it merges.

## Scope

- **In:** a marking for a removed path, beside the existing "new" marking and in the same form §5 uses for it; `ccp tasks check` accepts a marked-removed path whether or not it exists; §5 and the writing-tasks skill describe it (§31.1: the task's own feature).
- **Out:** deleting files.

## dod_checks

- id: `check-01`
  story: As a task writer, a retired file is not a warning.
  setup: a scratch product with a done task whose `paths:` names a file, marked removed, that no longer exists.
  steps:
    1. Run `ccp tasks check`.
  expect: no warning for that path.
  dry run: on the merge base the path is warned about.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 (implementer): the missing-path warning lives in `parallel.missing_paths` and
  `parallel.scope_warnings` (`ccp/parallel.py`, outside the declared paths). It reads only the Scope
  **In:** item's backticked tokens of a task not yet done, never `paths:`. The `new` marking was the
  word `new` within 25 characters after the token, and no SPEC section described it. The build adds
  `removed` to the same marking (`MARK_RE`), so a marked path is accepted whether or not it exists.
  The warning now says "not marked new or removed". §5.5's Scope row and the writing-tasks skill
  describe both markings. Premise conflict: on the merge base, a done task is not checked and
  `paths:` is never checked, so check-01's dry run (the path is warned about) does not hold.
  Flagged to the runner.

## Verification notes

*Append-only.*
