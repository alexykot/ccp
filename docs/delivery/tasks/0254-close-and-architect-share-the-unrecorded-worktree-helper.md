---
task_id: 0254-close-and-architect-share-the-unrecorded-worktree-helper
title: Close, the architect and tasks dry-run make and remove their own worktrees through one wt helper, and wt list shows a leftover arch- worktree
status: pending
kind: feature
depends_on: ["0215-a-reused-runner-worktree-moves-to-the-tip"]
clashes_with: ["0240-plane-workers-run-the-head"]
spec_refs: ["S12", "S19"]
review_refs: ["ar-20261121T020523Z-1d5f#F05", "ar-20261121T174754Z-7df5#F06"]
review_point: R17
paths: ["ccp/wt.py", "ccp/architect.py", "ccp/lifecycle.py", "ccp/dryrun.py", "tests/test_wt_unrecorded.py", "tests/test_wt_outside.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0254-close-and-architect-share-the-unrecorded-worktree-helper

## Intent

The plane's two unrecorded worktree kinds, close's `merge-<nnnn>` and an architect pass's
`arch-<review id>`, and `ccp tasks dry-run`'s temporary checkout are made and removed through one
public helper in `ccp/wt.py`, so none reaches into wt's private functions, and `ccp wt list` shows an `arch-` worktree a failed removal
left behind, as §12.1 says it shows any unrecorded worktree.

## Context (not checked)

From architect pass `ar-20261121T020523Z-1d5f`, finding F05, triaged by the lead on 2026-11-21.
Measured at `aaa81b2`. `depends_on` 0215 because it changes `ccp/wt.py`'s runner worktree and its
callers in `ccp/lifecycle.py`, next to the code this task moves.

- **The hand-made worktrees.** `git grep -nE 'wt\._(link|exclude_base)\(' -- ccp` at
  `aaa81b2`: 3 lines (`ccp/architect.py` `"def _make_worktree"` 2, `ccp/lifecycle.py` 1, close's merge
  worktree). `git grep -n '"worktree", "add"' -- ccp/architect.py ccp/lifecycle.py` at `aaa81b2`:
  2 lines. `ccp/architect.py` `"def _drop_worktree"` removes with `--force` and prunes, ignoring
  failures.
- **Listing.** `ccp/wt.py` lists, among unrecorded directories, only those matching `MERGE_RE`
  (`grep -c 'MERGE_RE.match' ccp/wt.py` at `aaa81b2`: 2, one in listing, one in `gc`). SPEC §12.1:
  "`ccp wt list [--task ID]` shows the records and any unrecorded worktree" (`grep -c 'any unrecorded worktree' docs/spec/02-delivery.md` at `aaa81b2`: 1).
- **Ruling.** `ccp/wt.py` gains a public `def link(cfg, main, path)` (today's `_link`: links `worktrees.links` into `path`), `def add_unrecorded(cfg, main, path, rev)` (names the worktree base in
  `info/exclude`, `git worktree add -q --detach`, then `link`; a git error raises
  `QueueError` naming the path) and `def remove_unrecorded(main, path)` (`worktree remove --force`,
  then `prune`; failures ignored, as `_drop_worktree` does today). Close's merge worktree keeps its own
  reuse of an existing worktree (reset and clean), then calls `link`, as it calls `wt._link` today;
  it calls `add_unrecorded` only to make a new one.
  An `ARCH_RE` beside `MERGE_RE` (`^arch-` followed by the review id) makes `ccp wt list` show an `arch-`
  directory as unrecorded, with no task. `ccp wt gc` and `ccp wt remove` are unchanged: the pass's own
  check that marks a dead pass `failed` removes its worktree (§12.1).
- **Tasks dry-run, the third site** (architect pass `ar-20261121T174754Z-7df5`, F06, folded in by
  its triage). 0244 added `ccp/dryrun.py`, whose `"def main"` runs `git worktree add -q --detach`
  itself, calls `wt._link` and removes the tree with `worktree remove --force` and `prune`.
  `git grep -nE 'wt\._[a-z_]+\(|"worktree", "(add|remove)"' -- ccp/dryrun.py` at `31357f0`: 3 lines.
  Ruling: the dry run makes its tree with `wt.add_unrecorded` and removes it with
  `wt.remove_unrecorded`; its tree stays in its own temp directory (it is not an `arch-` or `merge-`
  worktree, so `ccp wt list` does not show it), and the temp directory is still removed after.
- **A follow-up of 0227** (the lead's log): `tests/test_wt_outside.py`'s close test asserts
  `set(made)`, so a second checkout at the same path, or one fewer, passes unseen.
  `git grep -n 'set(made)' -- tests/test_wt_outside.py` at `31357f0`: 1 line. Ruling: it asserts the
  exact list `made` holds, order and repeats included, as the code builds it at this task's head.
- **Not here:** the local PR adapter's own merge tree (`ccp/prhost.py` `"def _merge_tree"`) stays the
  adapter's (E19).
- **No SPEC change:** §12.1 already says list shows any unrecorded worktree, and both bullets for the
  two kinds stay true. `ccp/suite.py`'s prover checkout (a temp directory outside the worktree
  directory) is not one of these kinds.

## Scope

- **In:** `ccp/wt.py` (`link`, `add_unrecorded`, `remove_unrecorded`, `ARCH_RE` in listing),
  `ccp/architect.py` (`_make_worktree`, `_drop_worktree` call them), `ccp/lifecycle.py` (close's merge
  worktree), `ccp/dryrun.py` (its temporary tree), `tests/test_wt_unrecorded.py` (new),
  `tests/test_wt_outside.py` (the exact list).
- **Out:** `ccp wt gc` sweeping `arch-` leftovers; recording either kind; `ccp/suite.py`'s prover
  checkout; `ccp/prhost.py`'s local merge tree.

## dod_checks

- id: `wt-01`
  story: As a plane developer, no module outside wt calls its private worktree helpers or adds a worktree for close or the architect itself.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE 'wt\._(link|exclude_base)\(' -- ccp`.
    2. Run `git grep -n '"worktree", "add"' -- ccp/architect.py ccp/lifecycle.py`.
  expect: both print nothing.
  dry run (`aaa81b2`): step 1 printed 3 lines; step 2 printed 2 lines.
- id: `wt-02`
  story: As an operator, `ccp wt list` shows an architect worktree left behind, and the test bites.
  setup: a checkout of the PR head; then a separate copy of it with `ARCH_RE`'s match removed from `ccp/wt.py`'s listing.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_wt_unrecorded`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_wt_unrecorded`.
  expect: step 1 exits 0, with a test that makes an `arch-<id>` worktree through `wt.add_unrecorded` in a fenced product and finds it among the unrecorded worktrees `ccp wt list` prints; step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `wt-03`
  story: As a plane developer, close's merge worktree and the architect's pass worktree behave as before.
  setup: a checkout of the PR head; then a separate copy of it where `wt.add_unrecorded` skips linking `worktrees.links`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_architect tests.test_tasks_close tests.test_wt tests.test_wt_outside`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_wt_unrecorded tests.test_architect tests.test_tasks_close`.
  expect: step 1 exits 0; step 2 exits non-zero.
  dry run (`aaa81b2`): step 1 exited 0 (`OK`, 155 s); step 2 n/a, the helper is new.
- id: `wt-04`
  story: As a plane developer, tasks dry-run makes its checkout through the same helper, and the close test pins the exact checkouts it made.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE 'wt\._[a-z_]+\(|"worktree", "(add|remove)"' -- ccp/dryrun.py`.
    2. Run `git grep -n 'set(made)' -- tests/test_wt_outside.py`.
    3. Run `python3 -B -m unittest -q tests.test_tasks_dry_run tests.test_wt_outside`.
  expect: steps 1 and 2 print nothing; step 3 exits 0.
  dry run (`31357f0`): step 1 printed 3 lines (`ccp/dryrun.py:162`, `:165`, `:171`); step 2 printed 1 line (`tests/test_wt_outside.py:132`); step 3 exited 0 (`OK`).

## Implementation notes

## Verification notes
