---
task_id: 0260-review-tools-and-the-tests-for-new-behaviour-section
title: Every round names the affected-modules command against the integration tip, the reviewer brief a base checkout, and the report table asks for and checks the tests-for-new-behaviour section
status: pending
kind: feature
depends_on: ["0255-test-fixtures-shared-helpers-and-one-repo-build", "0257-one-gate-block-and-one-sentence-per-line"]
clashes_with: ["0219-integration-merges-leave-out-the-tip", "0242-retire-restructure-scaffolding-and-queue-markers", "0256-suite-run-refuses-a-closed-run-and-config-reads", "0258-the-plane-writes-the-pre-merge-phases"]
spec_refs: ["S13", "S15"]
review_refs: ["ar-20261121T111633Z-4e26#F02", "ar-20261121T111633Z-4e26#F03", "ar-20261121T132817Z-d5e5#F03"]
rule_refs: ["E13"]
review_point: R19
paths: ["templates/prompts/review.md", "templates/prompts/_gate.md", "ccp/prompt.py", "templates/prompts/implement.md", "templates/prompts/fix.md", "templates/prompts/merge.md", "templates/prompts/ruling.md", "plugin/agents/delivery-reviewer.md", "ccp/report.py", "docs/spec/02-delivery.md", "tests/helpers.py", "tests/test_prompt_tools.py", "tests/test_worker_efficiency.py", "tests/test_report_tests_section.py", "tests/test_board_staleness.py", "tests/test_full_lane_prompt.py", "tests/test_health_conflicts.py", "tests/test_prompt_end.py", "tests/test_prompt_rounds.py", "tests/test_report_correction.py", "tests/test_report_fields.py", "tests/test_report_sections.py", "tests/test_resolution_review.py", "tests/test_review_gate.py", "tests/test_review_skip.py", "tests/test_review_skip_clean.py", "tests/test_review_skip_provers.py", "tests/test_suite.py", "tests/test_tasks_release_keep_branch.py", "tests/test_toolkit.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0260-review-tools-and-the-tests-for-new-behaviour-section

## Intent

A reviewer picks the test modules a PR touches with the same command the implementer uses, and
reads or runs code at the PR's merge base through `ccp wt`, instead of guessing modules and
improvising checkouts. The fix, ruling and merge rounds pick their pre-gate's modules from their own
change against the integration tip, as the implement round does, so a catch-up merge no longer sends
the tip's own modules to the part lane. The `## Tests for new behaviour` list the reviewer checks is asked for in the
rendered prompt's last part, from the report table, and `ccp report` refuses a done implement, fix,
merge or ruling report without it, so a missing list is caught when the report is filed, not by the
reviewer.

## Context (not checked)

Measured at `1aa5e3f`.

- From architect pass `ar-20261121T111633Z-4e26`, F02 and F03 (the record is in
  `docs/delivery/reviews/`).
- **The affected-modules command.** `git grep -c 'suite affected' -- templates/prompts` at `1aa5e3f`:
  `fix.md`, `implement.md`, `merge.md`, `ruling.md`, one line each; none in `review.md`. Only the
  implement round renders `{{ccp}} suite affected --since origin/{{integration}}`; fix, merge and
  ruling render `--since {{head}}` (corrected by the triage of `ar-20261121T132817Z-d5e5`):
  `git grep -n 'suite affected --since {{head}}' -- templates/prompts` at `ce0f4bb`: 3 lines, `fix.md`, `merge.md`, `ruling.md`. In a detached review
  worktree, `ccp suite affected` with no `--since` diffs against `HEAD` and finds nothing
  (`"ref = since or \"HEAD\""` in `ccp/suite.py`). The PR head has caught up with the tip before
  review (§16.5), so `--since origin/{{integration}}` names the PR's own change there too.
- **The base checkout.** `git grep -c 'kind base' -- plugin/agents` at `1aa5e3f`: `delivery-verifier.md` 1, `delivery-reviewer.md` none.
  The reviewer brief says "Read the code at
  the PR's merge base before calling a citation wrong" and names no tool.
- **The section.** `git grep -c 'Tests for new behaviour' -- templates/prompts ccp/report.py` at
  `1aa5e3f`: the four change-round templates and `review.md`, one line each; `ccp/report.py` none.
  `report.SECTIONS` has no such section, so the last part never asks for it and `ccp report` never
  reads it. `merge.md` alone gives its `none` form (`none: the merge adds no behaviour`).
- **SPEC text.** §13.4 already lists the section among the report lines ("for implement, fix,
  merge and ruling, `## Tests for new behaviour` (§13.5)"), and §13.5 describes the self-check
  (`git grep -n 'Tests for new behaviour' -- docs/spec` at `1aa5e3f`: 2 lines). Every other report
  line §13.4 lists is refused when missing; this task makes this one the same, and its §13.4 bullet
  says when it is required and gives its `none` form, describing only this feature (§31.1, Scope).
- **Tests that file done reports.** Requiring the section breaks every test module that files a done
  implement, fix, merge or ruling report without it: `GATE_COLD=1 python3 scripts/gate_parallel.py` in a scratch copy of `7b242fe` with a minimal required section added: 16 modules fail.
  They are `test_board_staleness`, `test_full_lane_prompt`, `test_health_conflicts`,
  `test_prompt_end`, `test_prompt_rounds`, `test_report_correction`, `test_report_fields`,
  `test_report_sections`, `test_resolution_review`, `test_review_gate`, `test_review_skip`,
  `test_review_skip_clean`, `test_review_skip_provers`, `test_suite`,
  `test_tasks_release_keep_branch` and `test_toolkit`.
- **The fix, ruling and merge pre-gate** (architect pass `ar-20261121T132817Z-d5e5`, F03). Those
  rounds merge `origin/<integration>` in before the pre-gate, so `--since {{head}}` (the round's
  starting head) diffs every file the tip brought in. 0215's fix round, measured in the plane's queue
  at triage (data only the queue holds), `grep -e st-20261121T125900Z-e4d8a0 -e st-20261121T130923Z-786580 runs/_suites.jsonl`: part lane 823 tests in 617 s, then the whole gate 3191 tests in 263 s. After the catch-up, `--since origin/{{integration}}` names
  the task's own change and its conflict resolutions, which is what the pre-gate fails fast on; the
  tip's own files passed their gate when they merged. After 0257 the block lives in
  `templates/prompts/_gate.md` (made by 0257), with the since-ref a per-phase difference set in
  `ccp/prompt.py`.
- **Rulings for the build** (the lead's):
  - The section is a `report.SECTIONS` entry for the implement, fix, merge and ruling phases,
    required with `Outcome: done`: `- ` (or `* `) lines, or a single line beginning `none` followed
    by why. A done report without it, or with an empty section, is refused (exit 1, nothing
    written), naming the section. The run keeps nothing new. The rendered last part asks for it from the entry's prompt line.
  - The four change-round templates keep the self-check instruction (list each branch, field,
    refusal or behaviour the diff adds or changes, with the test that fails without it, and write
    the missing tests) and name neither the section's heading nor its format: those come from the
    last part. `review.md` keeps its one sentence telling the reviewer to check those lists.
  - `review.md` renders the affected-modules command with `--since origin/{{integration}}`, for the
    reviewer's part-lane run.
  - The fix, ruling and merge rounds render it with `--since origin/{{integration}}` too, so every
    phase renders the one form and the per-phase difference 0257 sets for it goes.
  - The reviewer brief names `ccp wt create --kind base --task <task_id> --sha <merge base> --
    <command>` (the merge base from `git merge-base origin/<integration> <PR head>`) for reading or
    running code at the base, and says never a hand-made checkout, `git archive` or `--kind mut` for it.
  - The tests file done reports through one shared helper in `tests/helpers.py` that writes a done
    report for a phase, with the section for the four change rounds; the modules listed above use it
    instead of their own report text.
- **Ordering.** `depends_on` 0257, which rewrites every template one sentence per line and depends on
  every pending template task, and 0255, which reworks the shared fixtures and most of those modules
  (it depends on 0227 and 0241, which touch `tests/helpers.py` and `test_toolkit`). Clashes with 0219
  and 0258 (`ccp/report.py`; 0258 also `test_toolkit` and `test_tasks_release_keep_branch`), 0242
  (`test_toolkit`, `test_tasks_release_keep_branch`) and 0256 (`test_suite`).

## Scope

- **In:** `templates/prompts/review.md`, `templates/prompts/implement.md`, `templates/prompts/fix.md`,
  `templates/prompts/merge.md`, `templates/prompts/ruling.md`, `templates/prompts/_gate.md` (new in
  0257; here its since-ref), `ccp/prompt.py` (the since-ref's per-phase value), `plugin/agents/delivery-reviewer.md`,
  `ccp/report.py` (the new `SECTIONS` entry and its reader), `tests/helpers.py` (the done-report
  helper), `tests/test_prompt_tools.py`, `tests/test_worker_efficiency.py` (its three lines that pin
  the section's template wording), `tests/test_report_tests_section.py` (new), and the 16 modules
  listed in Context (their done reports through the helper).
- **SPEC (§31.1: the text only describes this task's feature):** `docs/spec/02-delivery.md` §13.4,
  the report-lines bullet for the section:

  CURRENT (`docs/spec/02-delivery.md` at `7b242fe`):
  > - for implement, fix, merge and ruling, `## Tests for new behaviour` (§13.5);

  PROPOSED:
  > - for implement, fix, merge and ruling with `Outcome: done`, `## Tests for new behaviour` (§13.5): a
  >   `- ` line for each behaviour the round's commits add or change, with the test that fails without
  >   it, or a single line beginning `none` followed by why; a done report without it, or with the
  >   section empty, is refused;
- **Out:** `ccp suite affected` itself (unchanged), the verifier brief, the run record.

## dod_checks

- id: `rv-01`
  story: As a reviewer, my prompt gives me the command that lists the test modules the PR touches.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prompt_tools 2>&1 | grep -i review`.
    2. Run `git grep -c 'suite affected --since origin/{{integration}}' -- templates/prompts/review.md`.
  expect: step 1 prints at least one line ending `ok` for a test that renders the review prompt and finds `suite affected --since origin/<integration>` in it; step 2 prints `templates/prompts/review.md:1`.
  dry run (`1aa5e3f`): step 1 printed no review test; step 2 printed nothing (exit 1).
- id: `rv-02`
  story: As a reviewer, my brief tells me how to read or run code at the PR's merge base.
  setup: A checkout of the PR head.
  steps:
    1. Run `grep -c -- '--kind base' plugin/agents/delivery-reviewer.md`.
  expect: prints `1` or more.
  dry run (`1aa5e3f`): printed `0`.
- id: `rv-03`
  story: As a runner, `ccp report` refuses a done implement report with no tests-for-new-behaviour list, and accepts one with lines or a `none` line.
  setup: A checkout of the PR head; then a separate copy of it with the new `SECTIONS` entry removed from `ccp/report.py`.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_report_tests_section 2>&1 | tail -8`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_report_tests_section`.
  expect: step 1 exits 0, listing as `ok` tests for: a done implement report without the section is refused naming it; one with `- ` lines is accepted; one with the single line `none: the merge adds no behaviour` is accepted for merge; an empty section is refused; a blocked report without it is accepted; a review report is not asked for it. Step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `rv-04`
  story: As a plane developer, the section's heading and format are given once, by the report table, not in four templates.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -c 'Tests for new behaviour' -- templates/prompts`.
    2. Run `python3 -B -m unittest -v tests.test_worker_efficiency 2>&1 | tail -3`.
  expect: step 1 prints exactly one line, `templates/prompts/review.md:1`; step 2 ends `OK`.
  dry run (`1aa5e3f`): step 1 printed five lines (`fix.md`, `implement.md`, `merge.md`, `review.md`, `ruling.md`, 1 each); step 2 n/a (the test changes with the task).

- id: `rv-05`
  story: As the lead, §13.4 describes the section as the brief gives it.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0260`.
  expect: exit 0, the PROPOSED passage found in `docs/spec/02-delivery.md`.
  dry run (simulated, the passage applied to `docs/spec/02-delivery.md` on a scratch branch off `7b242fe`): exit 0, the passage found in `docs/spec/02-delivery.md`.

- id: `rv-06`
  story: As a fixer, ruling worker or merge worker, my pre-gate picks modules from my own change against the integration tip, not from everything the catch-up merge brought in.
  setup: A checkout of the PR head; then a separate copy of it where the fix phase renders `--since {{head}}`, wherever it is set (`_gate.md` or `ccp/prompt.py`).
  steps:
    1. Run `git grep -n 'suite affected --since {{head}}' -- templates/prompts`.
    2. On the head, run `python3 -B -m unittest -v tests.test_prompt_tools.PromptsNameTheTools.test_fix_ruling_and_merge_affected_since_the_tip`.
    3. In the copy, run `python3 -B -m unittest -q tests.test_prompt_tools`.
  expect: step 1 prints nothing (exit 1); step 2 exits 0, its one test (the implementer names it so, in the class `PromptsNameTheTools` of `tests/test_prompt_tools.py`) rendering the fix, ruling and merge prompts and finding `suite affected --since origin/<integration>` in each and the round's head sha after `--since` in none; step 3 exits non-zero.
  dry run (`ce0f4bb`): step 1 printed 3 lines (`fix.md`, `merge.md`, `ruling.md`); steps 2 and 3 n/a — the test is new.

## Implementation notes

## Verification notes
