---
task_id: 0255-test-fixtures-shared-helpers-and-one-repo-build
title: Test helpers other modules borrow move to test-free mixins, and ToolkitFixture builds its repositories once per test class
status: done
kind: refactor
depends_on: ["0227-the-test-fixture-uses-the-local-pr-host", "0241-gate-module-tests-wiring-only"]
clashes_with: ["0208-board-reads-the-latest-good-allowance", "0212-full-role-runs-the-gate-lane-and-a-pregate-lane", "0219-integration-merges-leave-out-the-tip"]
review_refs: ["ar-20261121T020523Z-1d5f#F06", "ar-20261121T020523Z-1d5f#F07"]
rule_refs: ["E4"]
review_point: R17
paths: ["tests/test_toolkit.py", "tests/review_flow.py", "tests/helpers.py", "tests/CLAUDE.md", "tests/test_review_gate.py", "tests/test_review_skip.py", "tests/test_usage.py", "tests/test_board_layout.py", "tests/test_allowance_lapse.py", "tests/test_full_lane_prompt.py", "tests/test_health_conflicts.py", "tests/test_model_alias.py", "tests/test_prompt_rounds.py", "tests/test_report_correction.py", "tests/test_resolution_review.py", "tests/test_review_skip_clean.py", "tests/test_review_skip_provers.py", "docs/delivery/plane.json"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0255-test-fixtures-shared-helpers-and-one-repo-build

## Intent

Helpers that several test modules use live on fixture classes that hold no tests, listed in
tests/CLAUDE.md, so a change to one module's tests no longer reaches ten others. The most reused
fixture, `ToolkitFixture`, builds its bare origin, clone and runner worktree once per test class and gives
each test a cheap private copy, so its 1200-odd tests stop paying seven git subprocesses each before
their bodies run. Behaviour of the plane and of every test is unchanged.

## Context (not checked)

From architect pass `ar-20261121T020523Z-1d5f`, findings F06 and F07, triaged by the lead on
2026-11-21, with the triage's amendment to house rule E4, whose command check lands here because it
fails until this task is built. Measured at `aaa81b2`. `depends_on` 0227 (it rewrites
`ToolkitFixture`'s fake PR host in `tests/test_toolkit.py`) and 0241 (it reworks the gate's test
modules and `tests/helpers.py`), so this task builds on both.

- **F06, borrowed helpers.** `git grep -nE '= test_[a-z_]+\.[A-Z][A-Za-z]+\.[a-z_]+' -- tests | wc -l`
  at `aaa81b2`: 36 lines, in 10 modules (`git grep -lE` with the same pattern: test_allowance_lapse,
  test_full_lane_prompt, test_health_conflicts, test_model_alias, test_prompt_rounds,
  test_report_correction, test_resolution_review, test_review_skip, test_review_skip_clean,
  test_review_skip_provers). The helpers come off `test_review_gate`'s `ReviewGate` (`run_phase`,
  `review`, `fix`, `verdict`), `RepeatVerify` (`verify_round`) and `MergeIn` (`commit`),
  `test_review_skip`'s `SkipReview` (`commit`, `fix`, `push`, `reviewed`, `verify`),
  `test_usage`'s `Fold` (`mkrun`, `write`, `rows`) and `test_board_layout`'s `Layout` (`page`).
  Ruling: the review and skip helpers move to two mixins in `tests/review_flow.py` (new),
  `ReviewFlow` and `SkipFlow`, which hold no test methods; `Fold`'s and `Layout`'s helpers move to
  mixins in `tests/helpers.py`. The defining classes and the borrowing modules inherit them.
  tests/CLAUDE.md's Shared fixtures list names each new mixin.
- **F07, the fixture's cost.** `tests/test_toolkit.py` `ToolkitFixture.setUp` runs `git init --bare`,
  `clone`, `checkout -b`, `add -A`, `commit`, `push -u` and `worktree add`.
  `git grep -l ToolkitFixture -- tests | wc -l` at `aaa81b2`: 63 modules. 
  Its setUp alone, timed by fx-03's step 1 (`python3 -B -c "…TextTestRunner…"`) at `aaa81b2`: 0.32 s and 0.48 s per test over two runs. Ruling: each test class builds the
  three repositories once, in `setUpClass`, into a class-level template under its own temp directory,
  and removes it in `tearDownClass`. The template's plane.json is the class's own `PLANE_JSON`
  (`git grep -l 'PLANE_JSON = ' -- tests | wc -l` at `aaa81b2`: 21 modules override it), so a class
  that overrides `PLANE_JSON` gets its own template and never a copy of another class's. Every test
  copies its class's template directory tree into its own temp directory (`shutil.copytree`, symlinks
  kept) and re-points the runner worktree and the clone's origin at the copy (`git worktree repair`
  and `git remote set-url`), then writes what setUp writes today after the push (the queue, the fake
  PR host, the environment). A test that changes `ToolkitFixture`'s built repository before setUp
  ends (a subclass overriding the build) keeps the per-test build through a class attribute
  `SHARED_REPO = False`.
- **E4, the text this task's check holds** (already in docs/ENGINEERING.md from the triage): "… A
  fixture class other modules reuse holds no test methods; a class with tests is never imported into
  another module (it would run twice), and no module binds another module's test-class methods as its
  own helpers." `architect.checks` `E4` (new): `! git grep -nE '= test_[a-z_]+\.[A-Z][A-Za-z]+\.[a-z_]+' -- tests`.

## Scope

- **In:**
  - `tests/review_flow.py` (new), `tests/helpers.py`, `tests/CLAUDE.md`.
  - `tests/test_review_gate.py`, `tests/test_review_skip.py`, `tests/test_usage.py`,
    `tests/test_board_layout.py` and the 10 borrowing modules listed in Context.
  - `tests/test_toolkit.py` (`ToolkitFixture`).
  - `docs/delivery/plane.json` (`architect.checks` `E4` added).
- **Out:** fixtures other than `ToolkitFixture` (`SuiteFixture` and the others inherit its change);
  the sentence assertions (ar-20261120T234012Z-27eb F10, deferred).

## dod_checks

- id: `fx-01`
  story: As a plane developer, no test module binds another module's test-class methods, and the E4 command check holds.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE '= test_[a-z_]+\.[A-Z][A-Za-z]+\.[a-z_]+' -- tests`.
    2. Run `python3 -B -c "import json; c={x['id']: x['cmd'] for x in json.load(open('docs/delivery/plane.json'))['architect']['checks']}; print(c.get('E4'))"`.
  expect: step 1 prints nothing; step 2 prints the E4 command given in Context.
  dry run (`aaa81b2`): step 1 printed 36 lines; step 2 printed `None`.
- id: `fx-02`
  story: As a test writer, the shared helpers sit on test-free mixins named in tests/CLAUDE.md.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -c 'def test' tests/review_flow.py`.
    2. Run `grep -cw -e ReviewFlow -e SkipFlow tests/CLAUDE.md`.
  expect: step 1 prints `0`; step 2 prints a count of at least 2.
  dry run: n/a — `tests/review_flow.py` is new.
- id: `fx-03`
  story: As a plane developer, a ToolkitFixture test's setUp no longer builds three repositories.
  setup: a checkout of the PR head, on the operator's Mac or the verifier's machine, with no suite running.
  steps:
    1. Run `python3 -B -c "import time,unittest; from tests.test_toolkit import ToolkitFixture; T=type('T',(ToolkitFixture,unittest.TestCase),{'test_x':lambda s: None}); s=unittest.TestSuite([T('test_x') for _ in range(10)]); t=time.time(); unittest.TextTestRunner(verbosity=0).run(s); print(round((time.time()-t)/10,3))"`.
  expect: the printed figure (seconds per test, the class's template build included) is at most `0.12`.
  dry run (`aaa81b2`): printed `0.482` (`0.316` on an earlier run).
- id: `fx-04`
  story: As a plane developer, each test still gets a private repository, and the tests that hold it bite.
  setup: a checkout of the PR head; then a separate copy of it where `ToolkitFixture` hands every test the class template's own directories instead of a copy.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_toolkit tests.test_tasks_close tests.test_review_gate tests.test_resolution_review` and then `git branch --list 'state/*'`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_toolkit tests.test_tasks_close`.
  expect: step 1's tests exit 0 and the branch list prints nothing; step 2 exits non-zero.
  dry run (`aaa81b2`): step 1 n/a as a whole; `tests.test_resolution_review` alone exited 0 in 63 s; step 2 n/a, the template is new.

## Implementation notes

- **F06.** `tests/review_flow.py` (new) holds `ReviewFlow` (`run_phase`, `review`, `fix`, `verdict`, `verify_round`, and
  `MergeIn`'s `commit`) and `SkipFlow(ReviewFlow)` (`SkipReview`'s `commit`, `fix`, `push`, `reviewed`, `verify`; its
  `commit` and `fix` replace `ReviewFlow`'s, which take other arguments). `Fold`'s helpers are `FoldRuns` and `Layout`'s
  `page` is `BoardPage`, both in `tests/helpers.py`. The defining classes (`ReviewGate`, `RepeatVerify`, `MergeIn`,
  `SkipReview`, `Fold`, `Layout`) and the 10 borrowing modules inherit them. Four things moved with them because a
  borrower reached them through the test module: `A`, `B` (to `review_flow`), `PROOF` and the skip product's plane
  (`SKIP_REVIEW_PLANE`, which `test_review_skip_clean` built on as `SkipReview.PLANE_JSON`), and `T0` (to `helpers`,
  `test_usage` imports it). `BoardPage.page` imports `HASH_STUB` from `test_board_drill` inside the method: that module
  imports `helpers` (a top-level import would be circular), and moving the constant would touch modules outside Scope.
- **F07.** `ToolkitFixture.setUpClass` builds the repositories once into a template under its own temp directory
  (`_build_repos`, with the class's `PLANE_JSON`, then `git gc` on both repositories so a copy has fewer files) and
  `addClassCleanup` removes it. `setUp` copies the tree (`shutil.copytree`, symlinks kept, `shutil.copy` as the copy
  function: no times or xattrs, which was the slow part on macOS), then `git remote set-url` and `git worktree repair`,
  then writes the queue and environment as before. `SHARED_REPO = False` keeps the per-test build; `test_report_sections`'
  `Prompts` sets it, because its `setUp` sets the commit dates before the build so the first commit hashes alike in
  two dumps. A class whose bases put `TestCase` before the fixture fails on an assertion naming the order.
- Measured at 91 to 110 load average on this Mac, so wall time is not the idle figure: 0.11 to 0.12 s per test by fx-03's
  command (0.37 to 0.40 s with `SHARED_REPO = False` in the same minutes); CPU seconds per test (self and children) 0.095,
  against 0.24 per-test build. `--template=` on `git init` and `clone` cut files but dropped `hooks/`, which the push-refusal
  tests write into; not used.
- `tests/test_toolkit.py` gains `SharedRepo`, `OwnPlaneJson` and `PerTestRepo` (the copy points at itself, a commit in one
  test is not seen by another, a class's own `PLANE_JSON` reaches its template, `SHARED_REPO = False` builds per test).
- `architect.checks` `E4` added to `docs/delivery/plane.json` as the task gives it. `tests/CLAUDE.md` names the mixins
  and the template and rewords the reuse rule; its sentence avoids the pattern E4 greps for.
- Context premises re-run at 31357f0: 38 lines (36 stated) of the borrowed-helper pattern, in the same 10 modules; 70
  modules (63) use `ToolkitFixture`; 24 (21) override `PLANE_JSON`. The counts grew with merged tasks; the sites are the same.


## Verification notes
- 2026-11-21 — verifier, PR #283 head `724394f` (squash `5b23f26`): APPROVE. Passed: fx-01, fx-02, fx-03, fx-04. Gate: `ccp wt exec -- suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0255-test-fixtures-shared-helpers-and-one-repo-build.json.

