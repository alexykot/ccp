---
task_id: 0190-the-plane-takes-its-own-upgrade-steps
title: The plane's own plane.json takes the ADR-0043 upgrade steps before their grace ends
status: pending
kind: feature
depends_on: ["0181-models-block-and-role-defaults", "0182-language-is-a-required-key", "0183-gate-lane-is-required", "0185-architect-on-by-default", "0186-account-facts-on-the-machine", "0187-short-plane-json"]
spec_refs: ["S8", "S19", "S29"]
review_point: R12
paths: ["docs/delivery/plane.json", ".claude/settings.json"]
adopt: none
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0190-the-plane-takes-its-own-upgrade-steps

## Intent

The plane manages itself, so it is the first product to take the steps ADR-0043 asks of every product
with history, before 0191 turns the grace's warnings into refusals: its plane.json names its language,
records its architect adoption point, gives its implementer models in the `models` block, and drops
every key that is now removed, merged or a constant. Its own commands then load with no deprecation
warning.

## Context (not checked)

- ADR-0043 D9's migration (the required steps for a product with history), accepted 2026-11-19.
- Depends on the tasks that introduce each step: 0182 (`language`), 0183 (the gate lane: the plane
  already has one, `scripts/gate.sh`), 0185 (the adoption point), 0181 (`models`), 0186 (the account
  keys: the plane's plane.json sets none) and 0187 (removed, merged and constant keys).
- Today, at `e9ff0fc`, `docs/delivery/plane.json` holds `package_docs.language: python`,
  `workers.implementer_model {small: sonnet, refactor: sonnet}`, `task_log.dir`, `worktrees.dir`,
  `package_docs.doc_name`, `docs.workers: 4`, `estimate.auto: true`, `review_points.file`, and no
  `architect` block (`cat docs/delivery/plane.json` at `e9ff0fc`).
- Decided here:
  - `language: python`; `package_docs.language` deleted.
  - `architect: {"shape_from_task": "<NNNN>"}` where `<NNNN>` is the next task number when this task
    is built (the highest task file number plus one, at the build's base). The house rules are
    `docs/ENGINEERING.md`, the default. The seat then enforces from that task on; nothing before it
    is judged by the kind rules (the R12 refactors cite `spec_refs`, as the task check needs with the
    seat off).
  - `models: {"implementer_small": "sonnet", "implementer_refactor": "sonnet"}`; `workers` deleted.
  - Every key `ccp --root . upgrade status` then lists as removed, merged or a constant is deleted,
    accepting the constant (the plane files no proposal to keep one); each step taken is recorded in
    `upgrade.taken` with this task's PR.
  - `.claude/settings.json` gains `"model": "opus"`, the lead's model (0181).
  - The plane's binding lives outside the repo (§8.3): its removed keys (0188) are the operator's to
    delete on the machine, and the machine file's account keys (0186) likewise. The PR body says so.
    No file outside the repo is written.

## Scope

- **In:**
  - `docs/delivery/plane.json`, `.claude/settings.json`: as decided.
- **Out:**
  - The plane's binding and the machine file (the operator's). Code.

## dod_checks

- id: `pl-01`
  story: As the operator, the plane's plane.json takes the required steps.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -c "import json; d=json.load(open('docs/delivery/plane.json')); print(d.get('language'), 'language' in d.get('package_docs', {}), bool(d.get('architect', {}).get('shape_from_task')), d.get('models'), 'workers' in d)"`.
  expect: prints `python False True {'implementer_small': 'sonnet', 'implementer_refactor': 'sonnet'} False`.
  dry run (`e9ff0fc`): printed `None True False None True`.
- id: `pl-02`
  story: As the operator, the plane has no upgrade step left to take but the binding's.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp --root . upgrade status` and list each step whose `check` is `not taken` and whose `adopt` names `plane.json`.
    2. Run `ccp --root . tasks check` and read its stderr.
  expect: step 1 lists no step from 0181, 0182, 0183, 0185 or 0187; step 2 exits 0 with no `deprecated`, `unknown key` or `moves to` warning about `docs/delivery/plane.json`.
  dry run: n/a — those steps come with their tasks.
- id: `pl-03`
  story: As the operator, the architect seat is on and adopted, and not due at once.
  setup: a checkout of the PR head, with `QUEUE_ROOT` set to the plane's queue (read only).
  steps:
    1. Run `ccp --root . architect due`.
  expect: prints `"enabled": true` and `"due": false`.
  dry run (`e9ff0fc`): printed `"enabled": false` with `"reason": "no architect block in docs/delivery/plane.json"`.
- id: `suite-01`
  story: As a plane developer, the plane's own checks still pass under its new configuration.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp docs check` and `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
