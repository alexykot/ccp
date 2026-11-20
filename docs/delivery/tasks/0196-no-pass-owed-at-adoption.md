---
task_id: 0196-no-pass-owed-at-adoption
title: A product that adopts the architect owes no pass at once; before its first pass each trigger counts only what follows the adoption point
status: pending
kind: feature
depends_on: ["0185-architect-on-by-default"]
spec_refs: ["S19"]
rule_refs: []
review_point: R12
paths: ["ccp/architect.py", "docs/spec/03-quality.md", "tests/test_architect_default_on.py", "tests/test_architect.py", "tests/test_rules.py", "tests/test_board_quality.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0196-no-pass-owed-at-adoption

## Intent

ADR-0043 D7 says "an upgraded product owes no pass at once", and SPEC §19.11 says everything the
seat enforces, its triggers included, starts at the adoption point. Task 0185 made the cadence count
only tasks from the adoption point. The other triggers still look at the whole history when no pass
has run yet:
- friction notes count every note in the queue;
- health drift compares the queue's last tasks;
- a failing budget, or a closing review point, fires at once.

So a product with history that records its adoption point is due a pass immediately. After
`grace_tasks`, `ccp tasks next` then blocks it. With this task, a product that has never had a pass
is judged only on what follows its adoption point, so it owes nothing at once. After its first
pass, every trigger works as today.

## Context (not checked)

- `ccp/architect.py` `due_info` builds the reasons, and every caller reads it: `ccp tasks next`'s
  gate, `ccp architect due` and status, and the board through `ccp/quality.py`. The cadence counts
  tasks numbered from `config.adoption_point` (the `counted` set). With no last pass, the other
  triggers look at the whole history:
  - notes count `health.notes(q, last.get("started_at"))`, which is every note;
  - drift compares the queue's last tasks;
  - every failing budget is new, because no pass recorded `budget_ids`;
  - the review-point trigger fires on a scope of tasks that predate adoption.

  (`git grep -n 'n_notes\|health.trend\|budget_failures\|review point closes\|counted' ccp/architect.py`
  at `70bcfe0`.)
- Found while adopting the architect on a queue with a long history: `ccp architect due` printed a
  pass due by friction notes and by drift, with no task done since the adoption point.
- A product whose architect has run before has a last pass in the architect state, so nothing
  changes for it.
- Four existing tests set an adoption point at the first task with no last pass, and rely on a
  non-cadence trigger firing:
  - `tests/test_architect.py`: `PassIsEnforced.test_review_point_close_needs_its_closing_pass` and
    `FrictionTriggersAPass.test_acceptance_2_notes_reach_the_prompt`;
  - `tests/test_rules.py`: `RulesDoc.test_a_budget_breach_makes_a_pass_due_and_never_fails_docs_check`;
  - `tests/test_board_quality.py`: `Quality.test_the_review_point_scope_is_the_one_ccp_architect_due_uses`.

  Found by a dry run of this change at `70bcfe0` with `scripts/gate.sh`.

## Scope

- **In `due_info`, when the architect state has no last pass:**
  - **Review point:** judged only on the scope's tasks numbered from the adoption point, using the
    same numbering test as `counted`. It fires when that subset is non-empty and all done.
  - **Notes:** only notes whose task is numbered from the adoption point count. A note with no task
    does not count.
  - **Drift:** compares only tasks numbered from the adoption point. Drift needs 15 timed tasks and
    the cadence fires after `every_n_tasks`, so in practice it does not fire before the first pass;
    implementing it as "off with no last pass" is acceptable.
  - **Budgets:** a baseline. The first `due_info` call with `record=True` after adoption, with no
    last pass, saves the budget ids failing at that moment in the architect state, as `seen` is
    saved. Until the first pass, only a failing budget id not in that baseline fires. The first pass
    records `budget_ids` as today, and the baseline is no longer read.
  - **Cadence and `max_days`:** keep their 0185 behaviour. `max_days` needs a last pass, as today.
  - The returned `health` value may still be computed for display.
- `ccp architect due` exits 3 (not due) for a product that has just adopted, whatever its history.
  The board shows no architect reason for it.
- The module docstring's trigger list (`ccp/architect.py`) says the same.
- **SPEC §19.6**, item 1. CURRENT, verbatim at `70bcfe0`: "with no pass yet, every done task
  counts." PROPOSED: "with no pass yet, every done task from the adoption point counts."
- **SPEC §19.6**, after the list of triggers, a new sentence: "Before a product's first pass, each
  trigger counts only what follows the adoption point (§19.11): a review point counts its tasks from
  the adoption point, friction notes count only those tasks' notes, drift compares only those
  tasks, and a budget counts only if it starts failing after adoption, so a product that adopts the
  seat with history owes no pass at once."

  Both state ADR-0043 D7 ("an upgraded product owes no pass at once") and §19.11 ("everything it
  enforces ... starts at the product's adoption point"), which the operator accepted (§31.1).
- **The four existing tests above** keep testing their trigger. Each either records a last pass in
  the architect state before the trigger (as `tests/test_board_quality.py` already writes
  `architect.json` with `last.started_at`), or uses scope tasks and notes numbered from the adoption
  point.
- **New class `NoPassOwedAtAdoption` in `tests/test_architect_default_on.py`**, each test with an
  adopted product. The tests may patch `architect.health.trend` to return `{"drift": True,
  "drift_ratio": 2.0}` and `architect.rules.budget_failures` to return a failing budget.
  - `test_history_owes_nothing`: no last pass; `notes_due + 5` notes on tasks before the adoption
    point; drift; a failing budget; a done review-point scope of pre-adoption tasks. `due_info`
    gives no reason, and a second call still gives none.
  - `test_cadence_from_the_adoption_point`: no last pass; `every_n_tasks` tasks done from the
    adoption point. The only reason is cadence.
  - `test_new_work_still_triggers`: no last pass; `notes_due` notes on tasks from the adoption point.
    A notes reason. Also, with a recorded last pass, `notes_due` notes since it give a notes reason,
    as today.
  - `test_a_budget_breached_after_adoption_triggers`: no last pass; a first `due_info` call with
    budget `a` failing gives no reason; budget `b` then also fails, and the next call gives a budget
    reason naming `b` only.

Out of scope: the cadence itself, `max_days`, how a pass records its state, and any product's own
adoption point.

## dod_checks

- id: `np-01`
  story: As a product that just recorded its adoption point, I owe no pass at once.
  setup: the PR head.
  steps:
    1. `python3 -m unittest tests.test_architect_default_on.NoPassOwedAtAdoption -v 2>&1 | grep -E '^test_|^OK|FAIL'`.
    2. `git diff $(git merge-base origin/main HEAD) HEAD -- ccp/architect.py | git apply -R`, rerun
       step 1, then `git checkout -- ccp/architect.py`.
  expect: step 1 shows four `... ok` lines (`test_history_owes_nothing`,
    `test_cadence_from_the_adoption_point`, `test_new_work_still_triggers`,
    `test_a_budget_breached_after_adoption_triggers`) and `OK`. In step 2,
    `test_history_owes_nothing` fails.

- id: `np-02`
  story: As the SPEC reader, §19.6 says what happens before the first pass.
  setup: the PR head.
  steps:
    1. `grep -n "Before a product's first pass\|every done task from the adoption point" docs/spec/03-quality.md`.
  expect: two lines, both in §19.6.

- id: `np-03`
  story: As the plane, the suite passes.
  setup: the PR head.
  steps:
    1. `scripts/gate.sh`.
  expect: exit 0.

## Refs

- ADR-0043 D7 ("an upgraded product owes no pass at once").
- Task 0185 (the adoption point and the cadence counted from it); task 0190 (the plane adopting).
- SPEC §19.6, §19.11.

## Implementation notes

## Verification notes
