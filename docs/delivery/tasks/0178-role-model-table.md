---
task_id: 0178-role-model-table
title: One table of each role's default model, which the launchers and the seat checks read
status: pending
kind: refactor
depends_on: []
spec_refs: ["S2"]
review_refs: ["sh-20261119T170325Z-8142#F06"]
rule_refs: ["E12"]
review_point: R12
paths: ["ccp/models.py", "ccp/estimator.py", "ccp/seats.py", "ccp/prompt.py", "ccp/runs.py", "scripts/observability/architecture_review.py", "tests/test_role_models.py", "tests/test_board_seats.py", "tests/test_estimator.py", "tests/test_prompt_model.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0178-role-model-table

## Intent

Each role's default model is written once, in a table in `ccp/models.py`; the headless launchers (the
architect, the estimator) and the seat checks read it; and a test holds each agent definition's full
model id to its role's row. When ADR-0043 sets a default model for every role and adds a per-role
override (0181), it edits the table and one lookup. Nothing the plane does changes.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, finding F06 and preparatory refactor P7; house rule E12 as amended
  in this triage (the roles and their default models are one enumerated concept).
- The pins at `e9ff0fc`:
  - agent definitions, `grep -n '^model' plugin/agents/*.md`: implementer `claude-opus-5-5`; runner,
    reviewer, verifier `claude-sonnet-5-5`;
  - headless launchers, `git grep -n 'claude-sonnet-5-5\|claude-opus-5-5' -- ccp scripts`: 2 lines,
    `ccp/estimator.py` (`HEADLESS_MODEL = ["--model", "claude-sonnet-5-5", "--effort", "medium"]`) and
    `scripts/observability/architecture_review.py` (`HEADLESS_MODEL = ["--model", "claude-opus-5-5", "--effort", "high"]`);
  - the SPEC §2.4 seat table; `config.WORKER_MODEL_ALIASES` and `workers.implementer_model` for the
    implementer's per-task alias.
  - `git grep -c 'claude-sonnet-5-5\|claude-opus-5-5' -- tests`, summed, at `e9ff0fc`: 97 lines, 46 of
    them in `tests/test_board_seats.py`. Most are telemetry samples (a model a request reported), which
    stay literal: they are data, not a role's default.
- Decided here:
  - `models.ROLES`: role → `(alias, effort)` for `runner`, `implementer`, `reviewer`, `verifier`,
    `architect`, `estimator`, at today's values (`sonnet`/`high`, `opus`/`high`, `sonnet`/`high`,
    `sonnet`/`high`, `opus`/`high`, `sonnet`/`medium`). The lead has no row yet: today the plane does
    not set it (0181 adds it).
  - `models.FULL_IDS`: alias → the full id the plane pins (`opus` → `claude-opus-5-5`, `sonnet` →
    `claude-sonnet-5-5`), the one place a full id is written in code.
  - `models.headless_flags(role)` returns `["--model", <full id>, "--effort", <effort>]`; both
    `HEADLESS_MODEL` constants become calls to it (the names may stay as module-level values derived
    from it, since `ccp/seats.py` reads them).
  - The definitions keep their full ids (SPEC §2.4: definitions never use aliases).
    `tests/test_role_models.py` (new) checks each definition's `model:` equals `FULL_IDS[ROLES[role][0]]`
    and its effort equals the row's.
  - Tests that assert a seat's expected default model (not a telemetry sample) read it from the table;
    the implementer lists each changed assertion in the notes. These are the only test expectations
    this task changes.
- No SPEC change: the SPEC states the models, not where code keeps them
  (`git grep -n "HEADLESS_MODEL\|models.py" -- docs/spec` at `e9ff0fc`: lines naming the launch flags
  as the source of the headless seats' models stay true).

## Scope

- **In:**
  - `ccp/models.py`: `ROLES`, `FULL_IDS`, `headless_flags`.
  - `ccp/estimator.py`, `scripts/observability/architecture_review.py`: their flags from the table.
  - `ccp/seats.py`, `ccp/prompt.py`, `ccp/runs.py`: where they name a role's default, the table.
  - `tests/test_role_models.py` (new); default-model assertions in the test modules in `paths`.
- **Out:**
  - Any model change, the lead's row, and the `models` override block (0181).
  - `plugin/agents/*.md` (their ids do not change).

## dod_checks

- id: `mod-01`
  story: As a plane developer, a full model id is written once in code.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'claude-sonnet-5-5\|claude-opus-5-5' -- ccp scripts`.
  expect: every line printed is in `ccp/models.py`.
  dry run (`e9ff0fc`): 2 lines, `ccp/estimator.py:54` and `scripts/observability/architecture_review.py:70`.
- id: `mod-02`
  story: As a plane developer, the launchers' flags are unchanged and come from the table.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -c "from ccp import estimator, models; print(estimator.HEADLESS_MODEL == models.headless_flags('estimator'), models.headless_flags('architect'))"`.
  expect: prints `True ['--model', 'claude-opus-5-5', '--effort', 'high']`.
  dry run (`e9ff0fc`): raised `AttributeError: module 'ccp.models' has no attribute 'headless_flags'`.
- id: `mod-03`
  story: As a plane developer, the definitions are held to the table, and the test bites.
  setup: a checkout of the PR head; then a separate copy with `plugin/agents/delivery-reviewer.md`'s `model:` changed to `claude-opus-5-5`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_role_models tests.test_board_seats tests.test_estimator tests.test_prompt_model tests.test_model_alias`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_role_models`.
  expect: step 1 exits 0; step 2 exits non-zero, naming the reviewer.
  dry run (`e9ff0fc`): step 1's existing modules pass at the base; `tests.test_role_models` is new.

## Implementation notes

*Append-only, newest last.*

- `ccp/models.py`: `ROLES`, `FULL_IDS` and `headless_flags` as decided, plus `default(role)` (the full id and
  effort of a row), the one lookup the seat checks and the tests read; `headless_flags` calls it. A role with
  no row (the lead) raises `KeyError`.
- `ccp/estimator.py` and `scripts/observability/architecture_review.py`: `HEADLESS_MODEL` is
  `models.headless_flags(...)`, same names; `ccp/seats.py` still reads those constants, so it needed no change. The
  review kit now puts the repo root on `sys.path` and imports `ccp.models`, as `team.py` does for other `ccp` modules.
- `ccp/prompt.py` and `ccp/runs.py` name no role's default model (the first reads the definition and the
  `workers.implementer_model` alias, the second the definition), so they are unchanged.
- `ccp/CLAUDE.md`: its one-line module description of `models.py` also says it holds the role table.
- Premise re-run at 8da6d52: `git grep` of the two full ids in `ccp scripts` printed the same 2 lines; in `tests` it
  sums to 98 lines (47 in `tests/test_board_seats.py`), one more than the 97 (46) the task states, not material.
- Test assertions changed (default model of a seat, now read from the table):
  - `tests/test_board_seats.py`: the product-copy definition pin's model for the implementer, the plugin runner's
    pin, the runner block's expected model (a runner of the implementer's agent type), the runner's and the implementer
    run's expected model and effort, the headless architect row's expected model and effort.
  - `tests/test_estimator.py`: the launch argv's `--model`/`--effort`, `estimator.pins()["model"]`, the estimator
    seat row's expected model and effort.
  - `tests/test_prompt_model.py`: the four `expected_model` assertions that pin the implementer definition's model.
  Telemetry samples, the lead's `design_seat` values and the `mismatch` unit cases stay literal. `tests/test_architect.py`
  and `tests/test_plugin.py` also hold a literal default but are outside the task's `paths`, so I left them.
- `tests/test_role_models.py` (new) holds each of the four definitions' `model:` and `effort:` to its role's row,
  the rows to `FULL_IDS`, the flags, and the two launchers' constants to `headless_flags`.

## Verification notes
