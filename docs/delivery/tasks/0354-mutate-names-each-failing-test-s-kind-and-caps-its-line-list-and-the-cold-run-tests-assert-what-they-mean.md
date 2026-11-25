---
task_id: 0354-mutate-names-each-failing-test-s-kind-and-caps-its-line-list-and-the-cold-run-tests-assert-what-they-mean
title: ccp mutate keeps each failing test's kind (a failure or an error) in its row and on its stderr line, with its signed §20.6 passage; its refusal of an old text found many times lists at most ten lines; the two cold-run lock tests stop asserting on another run's started row
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S16", "S20"]
review_refs: ["ar-20261125T202431Z-1a86#F07"]
review_point: R39
paths: ["ccp/mutate.py", "ccp/doclang/python.py", "contracts/plane_config.schema.json", "docs/spec/03-quality.md", "tests/test_mutate.py", "tests/test_mutate_interface.py", "tests/test_mutate_refusals.py", "tests/test_parallel_lanes.py", "tests/test_suite_cache_probe.py"]
clashes_with: ["0191-the-grace-release-ends", "0353-prompt-tests-pin-rendered-values-ccp-prompt-render-prints-a-template-and-the-lanes-line-names-the-module-form"]
sign_off: brief
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0354-mutate-names-each-failing-test-s-kind-and-caps-its-line-list-and-the-cold-run-tests-assert-what-they-mean

## Intent

A reviewer reading `ccp mutate`'s stderr line or its row sees whether a mutant was killed by a test failing or by a
test erroring (a `NameError` the revert introduced, say), without grepping the mutate log. A worker whose mutant's
old text is in a file hundreds of times gets a refusal of a readable length. A maintainer reading the cold-run lock
tests sees each assertion check the run it names.

## Context (not checked)

Finding F07 of architect pass `ar-20261125T202431Z-1a86` (`docs/delivery/reviews/ar-20261125T202431Z-1a86.md`), the
0350 reviewer's friction note behind it, and two follow-ups of R38 the lead passed to that pass: 0347's line list is
uncapped, and 0347's `assertNotIn("lane_skipped", self.started_rows()[-1])` after a busy exit reads another run's row.
Whether a mutant killed only by an erroring test counts as `killed` is a §20.6 decision deferred in
`docs/ROADMAP.md`; this task only shows the kind. The §20.6 text below is new rule text beyond the accepted intent,
so the operator signs it before the claim (triage `ar-20261125T202431Z-1a86`, question 2).

Measured at `becb6417`:

- `"outcome = (\"survived\""` (`ccp/mutate.py` `run`) reads a non-zero exit as `killed` unless `_says_unbuilt`;
  `"def _failed"` keeps `ln[m.end():].strip()`, the text after the `section_re` match, so the match itself (`FAIL: `
  or `ERROR: `) is dropped. The Python pack's `SUMMARY["section_re"]` is `^(?:FAIL|ERROR|UNEXPECTED SUCCESS): `
  (`ccp/doclang/python.py`). `"def lines"` prints `mutant <n>: <outcome> (<test id>)`.
- `"def _once"` lists every occurrence's line (`"def _lines_of"`), with no cap.
- `"def test_a_cold_run_takes_the_lock_whatever_its_tree"` (`tests/test_parallel_lanes.py`) and
  `"def test_a_cold_run_takes_the_lock_whatever_the_probe_says"` (`tests/test_suite_cache_probe.py`) assert
  `assertNotIn("lane_skipped", self.started_rows()[-1])` after a run that exited `suite.BUSY_EXIT`; `"def run"`
  (`ccp/suite.py`) returns `BUSY_EXIT` before it appends its `started` row, so the row read is an earlier run's.
  `git grep -nF 'assertNotIn("lane_skipped", self.started_rows()[-1])' -- tests/test_parallel_lanes.py tests/test_suite_cache_probe.py`
  at `becb6417`: 3 lines, the third in `test_a_free_lane_runs_no_probe`, whose run did start.

**Ruled.**

- **Kinds.** A `section_re` pattern may hold a group named `kind`. The Python pack's becomes
  `^(?P<kind>FAIL|ERROR|UNEXPECTED SUCCESS): ` (what it matches is unchanged). `_failed` returns each failing test's
  id and kind (the `kind` group's text, None when the pattern that matched has no such group). A row gains
  `failed_kinds`, one entry per `failed` id in the same order, left out when every entry is None; `failed` is
  unchanged. `lines` adds the row's distinct kinds, in first-seen order joined by ` and `, after the test id:
  `mutant 1: killed (<test id>, ERROR)`, `mutant 2: killed (<test id>, FAIL and ERROR)`; a row without
  `failed_kinds` prints as now. The schema's `suite.summary.section_re` description names the group. New tests
  `tests.test_mutate_interface.SeveralTests.test_a_row_keeps_each_failing_test_s_kind` (one mutant failing an
  assertion, one raising `NameError`: kinds `FAIL` and `ERROR`) and
  `tests.test_mutate.Outcomes.test_the_stderr_line_names_the_failing_kinds`.
- **Line list.** `_once` lists at most the first ten lines, then ` and <k> more`: `the old text is in calc.py 12
  times, at lines 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 and 2 more; a mutant names one place`. Ten or fewer read as now. New
  test `tests.test_mutate_refusals.TextMutants.test_an_old_text_found_many_times_names_ten_lines_and_counts_the_rest`.
- **Cold-run tests.** In the two cold-run tests, the `assertNotIn("lane_skipped", self.started_rows()[-1])` after the
  busy exit becomes an assertion that the number of `started` rows did not change across that run.
  `test_a_free_lane_runs_no_probe` keeps its assertion.
- No other test expectation changes.

## Scope

- **In:** `ccp/mutate.py` (`_failed`, the row, `lines`, `_once`); `ccp/doclang/python.py` (`SUMMARY["section_re"]`);
  `contracts/plane_config.schema.json` (the `section_re` description only); `tests/test_mutate.py`;
  `tests/test_mutate_interface.py`; `tests/test_mutate_refusals.py`; `tests/test_parallel_lanes.py`;
  `tests/test_suite_cache_probe.py`; the SPEC, signed:

  CURRENT (`docs/spec/03-quality.md` at `becb6417`), §20.6, *Bound to the calling seat's run*:
  > Each mutant adds a row to the run record's `mutation` list: the id of the test whose run decided its outcome (the one that failed, else the last), the ids of the failing tests that run's output names (the text after each line's `section_re` match, §14.2), the mutant's number, `kind` (`text`, `patch`, `revert` or `together`), the files it touched, a 12-character digest, the outcome, the exit code, the seconds, `timed_out` and the worktree's name; never the mutant's text, old or new, or the test's output, which goes to `<run record>-mutate.log` beside the run record. The call ends with one `run`/`recorded` event (run id and the counts) and prints on stderr one line per mutant, `mutant <n>: <outcome> (<test id>)`, the test that decided it.

  PROPOSED:
  > Each mutant adds a row to the run record's `mutation` list: the
  > id of the test whose run decided its outcome (the one that failed, else the last), the ids of the
  > failing tests that run's output names (the text after each line's `section_re` match, §14.2), each one's kind in
  > `failed_kinds` when the pattern that matched it has a group named `kind` (that group's text, such as `FAIL` or
  > `ERROR`), the mutant's number, `kind` (`text`, `patch`, `revert` or `together`), the files it
  > touched, a 12-character digest, the outcome, the exit code, the seconds, `timed_out` and the worktree's name;
  > never the mutant's text, old or new, or the test's output, which goes to `<run record>-mutate.log`
  > beside the run record.
  > The call ends with one `run`/`recorded` event (run id and the counts) and prints on stderr one line per mutant,
  > `mutant <n>: <outcome> (<test id>)`, the test that decided it, with the failing tests' kinds after the id when the
  > row has them (`mutant <n>: killed (<test id>, ERROR)`).

  Nothing retired: the two clauses are added.
- **Out:** whether an error-only kill counts as `killed` (`docs/ROADMAP.md`); the suite summary's own use of
  `section_re`; `ccp mutate` naming a module's test ids (`docs/ROADMAP.md`).

## dod_checks

- id: `spec-01`
  story: As the operator, §20.6 says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0354`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`becb6417`, with this brief): exit 1, the PROPOSED passage not found.
- id: `code-01`
  story: As a reviewer, a mutant's row and stderr line say whether its failing tests failed or errored.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_mutate_interface.SeveralTests.test_a_row_keeps_each_failing_test_s_kind tests.test_mutate.Outcomes.test_the_stderr_line_names_the_failing_kinds tests.test_mutate_interface tests.test_mutate`.
  expect: exit 0.
  dry run (`becb6417`): exit 1, 2 errors (`AttributeError: type object 'SeveralTests' has no attribute 'test_a_row_keeps_each_failing_test_s_kind'`, and the same for `Outcomes`'s new test).
- id: `code-02`
  story: As a worker, a mutant whose old text is everywhere is refused with a short line list.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_mutate_refusals.TextMutants.test_an_old_text_found_many_times_names_ten_lines_and_counts_the_rest tests.test_mutate_refusals`.
  expect: exit 0.
  dry run (`becb6417`): exit 1 (`AttributeError: type object 'TextMutants' has no attribute 'test_an_old_text_found_many_times_names_ten_lines_and_counts_the_rest'`).
- id: `test-01`
  story: As a maintainer, the cold-run lock tests assert on the run they name.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `git grep -nF 'assertNotIn("lane_skipped", self.started_rows()[-1])' -- tests/test_parallel_lanes.py tests/test_suite_cache_probe.py`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_parallel_lanes tests.test_suite_cache_probe`.
  expect: step 1 prints one line, in `tests/test_suite_cache_probe.py`; step 2 exits 0.
  dry run (`becb6417`): step 1 printed 3 lines; step 2 exit 0.

## Implementation notes

## Verification notes
