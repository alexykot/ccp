---
task_id: 0177-architect-on-and-adoption-point
title: One test for "the architect is on" and one accessor for its adoption point
status: done
kind: refactor
depends_on: []
spec_refs: ["S19", "S20"]
review_refs: ["sh-20261119T170325Z-8142#F08"]
rule_refs: ["E12"]
review_point: R12
paths: ["ccp/config.py", "ccp/architect.py", "ccp/board.py", "ccp/cli.py", "ccp/docrules.py", "ccp/health.py", "ccp/init.py", "ccp/prompt.py", "ccp/quality.py", "ccp/rules.py", "ccp/selection.py", "ccp/tasklog.py", "scripts/observability/team.py", "tests/test_architect_on.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0177-architect-on-and-adoption-point

## Intent

Whether the architect seat is on is answered by one function, and the task number it starts from (its
adoption point) by another, so that when ADR-0043 turns the architect on by default (0185) it changes
those two functions instead of about twenty call sites. Nothing the plane does changes.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, finding F08 and preparatory refactor P6.
- The on/off tests, `git grep -n 'architect is None\|architect is not None\|not cfg\.architect ' -- ccp scripts plugin ':(exclude)ccp/config.py'`
  at `e9ff0fc`: 16 lines (architect.py 5, board.py 1, cli.py 1, init.py 1, quality.py 2, rules.py 1,
  selection.py 1, tasklog.py 3, scripts/observability/team.py 1). Key reads such as
  `(cfg.architect or {}).get("checks")` or `cfg.architect or ARCHITECT_DEFAULTS` (11 more lines) are
  not on/off tests and stay as they are.
  A line that reads a key (`cfg.architect["grace_tasks"]`) after the on-test stays; only the test of
  "is it on" moves.
- `shape_from_task` is read in `ccp/config.py` (validation) and `ccp/tasklog.py` (`def _check_shaping`,
  `_number(a["shape_from_task"], cfg)`): `git grep -n 'shape_from_task' -- ccp` at `e9ff0fc`: 5 lines.
- Decided here:
  - `config.architect_on(cfg) -> bool` is `cfg.architect is not None` today. Every on/off test above
    calls it.
  - `config.adoption_point(cfg) -> int | None` is the task number `architect.shape_from_task` names,
    or None. `_check_shaping` reads it. The kinds and refactor-reference checks and the cadence do not
    read it yet: making them start there changes behaviour, which is 0185's.
  - The key keeps its name, `shape_from_task`: ADR-0043's appendix keeps it, and a rename would give
    every product an upgrade step. The shape's rename proposal is not taken.
- No SPEC change: no § names the call sites (`git grep -n "architect_on\|adoption_point" -- docs/spec`
  at `e9ff0fc` prints nothing).

## Scope

- **In:**
  - `ccp/config.py`: `architect_on`, `adoption_point`.
  - The modules listed in `paths`: each on/off test calls `config.architect_on(cfg)`;
    `ccp/tasklog.py` `_check_shaping` reads `config.adoption_point(cfg)`.
  - `tests/test_architect_on.py` (new): both functions on a config with no block, with a block, and
    with a block naming `shape_from_task` as a number and as an id.
- **Out:**
  - `"architect": false`, the default flip, and where the cadence and the kinds checks start (0185).

## dod_checks

- id: `arch-01`
  story: As a plane developer, "is the architect on" is asked in one place.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'architect is None\|architect is not None\|not cfg\.architect ' -- ccp scripts plugin ':(exclude)ccp/config.py'`.
    2. Run `git grep -n 'architect_on(' -- ccp scripts | wc -l`.
  expect: step 1 prints nothing; step 2 prints at least 16.
  dry run (`e9ff0fc`): step 1 printed 16 lines (counts in Context); step 2 printed 0.
- id: `arch-02`
  story: As a plane developer, the adoption point has one accessor.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_architect_on`.
    2. Run `git grep -n 'shape_from_task' -- ccp ':(exclude)ccp/config.py'`.
  expect: step 1 exits 0; step 2 prints nothing.
  dry run (`e9ff0fc`): step 1 n/a (new module); step 2 printed 2 lines in `ccp/tasklog.py`.
- id: `arch-03`
  story: As a plane developer, the architect behaves as before, and the tests that hold it bite.
  setup: a checkout of the PR head; then a separate copy with `architect_on` returning `True` always.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_architect tests.test_rules tests.test_kinds tests.test_board_quality tests.test_init`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_architect tests.test_kinds`.
  expect: step 1 exits 0; step 2 exits non-zero.
  dry run (`e9ff0fc`): step 1's modules pass at the base.

## Implementation notes

*Append-only, newest last.*

- `config.architect_on(cfg)` and `config.adoption_point(cfg)` sit in `ccp/config.py` after `lane_for`; both take
  any cfg-like object (`getattr`), as `lane_for` does. `adoption_point` matches the product's task-number
  width through `refs.ids(cfg)`, as `tasklog._number` does.
- Every on/off test at the 16 sites the Context counts moved to `config.architect_on(cfg)`. A 17th, in
  `plugin/hooks/runner-idle.sh` (a python heredoc, arrived with 0174 after `e9ff0fc`), moved too, because
  arch-01 step 1 greps `plugin`: it calls `ccp_config.architect_on(cfg)`. `ccp/tasklog.py` dropped its
  function-local `from ccp import config, init` for a module-level `config` import.
- `ccp/docrules.py`, `ccp/health.py` and `ccp/prompt.py` (in `paths`) hold only key reads
  (`(cfg.architect or {})...`), which stay, so they are unchanged.
- The `_check_shaping` docstring named `shape_from_task`; it now says "adoption point", so arch-02 step 2 prints nothing.
- Mutation check on arch-03: `architect_on` returning `True` is killed by `tests.test_kinds` (and
  `tests.test_architect_on`); `tests.test_architect` alone does not catch it, returning `False` it does.

## Verification notes
- 2026-11-19 — verifier, PR #202 head `dbfd419` (close's catch-up of the approved `e41e7d2`, gate run st-20261119T202138Z-6eb535) (squash `cd7df24`): APPROVE. Passed: arch-01, arch-02, arch-03. Gate: `ccp suite run --lane gate (scripts/gate.sh)` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0177-architect-on-and-adoption-point.json.

