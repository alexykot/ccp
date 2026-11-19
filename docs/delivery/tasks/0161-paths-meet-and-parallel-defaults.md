---
task_id: 0161-paths-meet-and-parallel-defaults
title: Rename parallel.clash to paths_meet behind one pairwise predicate, and read the parallel defaults from one place
status: done
kind: refactor
depends_on: []
spec_refs: ["S16"]
review_refs: ["sh-20261119T072530Z-663f#F05", "sh-20261119T072530Z-663f#F07"]
review_point: R11
paths: ["ccp/parallel.py", "tests/test_parallel_defaults.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0161-paths-meet-and-parallel-defaults

## Intent

Whether two tasks may run together is decided by one pairwise function in `ccp/parallel.py`, and the
function that tests whether two tasks' paths meet is named for what it tests, so the logical "clash"
that ADR-0042 brings in can be added in one place without a second meaning of the word. The parallel
defaults are written once, in `config.PARALLEL_DEFAULTS`, and a test holds the plane.json schema to
them. Nothing the plane does changes.

## Context (not checked)

- Shape report `sh-20261119T072530Z-663f`, findings F05 and F07; this is its task T0. Tasks that
  build on it: the clash schedule (the claim rule and the next walk under `parallel.schedule`) and the
  forecast's clash model, both of which depend on this task.
- F05: `def clash(cfg, a, b)` in `ccp/parallel.py` returns the first pair of meeting paths. Its
  callers: `git grep -nw "clash" -- ccp` at `b9e58ce`: 3 lines, the def and two calls (rule 3 in
  `join_refusal`, the passed-over walk in `next_choice`). No test calls it by name:
  `git grep -n "clash(" -- tests` at `b9e58ce` finds only a local variable in `tests/test_tasks_migrate.py`,
  which is not this function and stays. No doc names it: `git grep -nw "clash" -- docs/spec docs/cli README.md plugin templates`
  at `b9e58ce` finds nothing.
- The forecast (`ccp/forecast.py`) does not call `clash` today: it states in its model text that tasks
  whose paths meet are not modelled. So this task does not touch the forecast; the later forecast
  task calls the new predicate.
- F07: `def settings(cfg)` falls back to a literal copy of the defaults:
  `git grep -n '"session_ceiling_pct": 60' -- ccp` at `b9e58ce`: 2 lines, `ccp/config.py` (`PARALLEL_DEFAULTS`)
  and `ccp/parallel.py` (`settings`). The schema's parallel block (`contracts/plane_config.schema.json`)
  has `additionalProperties: false` and a `default` per key; at `b9e58ce` its defaults equal
  `PARALLEL_DEFAULTS` key for key (dry run below). `tests/test_toolkit.py`'s
  `test_plane_config_schema_lists_every_block` checks other blocks' keys but not `parallel`.
- `cfg.parallel` is `None` on a `Config` built without `config.load` (the dataclass default), which is
  when the fallback is read. The fallback returns a copy, so no caller can change the module constant.
- No SPEC change: the SPEC names neither function (search above), and the defaults do not change.
- House rules this follows (docs/ENGINEERING.md): E12 (one source per enumerated concept).

## Scope

- **In:**
  - `ccp/parallel.py`: `clash` is renamed `paths_meet`, its body and docstring unchanged except the
    name. A new pairwise predicate `kept_apart(cfg, a, b) -> tuple[str, str] | None` is the one function
    that says whether tasks `a` and `b` may run together: today it returns `paths_meet(cfg, a, b)`,
    and its docstring says it is where a scheduling mode branches. `join_refusal` (rule 3) and
    `next_choice` (the passed-over walk) call `kept_apart`, never `paths_meet`; their messages are
    unchanged.
  - `ccp/parallel.py` `settings`: falls back to a copy of `config.PARALLEL_DEFAULTS` (lists copied too),
    not a literal.
  - `tests/test_parallel_defaults.py` (new): the schema's `parallel` properties have exactly the keys of
    `config.PARALLEL_DEFAULTS`, each `default` equal to its value; `parallel.settings` of a `Config` with
    `parallel=None` equals `PARALLEL_DEFAULTS`, and changing the returned dict leaves the constant as it was.
  - No existing test changes.
- **Out:**
  - `clashes_with`, `parallel.schedule`, or any new branch in `kept_apart` (the clash schedule task).
  - The forecast (`ccp/forecast.py`).
  - The other plane.json blocks' defaults.

## dod_checks

- id: `par-01`
  story: As a plane developer, "clash" no longer names the path test, and rule 3 and the walk share one predicate.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nw "clash" -- ccp`.
    2. Run `git grep -n "paths_meet(" -- ccp` and `git grep -n "kept_apart(" -- ccp`.
  expect: step 1 prints nothing; step 2 prints exactly the `def paths_meet` line and one call inside `kept_apart` for the first, and exactly the `def kept_apart` line, one call in `join_refusal` and one in `next_choice` for the second, all in `ccp/parallel.py`.
  dry run (`b9e58ce`): step 1 printed 3 lines (`ccp/parallel.py:179` def, `:213` rule 3, `:291` the walk), the positive the absence check removes; step 2 printed nothing (new names).
- id: `par-02`
  story: As a plane developer, the parallel defaults are written once and the schema is held to them.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n '"session_ceiling_pct": 60' -- ccp`.
    2. Run `python3 -B -m unittest -q tests.test_parallel_defaults`.
  expect: step 1 prints one line, in `ccp/config.py`; step 2 exits 0.
  dry run (`b9e58ce`): step 1 printed 2 lines (`ccp/config.py:64`, `ccp/parallel.py:36`); step 2 n/a (new module); the schema's defaults equal `PARALLEL_DEFAULTS` at this commit (`True` from a one-off comparison), so the new test passes without a schema edit.
- id: `par-03`
  story: As a plane developer, the schema test bites.
  setup: a separate copy of the PR head (not the branch's worktree), with `"default": 60` of `session_ceiling_pct` changed to `50` in `contracts/plane_config.schema.json`; a second copy with a `"schedule": {"type": "string"}` property added to the parallel block.
  steps:
    1. In each copy, run `python3 -B -m unittest -q tests.test_parallel_defaults`.
  expect: each run exits non-zero, a failure naming the parallel defaults or keys.
  dry run: n/a (new module).
- id: `par-04`
  story: As a plane developer, scheduling behaves as before, and the tests that hold it bite.
  setup: a checkout of the PR head; then a separate copy with `kept_apart` made to return `None` always.
  steps:
    1. On the PR head, run `python3 -B -m unittest -q tests.test_parallel_claims tests.test_next_passes_over tests.test_parallel_slots tests.test_parallel_state tests.test_parallel_lanes tests.test_forecast tests.test_toolkit`, then `git diff --name-only origin/main...HEAD -- tests/`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_parallel_claims tests.test_next_passes_over`.
  expect: step 1 exits 0 and the diff lists only `tests/test_parallel_defaults.py`; step 2 exits non-zero with at least one failure.
  dry run (`b9e58ce`): step 1's modules passed (24 + 5 + 14 + 52 tests in the first four, 60 in toolkit, state and lanes); step 2 with `clash`'s meeting test replaced by `if False:` gave `FAILED (failures=7)` of 29.
- id: `suite-01`
  story: As a plane developer, the plane's own checks still pass.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: the three checks exit 0 and the branch list is empty.
  dry run (`b9e58ce`): `ccp docs check` printed `docs: clean`.

## Implementation notes

*Append-only, newest last.*

- Built as the Scope gives it. Premises re-run at d3a352c: `git grep -nw "clash" -- ccp` 3 lines (179, 213, 291), `git grep -n 'clash(' -- tests` finds no function call, the docs search finds nothing, `"session_ceiling_pct": 60` in 2 lines (`ccp/config.py:64`, `ccp/parallel.py:36`): as the task states.
- `settings` falls back to `copy.deepcopy(config.PARALLEL_DEFAULTS)` (lists copied too); only the fallback copies, a loaded `cfg.parallel` is returned as before. `parallel.py` imports `PARALLEL_DEFAULTS` from `ccp.config` next to `Config`.
- `kept_apart`'s docstring states it is the one pairwise predicate and where a scheduling mode branches; its body is `return paths_meet(cfg, a, b)`.

## Verification notes
- 2026-11-19 — verifier, PR #180 head `6e1bf80` (squash `a10053c`): APPROVE. Passed: par-01, par-02, par-03, par-04, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp suite run --lane part -- python3 -B -m unittest -q tests.test_parallel_defaults tests.test_parallel_claims tests.test_next_passes_over tests.test_parallel_slots tests.test_parallel_state tests.test_parallel_lanes tests.test_forecast tests.test_toolkit` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0161-paths-meet-and-parallel-defaults.json.

