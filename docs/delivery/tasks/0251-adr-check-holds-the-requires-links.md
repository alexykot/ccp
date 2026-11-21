---
task_id: 0251-adr-check-holds-the-requires-links
title: ccp adr check holds requires links to live decisions with no cycle, resolving retired ones through retired by
status: pending
kind: feature
depends_on: ["0225-decisions-may-depend-on-other-adrs-decisions", "0250-generic-cycles-and-closure-helpers"]
spec_refs: ["S6"]
adr_refs: ["0046 D2", "0046 D4"]
review_point: R15
paths: ["ccp/adr.py", "docs/spec/01-model.md", "docs/adr/0046-decisions-may-depend-on-other-adrs-decisions.md", "tests/test_adr_requires_check.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0251-adr-check-holds-the-requires-links

## Intent

After 0225 an ADR can name a decision's prerequisites. This task holds those links: `ccp adr check`
fails on a malformed entry, one naming a decision that does not exist or one in a rejected or
withdrawn ADR, and a cycle across ADRs; a prerequisite that was retired resolves through `retired by`
to its replacement, and one retired with no replacement is reported for the operator. `ccp adr
supersede` stops a whole-ADR supersede from silently cutting a `requires` chain.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0046 D2's failures and D4, accepted by the operator on 2026-11-20.
- **Shaped** by `sh-20261121T001225Z-7dbe`; its refactors are 0239 (one ADR-reference parser and the
  decision index) and 0250 (the graph helpers).
  - F01, the operator's: `ccp adr supersede` without `--by` records each retired decision `retired by
    <ADR id>`, with no Dk (`def supersede` in `ccp/adr.py`, the default), so D4 has no chain to follow.
    Recommended: a whole-ADR `retired by` is no replacement (reported, a failure under `adr.strict`),
    and `supersede` refuses without `--by` while a decision it retires is a `requires` target. This
    brief is written on that answer; if the operator answers otherwise, it is revised and signed again.
  - F03: the checks read 0239's decision index and its `resolve`; F07: the cycle check uses 0250's
    `graph.cycles`.
- **Strictness.** This repo sets `adr.strict: true` (`grep -n '"strict"' docs/delivery/plane.json` at
  `8aefa59`: one line).

## Scope

- **In:** `ccp/adr.py`, `docs/spec/01-model.md`,
  `docs/adr/0046-decisions-may-depend-on-other-adrs-decisions.md`, `tests/test_adr_requires_check.py` (new).
- **`ccp adr check` (D2).** Failures: an entry not of either form; one whose own or target decision
  does not exist; a target in a `rejected` or `withdrawn` ADR; a cycle, across ADRs included, naming
  its decisions in order. Warning, a failure under `adr.strict`: a target whose resolution ends in a
  decision retired with no replacement, a whole-ADR `retired by` included.
- **Resolution (D4).** `DecisionIndex.resolve` follows `retired by <ADR id> Dk`; a whole-ADR `retired
  by` ends the chain with no replacement; a loop is a cycle.
- **`ccp adr supersede`** refuses (exit 2, nothing written) without `--by` while a decision it would
  retire is a `requires` target, naming the requiring decisions.
- ADR-0046 D2 and D4 recorded `built`.
- **Tests** in `tests/test_adr_requires_check.py` (new), on decision indexes built from plain ADR dicts
  where they can be: each failure; the warning, and its failure under `adr.strict`; resolution through
  one and two links; a whole-ADR `retired by`; the supersede refusal, and the same supersede with `--by`.

### SPEC changes (signed in the brief, §31)

**a. §6.5, the links.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
> - `amends` changes an ADR or decision without replacing it.

PROPOSED:
> - `amends` changes an ADR or decision without replacing it.
> - `requires` says a decision rests on another and replaces nothing; it needs no reverse link. A
>   prerequisite recorded `retired by <ADR id> Dk` (§6.3) resolves to Dk, following the chain; one
>   recorded `retired by <ADR id>`, a whole ADR, has no replacement, so `ccp adr supersede` refuses
>   without `--by` while a decision it retires is a `requires` target. No command rewrites another
>   ADR's `requires`.

**b. §6.7, the failures.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
>   body decision; a task `adr_refs` entry citing a decision (`NNNN Dn`) its ADR does not have; a stale
>   or missing index.

PROPOSED:
>   body decision; a task `adr_refs` entry citing a decision (`NNNN Dn`) its ADR does not have; a
>   `requires` entry that is malformed, names a decision that does not exist or one in a `rejected` or
>   `withdrawn` ADR, or closes a cycle (across ADRs included); a stale or missing index.

**c. §6.7, the warnings.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
>   for one id; a missing reverse link; a link key holding prose; and **in force**: a `done` task
>   citing a decision recorded `not_built`.

PROPOSED:
>   for one id; a missing reverse link; a link key holding prose; a `requires` target whose `retired
>   by` chain ends in a decision retired with no replacement, a whole-ADR `retired by` included (the
>   decision resting on it goes to the operator); and **in force**: a `done` task citing a decision
>   recorded `not_built`.

- **Out:** the task-log report (0252), and rewriting another ADR's `requires`.

## dod_checks

- id: `rc-01`
  story: As an ADR writer, a broken or circular prerequisite is refused.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_adr_requires_check 2>&1 | tail -15`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `rc-02`
  story: As a plane developer, the cross-ADR cycle check bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    cycle check reads only links within one ADR.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_adr_requires_check`.
  expect: at least one failure (the cross-ADR cycle).
  dry run: n/a — the module is new.

- id: `rc-03`
  story: As a product with ADRs and no `requires`, nothing changes.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_adr tests.test_adr_decisions tests.test_tasklog_adr_unbuilt 2>&1 | tail -3`.
    2. Run `bin/ccp --root . adr check; echo rc=$?`.
  expect: step 1 exits 0 with `OK`; step 2 prints `rc=0`.
  dry run (`8aefa59`): step 1 `OK`; step 2 `rc=0`.

- id: `rc-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0251 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`8aefa59`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
