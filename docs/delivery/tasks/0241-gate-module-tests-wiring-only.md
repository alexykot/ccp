---
task_id: 0241-gate-module-tests-wiring-only
title: The gate's slowest module tests the catch-up wiring only, and tests name fixture facts through code
status: done
kind: refactor
depends_on: ["0240-plane-workers-run-the-head", "0242-retire-restructure-scaffolding-and-queue-markers", "0243-one-source-for-syntax-events-and-config", "0244-tasks-check-runs-dry-runs"]
review_refs: ["ar-20261120T234012Z-27eb#F02", "ar-20261120T234012Z-27eb#F11"]
rule_refs: ["E15", "E4"]
review_point: R16
paths: ["tests/test_behind_tip_catch_up.py", "tests/test_catch_up_decision.py", "tests/helpers.py", "tests/"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0241-gate-module-tests-wiring-only

## Intent

The plane's gate stops waiting on one module. `tests.test_behind_tip_catch_up` keeps one end-to-end
test per wiring path of the behind-tip catch-up and moves every other decision branch to the
plain-value module, which already holds most of them, so the parallel gate's critical path drops.
And tests stop copying plane facts as literals: the worktrees directory is named through the code,
and a binding is written by one shared builder, so changing either is a one-line change, not a sed
across the suite that collides with tasks in flight.

## Context (not checked)

From architect pass `ar-20261120T234012Z-27eb`, findings F02 and F11, triaged by the lead on
2026-11-21. House rules E15 (each branch unit-tested on plain values, end-to-end tests cover the
wiring) and E4 as amended by that triage (a test names a plane constant or shared fixture fact
through the code or a fixture helper). Measured at `8aefa59`.

- **F02.** `grep -c 'def test' tests/test_behind_tip_catch_up.py` at `8aefa59`: 46 (44 run; the
  class is `CatchUp(ToolkitFixture, unittest.TestCase)` with a commit and a push in `setUp`).
  `grep -c 'def test' tests/test_catch_up_decision.py` at `8aefa59`: 27, on `catch_up_blocked` and
  plain values. Timed alone on the operator's Mac at `8aefa59`,
  `/usr/bin/time -p python3 -B -m unittest -q tests.test_behind_tip_catch_up`: real 155.37 s. In the cold gate `st-20261120T091422Z-26c1ec` (queue `runs/_suites.jsonl`) it took 176.56 s of the run, the next slowest module 97.62 s. `scripts/gate_parallel.py` runs modules in parallel with `SERIAL` empty,
  so the slowest module bounds the gate.
- **The wiring paths to keep end to end** (ruling): caught up, gated and merged; refused (one
  overlap case); a red gate on the merge; a refused push and a refused merge closed by a rerun; a
  failed reconcile closed by a rerun; a tip moving during the gate; the gate's environment; a
  carried build sign-off held across a rerun; the refusals that need a queue or a lane (no gate lane,
  no worktrees dir, a lane held, a queue in git). Each other branch (overlap kinds, renames, declared
  paths, shared-file appends, the `clashes` cases, sign-off carry cases) moves to
  `tests/test_catch_up_decision.py` as a plain-value test, or is deleted where that module already
  has it. Splitting the remainder into two modules is allowed when it alone stays slow.
- **F11.** `git grep -c '\.plane-runtime' -- tests` at `8aefa59`: 143 occurrences in 28 modules,
  while `ccp/config.py` defines `WORKTREES_DIR`. `git grep -l 'product_root:' -- tests` at `8aefa59`: 21 modules writing a binding by hand; `tests/helpers.py` defines `machine_file`, `merged_plane` and
  `Product`, no binding builder. Ruling: add `binding(**keys)` to `tests/helpers.py` returning the
  binding text, and use it in every module that only needs a binding; the modules that test the
  binding format or `ccp init`'s output keep literal text (`tests/test_binding_reader.py`,
  `tests/test_short_binding.py`, `tests/test_init.py`, `tests/test_init_session_settings.py`,
  `tests/test_init_telemetry.py`). Name the worktrees directory as `config.WORKTREES_DIR` (or a
  fixture attribute set from it); a test that pins the constant's own value keeps the literal.
- No test expectation changes, except where a branch moves module.
- **Runs last in R16** (the lead's ruling on the triage review): it rewrites fixture literals across
  most test modules, which every other R16 task's tests touch, so landing it after them spares each
  of them a catch-up through this one. `depends_on` is how the plane orders it (§10.3); the
  wide-plan advice is set aside here on purpose.

## Scope

- **In:**
  - `tests/test_behind_tip_catch_up.py`, `tests/test_catch_up_decision.py`.
  - `tests/helpers.py` (`binding`), and every test module that spells `.plane-runtime` or writes a
    binding by hand (the 28 and 21 modules measured above).
- **Out:**
  - Code under `ccp/`: no behaviour changes.
  - Prose assertions (F10, deferred to the roadmap).

## dod_checks

- id: `tb-01`
  story: As a plane developer, the catch-up's end-to-end module runs only its wiring paths.
  setup: a checkout of the PR head on the operator's Mac (the machine of the dry run).
  steps:
    1. Run `grep -c 'def test' tests/test_behind_tip_catch_up.py`.
    2. Run `/usr/bin/time -p python3 -B -m unittest -q tests.test_behind_tip_catch_up`.
  expect: step 1 prints a number no greater than 14; step 2 exits 0 with `real` under 60 seconds.
  dry run (`8aefa59`): step 1 printed `46`; step 2 exited 0 with real 155.37.
- id: `tb-02`
  story: As a plane developer, every decision branch the end-to-end module dropped is still tested on plain values, and a moved branch's test bites.
  setup: a checkout of the PR head; then a separate copy where `ccp/lifecycle.py` `catch_up_blocked` refuses a task with no declared paths under `schedule == "clashes"` too (its `if not declared` test moved above the `clashes` branch): a branch the end-to-end module tests today as `test_under_clashes_a_task_with_no_declared_paths_is_caught_up`, which this task moves to the plain-value module.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_catch_up_decision tests.test_behind_tip_catch_up`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_catch_up_decision`.
  expect: step 1 exits 0 and `grep -c 'def test' tests/test_catch_up_decision.py` is greater than 27; step 2 exits non-zero.
  dry run (`8aefa59`): both modules exited 0 (run separately); 27 tests in the decision module.
- id: `tb-03`
  story: As a plane developer, tests name the worktrees directory through the code.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -c '\.plane-runtime' -- tests`.
  expect: at most 3 modules are listed, each holding a test that asserts the constant's own value, with no more than 3 occurrences in all.
  dry run (`8aefa59`): 28 modules, 143 occurrences.
- id: `tb-04`
  story: As a plane developer, a binding in a fixture comes from one builder.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -l 'product_root:' -- tests`.
    2. Run `grep -c 'def binding' tests/helpers.py`.
  expect: step 1 lists only `tests/helpers.py`, `tests/test_binding_reader.py`, `tests/test_short_binding.py`, `tests/test_init.py`, `tests/test_init_session_settings.py` and `tests/test_init_telemetry.py`; step 2 prints `1`.
  dry run (`8aefa59`): step 1 listed 21 modules (not `tests/helpers.py`); step 2 printed `0`.

## Implementation notes

- **F11.** `tests/helpers.py` gains `binding(**keys)`: `project_id: demo` first, then each key as `key: value`, a dict as an
  indented block, `None` leaves a key out (`project_id=None` for a test that appends to a binding already written).
  Every module that only needs a binding uses it; the five modules the task names keep literal text.
  A test names the worktrees directory as `config.WORKTREES_DIR`; the only literals left are the constants table and the
  pin of the constant's own value in `tests/test_plane_json_constants.py` (2 occurrences, 1 module).
  `tests/CLAUDE.md` names both helpers.
- **F02, kept end to end** (14 tests in `tests/test_behind_tip_catch_up.py`, `grep -c 'def test'` prints 14; the two inline
  product test modules are built by `product_test`, since a `def test` inside a string counts): caught up, gated and
  merged; one overlap refusal; red gate; tip moving during the gate, and a tip that keeps moving; the gate's environment;
  no gate lane, no worktrees dir, a lane held, a queue in git; a refused push; a refused merge and a failed reconcile
  closed by a rerun; a carried build sign-off held across a rerun (now also asserting the record's and the event's
  `sign_off_carried`, as the dropped carry test did). The first test also asserts a catch-up with no sign-off due
  carries none. Alone, the module ran in 43 s on this machine.
- **F02, moved to `tests/test_catch_up_decision.py`** (27 tests became 54): the merge commit and its shared-file union,
  both sides' files with renames, and the task's own patch under `clashes` (far hunk, near hunk, a union in a shared path)
  run on a throwaway repository built on `Product` (`_catch_up_commit`, `_tip_files`, `_task_files`, `_own_patches`), with
  no queue, gate or pull request; `_task_worktree_env` (the two missing-field cases and the full one) on a temp queue;
  `sign_off_gaps` for a build sign-off for another head, stale unless a catch-up carried it; the
  `sign_off_carried` reader and `MergeOkReadsTheCatchUp` (moved whole, both plain values); and a task with no declared
  paths under `clashes`. A verdict carrying a catch-up is refused: `tests/test_verify.py` `Record`.
- **Deleted as already held** by a plain-value test in the decision module: declared path the diff leaves, no declared
  paths (paths schedule), a tip changing a shared file elsewhere is no overlap (`catch_up_blocked` shared), the
  sign-off-not-carried-over-a-shared-file and -declared-path cases, the sign-off carried under `clashes` cases, the brief
  sign-off and `spec_beyond_intent` carry cases (`due_stages`, already in `tests/test_sign_off_beyond_intent.py`).
- Open choices: the throwaway-repo tests sit in the decision module rather than a new module (each takes about 0.1 s);
  `test_a_tip_that_keeps_moving_refuses_after_three_catch_ups` is kept unpatched (three gate runs) as the one cap test.
- **Fix round 1** (review of PR #279, head `765ac01`):
  - Close's catch-up under `parallel.schedule: clashes` (the product default) and the record's `merge_tree: union` lost
    their end-to-end tests: the kept tip-moves-during-the-gate test now runs under `clashes` with a task declaring no
    paths and a both-sides append in a `parallel.shared` file, and asserts `merge_tree == "union"`, the tip's files and the
    merged text. Still 14 tests.
  - Hand-written bindings left in `tests/test_wt.py`, `tests/test_usage.py`, `tests/test_verify.py` and
    `tests/test_notify.py` now use `binding(...)`.
  - Decision-module nits: the tip-files test sets `merge.behind_tip_ignore` and a tip commit under it; the
    appended-lines refusal also asserts `conflicts in`; the second test of the no-declared-paths class is named for what
    it checks (a changed patch is refused under `clashes`).

## Verification notes
- 2026-11-21 — verifier, PR #279 head `d2350fd` (squash `ce5f845`): APPROVE. Passed: tb-01, tb-02, tb-03, tb-04. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0241-gate-module-tests-wiring-only.json.

