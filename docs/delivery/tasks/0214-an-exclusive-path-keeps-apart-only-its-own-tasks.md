---
task_id: 0214-an-exclusive-path-keeps-apart-only-its-own-tasks
title: An exclusive path keeps apart only the tasks that meet the same entry
status: pending
kind: feature
depends_on: []
spec_refs: ["S16", "S26"]
review_point: R15
paths: ["ccp/parallel.py", "ccp/forecast.py", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "tests/test_parallel_claims.py", "tests/test_clashes_with.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0214-an-exclusive-path-keeps-apart-only-its-own-tasks

## Intent

`parallel.exclusive` names files whose concurrent edits git cannot merge safely, such as a schema or
a migration list. Today a task touching one runs alone: nothing else may start beside it, even a task
in another part of the product. So one migration task idles every other slot for its whole run.
After this task, an exclusive entry keeps apart only the tasks that both meet that same entry; a task
meeting it runs beside tasks that do not. `parallel: false` still means "runs alone".

## Context (not checked)

Measured at `1b734dd`.

- Provenance: an accepted plane proposal (triage item T11).
- **Rule 4 is whole-set.** `ccp/parallel.py` `join_refusal`: for every task in `[cand, *active]`
  not `parallel: true`, any path meeting any `exclusive` entry refuses ("it runs alone (rule 4)",
  `git grep -n '(rule 4)' -- ccp/parallel.py` at `1b734dd`: one line). `runs_alone` counts a path
  meeting an exclusive entry as running alone, and the forecast gives such a task every slot
  (`git grep -n 'parallel.runs_alone' -- ccp` at `1b734dd`: one line, `ccp/forecast.py`).
- **The pairwise predicate already exists.** `kept_apart(cfg, a, b)` is, in its docstring's words,
  the one pairwise predicate that the clash rule and `next`'s passed-over walk both ask, and the
  forecast's `apart` pairs come from it (`git grep -n 'kept_apart(' -- ccp` at `1b734dd`: the
  definition, two calls in `parallel.py` and one in `forecast.py`). `join_refusal(..., rule3=False)` is how `next` asks whether only rule 3 keeps a
  task out, so a task kept out by a pairwise rule is passed over, not the end of the walk.
- **`meets(p, x)`** is the path test rule 4 already uses (equal, a directory holding the other, or a
  glob or bare name matching it).
- **ADR-0043 D2** makes parallel the default; nothing in it asks that an exclusive path stop every
  slot.
- `tests/test_parallel_claims.py` holds the claim-rule tests
  (`python3 -B -m unittest tests.test_parallel_claims` at `1b734dd`: 24 tests, OK). Its
  `test_exclusive_no_path_and_parallel_false_run_alone` asserts that a task beside an exclusive one
  is refused, and `test_meeting_paths_are_refused_and_a_task_that_runs_alone_holds_the_line` that an
  exclusive task holds the line; both change with this task.
- **`tests/test_clashes_with.py`** asserts the whole-set rule too:
  `Claims.test_a_task_with_no_path_still_runs_alone_and_exclusive_paths_still_apply` claims a task on
  `src/app/views.py` (exclusive) beside an in-flight task on `src/app/pool.py` and expects a refusal
  naming the exclusive rule; under the pairwise rule that claim succeeds, so the test changes
  (`python3 -B -m unittest tests.test_clashes_with` at `1b734dd`: OK).
- No R14 task edits `ccp/parallel.py` or these passages. Task 0202 edits §26.4's **Output** bullet,
  not the **Throughput** bullet below.

## Scope

- **In:** `ccp/parallel.py`, `ccp/forecast.py`, `docs/spec/02-delivery.md`,
  `docs/spec/04-observability.md`, `tests/test_parallel_claims.py`, `tests/test_clashes_with.py`.
- **`kept_apart`** first asks rule 4: when neither task says `parallel: true` and some path of `a`
  and some path of `b` both meet the same `exclusive` entry `x`, it returns
  `Apart("exclusive", <a's path>, <b's path>)` (the entry in the message), under either
  `parallel.schedule`. Otherwise it asks rule 3 as today.
- **`join_refusal`.** The whole-set rule 4 loop is removed. The pairwise loop over `active` reports
  an `exclusive` apart as "`<cand>`'s `<path>` and in-flight `<task>`'s `<path>` both meet the
  exclusive `<x>` (parallel.exclusive, rule 4)". The `rule3` flag becomes `pairwise` and skips rules 3
  and 4 together, so `next` passes over a task that either keeps out and names why.
- **`runs_alone`** keeps rule 2 only (`parallel: false`; no path and no `parallel: true`). The
  forecast's `alone` set therefore no longer holds exclusive tasks, and its `apart` pairs, built from
  `kept_apart`, hold the exclusive pairs.
- The module docstring of `ccp/parallel.py` says rule 4 is pairwise.
- **Tests** in `tests/test_parallel_claims.py`:
  - with 0005 (`db/schema.sql`) in flight, 0003 (`src/app/views.py`) is claimed beside it;
  - a second task meeting `db/schema.sql` is refused with the rule 4 message, and `ccp tasks next`
    passes over it and offers a later task that meets no exclusive entry;
  - `parallel: false` and a task with no path still run alone;
  - a forecast with two tasks meeting the same exclusive entry and one that does not runs the third
    beside the first (`apart_pairs` 1, no task in `alone`).
- **`tests/test_clashes_with.py`**: `test_a_task_with_no_path_still_runs_alone_and_exclusive_paths_still_apply`
  is rewritten so both tasks meet the entry: in-flight 0002 is given `src/app/views.py` too, and 0003's
  claim is still refused with "rule 4"; its no-path half is unchanged.

### SPEC changes (signed in the brief, §31)

**a. §16.3 rule 4.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> 4. No path of C or of a task in A meets an `exclusive` entry.

PROPOSED:
> 4. No task in A meets an `exclusive` entry that C also meets: a path of each meeting the same entry
>    (a task that says `parallel: true` meets none). A task meeting an exclusive entry runs beside
>    tasks that do not.

**b. §16.3, `ccp tasks next`'s walk.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> **`ccp tasks next`** ranks as before (§10.3), then walks the ready tasks not in A in that order and returns the first that could be claimed beside A and that rule 3 would not keep from joining any task it passed over; it passes over, naming each, a task that rule 3 alone keeps from joining A and a task that rule 3 would keep from joining one it passed over; a task that any other rule keeps from joining A ends the walk with none (head of line: no task waits forever behind smaller ones, and a task passed over waits only for the in-flight tasks rule 3 keeps it from: those its paths meet, or under `clashes` those it clashes with).

PROPOSED:
> **`ccp tasks next`** ranks as before (§10.3), then walks the ready tasks not in A in that order and returns the first that could be claimed beside A and that rules 3 and 4 would not keep from joining any task it passed over; it passes over, naming each, a task that rules 3 and 4 alone keep from joining A and a task that they would keep from joining one it passed over; a task that any other rule keeps from joining A ends the walk with none (head of line: no task waits forever behind smaller ones, and a task passed over waits only for the in-flight tasks rules 3 and 4 keep it from: those its paths meet, or under `clashes` those it clashes with, and those meeting an exclusive entry it meets).

**c. §16.1, the last paragraph's schedule sentence.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> Under `parallel.schedule: clashes`, the default, the writer's `clashes_with` decides what to start together, and paths still decide what `parallel.exclusive` keeps alone (§16.3); under `paths`, declared paths decide.

PROPOSED:
> Under `parallel.schedule: clashes`, the default, the writer's `clashes_with` decides what to start together, and paths still decide which tasks `parallel.exclusive` keeps apart (§16.3 rule 4); under `paths`, declared paths decide.

**d. §16.7, Forecast.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> one without paths and without `parallel: true`, or touching an exclusive path, takes
>   every slot;

PROPOSED:
> one without paths and without `parallel: true`, or saying `parallel: false`, takes
>   every slot, and one touching an exclusive entry starts after each task ahead of it that touches
>   the same entry (rule 4);

**e. §26.4, Throughput.**

CURRENT (`docs/spec/04-observability.md` at `8aefa59`):
> a task without
>   paths and without `parallel: true`, or touching an exclusive path, takes every slot.

PROPOSED:
> a task without
>   paths and without `parallel: true`, or saying `parallel: false`, takes every slot, and a task
>   touching an exclusive entry also waits for each task ahead of it touching the same entry (§16.3
>   rule 4).

- **Out:** `parallel.shared`, rule 3, `parallel: false`, and close's merge (§16.5).

## dod_checks

- id: `ex-01`
  story: As a lead, a migration task no longer idles every other slot.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_parallel_claims 2>&1 | tail -35`.
  expect: exit 0, with the Scope's four tests listed `ok`.
  dry run (`1b734dd`): 24 tests, OK; the new tests do not exist yet.

- id: `ex-02`
  story: As a plane developer, the pairwise rule is tested and the tests bite.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `runs_alone` again returns true for a path meeting an exclusive entry.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_parallel_claims`.
  expect: at least one failure (the forecast test).
  dry run: n/a — the tests are new.

- id: `ex-03`
  story: As the plane, no whole-set exclusive rule is left.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'it runs alone (rule 4)' -- ccp/parallel.py`.
    2. Run `git grep -n 'both meet the exclusive' -- ccp/parallel.py`.
  expect: step 1 prints nothing; step 2 prints one line.
  dry run (`1b734dd`): step 1 prints one line (`join_refusal`); step 2 prints nothing.

- id: `ex-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0214 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`1b734dd`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
