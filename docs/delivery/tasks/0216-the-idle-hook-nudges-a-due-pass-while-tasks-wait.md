---
task_id: 0216-the-idle-hook-nudges-a-due-pass-while-tasks-wait
title: The runner-idle hook nudges a due architect pass while the runner holds only waiting tasks
status: pending
kind: feature
depends_on: []
spec_refs: ["S18", "S19"]
review_point: R15
paths: ["plugin/hooks/runner-idle.sh", "docs/spec/02-delivery.md", "tests/test_team_hosting.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0216-the-idle-hook-nudges-a-due-pass-while-tasks-wait

## Intent

When every task a runner holds waits on someone (a gate, the operator), the runner goes
idle, which is right for task work. But an architect pass that is due is work the runner can do in
that time, and the idle hook never tells it so: it asks `ccp tasks next` only when some task is
ready. The pass then waits until a task moves again. After this task, the idle hook, finding the
runner holding only waiting tasks with the architect seat adopted, asks `ccp tasks next` all the same,
and when a pass is due it keeps the runner working on the pass.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: an accepted plane proposal, cut from R10 because it changes a § rule (triage item T17).
- **`next` is asked only with something ready.** `plugin/hooks/runner-idle.sh`:
  `if ready and (parallel_on or has_architect):` runs `ccp tasks next --scope … --json`
  (`git grep -n 'if ready and (parallel_on or has_architect)' -- plugin/hooks/runner-idle.sh` at
  `1b734dd`: one line). With `ready` empty, `n` stays None, so the later
  `if n is not None and has_architect and n.returncode == 4:` never sees a due pass.
- **One runner holding tasks.** Without slots and with parallel off, a runner holding an in-flight task
  that is open is ready only for that task: `ready = [t for t in ready if t in holding]`. With slots
  (`SLOT`), `mine` is the slot's own tasks, kept only when ready and no worker runs. So a runner
  whose held tasks all wait ends with `ready` empty in each mode.
- **What `next` answers.** With nothing ready and a pass due, `ccp tasks next` exits 4 at once with an
  `architect` block of `kind: pass` (§19.6: "`next` would name no task at all and a pass is due: a due
  pass then blocks at once"). With a triage overdue it gives `kind: triage`, and the hook lets the
  runner idle, as today.
- **The block message** for a due pass is already there: `"{architect_due}. Run `bin/ccp architect run
  --detach` (SPEC §19.6), then `ccp tasks next` and carry on with {ready[0]}."`, `ready` being
  `["the architect pass"]` when nothing else is ready.
- §18.2 lists when the hook exits 2 and does not mention the architect; §19.6 says only that the hook
  lets the runner idle while `next` is blocked on a triage.
- `tests/test_team_hosting.py` `TestIdleHook` runs the hook on a temp product
  (`python3 -B -m unittest tests.test_team_hosting` at `1b734dd`: 46 tests, OK). One test drives the
  hook's architect branch, `test_architect_triage_block_waits_on_the_lead`, with a ready task and an
  `architect.json` whose report awaits triage (`grep -n 'def test_architect' tests/test_team_hosting.py`
  at `1b734dd`: one line); none drives a due pass.
- No R14 task edits the hook or §18.2.

## Scope

- **In:** `plugin/hooks/runner-idle.sh`, `docs/spec/02-delivery.md`, `tests/test_team_hosting.py`.
- **The hook.** After its ready set is computed (and the slot or holding filter applied), when `ready`
  is empty, the architect seat is adopted (`has_architect`), and the runner (its slot, with slots)
  holds at least one in-flight task not done or dropped, and none of its held tasks waits on `quota`
  (a pass would spend the allowance that is already out), the hook runs the same `ccp tasks next
  --scope … --json` call. Its existing exit-4 handling then applies: `kind: pass` blocks (exit 2) with
  the pass message and "the architect pass" as the work, counted toward the block limit like any
  other; `kind: triage` lets the runner idle. A runner holding nothing is unchanged (it stops at an
  empty scope, §10.2), and so is any case with something ready.
- The header comment's architect line says it also asks `next` while every held task waits.
- **Tests** in `tests/test_team_hosting.py` `TestIdleHook`, set up as
  `test_architect_triage_block_waits_on_the_lead` is (the architect adopted in plane.json, state in
  `architect.json`, done tasks merged to make the cadence due):
  - a runner holding one task waiting on `operator_step`, with a pass due: the hook exits 2 and its
    stderr holds `ccp architect run --detach`;
  - the same with a report awaiting triage past its grace instead: exit 0;
  - the same with no pass due: exit 0;
  - a runner holding nothing, with nothing ready and a pass due: exit 0;
  - a runner holding one task waiting on `quota`, with a pass due: exit 0.

### SPEC changes (signed in the brief, §31)

**a. §18.2, a bullet after the exit-2 bullet.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> its runtime `waiting_on`, an open question's `blocks`, or an undecided gate. `work.json`'s own
>   `waiting_on` is not a scope-wide stop.

PROPOSED:
> its runtime `waiting_on`, an open question's `blocks`, or an undecided gate. `work.json`'s own
>   `waiting_on` is not a scope-wide stop.
> - With the architect seat adopted (§19.11), it also exits 2 when nothing is ready but the runner
>   (its slot, with several) holds in-flight tasks that all wait, none on `quota`, and `ccp tasks
>   next` answers that a pass is due (§19.6): the runner starts the pass with `ccp architect run
>   --detach` meanwhile. A held task waiting on `quota`, or a triage overdue, lets it idle.

- **Out:** the block limit, the rotation and park rules, `ccp tasks next` itself, and a runner holding
  no task.

## dod_checks

- id: `ih-01`
  story: As a lead, a due pass runs while the runner's tasks wait.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_team_hosting.TestIdleHook 2>&1 | tail -25`.
  expect: exit 0, with the Scope's five tests listed `ok`.
  dry run (`1b734dd`): 12 tests, OK; the new tests do not exist yet.

- id: `ih-02`
  story: As a plane developer, the new branch is tested and the tests bite.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    new `ccp tasks next` call for an empty ready set is removed.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_team_hosting.TestIdleHook`.
  expect: at least one failure (the `pass` block test).
  dry run: n/a — the tests are new.

- id: `ih-03`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0216 --base origin/main`.
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
