---
task_id: 0294-suite-summary-branches-and-catch-up-preconditions-are-tested-on-plain-values
title: The suite summary's cap, cut, tally and empty-log branches and close's three static catch-up refusals are tested on plain values, leaving end-to-end tests only for the wiring
status: pending
kind: refactor
depends_on: []
rule_refs: ["E15"]
review_refs: ["ar-20261122T100027Z-dd31#F06", "ar-20261122T100027Z-dd31#F07"]
review_point: R26
paths: ["ccp/lifecycle.py", "tests/test_suite.py", "tests/test_catch_up_decision.py", "tests/test_behind_tip_catch_up.py"]
clashes_with: ["0191-the-grace-release-ends", "0273-verify-refuses-early-what-record-would-refuse", "0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0294-suite-summary-branches-and-catch-up-preconditions-are-tested-on-plain-values

## Intent

The two slow modules the architect named test their decision branches the way E15 asks: the suite
summary's caps, cuts, tally parsing and empty-log text are tested on `digest` and `render_summary`
with plain values, not through a product and a `ccp suite run` subprocess each, and close's three
static catch-up refusals (no gate lane, no merge worktree, verification records in git) are judged by
one plain function tested in the catch-up decision tests. The end-to-end tests that stay cover the
wiring. Behaviour does not change.

## Context (not checked)

From the triage of architect pass `ar-20261122T100027Z-dd31` (F06, F07; the record is in `docs/delivery/reviews/`).
Measured at `e92f362`.

- **The suite summary.** `tests.test_suite` was the slowest module of the cold gate run the architect cited (the health
  record is in the queue; the review record quotes its figures). `python3 -B -m unittest -v tests.test_suite.Summary 2>&1 | grep -c 'Summary\.test_'` at `e92f362`: 27 tests,
  each through `SuiteFixture` (a `ToolkitFixture`) and a `ccp suite run` subprocess. Thirteen of them test a branch of `digest`,
  `render_summary` or the count read from the log, listed by name in the first step of `test-01`, whose dry run gives their count.
  `tests/test_suite.py`'s `class Digest(unittest.TestCase)` holds 3 plain tests; `git grep -ln 'render_summary(' -- tests` at `e92f362`: none.
- **The catch-up refusals.** `"def _catch_up"` in `ccp/lifecycle.py` raises `_NoCatchUp` for "no gate lane", "no merge worktree"
  and "the queue keeps its verification records in git" before it merges anything, and "gate lane busy" while it waits
  for the lane: `git grep -n '_NoCatchUp(' -- ccp/lifecycle.py` at `e92f362`: 19 lines. Of the four reasons, `git grep -c -e 'no gate lane' -e 'no merge worktree' -e 'records in git' -e 'gate lane busy' -- tests/test_catch_up_decision.py` at `e92f362`: no line (exit 1).
  `tests/test_behind_tip_catch_up.py` holds 14 tests (`grep -c '    def test_' tests/test_behind_tip_catch_up.py` at `e92f362`: 14), among them
  `test_a_product_with_no_gate_lane_refuses_and_never_skips_the_run`, `test_a_product_with_no_worktrees_dir_refuses`,
  `test_a_gate_lane_held_by_another_run_refuses` and `test_a_queue_that_keeps_its_records_in_git_refuses`. Its docstring says
  "Each decision branch is tested on plain values in the catch-up decision tests", which the three static refusals make false.
  The busy refusal depends on a held lane lock, I/O by nature, and stays end to end.
- **Other tasks.** 0288 edits `tests/test_catch_up_decision.py` (its fixture event's actor) and `tests/test_behind_tip_catch_up.py`;
  0273, 0191 and 0293 edit other code in `ccp/lifecycle.py`; 0293 does not touch `tests/test_suite.py`. Recorded as clashes.

### Rulings for the build (the lead's)

- **Summary.** Each of the thirteen tests named in `test-01`'s pattern becomes a plain-value test of `suite.digest`,
  `suite.render_summary` or the function that reads `ran` and `cached` from the log, keeping its name, in `class Digest` or a
  new `class RenderSummary(unittest.TestCase)` in `tests/test_suite.py`; it leaves `Summary`. A test whose expectation reads the
  `ended` row checks the function's return value instead. If one of the thirteen cannot be judged without the subprocess, it
  stays in `Summary` and the report names it.
- **Catch-up.** `ccp/lifecycle.py` gains `def catch_up_precondition(has_gate_lane: bool, lane: str, has_merge_worktree: bool,
  records_written: bool) -> str | None`, returning the first of the three refusal texts, word for word as today, in today's
  order, or None. `_catch_up` computes the three facts and raises `_NoCatchUp` with its result. `tests/test_catch_up_decision.py`
  tests each branch and the None case on plain values; `tests/test_behind_tip_catch_up.py` keeps
  `test_a_product_with_no_gate_lane_refuses_and_never_skips_the_run` (the wiring, and that no run is skipped) and
  `test_a_gate_lane_held_by_another_run_refuses`, drops the other two, and its docstring says the busy and moving-tip paths
  are tested end to end and every other decision on plain values.

## Scope

- **In:** `ccp/lifecycle.py` (`catch_up_precondition`, `_catch_up`'s three checks), `tests/test_suite.py`,
  `tests/test_catch_up_decision.py`, `tests/test_behind_tip_catch_up.py`.
- **Out:** `ccp/suite.py` (unless a function needs exposing to be called on plain values, which the report names); the busy
  refusal; any refusal text.

## dod_checks

- id: `test-01`
  story: As a plane developer, the summary's branches run as plain-value tests, not end to end.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_suite 2>&1 | grep -E 'test_(what_a_failure_shows_is_capped|one_huge_failure_is_cut_not_dropped|a_cache_tally_gives_the_module_counts|without_tally_knobs_a_tally_line_counts_nothing|the_removed_knob_names_are_ignored|an_all_cached_gate_counts_zero_tests_ran_and_its_cached_tests|a_module_that_ran_without_a_count_line_leaves_no_count|a_quoted_tally_inside_a_line_is_not_counted|no_tally_still_means_no_count|full_still_counts_the_fields|a_red_gate_step_after_many_failures_survives_the_cap|long_lines_then_a_final_error_shows_the_final_error|a_short_log_is_shown_whole_and_an_empty_one_says_so) '`.
    2. Run `grep -nE '^class (Digest|RenderSummary)\(' tests/test_suite.py`.
    3. Run `python3 -B -m unittest tests.test_suite.Digest tests.test_suite.RenderSummary 2>&1 | grep '^Ran'`.
  expect: step 1 prints 13 lines, each `ok`, none in `tests.test_suite.Summary`; step 2 prints two lines, each class's base `(unittest.TestCase)`; step 3 prints `Ran <n> tests in <s>s` with `n` at least 16 and `s` under 2.
  dry run (`e92f362`): step 1 printed 13 lines, all in `Summary`; step 2 printed only `Digest`; step 3 errored (no `RenderSummary`), and `tests.test_suite.Digest` alone ran 3 tests in 0.008 s.
- id: `test-02`
  story: As a plane developer, a cap that stops capping is caught by a plain-value test.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_suite.RenderSummary --mutant-file <file>`, the file's mutant making `render_summary` show every failure section, uncapped.
  expect: prints the mutant `killed`.
  dry run: n/a — `RenderSummary` is new.
- id: `test-03`
  story: As a plane developer, close's static catch-up refusals are judged on plain values and the end-to-end module keeps only their wiring.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_catch_up_decision 2>&1 | grep -e precondition -e '^OK'`.
    2. Run `grep -c '    def test_' tests/test_behind_tip_catch_up.py`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_catch_up_decision --mutant-file <file>`, the file's mutant swapping the order of the no-merge-worktree and records-in-git checks in `catch_up_precondition`.
  expect: step 1 lists, each `ok`, tests whose names hold `precondition`, covering each of the three refusals and the None case, then `OK`; step 2 prints `12`; step 3 prints the mutant `killed`.
  dry run (`e92f362`): step 1 printed only `OK`; step 2 printed `14`.

## Implementation notes

## Verification notes
