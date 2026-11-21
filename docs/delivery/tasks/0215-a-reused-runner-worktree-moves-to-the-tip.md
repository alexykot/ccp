---
task_id: 0215-a-reused-runner-worktree-moves-to-the-tip
title: A reused runner worktree that holds no task is brought to the integration tip
status: done
kind: feature
depends_on: []
spec_refs: ["S12", "S16"]
review_point: R15
paths: ["ccp/wt.py", "ccp/lifecycle.py", "scripts/observability/team.py", "docs/spec/02-delivery.md", "tests/test_wt.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0215-a-reused-runner-worktree-moves-to-the-tip

## Intent

A runner's worktree is made detached at the integration tip, but one that already exists is left
where it is. A fresh runner spawned days later therefore starts in a worktree many merges behind,
and its first operator step or merge reads stale files until something moves it. After this task, a
spawn or `ccp tasks worktree` that finds the worktree existing and holding nothing of a task (detached,
with nothing to commit) fetches and moves it to `origin/<integration>`; one that holds changes or a
branch is still left alone, with a warning saying why.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: an accepted plane proposal (triage item T13).
- **An existing one is left alone.** `ccp/wt.py` `def runner_worktree(main, path, integ)` returns
  `(wt, False)` at once when `wt` is a working tree ("left alone when it exists",
  `git grep -n 'left alone when it exists' -- ccp/wt.py` at `1b734dd`: one line). Its two callers are
  `lifecycle.runner_worktree` (`ccp tasks worktree [--runner <slot>]`) and
  `scripts/observability/team.py` `single_runner_worktree` (the single runner's spawn)
  (`git grep -n 'wt.runner_worktree(' -- ccp scripts` at `1b734dd`: those two calls;
  `lib.runner_worktree` only derives the path).
- **The tests pin the old rule.** `tests/test_wt.py` `SingleRunnerWorktree`:
  `test_the_spawn_makes_it_at_the_tip_and_a_respawn_leaves_it_alone` and
  `test_tasks_worktree_without_a_slot_makes_the_one_runners` assert the worktree stays at the old tip
  after the tip advances (at `1b734dd`,
  `python3 -B -m unittest tests.test_wt.SingleRunnerWorktree`: 4 tests, OK).
- **What a runner worktree may hold.** It is detached (§12.1: "the main checkout holds the branch"),
  and `ccp tasks close` refuses to run from one with changes
  (`tests/test_toolkit.py` `test_close_refuses_a_dirty_runner_worktree`). A worktree on a branch, or
  with a tracked change or an untracked file, holds something a person or a step left there; moving
  it could lose that.
- Close already moves a detached runner worktree to the reconcile commit it pushed, so moving a clean
  one to the tip changes nothing a task depends on.
- No R14 task edits this passage. Task 0198 adds a bullet to §12.1 after the `merge-<nnnn>` bullet,
  in the worktree-kinds list, not in the "The lead and the runners" paragraph below.

## Scope

- **In:** `ccp/wt.py`, `ccp/lifecycle.py`, `scripts/observability/team.py`,
  `docs/spec/02-delivery.md`, `tests/test_wt.py`.
- **`wt.runner_worktree`** returns `(path, made, moved, kept)`. For an existing working tree:
  - **holds no task** when `git symbolic-ref -q HEAD` fails (detached) and `git status --porcelain`
    prints nothing (no change, no untracked file): it runs `git fetch -q origin` in the main checkout
    and `git checkout -q --detach origin/<integ>` in the worktree, returning `moved` true (false when
    it was already there);
  - otherwise it is left as it is, `kept` naming why (`on branch <b>`, or `has changes`);
  - a fetch or checkout that fails is `kept` with the git error's first line, never a refusal.
- **The callers** add `moved` and, when set, `kept` to what they print: `ccp tasks worktree`'s JSON
  (and, when `kept` is set, a `warning: runner worktree <path> left as it is: <why>` line on stderr),
  and the spawn's `runner_worktree` (whose `kept` also becomes a warning in the spawn's `warnings`).
- **A spawn dry run** (`team.sh runner spawn --dry-run`) neither fetches nor moves the worktree: it
  makes no change, as today.
- **Tests** in `tests/test_wt.py` `SingleRunnerWorktree`:
  - the respawn and the second `ccp tasks worktree` after the tip advances leave the worktree at the
    new tip, `moved: true`;
  - a worktree with an untracked file, and one on a branch, stay where they were, `kept` naming why,
    and the spawn and `ccp tasks worktree` (on stderr) warn;
  - a spawn dry run after the tip advances leaves the worktree where it was.

### SPEC changes (signed in the brief, §31)

**a. §12.1, the runner worktree.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> detached at `origin/<integration_branch>` (the
> main checkout holds the branch). An existing one is left alone; one the spawn cannot make is a
> warning,

PROPOSED:
> detached at `origin/<integration_branch>` (the
> main checkout holds the branch). An existing one that holds no task (detached, with nothing to
> commit and no untracked file) is fetched and moved to `origin/<integration_branch>` by the same
> spawn or `ccp tasks worktree`; one on a branch or with changes is left as it is, with a warning
> naming why; one the spawn cannot make is a
> warning,

- **Out:** the slots' worktree paths, close's move to the reconcile, and a worktree that is not a
  working tree (still refused or warned about as today).

## dod_checks

- id: `rw-01`
  story: As a lead, a runner spawned after merges starts at the tip.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_wt.SingleRunnerWorktree 2>&1 | tail -15`.
  expect: exit 0, with the Scope's tests listed `ok`: the moved worktree at the new tip, and the
    untracked-file and on-branch worktrees kept.
  dry run (`1b734dd`): 4 tests, OK; the new tests do not exist yet.

- id: `rw-02`
  story: As a plane developer, the move is tested and the tests bite.
  setup: a checkout of the PR head; then two copies (`git worktree add --detach <tmp> HEAD`): in copy
    A, `runner_worktree` returns an existing worktree at once again; in copy B the `git status
    --porcelain` condition is removed.
  steps:
    1. In copy A, run `python3 -B -m unittest -q tests.test_wt.SingleRunnerWorktree`.
    2. In copy B, run the same.
  expect: each step has at least one failure.
  dry run: n/a — the tests are new.

- id: `rw-03`
  story: As the plane, the old "left alone" rule is gone from the code.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -e 'left alone when it exists' -e 'existing one is left alone' -e 'leaves it alone' -- ccp/wt.py scripts/observability/team.py`.
  expect: prints nothing.
  dry run (`1b734dd`): prints three lines, `ccp/wt.py` (`runner_worktree`'s docstring) and
    `scripts/observability/team.py` (`single_runner_worktree`'s docstring, twice).

- id: `rw-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0215 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`1b734dd`): exit 1, the passage not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `ccp/wt.py`: `runner_worktree` returns `(path, made, moved, kept)`. For an existing working tree,
  `_runner_to_tip` reads `git symbolic-ref -q HEAD` and `git status --porcelain` in the worktree; the
  pure `runner_worktree_holds(branch, porcelain)` decides `on branch <b>` / `has changes` / nothing
  (E15). A worktree that holds no task gets `git fetch -q origin` in the main checkout and
  `git checkout -q --detach origin/<integ>`; `moved` compares HEAD before and after. A status, fetch or
  checkout that fails is `kept` with the git error's first line, never a refusal. `kept_warning`
  holds the one warning text both callers print.
- `ccp tasks worktree` adds `moved` to its JSON, and `kept` plus a `warnings` entry when set (the
  toolkit wrapper prints it on stderr as `warning: runner worktree <path> left as it is: <why>`).
- The spawn's `runner_worktree` adds `moved`, and `kept` when set, which also goes into the spawn's
  `warnings`. The dry run never calls `single_runner_worktree`, so it moves nothing, as before.
- Narrowest choice: the spawn's `error` dict (a path that is no working tree) is unchanged, with no
  `moved`: nothing ran on it.
- Fix round 1 (review): `advance_tip` now puts the main checkout's `origin/main` back to the old tip
  after the push, so the tip advances on origin only, as a forge merge does, and only the fetch
  brings it in (a fetch that updates no ref used to pass). The failed fetch/checkout test asserts
  that `kept` is git's own error: it names `origin/no-such-branch`, or the missing `no-such-origin`.

## Verification notes
- 2026-11-21 — verifier, PR #266 head `dec59c6` (squash `6b7d5f1`): APPROVE. Passed: rw-01, rw-02, rw-03, rw-04, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0215-a-reused-runner-worktree-moves-to-the-tip.json.

