---
task_id: 0196-no-pass-owed-at-adoption
title: A product that adopts the architect owes no pass at once; before the first pass only the cadence counts
status: pending
kind: feature
depends_on: ["0185-architect-on-by-default"]
spec_refs: ["S19"]
rule_refs: []
review_point: R12
paths: ["ccp/architect.py", "docs/spec/03-quality.md", "tests/test_architect_default_on.py"]
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
is due only by the cadence, counted from its adoption point. After its first pass, every trigger
works as today.

## Context (not checked)

- `ccp/architect.py` `due_info` builds the reasons. The cadence counts tasks numbered from
  `config.adoption_point`. Notes count `health.notes(q, last.get("started_at"))`, which is every
  note when there is no last pass. Drift, budgets and the review-point trigger take no account of
  the adoption point (`git grep -n 'n_notes\|health.trend\|budget_failures\|review point closes'
  ccp/architect.py` at `70bcfe0`).
- Found adopting the architect on a queue with a long history: `ccp architect due` printed a pass
  due by friction notes and by drift, with no task done since the adoption point.
- A product whose architect has run before keeps its last pass in the architect state, so this
  changes nothing for it.

## Scope

- In `due_info`, when the architect state has no last pass, only the cadence reason is computed:
  - the review-point trigger is off;
  - the notes trigger is off;
  - the drift trigger is off;
  - the budget trigger is off.

  The cadence and `max_days` keep their 0185 behaviour; `max_days` needs a last pass, as today. The
  returned `health` value may still be computed for display.
- `ccp architect due` still exits 1, not due, and the board shows no architect reason for such a
  product until its cadence fires.
- SPEC §19.6, after the list of triggers, adds one sentence: "Before a product's first pass, only
  the cadence counts (§19.11): a product that adopts the seat with history owes no pass at once." It
  states ADR-0043 D7, which the operator accepted (§31.1).
- `tests/test_architect_default_on.py` gains these tests, each with an adopted product:
  - with no last pass, 788 friction notes, a drift-shaped health history and a failing budget,
    `due_info` gives no reason;
  - with no last pass, `every_n_tasks` tasks done from the adoption point, the only reason is
    cadence;
  - with a recorded last pass, `notes_due` notes since it still make a pass due, as today.

Out of scope: the cadence itself, `max_days`, how a pass records its state, and any product's own
adoption point.

## dod_checks

- id: `np-01`
  story: As a product that just recorded its adoption point, I owe no pass at once.
  setup: the PR head, with the three new tests in place.
  steps:
    1. `python3 -m unittest tests.test_architect_default_on -v 2>&1 | tail -5`.
  expect: `OK`. Revert the `due_info` change locally and run it again: the no-pass test fails,
    naming a notes or drift reason.

- id: `np-02`
  story: As the SPEC reader, §19.6 says what happens before the first pass.
  setup: the PR head.
  steps:
    1. `grep -n "Before a product's first pass" docs/spec/03-quality.md`.
  expect: one line, in §19.6.

- id: `np-03`
  story: As the plane, the suite passes.
  setup: the PR head.
  steps:
    1. `scripts/gate.sh`.
  expect: exit 0.

## Refs

- ADR-0043 D7 ("an upgraded product owes no pass at once").
- Task 0185 (the adoption point and the cadence counted from it).
- SPEC §19.6, §19.11.

## Implementation notes

## Verification notes
