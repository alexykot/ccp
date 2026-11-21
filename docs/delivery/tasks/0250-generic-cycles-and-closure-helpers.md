---
task_id: 0250-generic-cycles-and-closure-helpers
title: One cycles helper and one closure helper over a dependency map, used by the task log's walks
status: done
kind: refactor
depends_on: []
clashes_with: ["0234-one-check-parser-and-one-file-at-rev-reader"]
review_refs: ["sh-20261121T001225Z-7dbe#F07", "sh-20261121T001225Z-7dbe#F08"]
rule_refs: ["E12", "E15", "E24"]
review_point: R15
paths: ["ccp/graph.py", "ccp/tasklog.py", "ccp/plan.py", "ccp/CLAUDE.md", "tests/test_graph.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0250-generic-cycles-and-closure-helpers

## Intent

ADR-0046 needs a cycle check over `requires` links and a `depends_on` closure. The task log already
walks its dependency graph by hand in `dependency_cycles` and `scope_deps`, and the planner builds
its own map. After this task `ccp/graph.py` holds `cycles(deps)` and `closure(deps, start)` on plain
mappings, the task-log walks and the planner use them, and `tasklog.py`'s docstrings stop restating
the list of warnings. Nothing a product sees changes.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0046 (`sh-20261121T001225Z-7dbe`): F07 and F08's `tasklog.py` half.
- **The walks.** `def dependency_cycles` and `def scope_deps` in `ccp/tasklog.py`
  (`git grep -n 'def dependency_cycles\|def scope_deps' -- ccp/tasklog.py` at `8aefa59`: two lines),
  and the planner's own map in `ccp/plan.py`. `ccp/forecast.py` and `ccp/parallel.py` read
  `depends_on` for other purposes and stay as they are.
- **The docstrings.** `tasklog.py`'s module docstring and `warnings()`'s list the warnings, already
  missing two the code emits (the shape's evidence).
- A refactor: the cycles named, their order and every scope stay as they are.

## Scope

- **In:** `ccp/graph.py` (new), `ccp/tasklog.py`, `ccp/plan.py`, `ccp/CLAUDE.md`,
  `tests/test_graph.py` (new).
- **`graph.cycles(deps) -> list[list[str]]`** and **`graph.closure(deps, start) -> set[str]`** on a
  `Mapping[str, list[str]]`; `dependency_cycles`, `scope_deps` and the planner's walk use them;
  `ccp/CLAUDE.md` lists the module.
- `tasklog.py`'s module docstring and `warnings()`'s name §21.1 instead of listing the warnings.
- **Tests** in `tests/test_graph.py` (new): no cycle, a self-loop, two cycles, a closure through a
  diamond, a missing node.

## dod_checks

- id: `gr-01`
  story: As a plane developer, the graph helpers are tested on plain mappings.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_graph 2>&1 | tail -8`.
  expect: exit 0, the Scope's five tests listed `ok`.
  dry run: n/a — the module is new.

- id: `gr-02`
  story: As a task-log owner, cycles and scopes are found as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_tasklog tests.test_forecast tests.test_parallel_claims 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

- id: `gr-03`
  story: As a plane developer, the task log's cycle check really uses the helper.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `graph.cycles` returns an empty list.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_tasklog`.
  expect: at least one failure (a cycle test).
  dry run: n/a — the module is new.

## Implementation notes

- `graph.cycles` is `dependency_cycles`'s walk moved unchanged; `dependency_cycles` keeps its signature and builds the map.
- `graph.closure(deps, start)` returns what `start` depends on, a dependency that is not a key included and not followed, `start` itself only through a cycle. `scope_deps` prunes the map to out-of-scope, non-dropped dependencies and takes the closure for each open scope task, lowest number first with `setdefault`: the same set and the same needing task as the old stack walk.
- The planner's `chain_report` builds one map within the group (self-dependencies kept) for `graph.cycles`, and derives the self-free map `_depths` reads. `_depths` stays: it is a longest-chain computation, neither of the two helpers.
- The module docstring and `warnings()` name §21.1; `ccp/CLAUDE.md` lists `graph.py` under Helpers.
- Fix round 1: the two §21.1 mentions in `ccp/tasklog.py` now say "(§21.1); each warning is stated with its rule's §", since §21.1 states only one of the warnings. Added pins for what the rewrites preserved: two `scope_deps` tests in `tests/test_kinds.py` (the lowest open scope task is the needing one; the walk does not go through a scope task) and a self-dependency group case in `tests/test_tasks_check_chain.py`. NIT 1 (gr-01's `tail -8`) is the task file's check and is left as written.

## Verification notes
- 2026-11-21 — verifier, PR #258 head `7ce8de2` (squash `b48712c`): APPROVE. Passed: gr-01, gr-02, gr-03. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0250-generic-cycles-and-closure-helpers.json.

