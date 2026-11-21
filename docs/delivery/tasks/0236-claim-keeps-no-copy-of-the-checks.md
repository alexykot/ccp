---
task_id: 0236-claim-keeps-no-copy-of-the-checks
title: Claim stops copying the check ids into queue state, and the task-state contract says so
status: pending
kind: feature
depends_on: []
spec_refs: ["S4"]
review_refs: ["sh-20261121T000350Z-5ef1#F07"]
review_point: R15
paths: ["ccp/lifecycle.py", "contracts/task.schema.json", "tests/test_task_state_contract.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0236-claim-keeps-no-copy-of-the-checks

## Intent

`ccp tasks claim` writes the task's check ids into the queue's task state, nothing reads them back,
and `contracts/task.schema.json` describes that field as objects the code never writes. A fix round
can amend the checks, so the copy goes stale, and ADR-0045's refusals must read the checks from the
task file at the head, not from it. After this task claim writes no `dod_checks`, the contract drops
the field, and a test holds what claim writes to the contract.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0045 (`sh-20261121T000350Z-5ef1`), F07.
- **The writer.** `ccp/lifecycle.py` claim: `"dod_checks": meta["_checks"],`
  (`git grep -n '"dod_checks": meta' -- ccp` at `8aefa59`: one line). No reader:
  `git grep -nE "\[.dod_checks.\]|get\(.dod_checks.\)" -- ccp scripts plugin` at `8aefa59`: one line,
  `ccp/estimator.py` reading the estimate's own feature count, not the task state.
- **The contract.** `contracts/task.schema.json` `dod_checks.items` requires `id` and `description`,
  with a `kind` enum; nothing validates the queue state against it.
- **No SPEC change.** §4 keeps runtime state in the queue and names the contract
  (`grep -n 'task.schema.json' docs/spec/01-model.md` at `8aefa59`: one line); it lists no field.
- A feature, since stored data changes. Task states already written keep the key; readers ignore it.

## Scope

- **In:** `ccp/lifecycle.py`, `contracts/task.schema.json`, `tests/test_task_state_contract.py` (new).
- Claim's task state has no `dod_checks`; the schema drops the property.
- **Tests** in `tests/test_task_state_contract.py` (new): a claimed task's state validates against
  `contracts/task.schema.json`, and has no `dod_checks`.
- **Out:** the reverify packet's `dod_checks` (a different contract, which is read).

## dod_checks

- id: `cs-01`
  story: As a runner, what claim writes matches its contract.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_task_state_contract 2>&1 | tail -6`.
  expect: exit 0, both tests listed `ok`.
  dry run: n/a — the module is new.

- id: `cs-02`
  story: As the plane, no second list of checks is kept.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n '"dod_checks"' -- ccp/lifecycle.py contracts/task.schema.json`.
  expect: prints nothing.
  dry run (`8aefa59`): prints two lines, one in each file.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- 2026-11-21 (implementer): claim no longer writes `dod_checks`; `contracts/task.schema.json` drops the
  property. Dropping it alone did not make a claimed state validate: the schema also required `goal` and
  `created_at`, which claim never writes (nor does anything else to task state), and its
  `additionalProperties: false` refused eight keys claim does write (`kind`, `adr_refs`, `lease_since`,
  `claimed_at`, `pr`, `merge_sha`, `branch`, `worktree_path`). The schema now names those eight and
  requires only `task_id`, `project_id`, `title` and `status`, so the new test holds claim to it. No
  other writer's keys were added: the test covers what claim writes, as the task says. Task states
  written before this keep their `dod_checks` key; nothing reads it.
- The test validates with `ccp.verify.schema_errors`, the plane's own checker of its contracts' keywords.

## Verification notes
