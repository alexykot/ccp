---
task_id: 0310-worker-briefs-name-suite-run-affected-and-log-texts-follow-the-pruning-of-every-suite-run-log
title: Worker briefs name ccp suite run --affected in place of the suite affected hand-off, the log texts follow §14.4's pruning of every suite-run log, the full-log test closes its pipe, and lib names its retired review event types
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S19"]
rule_refs: ["E9", "E13"]
review_point: R30
paths: ["ccp/prompt.py", "plugin/agents/delivery-implementer.md", "tests/test_full_lane_prompt.py", "ccp/config.py", "contracts/plane_config.schema.json", "ccp/suite.py", "tests/test_suite_wait.py", "tests/test_suite_full_log.py", "scripts/observability/lib.py"]
clashes_with: ["0191-the-grace-release-ends"]
adopt: "none"
created: 2026-11-23
updated: 2026-11-23
---

# Task: 0310-worker-briefs-name-suite-run-affected-and-log-texts-follow-the-pruning-of-every-suite-run-log

## Intent

The leftovers of 0299 and 0308 close. A worker's Lanes line and the implementer's brief point at
`ccp suite run --affected` for the tests a change touches, which 0299 built, instead of telling the
worker to copy the module list `ccp suite affected` prints into a `--lane part` run. The plane.json
text for `suite.log_keep_days` and the line `ccp suite wait` prints for a run with no log say what is
true since 0299: every recorded suite run keeps a log and every such log is pruned. The ClosedLog test
closes the pipe it opens, so a verbose run prints no ResourceWarning. And lib says, in one comment, that
`architecture_review` and `docs_audit` are the retired review kinds' types, kept so an older ledger reads.

## Context (not checked)

Covers these open follow-ups (`ccp --root . tasks follow-ups --open`), `0299` and `0308` standing for
`0299-the-pre-gate-and-review-run-what-the-branch-touches-and-every-recorded-suite-run-keeps-a-log` and
`0308-module-docstrings-and-queue-docs-stop-restating-the-spec`:

- `0299/implement#1` (the Lanes line and `SUITE_LANES` still name `ccp suite affected`): `code-01`. Its §14.7 half
  is ruled below: no SPEC change.
- `0299/review#1`, `0299/fix#1`, `0299/verify#1` ("summary-mode logs"): `code-02`.
- `0299/implement#2`, `0299/review#2` (`ended_summary`'s "no log was kept (--full)"): `code-03`.
- `0299/verify#2` (the ClosedLog ResourceWarning): `code-04`.
- `0308/implement#2` (the retired review event types' comment): `code-05`.

`0299/review#3` (a staged part lane) is task 0311. Measured at `e13c1380` (origin/main) unless a line says otherwise.

- **The prompts already run `--affected`; the Lanes line and one brief do not.** 0299 rewrote the pre-gate
  (`templates/prompts/_gate.md`, shared by the implement, fix and merge prompts) and the review prompt
  (`templates/prompts/review.md`) to `ccp suite run --affected --since origin/<integration>...`:
  `git grep -n -e '--affected' -- templates/prompts` at `e13c1380`: 2 lines. What still hands the list over:
  `git grep -n 'suite affected' -- ccp/prompt.py plugin/agents templates/prompts` at `e13c1380`: 3 lines,
  `"def suite_lanes"`'s docstring and its `_as` text in `ccp/prompt.py`, and the bullet of
  `plugin/agents/delivery-implementer.md` that starts "After you merge the integration branch in". The rendered
  Lanes line for this repo's plane.json (a probe at `e13c1380`, `python3 -B -c 'from pathlib import Path; from ccp import config, prompt; print(prompt.suite_lanes(config.load(Path(".")), "review"))'`)
  reads "`--lane part` with `scripts/gate.sh <modules>` after `--`: the tests you run, as `ccp suite affected` prints it (…)".
  `tests/test_full_lane_prompt.py` pins that text (`git grep -n 'suite affected' -- tests/test_full_lane_prompt.py` at `e13c1380`: 1 line).
- **`--affected` takes no `--lane`.** `docs/cli/02-delivery.md` gives `ccp suite run [--lane L | --affected [--since REF]] …`,
  and `QUEUE_ROOT=<scratch> CCP_DEV=1 ./bin/ccp suite run --lane part --affected` at `e13c1380` printed
  "ccp suite: --affected picks the lane itself: give no --lane", exit 2. So the briefs name `ccp suite run --affected`,
  never `--lane part --affected`.
- **No SPEC change for the stderr line.** §14.7 says `ccp suite affected` prints, on stderr, `ccp suite run --lane <part lane> -- <command> <modules>`,
  and that `ccp suite run --affected` runs what that line names. Both are still true, and the line still serves a reader of
  `ccp suite affected`; only the briefs change. `git grep -n 'suite affected' -- docs/spec` at `e13c1380`: 1 line, §14.7's
  synopsis ("so a worker picks the `part` lane from them after a merge or a fix instead of guessing"), still true:
  `--affected` picks from the same list.
- **"summary-mode logs".** §14.4's bullet **Logs are pruned** says a recording `ccp suite run` removes suite-run logs
  (`runs/<task>/*-suite-st-*.log`, `runs/_suite-logs/st-*.log`) older than 14 days. `git grep -n -i 'summary-mode' -- ccp/config.py contracts/plane_config.schema.json`
  at `e13c1380`: 3 lines, the comment before `SUITE_DEFAULTS`' notes (`` # `log_keep_days`: ``), the `suite.log_keep_days` error in config
  validation, and the key's `description` in the schema (which also cites "SPEC §14.1" for it). No test pins either text
  (`git grep -n 'summary-mode\|days a summary' -- tests` at `e13c1380`: no line).
- **The no-log line.** `"def ended_summary"` (`ccp/suite.py`) ends a run whose row has no `log` with "ccp suite: no log was kept (--full)".
  Since 0299 a recorded `--full` run keeps a log, so a row with none is a run whose log could not be opened, in either mode, or a row
  from before 0299. Probe at `e13c1380`: `python3 -B -c 'from ccp import suite; print(suite.ended_summary(None, None, {"suite_id": "st-x", "exit_code": 0, "seconds": 1, "log": None}), end="")'`
  printed that line. `git grep -n 'no log was kept' -- ccp tests docs` at `e13c1380`: 1 line, in `ccp/suite.py`; no test pins it.
- **The ResourceWarning.** `ClosedLog.test_a_pump_outliving_the_closed_log_writes_nothing_to_the_file_its_fd_number_names_next`
  (`tests/test_suite_full_log.py`) wraps the pipe's read end in `src = os.fdopen(src_r, "rb", buffering=0)` and never closes it.
  `QUEUE_ROOT=<scratch> CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -W always::ResourceWarning -m unittest -v tests.test_suite_full_log`
  at `e13c1380`: passed, 3 tests; `grep -c ResourceWarning <its log>`: 2 lines ("unclosed file <_io.FileIO name=4 mode='rb' closefd=True>"
  and tracemalloc's hint).
- **The retired review types.** 0308 cut the comment above `REVIEW_EVENT_TYPES` in `scripts/observability/lib.py`, which also said
  the first two types are retired (§19.12) and stay so an older ledger reads. They are still in `REVIEW_EVENT_TYPES`, `EVENT_TYPES`,
  lib's op table and the event contract's enum, and nothing writes them: `git grep -n '"architecture_review"\|"docs_audit"' -- ccp scripts plugin templates`
  at `e13c1380`: 11 lines, all in `scripts/observability/lib.py` (the constant and its ten op-table rows). `grep -n -B1 '^REVIEW_EVENT_TYPES' scripts/observability/lib.py`
  at `e13c1380` shows the `ACTORS` line before it, no comment. `LEGACY_ACTORS` and `LEGACY_EVENT_TYPES` carry the same fact as
  one-line comments, which is where it goes here; moving the two types into `LEGACY_EVENT_TYPES` would stop lib folding them,
  a change of behaviour this task does not make.
- **Other tasks.** A script over the pending tasks' `paths` at `e13c1380` (0191, 0296, 0300, 0303, 0304, 0305, 0306, 0307, 0309, 0311):
  0191 names `ccp/config.py`, `ccp/prompt.py`, `scripts/observability/lib.py`, the plane.json schema and `tests/`, recorded as a clash;
  0303 names `ccp/prompt.py` (the prompt audit) and `scripts/observability/lib.py` (`validate_event` and `LEGACY_ACTORS`' comment),
  0296 names lib.py's config loader and `project_id`, 0300 names `ccp/suite.py` (a new `section_patterns`), and 0311 names
  `ccp/suite.py` (`affected_plan`): each changes other logic, so none is a clash.

### Rulings for the build (the lead's)

- **The Lanes line.** In `"def suite_lanes"`, the declared part argv's `_as` text becomes
  ``", or `ccp suite run --affected` for the modules a change touches"``, so the review Lanes line reads "… the tests you run, or
  `ccp suite run --affected` for the modules a change touches (…)". The docstring's "as `ccp suite affected` prints it (§14.7)"
  becomes "or `ccp suite run --affected` picks them (§14.7)". The other branches are unchanged.
  `DeclaredPartLane.test_a_declared_part_argv_takes_the_module_names_after_it` asserts the new text in place of the old.
- **The implementer brief.** The bullet in `plugin/agents/delivery-implementer.md` becomes: "After you merge the integration
  branch in, or change code, run the tests the change touches with `ccp suite run --affected` (`--since <ref>` for what a merge
  brought in), not a guess at module names."
- **The log texts.** The `config.py` comment:
  ``# `log_keep_days`: suite-run logs in the queue older than this are removed when a recording run starts (§14.4).``
  The error: `suite.log_keep_days must be an integer >= 1 (days a suite-run log is kept)`. The schema description:
  ``Constant, 14 (SPEC §29.3): SPEC §14.4: suite-run logs in the queue (runs/<task>/*-suite-st-*.log, runs/_suite-logs/st-*.log) older than this many days are removed when a recording `ccp suite run` starts. Default 14. A value set here other than the constant still applies, with a warning, until the key is deleted.``
  The schema's shape is unchanged.
- **The no-log line** becomes "ccp suite: no log was recorded for this run". A new test in `tests/test_suite_wait.py`,
  `test_a_run_with_no_log_says_none_was_recorded`, waits on an ended row with `"log": None` and asserts that line, and that `--full`
  is not in the output.
- **The pipe.** The test closes `src` (an `addCleanup(src.close)` or a `finally`), after the pump has stopped; nothing else in the
  test changes.
- **The comment.** One line right above `REVIEW_EVENT_TYPES`: "# architecture_review and docs_audit: the retired review kinds' types
  (§19.12), still read so an older ledger folds; nothing writes them (E9)". No SPEC, contract or ENGINEERING.md text.

### Ruling round 1 (the lead's)

> Ruling 0310-worker-briefs-name-suite-run-affected-and-log-texts-follow-the-pruning-of-every-suite-run-log-r1 (lead, 2026-11-24, spec question sm-20261124T015714Z-167e, spec commit b1a2ca0aa47bc3d4e3246aaac9033018f7c3cf5a):
> Option (A) as built. The bullet in plugin/agents/delivery-implementer.md names the suite run's --affected without restating the full ccp suite run command, so SPEC §13.5's one statement holds and both tests stay unchanged. The ruled wording's intent was to point at --affected, not to add a second command statement. No check changes: code-01 pins the Lanes line in ccp/prompt.py, not this bullet.

## Scope

- **In:** `ccp/prompt.py` (`suite_lanes`), `plugin/agents/delivery-implementer.md`, `tests/test_full_lane_prompt.py`,
  `ccp/config.py` (the comment and the error text), `contracts/plane_config.schema.json` (`suite.log_keep_days`' description),
  `ccp/suite.py` (`ended_summary`), `tests/test_suite_wait.py`, `tests/test_suite_full_log.py`, `scripts/observability/lib.py`
  (one comment line).
- No SPEC change (measured in Context).
- **Out:** §14.7's stderr line and `ccp suite affected` itself; a staged part lane (0311); the templates under `templates/prompts`,
  which already name `--affected`; the other agent briefs; moving the retired types into `LEGACY_EVENT_TYPES`.

## dod_checks

- id: `code-01`
  story: As a worker, my Lanes line and the implementer's brief point me at `ccp suite run --affected` for what my change touches.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `git grep -n 'suite affected' -- ccp/prompt.py plugin/agents templates/prompts`.
    2. Run `python3 -B -c 'from pathlib import Path; from ccp import config, prompt; print(prompt.suite_lanes(config.load(Path(".")), "review"))'`.
    3. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_full_lane_prompt`.
    4. Run `grep -e a_declared_part_argv_takes_the_module_names_after_it -e '^OK' <the log step 3 names>`.
  expect: step 1 prints nothing (exit 1); step 2 prints a line holding "the tests you run, or `ccp suite run --affected` for the modules a change touches"; step 3 exits 0; step 4 lists `test_a_declared_part_argv_takes_the_module_names_after_it` `ok`, then `OK`.
  dry run (`e13c1380`): step 1 printed 3 lines (`ccp/prompt.py` twice, `plugin/agents/delivery-implementer.md` once); step 2 printed "… the tests you run, as `ccp suite affected` prints it (…)"; step 3 (scratch QUEUE_ROOT) printed `passed, exit 0, lane part … 13 tests`; step 4 on its log listed the test `ok`, then `OK`.
- id: `code-02`
  story: As an operator reading plane.json's schema or a refusal, `suite.log_keep_days` is the age of every suite-run log, not only summary mode's.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n -i 'summary-mode' -- ccp/config.py contracts/plane_config.schema.json`.
    2. Run `git grep -n 'suite-run log' -- ccp/config.py contracts/plane_config.schema.json`.
  expect: step 1 prints nothing (exit 1); step 2 prints exactly 3 lines: two in `ccp/config.py` (the comment and the error) and one in `contracts/plane_config.schema.json` (the description, citing `SPEC §14.4`).
  dry run (`e13c1380`): step 1 printed 3 lines; step 2 printed nothing.
- id: `code-03`
  story: As a worker waiting on a run that kept no log, `ccp suite wait` says no log was recorded, not that `--full` kept none.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `python3 -B -c 'from ccp import suite; print(suite.ended_summary(None, None, {"suite_id": "st-x", "exit_code": 0, "seconds": 1, "log": None}), end="")'`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_suite_wait`.
    3. Run `grep -e a_run_with_no_log_says_none_was_recorded -e '^OK' <the log step 2 names>`.
  expect: step 1's last line is `ccp suite: no log was recorded for this run`, and `--full` appears nowhere in its output; step 2 exits 0; step 3 lists `test_a_run_with_no_log_says_none_was_recorded` `ok`, then `OK`.
  dry run (`e13c1380`): step 1's last line was `ccp suite: no log was kept (--full)`; step 2 (scratch QUEUE_ROOT) printed `passed, exit 0, lane part … 13 tests`; step 3 on its log printed only `OK` (the test is new).
- id: `code-04`
  story: As a developer running the full-log tests verbosely, no unclosed pipe is reported.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -W always::ResourceWarning -m unittest -v tests.test_suite_full_log`.
    2. Run `grep -c ResourceWarning <the log step 1 names>`.
  expect: step 1 exits 0 with 3 tests; step 2 prints `0`.
  dry run (`e13c1380`): step 1 (scratch QUEUE_ROOT) printed `passed, exit 0, lane part … 3 tests`; step 2 printed `2`.
- id: `code-05`
  story: As a reader of lib, the two retired review types are named as such where the type list is.
  setup: A checkout of the PR head.
  steps:
    1. Run `grep -n -B1 '^REVIEW_EVENT_TYPES' scripts/observability/lib.py`.
  expect: the line before `REVIEW_EVENT_TYPES` is a comment holding `architecture_review`, `docs_audit`, `§19.12` and `E9`; `REVIEW_EVENT_TYPES` itself still lists `"architecture_review", "docs_audit", "architect"`.
  dry run (`e13c1380`): the line before it was the `ACTORS = …` line, no comment.

## Implementation notes

- Premises re-measured at `f7b43ccf`: every figure in Context held (2 `--affected` lines in templates/prompts; 3 `suite affected`
  lines in prompt.py and the implementer brief; 1 in the test; 3 `summary-mode` lines; 1 `no log was kept`; 11 retired-type lines).
- `suite_lanes`, the config comment and error, the schema description, `ended_summary`'s line, the lib comment and both tests
  follow the rulings word for word.
- **The implementer bullet departs from the ruled text.** The ruled sentence names `ccp suite run --affected`, a second
  `ccp suite run` in `plugin/agents/delivery-implementer.md`, which §13.5's "One statement of each rule" forbids (a worker
  definition names the command only in §13.1's evidence rule) and which `test_suite.ReportCrossCheck.test_the_prompt_tells_workers_to_use_it`
  and `test_worker_efficiency.Definitions.test_the_suite_rule_is_stated_once_in_the_prompt` hold. The bullet reads "run the tests
  the change touches with the suite run's `--affected` (`--since <ref>` for what a merge brought in), not a guess at module names":
  the ruling's meaning without restating the command. Raised with the runner as an open question.
- The ClosedLog pipe closes through `addCleanup(src.close)`, which runs after the test body's `pump.join`.
- Ruling round 1: the lead kept the implementer bullet as built (option A), so §13.5's one statement holds; the ruling is
  recorded in Context and no code, test or doc changed.

## Verification notes
