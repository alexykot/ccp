---
task_id: 0154-worktrees-outside-repo-safety
title: Under a worktrees.dir outside the main checkout, wt create adopts and wt remove deletes an unrecorded directory only when git names it, and §12.1 says which unrecorded directories the plane touches there
status: done
kind: feature
depends_on: []
spec_refs: ["S12"]
review_point: R10
sign_off: brief
paths: ["ccp/wt.py", "docs/spec/02-delivery.md", "tests/test_wt_outside.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0154-worktrees-outside-repo-safety
## Intent

A product whose `worktrees.dir` lies outside its repository, in a directory another checkout may
share, never has the plane adopt or delete another checkout's directory. Every path that acts on a
directory with no worktree record asks git first, and the SPEC states this, so a product sharing the
directory knows which of its directories the plane may touch.

## Context (not checked)

- Task 0140 let `worktrees.dir` resolve outside the main checkout. It limited `wt.listing`,
  `remove_task`'s pre-record fallback and `gc`'s merge-worktree sweep to the directories
  `git worktree list --porcelain` names in the main checkout (`_git_named`, `_ours` in `ccp/wt.py`).
  Two paths were left out, as read at `85d388b`:
  - `create`, for a name with no record whose directory exists, adopts it
    (`"if path.is_dir():  # made before §12.1 recorded worktrees: adopt it"`) with no `_ours` test.
  - `remove`, for a name with no record, falls back to `base / name` (`"if st is None:"`) and removes it
    with `_rm_tree`, with no `_ours` test.
- Inside the main checkout `_git_named` returns None (any directory is ours), so both stay as they are
  there.
- `remove` already refuses a name with neither a record nor a directory with exit 3 (`"no worktree
  {name} recorded in"`); the new refusals use the same code.
- 0140 carried no SPEC text for the limit. §12.1's bullets on `ccp wt list`, close's fallback, gc and
  `create`'s adoption still read as acting on any matching directory. That is a rule change, carried
  below for signing.

## Scope

- **In:**
  - `ccp/wt.py` `create`: when the name has no record and its directory exists under a `worktrees.dir`
    outside the main checkout, it is adopted only when `_ours(path, _git_named(cfg, base))`. Otherwise
    it is refused with exit 3 and nothing written: "<path> exists, has no worktree record and is not
    a worktree of this repository (`git worktree list`): another checkout's? Remove it or give
    another --name".
  - `ccp/wt.py` `remove`: a name with no record whose directory exists under a `worktrees.dir`
    outside the main checkout is removed only when `_ours` holds. Otherwise it is refused with exit 3,
    nothing removed: "<path> has no worktree record and is not a worktree of this repository
    (`git worktree list`): left alone".
  - Both unchanged under a `worktrees.dir` inside the main checkout, and for a recorded worktree.
  - `docs/spec/02-delivery.md` §12.1. CURRENT (at `85d388b`): "at another head it refuses (exit 3). A default name taken meanwhile moves to the next `-<n>`." PROPOSED:
    > at another head it refuses (exit 3). A default name taken meanwhile moves to the next `-<n>`. Under a `worktrees.dir` that resolves outside the main checkout, which another checkout may share, a directory with no worktree record is listed by `ccp wt list`, removed by `ccp wt remove NAME` or by close's fallback, swept by `ccp wt gc`, or adopted by `create` only when `git worktree list --porcelain` run in the main checkout names it; `ccp wt remove NAME` and `create` refuse any other (exit 3), and the rest leave it alone. Inside the main checkout these act on any matching directory, as above.
    Replace the CURRENT line with the PROPOSED passage as one unwrapped line, so `ccp verify spec-text`
    finds it.
  - `tests/test_wt_outside.py`: the tests for this task.
- **Out:**
  - A shallow clone (`--shallow`) with no record: git does not list a clone, so outside the main
    checkout it is refused like any other unnamed directory. No change for a recorded one.
  - `runner_worktree` and close's own `merge-<nnnn>` creation, which make, never adopt.

## dod_checks

- id: `wt-01`
  story: As a product sharing a sibling worktrees directory, the plane does not adopt another checkout's directory.
  setup: the sibling fixture of `tests/test_wt_outside.py` (`worktrees.dir` `../<repo>-wt`) and a claimed task 0002 with no worktree record; under the sibling directory, a plain directory `impl-0002` holding one file, which no `git worktree list` of the product names.
  steps:
    1. Run `ccp wt create --kind impl --task 0002`.
  expect: exit 3; stderr names the path and `git worktree list`; no record `worktrees/impl-0002.json` exists; the directory and its file are unchanged.
  dry run: n/a.
- id: `wt-02`
  story: As a product sharing a sibling worktrees directory, `wt remove` leaves another checkout's directory alone.
  setup: the fixture of wt-01, with a plain directory `rev-0002` under the sibling directory and no record for it.
  steps:
    1. Run `ccp wt remove rev-0002`.
  expect: exit 3; the directory and its file still exist.
  dry run: n/a.
- id: `wt-03`
  story: As a product, a worktree git names is still adopted and removed without a record.
  setup: the sibling fixture with two git worktrees made by `git worktree add` in the main checkout under the sibling directory, `impl-0002` (on `task/0002-second`) and `rev-0002` (detached), neither with a record.
  steps:
    1. Run `ccp wt create --kind impl --task 0002`, then `ccp wt remove rev-0002`.
  expect: step 1 exits 0 with `adopted: true` and a record; step 2 exits 0 and `rev-0002` is gone.
  dry run: n/a.
- id: `wt-04`
  story: As a product whose worktrees are inside its checkout, nothing changes.
  setup: a scratch product with `worktrees.dir` `.rt` and a plain directory `.rt/impl-0002` with no record, then a plain `.rt/rev-0002` with no record.
  steps:
    1. Run `ccp wt create --kind impl --task 0002`, then `ccp wt remove rev-0002`.
  expect: step 1 adopts `impl-0002` (exit 0, `adopted: true`); step 2 exits 0 and removes `rev-0002`.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Run `ccp verify spec-text 0154-worktrees-outside-repo-safety`, and compare the §12.1 edit with the PROPOSED text above.
  expect: exit 0, the edit matches word for word, and no other § rule changes.
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

- 2026-11-18 (implementer): `create` checks `_ours(path, _git_named(cfg, base))` at the top of its
  adoption branch, before `_same_head` and `_same_depth`, so a refusal writes no record; `remove`
  checks it in the no-record fallback, before any hook or `_rm_tree`. Both use exit 3 and the
  task's wording. The `create` check applies only when the name has no record, as the Scope says:
  a recorded name whose recorded path is gone still adopts its directory, as before (tested).
- wt-04 as written does not hold at the base, inside the main checkout or out: `remove` of a plain
  unrecorded directory runs `git worktree remove --force` on it, which git refuses, so `wt remove`
  exits 0 with a warning and the directory stays. The inside path is unchanged by this task, so
  wt-04's test makes `.rt/rev-0002` a detached git worktree (removed, exit 0) and keeps
  `.rt/impl-0002` a plain directory for the adoption half. Raised with the runner.
- Beyond the checks: a `Shared` test that `wt remove` refuses another repository's clone (which
  `_rm_tree` would have deleted outright) and its worktree under a shared absolute `worktrees.dir`.

## Verification notes
- 2026-11-18 — verifier, PR #175 head `84d831f` (squash `ceb09d7`): APPROVE. Passed: wt-01, wt-02, wt-03, wt-04, check-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0154-worktrees-outside-repo-safety.json.

