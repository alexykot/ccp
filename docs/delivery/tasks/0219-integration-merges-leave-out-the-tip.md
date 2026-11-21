---
task_id: 0219-integration-merges-leave-out-the-tip
title: A round's recorded integration merges leave out every commit already on the integration tip
status: pending
kind: feature
depends_on: []
spec_refs: ["S11", "S27"]
review_point: R15
paths: ["ccp/report.py", "docs/spec/02-delivery.md", "tests/test_health_conflicts.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0219-integration-merges-leave-out-the-tip

## Intent

Each done change round records the integration merges it made (`integration_merges`), and health
counts the conflicted ones as conflict catch-ups. The range it reads runs from the previous round's
head to this one, so when a task branch has been rebuilt on a newer integration tip, the tip's own
merge commits (other tasks' merges, a reconcile) fall inside the range and are counted as this task's
catch-ups. After this task, the range leaves out every commit already on `origin/<integration>`, so a
round records only the merges its own branch made.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: an accepted plane proposal, moved out of R14's task 0203 because it redefines the
  recorded `integration_merges` of §11.1 (`grep -n 'integration_merges' docs/delivery/tasks/0203-*.md`
  at `1b734dd`: one line, its Context's note).
- **The range.** `ccp/report.py` `round_merges`: `queue.git(repo, "rev-list", "--merges",
  "--first-parent", "--topo-order", "--reverse", f"{base}..{tip}")`
  (`git grep -n 'f"{base}..{tip}"' -- ccp/report.py` at `1b734dd`: one line). `base` is the previous
  done change round's head, else `origin/<integration>`; `integ`, the tip's sha, is already resolved
  in the function. A merge is kept when its second parent is an ancestor of `integ`, which a tip's own
  merge commit also satisfies.
- **Who reads it.** `health.conflict_catch_ups` reads each run's `integration_merges`
  (`git grep -n 'integration_merges' -- ccp/health.py` at `1b734dd`: its docstring and the read), and
  §27.1's **Conflict catch-ups** bullet reports them. Runs already recorded keep their lists; only
  rounds reported after this task use the new range.
- The proposal's other point, health's `--since` window, is fixed already: `health` passes its window
  to `conflict_catch_ups` (`git grep -n 'conflict_catch_ups(q, window)' -- ccp/health.py` at
  `1b734dd`: one line).
- `tests/test_health_conflicts.py` holds the measure's tests
  (`python3 -B -m unittest tests.test_health_conflicts` at `1b734dd`: 13 tests, OK), among them
  `test_a_merge_inside_the_tip_is_not_the_rounds_own`, whose branch merges a tip holding another
  branch's merge.
- No R14 task changes `round_merges`: task 0203 edits `ccp/report.py`'s `resolution_lines`.

## Scope

- **In:** `ccp/report.py`, `docs/spec/02-delivery.md`, `tests/test_health_conflicts.py`.
- **The range** becomes `rev-list --merges --first-parent --topo-order --reverse <base>..<tip>
  ^<integ>`: the same walk, with every commit reachable from `origin/<integration>` left out. The
  second-parent condition and everything else in `round_merges` is unchanged. The docstring says so.
- **Tests** in `tests/test_health_conflicts.py`:
  - a task branch rebuilt on a tip whose first-parent line holds a `--no-ff` merge of another branch,
    then given one catch-up merge of its own: the round records only its own merge's sha;
  - the existing tests still pass unchanged.

### SPEC changes (signed in the brief, §31)

**a. §11.1, `integration_merges`.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> `ccp report` computes them when the round reports, never from the report's prose: `integration_merges` lists,
>   oldest first, the merge commits on the head's first-parent line, from the task's previous done change round's
>   reported head (for its first, from `origin/<integration>`) to this head, whose second parent is an ancestor of
>   `origin/<integration>`,

PROPOSED:
> `ccp report` computes them when the round reports, never from the report's prose: `integration_merges` lists,
>   oldest first, the merge commits on the head's first-parent line, from the task's previous done change round's
>   reported head (for its first, from `origin/<integration>`) to this head, leaving out every commit already on
>   `origin/<integration>` (a branch rebuilt on a newer tip does not count the tip's own merges), whose second
>   parent is an ancestor of `origin/<integration>`,

- **Out:** re-measuring rounds already recorded, the conflict probe, and health's report.

## dod_checks

- id: `im-01`
  story: As a lead reading conflict catch-ups, a task counts only its own merges.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_health_conflicts 2>&1 | tail -20`.
  expect: exit 0, 14 or more tests, the Scope's rebuilt-branch test listed `ok`.
  dry run (`1b734dd`): 13 tests, OK; the new test does not exist yet.

- id: `im-02`
  story: As a plane developer, the new test bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    `^<integ>` exclusion is removed from the `rev-list` call.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_health_conflicts`.
  expect: at least one failure (the rebuilt-branch test).
  dry run: n/a — the test is new.

- id: `im-03`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0219 --base origin/main`.
  expect: exit 0, the passage found.
  dry run (`1b734dd`): exit 1, the passage not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
