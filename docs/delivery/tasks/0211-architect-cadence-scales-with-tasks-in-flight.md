---
task_id: 0211-architect-cadence-scales-with-tasks-in-flight
title: The architect's cadence scales with tasks in flight, and a budget breach a pending task already fixes makes no pass due
status: pending
kind: feature
depends_on: []
spec_refs: ["S19", "S20"]
review_point: R15
paths: ["ccp/architect.py", "docs/spec/03-quality.md", "tests/test_architect_default_on.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0211-architect-cadence-scales-with-tasks-in-flight

## Intent

The architect's cadence counts merges, so a product running three tasks at once owes a pass three
times as often in wall time as one running a task at a time, for the same amount of change per task.
A budget breach also keeps making a pass due after the lead has already written the task that fixes
it, so the pass only finds what is already tasked. After this task, the cadence's merge count is
multiplied by the number of tasks the product runs at once, and a breached budget whose id a pending
task cites in `rule_refs` makes no pass due.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: two accepted plane proposals (triage item T5).
- **The cadence counts merges.** `ccp/architect.py` `due_info`: `elif since >= a["every_n_tasks"]:`
  (`git grep -n 'every_n_tasks"\]' -- ccp/architect.py` at `1b734dd`: two lines, the comparison and
  the reason's due count), and the not-due reason prints `{since} of {a['every_n_tasks']} tasks done`.
  `every_n_tasks` defaults to 4 (`git grep -n '"every_n_tasks": 4' -- ccp/config.py` at `1b734dd`).
- **Tasks in flight.** `parallel.settings(cfg)["max_in_flight"]` is the product's slot count,
  default 3 (`git grep -n '"max_in_flight": 3' -- ccp/config.py` at `1b734dd`), and
  `parallel.enabled(cfg)` is true when it is above one. The forecast already reads them so
  (`git grep -n 'parallel.enabled(cfg) else 1' -- ccp/forecast.py` at `1b734dd`: one line).
- **Budgets.** `new_budgets = [b for b in budgets if b.split(":", 1)[0] not in known]`
  (`git grep -n 'new_budgets = ' -- ccp/architect.py` at `1b734dd`): `known` is the ids the last pass
  saw (or the adoption baseline). A breach first seen after that pass makes a pass due, whatever the
  task log says. `rules.budget_failures` names each breach `E<n>: <path> ...`, the budget's house-rule
  id first. A task cites a house rule in `rule_refs` (`"E7"`).
- `tests/test_architect_default_on.py` holds the trigger tests (at `1b734dd`,
  `python3 -B -m unittest tests.test_architect_default_on`: 32 tests, OK). Its `test_cadence_from_the_adoption_point` merges `every_n_tasks`
  tasks on a product with the default `max_in_flight`, so it changes with this task.
- No R14 task edits these passages. Task 0198 edits `ccp/architect.py`'s pass run and §19.5, §19.7
  and §12.1; task 0204 edits §19.6's **Shape is due** paragraph. Neither changes `due_info`'s
  cadence or budget code, or the two §19.6 items below.

## Scope

- **In:** `ccp/architect.py`, `docs/spec/03-quality.md`, `tests/test_architect_default_on.py`.
- **The cadence.** `due_info` computes `cadence = every_n_tasks * slots`, where `slots` is
  `parallel.settings(cfg)["max_in_flight"]` when `parallel.enabled(cfg)`, else 1. The cadence reason
  fires when `since >= cadence`, with the due count computed from `cadence`. `info` gains
  `cadence_tasks` (that number). The not-due reason reads `{since} of {cadence} tasks done since
  {label}`. The 14-day trigger is unchanged.
- **Budgets a pending task fixes.** A breach whose id (the text before its first `:`) is cited in the
  `rule_refs` of a `pending` task is left out of `new_budgets`. It is still listed in
  `budget_failures`, and `ccp health` still reports it. It is not added to the pass's `budget_ids`
  either, so once the citing task is done and the breach remains, it makes a pass due.
- **Tests** in `tests/test_architect_default_on.py`:
  - `test_cadence_from_the_adoption_point` merges `every_n_tasks * max_in_flight` tasks;
  - with `max_in_flight` 3 and `every_n_tasks` 4, 11 merges make no cadence reason and 12 do;
  - with `max_in_flight` 1, 4 merges make one;
  - a new breach `E7` with a pending task citing `rule_refs: ["E7"]` gives no budget reason; the
    same breach with that task `done` gives one;
  - `cadence_tasks` is in `info`.

### SPEC changes (signed in the brief, §31)

**a. §19.6 item 1, Cadence.**

CURRENT (`docs/spec/03-quality.md` at `8aefa59`):
> 1. **Cadence.** `every_n_tasks` tasks numbered from the adoption point (§19.11) have merged since the last pass, or 14 days
>    have passed with at least one merge. Each pass records the done set at its start;
>    with no pass yet, every done task from the adoption point counts.

PROPOSED:
> 1. **Cadence.** `every_n_tasks` times the product's `parallel.max_in_flight` (1 when tasks run one at
>    a time, §16.2) tasks numbered from the adoption point (§19.11) have merged since the last pass, so
>    a pass comes after about as much wall time whatever the number of tasks in flight, or 14 days
>    have passed with at least one merge. Each pass records the done set at its start;
>    with no pass yet, every done task from the adoption point counts.

**b. §19.6 item 4, Health drift** (its first sentence).

CURRENT (`docs/spec/03-quality.md` at `8aefa59`):
> 4. **Health drift.** `ccp health` finds the median active time of the last 5 tasks above
>    1.5 times the median of the 10 before them (drift needs 15 timed tasks),
>    or a house-rule budget (§20.2) over its limit on the integration branch.

PROPOSED:
> 4. **Health drift.** `ccp health` finds the median active time of the last 5 tasks above
>    1.5 times the median of the 10 before them (drift needs 15 timed tasks),
>    or a house-rule budget (§20.2) over its limit on the integration branch that no `pending` task
>    cites in its `rule_refs` (a breach already tasked calls no pass; once that task is done, a breach
>    that remains does).

**c. §20.2, the first bullet.**

CURRENT (`docs/spec/03-quality.md` at `8aefa59`):
> - **Budgets are not in the verifier's gate.** They are diagnostics: `ccp architect due` measures
>   them, where a breach on the integration branch makes a pass due with a reason naming the budget
>   (§19.6), and `ccp health` reports them. One file growing never fails an unrelated task's verifier.

PROPOSED:
> - **Budgets are not in the verifier's gate.** They are diagnostics: `ccp architect due` measures
>   them, where a breach on the integration branch makes a pass due with a reason naming the budget,
>   unless a `pending` task cites the budget's id in its `rule_refs` (§19.6), and `ccp health` reports
>   them all. One file growing never fails an unrelated task's verifier.

- **Out:** the 14-day trigger, `every_n_tasks`'s default, friction notes, drift, and the triggers'
  blocks at `ccp tasks next`.

## dod_checks

- id: `ca-01`
  story: As a lead running three tasks at once, a pass comes after as much work as with one.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_architect_default_on 2>&1 | tail -45`.
  expect: exit 0, with the Scope's cadence tests (11 merges none, 12 merges one, `max_in_flight` 1
    with 4 merges one) and the budget tests listed `ok`.
  dry run (`1b734dd`): 32 tests, OK; the new tests do not exist yet.

- id: `ca-02`
  story: As a plane developer, the cadence and budget tests bite.
  setup: a checkout of the PR head; then two copies (`git worktree add --detach <tmp> HEAD`): in copy
    A the cadence is `every_n_tasks` again (the multiplication removed); in copy B the `rule_refs`
    filter on `new_budgets` is removed.
  steps:
    1. In copy A, run `python3 -B -m unittest -q tests.test_architect_default_on`.
    2. In copy B, run the same.
  expect: each step has at least one failure.
  dry run: n/a — the tests are new.

- id: `ca-03`
  story: As a lead, `ccp architect due` says how many merges the cadence waits for.
  setup: a checkout of the PR head; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . architect due | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['cadence_tasks'], d['reason'])"`.
  expect: the line starts `12 ` (this repo's `every_n_tasks` 4 times its `max_in_flight` 3), and the
    reason, when it is the not-due one, reads `<n> of 12 tasks done since none`.
  dry run (`1b734dd`): `ccp architect due` exits 3, its JSON with no `cadence_tasks` key and the
    reason "1 of 4 tasks done since none; nothing else due".

- id: `ca-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0211 --base origin/main`.
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
