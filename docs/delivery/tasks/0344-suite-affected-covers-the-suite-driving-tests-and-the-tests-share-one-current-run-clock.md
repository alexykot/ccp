---
task_id: 0344-suite-affected-covers-the-suite-driving-tests-and-the-tests-share-one-current-run-clock
title: This repo's suite.affected_map names the test modules that drive ccp suite through a subprocess, so suite run --affected selects them for a change to ccp/suite.py; the tests' copies of a fixed past-day run clock become one helper anchored at the real time, and 0340's expiry patches go; E17's check reads a single-quoted f-string, and the docs sync builds no binding path of its own
status: pending
kind: feature
depends_on: []
spec_refs: ["S14"]
rule_refs: ["E17"]
review_refs: ["ar-20261125T094654Z-c8a0#F03", "ar-20261125T094654Z-c8a0#F04"]
review_point: R37
paths: ["docs/delivery/plane.json", "scripts/sync-product-docs.sh", "tests/helpers.py", "tests/CLAUDE.md", "tests/test_run_clock.py", "tests/review_flow.py", "tests/test_formal_submit.py", "tests/test_full_lane_prompt.py", "tests/test_health_conflicts.py", "tests/test_marked_checks_loop.py", "tests/test_prompt_rounds.py", "tests/test_report_correction.py", "tests/test_resolution_review.py", "tests/test_review_gate.py", "tests/test_review_skip.py", "tests/test_review_skip_clean.py", "tests/test_review_skip_provers.py", "tests/test_stale_context_audience.py", "tests/test_verify_record_head.py"]
clashes_with: ["0191-the-grace-release-ends", "0343-the-reviewer-and-verifier-definitions-leave-their-templates-instructions-to-them-and-the-lanes-line-gives-whole-commands"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0344-suite-affected-covers-the-suite-driving-tests-and-the-tests-share-one-current-run-clock

## Intent

A reviewer who runs `ccp suite run --affected` on a change to `ccp/suite.py`, as the review prompt tells them to, runs
the test modules that drive `ccp suite` through a subprocess too, so a failure there surfaces at review, not at
verify. And a test of a rule that compares a run's stamp with the real time sees runs stamped now, not a month ago:
the tests share one run clock, so no test patches a bound away to survive its own clock. House rule E17's check
catches a binding path built outside `ccp/lib.py` however its f-string is quoted, and the docs sync builds none.

## Context (not checked)

Findings F03 and F04 of architect pass `ar-20261125T094654Z-c8a0` (`docs/delivery/reviews/ar-20261125T094654Z-c8a0.md`),
which also absorb two follow-ups the lead passed to that pass: 0339's (`--affected` missing the modules that reach
`ccp/suite.py` only through a `ccp` subprocess) and 0340's (a shared fake-clock fixture). Also 0331's follow-up on
E17's grep missing a single-quoted f-string, which the triage measured has a hit, so it is widened here with the fix.

Measured at `704ca8de`:

- **F03.** `CCP_DEV=1 ./bin/ccp suite affected --paths ccp/suite.py` lists 18 modules and none of
  `tests.test_suite_wait`, `tests.test_suite_cold` and `tests.test_marked_checks_loop`: each reaches `ccp/suite.py`
  only through `tests.suite_fixture`'s `ccp_proc`, which runs `ccp suite run` as a subprocess
  (`git grep -l 'suite_fixture' -- 'tests/test_*.py'`: 12 modules, the other 9 selected already). plane.json
  `suite.affected_map` maps only `docs/delivery/plane.json`.
- **F04.** `git grep -n 'ccp.runs.iso' -- tests`: 18 lines, 17 in 13 test modules (`test_formal_submit`,
  `test_full_lane_prompt`, `test_health_conflicts`, `test_marked_checks_loop`, `test_prompt_rounds` ×2,
  `test_report_correction`, `test_resolution_review`, `test_review_gate` ×3, `test_review_skip`,
  `test_review_skip_clean` ×2, `test_review_skip_provers`, `test_stale_context_audience`, `test_verify_record_head`)
  and one in `tests/review_flow.py` (the report counted 14 modules). Each builds
  `iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))`, one minute a call.
  `git grep -n 'PENDING_EXPIRY_S", float' -- tests`: `tests/review_flow.py` and `tests/test_formal_submit.py`, 0340's
  patches ("the clock's past day expires no run").
- **E17.** plane.json `architect.checks` `E17` greps `bindings_dir() / f"{` with `-F`, so a single-quoted f-string
  passes it. `git grep -nP 'bindings_dir\(\) / f["\x27]\{' -- ccp scripts ':(exclude)ccp/lib.py'`: 1 line,
  `scripts/sync-product-docs.sh` (`fail(f"no project binding {yml or lib.bindings_dir() / f'{project}.yaml'}")`), an
  error message building a binding path itself. In a scratch worktree, `x = bindings_dir() / f'{pid}.yaml'` planted
  in `ccp/otel.py` passes the old grep and is found by the widened one.

**Ruled.**

- **F03.** plane.json `suite.affected_map` gains `"ccp/suite.py": ["tests.test_suite_wait", "tests.test_suite_cold",
  "tests.test_marked_checks_loop"]`, beside its existing key. The language pack is unchanged: following a test's
  fixture imports would select nearly every module for any change to `ccp` (`tests/toolkit_fixture.py` imports
  `ccp.cli`), and §14.7 states the pack's rule.
- **F04.** `tests/helpers.py` gains `run_clock(case, *where, start=None)`: it patches each dotted name in `where`
  (default `("ccp.runs.iso",)`) with one shared generator of stamps in the `iso()` form, one minute apart, the first
  at `start` or, by default, the real UTC time at the call, to the minute, and stops the patches at the case's
  cleanup. Each of the 18 sites calls it (`review_flow.py` and `test_report_correction.py` with `"ccp.runs.iso",
  "ccp.report.iso"`). A module whose assertions name a stamp of the old day passes `start="2026-10-22T10:00:00Z"`,
  except `tests/review_flow.py` and `tests/test_formal_submit.py`, which take the default and drop their
  `PENDING_EXPIRY_S` patches. `tests/CLAUDE.md`'s `helpers.py` bullet names `run_clock`. New module
  `tests/test_run_clock.py`, test `tests.test_run_clock.RunClock.test_a_run_opened_on_the_default_clock_has_not_expired`:
  the first stamp is within two minutes of the real time, stamps strictly increase, and `ccp.runs.expired` on a
  pending record opened at the first stamp is false at the real time.
- **E17.** The `E17` entry's second grep becomes `! git grep -nP 'bindings_dir\(\) / f["\x27]\{' -- ccp scripts
  ':(exclude)ccp/lib.py'` (in plane.json's JSON, `\\(`, `\"` and `\\x27` escaped); its first grep is unchanged.
  `scripts/sync-product-docs.sh`'s message becomes `f"no project binding {yml}"` when `yml` names a file path and
  `f"no project binding for {project} in {lib.bindings_dir()}"` when it is None. E17's text is unchanged.
- No other test expectation changes.

## Scope

- **In:** `docs/delivery/plane.json` (`suite.affected_map`, `architect.checks` `E17`); `scripts/sync-product-docs.sh`; `tests/helpers.py`; `tests/CLAUDE.md`;
  `tests/test_run_clock.py` (new); `tests/review_flow.py`; and the 13 test modules listed above.
- **Out:** `ccp/doclang/python.py` (the reader's rule); `templates/prompts/review.md`; `ccp/runs.py`
  (`PENDING_EXPIRY_S` and the expiry rule); `tests/test_run_abandon.py` (its `PENDING_EXPIRY_S` arithmetic tests the
  bound itself); the other `2026-10-22` literals in tests that do not feed `runs.iso` or `report.iso`.

## dod_checks

- id: `cmd-01`
  story: As a reviewer, suite run --affected on a change to ccp/suite.py selects the modules that drive ccp suite by subprocess.
  setup: A checkout of the PR head, with `QUEUE_ROOT` naming a scratch queue directory (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite affected --paths ccp/suite.py 2>/dev/null | grep -cxE 'tests\.(test_suite_wait|test_suite_cold|test_marked_checks_loop)'`.
  expect: prints `3`.
  dry run (`704ca8de`): printed `0`, exit 1.
- id: `code-01`
  story: As a test writer, one current run clock serves every test, and no test patches the expiry bound to survive it.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `git grep -n -e 'ccp.runs.iso' -e 'PENDING_EXPIRY_S", float' -- 'tests/test_*.py' tests/review_flow.py`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_run_clock.RunClock.test_a_run_opened_on_the_default_clock_has_not_expired tests.test_formal_submit tests.test_review_gate`.
  expect: step 1 prints nothing (git grep's exit 1, no match); step 2 exits 0.
  dry run (`704ca8de`): step 1 printed 20 lines (18 clock sites, 2 expiry patches), exit 0; step 2 exit 1 (`ModuleNotFoundError: No module named 'tests.test_run_clock'`).

- id: `rule-01`
  story: As the architect, E17's check finds a binding path built outside ccp/lib.py whatever its f-string quotes, and none is left.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nP 'bindings_dir\(\) / f["\x27]\{' -- ccp scripts ':(exclude)ccp/lib.py'`.
    2. Run `git grep -c 'x27' -- docs/delivery/plane.json`.
  expect: step 1 prints nothing (git grep's exit 1, no match); step 2 prints `docs/delivery/plane.json:1`.
  dry run (`704ca8de`): step 1 printed `scripts/sync-product-docs.sh:111: …`, exit 0; step 2 printed nothing, exit 1.

## Implementation notes

## Verification notes
