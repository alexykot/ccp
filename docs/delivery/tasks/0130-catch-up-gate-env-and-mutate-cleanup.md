---
task_id: 0130-catch-up-gate-env-and-mutate-cleanup
title: Close's catch-up gate runs with its own worktree's values and the product's worker_env, and mutate clears stale bytecode first
status: pending
kind: feature
depends_on: ["0126-append-only-shared-paths"]
spec_refs: ["S14", "S16"]
review_point: R8
sign_off: brief
paths: ["ccp/lifecycle.py", "ccp/prompt.py", "ccp/mutate.py", "docs/spec/02-delivery.md", "tests/test_tasks_close.py", "tests/test_mutate.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0130-catch-up-gate-env-and-mutate-cleanup
## Intent

A product's gate run by close's catch-up sees the worktree it actually runs in and the same
`worker_env` values a worker's gate sees, so its per-worktree resources do not collide with the
implementer's; close survives a partial worktree record; and a mutation run never reads stale
bytecode.

## Context (not checked)

- The catch-up gate's `CCP_WT_WORKTREE` names the implementer's worktree, not close's `merge-<nnnn>`
  worktree where the gate runs, and the gate gets no `prompts.worker_env` values.
- `_task_worktree_env` (`"def _task_worktree_env"` in `ccp/lifecycle.py`) raises `KeyError` on a
  worktree record missing a field.
- `tests/test_tasks_close.py` lost its `if __name__ == "__main__":` guard.
- `ccp mutate` drops stale bytecode after a restore but not before the mutated run.
- Depends on 0126: both change close's catch-up in `ccp/lifecycle.py`.

## Scope

- **In:**
  - `ccp/lifecycle.py`: the catch-up gate's stages get `CCP_WT_WORKTREE` naming the `merge-<nnnn>`
    worktree, `CCP_WT_KIND` `merge`, the task's other fields, and `prompts.worker_env` rendered for
    that worktree; a record missing a field gives that variable empty, never a `KeyError`.
  - `ccp/mutate.py`: drops the mutated file's bytecode before the run as well as after the restore.
  - `tests/test_tasks_close.py`: the `__main__` guard restored.
  - `docs/spec/02-delivery.md` §16.5 rule 4. CURRENT (at `b4de6ad`): "runs the gate lane on the result as a recorded run," PROPOSED:
    > runs the gate lane on the result as a recorded run in its `merge-<nnnn>` worktree, whose stages get that worktree's `CCP_WT_<FIELD>` variables (kind `merge`) and `prompts.worker_env` rendered for it,
- **Out:**
  - Making `merge-<nnnn>` a recorded `ccp wt` kind.

## dod_checks

- id: `close-01`
  story: As a product's gate, I see the worktree I run in.
  setup: a scratch product whose gate lane writes `$CCP_WT_WORKTREE`, `$CCP_WT_KIND` and a `worker_env` variable `SCRATCH={{kind}}_{{nnnn}}` to a file, and a task whose close needs a clean catch-up.
  steps:
    1. Run `ccp tasks close <task>`.
  expect: the file names the `merge-<nnnn>` worktree, kind `merge`, and `SCRATCH=merge_<nnnn>`.
  dry run: n/a.
- id: `close-02`
  story: As close, a partial record does not crash me.
  setup: the product of close-01 with the task's `impl` worktree record lacking its `seat` field.
  steps:
    1. Run `ccp tasks close <task>`.
  expect: no `KeyError`; the gate's `CCP_WT_SEAT` is empty.
  dry run: n/a.
- id: `mut-01`
  story: As a verifier, a mutation never runs stale bytecode.
  setup: a scratch package whose module's `__pycache__` holds bytecode compiled from a different source, and a test that catches the mutant.
  steps:
    1. Run `ccp mutate --mutant '<module file>:<old>=><new>' -- python3 -m unittest`.
  expect: the test fails on the mutant (the mutated source ran), and the file is restored.
  dry run: n/a.
- id: `code-01`
  story: As a developer, the close tests run on their own.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 tests/test_tasks_close.py`.
  expect: the tests run and pass.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §16.5 edit with the PROPOSED text above.
  expect: it matches word for word, and no other § rule changes.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 (implementer): `_task_worktree_env` now takes the merge worktree's path and builds the gate's
  environment itself, without `wt.context` (which indexes every field): `CCP_WT_WORKTREE` the `merge-<nnnn>`
  path, `CCP_WT_NAME` its name, `CCP_WT_KIND` `merge`, `CCP_WT_TASK_ID`/`CCP_WT_NNNN`/`CCP_WT_MAIN_CHECKOUT`
  from the task, `CCP_WT_SEAT`, `CCP_WT_TAG` and `CCP_WT_ROUND` from the task's `impl` record (empty when
  missing, the round 1), `CCP_TASK_ID`/`CCP_NNNN`, and `prompts.worker_env` rendered with `kind` `merge`, the
  merge path, `run_id` empty (close has no run) and `phase` `verify` (the phase the gate run is recorded
  under). With no `impl` record the gate still gets the merge worktree's fields, seat and tag empty, and the
  warning stays. `ccp mutate` drops each mutated file's `__pycache__` entries after applying the mutant, before
  its test runs. `tests/test_tasks_close.py` has its `__main__` guard back and, run as a script, puts the
  checkout's root on `sys.path` (importing `tests` first, for the fence): without it `python3
  tests/test_tasks_close.py` cannot import `ccp`. The catch-up's env tests live in
  `tests/test_behind_tip_catch_up.py` (not in `paths`), where one test pinned `impl-0002`/`impl` and had to change.

## Verification notes
