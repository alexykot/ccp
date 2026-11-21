---
task_id: 0239-one-adr-reference-parser-and-a-decision-index
title: One ADR-reference parser in refs, and one pure decision index that every build-state reader uses
status: pending
kind: refactor
depends_on: []
clashes_with: ["0234-one-check-parser-and-one-file-at-rev-reader"]
review_refs: ["sh-20261121T001225Z-7dbe#F02", "sh-20261121T001225Z-7dbe#F03", "sh-20261121T001225Z-7dbe#F08"]
rule_refs: ["E23", "E12", "E15", "E24"]
review_point: R15
paths: ["ccp/refs.py", "ccp/adr.py", "tests/test_refs.py", "tests/test_adr_index.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0239-one-adr-reference-parser-and-a-decision-index

## Intent

ADR-0046 adds `requires` links and checks that read a decision's build state and follow `retired by`.
Today `<ADR id>[ Dn]` is parsed by two regexes that already differ (`refs.Ids` and `adr._link`), and
a decision's state is computed in four places with two opposite readings of "no recorded state".
After this task `refs.Ids` has the one parser and `adr._link` delegates to it, and `adr.DecisionIndex`,
built once from the loaded ADRs, holds each decision's state, a `resolve` that follows `retired by` as
recorded, and named predicates that `analyse`, `unbuilt_cited` and `built` read. `adr.py`'s module
docstring stops restating the frontmatter keys. Nothing a product sees changes.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0046 (`sh-20261121T001225Z-7dbe`): F02, F03 and F08's `adr.py` half; house
  rules E23 (one parser per reference form) and E24 (docstrings don't restate).
- **The parsers.** `refs.Ids._adr_ref_re` and `def _link` in `ccp/adr.py`
  (`git grep -n 'def _link\|_adr_ref_re' -- ccp/adr.py ccp/refs.py` at `8aefa59`: three lines).
- **The state readers.** `analyse` builds its state map inline; `unbuilt_cited` reads
  `decision_states`; `built()` counts a decision with no recorded state as not built, while the
  in-force check reads only `state == "not_built"`. The index names both readings (`is_built`,
  `blocks_done`) and keeps each caller's.
- **The docstring** lists the optional keys that `OPTIONAL` holds and `tests/test_adr.py` ties to the
  schema (`grep -c 'superseded_by' ccp/adr.py` at `8aefa59`: the docstring's two lines and `OPTIONAL`).
- A refactor: every refusal, warning and listing stays as it is.

## Scope

- **In:** `ccp/refs.py`, `ccp/adr.py`, `tests/test_refs.py`, `tests/test_adr_index.py` (new).
- **`refs.Ids.adr_link(s) -> (number, decision | None) | None`**, the one `<ADR id>[ Dn]` parser;
  `adr._link` and `parse_adr_ref` use it.
- **`adr.DecisionIndex.build(adrs)`**: `state(adr, d)`, `resolve(adr, d)` following each recorded
  `retired by <ADR id> Dk` to its end (a loop returned as such), `is_built` and `blocks_done`;
  `analyse`, `unbuilt_cited` and `built` read it.
- `adr.py`'s module docstring names §6 and what the module is for; the key list goes.
- **Tests** in `tests/test_adr_index.py` (new), on plain ADR dicts: each state; `resolve` through none,
  one and two links and a loop; both predicates on a decision with no recorded state. `tests/test_refs.py`
  gains the parser's accepted and refused forms.

## dod_checks

- id: `ai-01`
  story: As a plane developer, the decision index is tested on plain values.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_adr_index 2>&1 | tail -12`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `ai-02`
  story: As the plane, an ADR reference is parsed in one place.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 're.fullmatch' -- ccp/adr.py | grep -c 'D(\\d'`.
  expect: prints 0.
  dry run (`8aefa59`): prints 1 (`_link`'s own pattern).

- id: `ai-03`
  story: As a task-log owner, ADR checks and listings behave as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_adr tests.test_adr_decisions tests.test_refs tests.test_tasklog_adr_unbuilt 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

## Implementation notes

## Verification notes
