---
task_id: 0072-adoption-baseline-gate-and-rules-doc
title: A product adopting the plane runs its gate once on the tip and brings its existing rules doc in
status: done
kind: feature
depends_on: []
spec_refs: ["S4", "S12", "S20"]
review_point: R5
paths: ["ccp/wt.py", "ccp/init.py", "ccp/rules.py", "ccp/cli.py", "README.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "tests/test_wt.py", "tests/test_init*.py", "tests/test_rules.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0072-adoption-baseline-gate-and-rules-doc

## Intent

An adopting lead learns the integration tip is red before the first verifier does, by running the gate once in a verifier-shaped worktree that needs no task (§12.1), and brings an existing engineering-rules doc under the architect without one docs-check failure per rule (§20.1, §20.5).

## Context (not checked)

- Accepted plane proposals: getting a verifier-shaped worktree today needs a task, so an adopting lead invented one; and setting `architect.rules_doc` on a doc whose rules have ids but no `check:` lines fails `ccp docs check` once per rule, with no warning, while the starter rules (§20.5) go unnoticed.

## Scope

- **In:** `ccp wt create --kind ver --baseline` makes a recorded worktree at the integration tip with no task (named `ver-baseline`) and runs the setup hook; the README's adoption steps run the gate lane there once; `ccp init --rules-doc PATH` reports each rule lacking a `check:` line, and with `--adopt` writes `check: pass` lines within the doc's budget, and points at the starter rules (§20.5); §4.5 and §12.1 describe both.
- **Out:** mapping a product's rules to the starter set automatically.

## dod_checks

- id: `check-01`
  story: As an adopting lead, I can run the gate on the tip without a task.
  setup: a scratch product with an integration branch.
  steps:
    1. Run `ccp wt create --kind ver --baseline`.
  expect: a `ver-baseline` worktree at the tip exists and is recorded; `ccp wt remove ver-baseline` removes it.
  dry run: on the merge base `--kind ver` without a task is refused.
- id: `check-02`
  story: As an adopting lead, my rules doc is brought in.
  setup: a scratch product whose rules doc has three ids and no `check:` lines.
  steps:
    1. Run `ccp init --rules-doc <doc>`.
    2. Run it with `--adopt`, then `ccp docs check`.
  expect: the first lists the three rules; after `--adopt` the doc carries `check: pass` lines and docs check passes.
  dry run: on the merge base the flag does not exist.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12 (implementer): `ccp wt create --kind ver --baseline` (`wt.create_baseline`) fetches, resolves
  `origin/<integration>` and makes `ver-baseline` through `wt.create` with an empty task id and number, so
  it is recorded and set up like any other worktree. `remove` now runs `down`/`teardown` for any recorded
  worktree (it used to key on a task id), and `gc` reads no task state for it. `--baseline` refuses
  `--task`, `--sha`, `--name`, another kind and another action (exit 2); no tip, or one at another head,
  exit 3. `contracts/worktree.schema.json` names `ver-baseline`.
- 2026-11-12 (implementer): `ccp init --rules-doc PATH [--adopt]` is its own mode, like `--permissions`:
  it writes no footprint and refuses the other init flags. PATH is root-relative; the rule-id pattern and
  `rules_max_lines` are the product's when `plane.json` loads, else the defaults. `--adopt` adds
  `check: pass` at the end of each unchecked rule's item, indented as its text, and refuses (exit 1,
  nothing written) over the cap. It does not set `architect.rules_doc`; the report says so while the doc
  is not the configured one, and always names the starter set's template. The report exits 0.
- 2026-11-12 (implementer): also touched outside `paths`: `contracts/worktree.schema.json` and the command
  reference rows in `docs/cli/01-model.md` and `docs/cli/02-delivery.md`.

## Verification notes

- 2026-11-12 — verifier, PR #76 head `849a3d4` (squash `0126e9b`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0072-adoption-baseline-gate-and-rules-doc.json.
