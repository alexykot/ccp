---
task_id: 0069-removed-scope-paths-marking
title: A task can name a path it removes without a scope warning
status: done
kind: feature
depends_on: []
spec_refs: ["S5"]
review_point: R4
paths: ["ccp/parallel.py", "ccp/tasklog.py", "docs/spec/01-model.md", "plugin/skills/writing-tasks/", "tests/test_tasklog*.py", "tests/test_parallel*.py", "tests/test_scope*.py"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0069-removed-scope-paths-marking

## Intent

`ccp tasks check` does not warn about a declared path the task deletes or replaces when the task marks it as removed, so a task that retires a file can name it in `paths:` without a standing warning.

## Context (not checked)

- A task that deletes a file names, in its Scope, a path that stops existing once it merges, and `ccp tasks check` warns about it as missing.
- Supersedes task 0067, whose check-01 could not fail on the merge base and whose paths omitted `ccp/parallel.py`. The missing-path warning (`parallel.scope_warnings` / `missing_paths`) reads the backticked tokens of a pending task's Scope **In:** item only. The "new" marking existed only in code before; the §5 wording for both markings is the implementer's (§31.1). Work already built for 0067 (PR #56) may be carried over.

## Scope

- **In:** a marking for a removed path, beside the existing "new" marking and in the same form §5 uses for it; `ccp tasks check` accepts a marked-removed path whether or not it exists; §5 and the writing-tasks skill describe it (§31.1: the task's own feature).
- **Out:** deleting files.

## dod_checks

- id: `check-01`
  story: As a task writer, a file my task removes is not a warning.
  setup: a scratch product with a pending task whose Scope **In:** item (not `paths:`) names, in
    backticks, a path holding a `/` that does not exist, marked `(removed)` right after it, in the same
    form and within the same distance as the `new` marking.
  steps:
    1. Run `ccp tasks check`.
  expect: no missing-path warning for that file; the same file unmarked is still warned about.
  dry run: on the merge base the marked file is warned about as missing.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 (implementer): carried over the 0067 build (PR #56, c89a784) without its task-file
  notes. `ccp/parallel.py`: `MARK_RE` (`new` or `removed`, a whole word, any case) replaces the
  `new`-only search in `missing_paths`, so a Scope **In:** path followed within 25 characters by
  `removed` is accepted whether or not it exists; the warning now ends "is not marked new or
  removed". §5.5's Scope row and the writing-tasks skill describe both markings (the implementer's
  wording, §31.1). The test in `tests/test_tasklog.py` builds a pending task whose Scope **In:**
  names `src/retired.py` (removed) and checks it gets no warning, then that the same file unmarked
  does. `paths:` and done tasks stay unchecked, as before.

## Verification notes

- 2026-11-11 — verifier, PR #58 head `ed74fdf` (squash `39f7944`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0069-removed-scope-paths-marking.json.
