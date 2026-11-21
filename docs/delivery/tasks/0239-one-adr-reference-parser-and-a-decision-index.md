---
task_id: 0239-one-adr-reference-parser-and-a-decision-index
title: One ADR-reference parser in refs, and one pure decision index that every build-state reader uses
status: pending
kind: refactor
depends_on: ["0202-forecast-and-health-report-task-supply"]
clashes_with: ["0234-one-check-parser-and-one-file-at-rev-reader"]
review_refs: ["sh-20261121T001225Z-7dbe#F02", "sh-20261121T001225Z-7dbe#F03", "sh-20261121T001225Z-7dbe#F08"]
rule_refs: ["E23", "E12", "E15", "E24"]
review_point: R15
paths: ["ccp/refs.py", "ccp/adr.py", "tests/test_refs.py", "tests/test_adr_index.py", "tests/test_task_supply.py"]
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
- **R14's 0202** adds `adr.untasked` (`ccp health`'s and `ccp forecast`'s untasked decisions), a fifth
  reader of decision state, and parses ADR refs in task frontmatter. This task depends on it (rather
  than only clashing) so that `untasked` exists to fold into the index; its tests stay in
  `tests/test_task_supply.py`.
- A refactor: every refusal, warning and listing stays as it is.

## Scope

- **In:** `ccp/refs.py`, `ccp/adr.py`, `tests/test_refs.py`, `tests/test_adr_index.py` (new),
  `tests/test_task_supply.py`.
- **`refs.Ids.adr_link(s) -> (number, decision | None) | None`**, the one `<ADR id>[ Dn]` parser;
  `adr._link` and `parse_adr_ref` use it.
- **`adr.DecisionIndex.build(adrs)`**: `state(adr, d)`, `resolve(adr, d)` following each recorded
  `retired by <ADR id> Dk` to its end (a loop returned as such), `is_built` and `blocks_done`;
  `analyse`, `unbuilt_cited`, `built` and 0202's `untasked` read it, and `untasked` parses each task
  ref with `refs.Ids.adr_link`.
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

- id: `ai-04`
  story: As a plane developer, the index's `retired by` walk is tested.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `DecisionIndex.resolve` stops after the first `retired by` link.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_adr_index`.
  expect: at least one failure (the two-link test).
  dry run: n/a — the module is new.

- id: `ai-03`
  story: As a task-log owner, ADR checks and listings behave as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_adr tests.test_adr_decisions tests.test_refs tests.test_tasklog_adr_unbuilt tests.test_task_supply 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK` for the first four modules; `tests.test_task_supply` comes with 0202.

## Implementation notes

- `refs.Ids.adr_link` is the old `adr._link` pattern moved unchanged (a whole string, prefix and `D` case-insensitive, any number of digits). `adr._link` is a one-line delegate. `parse_adr_ref` reads number, decision from `adr_link` when the whole ref is a link, and keeps its loose reading (a `D` anywhere, a trailing section) for any other ref. `parse_adr_ref` takes the decision from `adr_link` only when it is the form a ref has always cited (a capital `D`, a lower-case suffix); `0040 d2` and `0040 D2A` stay section anchors, as at the base.
- `adr.DecisionIndex.build(adrs, ids=refs.DEFAULT)` holds the recorded states and each ADR's body order. `state`, `decisions` (the body's order, `state` None when unrecorded), `resolve` (returns `adr.Resolved(adr, decision, loop)`; a link naming a whole ADR ends the walk with `decision` None; a `retired by` that is not a link ends it at the decision), `is_retired`, `is_built` and `blocks_done`. `analyse`, `unbuilt_cited`, `in_force_at`, `built`, `decision_states` and `untasked` read it; `not_in_force` is gone, `blocks_done` is its rule. `untasked` uses `blocks_done` for its `not_built` test (the same fact).
- `untasked` parses a ref with `parse_adr_ref`, which delegates to `adr_link`: calling `adr_link` there as well would change nothing for a whole link and would need the loose reading again for a file or section ref.
- The module docstring drops the command table, the key list and the format paragraph (the SPEC §6 text and docs/cli hold them).
- Fix round 1: (a) `parse_adr_ref` keeps the base reading of `d2` and `D2A` (above), pinned in `tests/test_refs.py`. (b) `unbuilt_cited` warns only for a decision the ADR body has, as `decision_states` did; a recorded `D9 not_built` with no heading raises no warning (`tests/test_tasklog_adr_unbuilt.py`). (c) `untasked` builds the index per ADR file, so two files with one number each list their own decisions (`tests/test_task_supply.py`).
- Fix round 2: (a) `unbuilt_cited` reads each cited ADR file on its own record (`DecisionIndex.build([m], ids)`), as `decision_states(m)` did, so two files sharing a number do not read each other's states (`tests/test_tasklog_adr_unbuilt.py`). (b) `parse_adr_ref` keeps the base reading exactly: the decision is the first `\bD(\d+[a-z]?)\b` of the ref, and `adr_link`'s decision counts only when it is that same one, so a prefix ending in `D` written without its dash (`D0040 D2` with `D-`) still reads as at the base (`tests/test_refs.py`). The link branch therefore changes no reading; it only agrees with the loose one.
- Fix round 3: `in_force_at` hands the index only `_number` and `decisions` from the PR head's frontmatter, not the whole raw frontmatter: `build` reads `_decisions` as the body, and a frontmatter key of that name (which `parse` accepts) crashed the pre-verdict refusal where the base refused cleanly (`tests/test_verify_adr.py`). `parse_adr_ref` keeps its `adr_link` call (the Scope names it).

## Verification notes
