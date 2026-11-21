---
task_id: 0260-review-tools-and-the-tests-for-new-behaviour-section
title: The review prompt names the affected-modules command and the reviewer brief a base checkout, and the report table asks for and checks the tests-for-new-behaviour section
status: pending
kind: feature
depends_on: ["0257-one-gate-block-and-one-sentence-per-line"]
clashes_with: ["0219-integration-merges-leave-out-the-tip", "0258-the-plane-writes-the-pre-merge-phases"]
spec_refs: ["S13", "S15"]
review_refs: ["ar-20261121T111633Z-4e26#F02", "ar-20261121T111633Z-4e26#F03"]
rule_refs: ["E13"]
review_point: R19
paths: ["templates/prompts/review.md", "templates/prompts/implement.md", "templates/prompts/fix.md", "templates/prompts/merge.md", "templates/prompts/ruling.md", "plugin/agents/delivery-reviewer.md", "ccp/report.py", "tests/test_prompt_tools.py", "tests/test_worker_efficiency.py", "tests/test_report_tests_section.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0260-review-tools-and-the-tests-for-new-behaviour-section

## Intent

A reviewer picks the test modules a PR touches with the same command the implementer uses, and
reads or runs code at the PR's merge base through `ccp wt`, instead of guessing modules and
improvising checkouts. The `## Tests for new behaviour` list the reviewer checks is asked for in the
rendered prompt's last part, from the report table, and `ccp report` refuses a done implement, fix,
merge or ruling report without it, so a missing list is caught when the report is filed, not by the
reviewer.

## Context (not checked)

Measured at `1aa5e3f`.

- From architect pass `ar-20261121T111633Z-4e26`, F02 and F03 (the record is in
  `docs/delivery/reviews/`).
- **The affected-modules command.** `git grep -c 'suite affected' -- templates/prompts` at `1aa5e3f`:
  `fix.md`, `implement.md`, `merge.md`, `ruling.md`, one line each; none in `review.md`. The change
  rounds render `{{ccp}} suite affected --since origin/{{integration}}`. In a detached review
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
- **No SPEC change.** §13.4 already lists the section among the report lines ("for implement, fix,
  merge and ruling, `## Tests for new behaviour` (§13.5)"), and §13.5 describes the self-check
  (`git grep -n 'Tests for new behaviour' -- docs/spec` at `1aa5e3f`: 2 lines). Every other report
  line §13.4 lists is refused when missing; this task makes this one the same.
- **Rulings for the build** (the lead's):
  - The section is a `report.SECTIONS` entry for the implement, fix, merge and ruling phases,
    required with `Outcome: done`: `- ` (or `* `) lines, or a single line beginning `none` followed
    by why. A done report without it, or with an empty section, is refused (exit 1, nothing
    written), naming the section. The run keeps nothing new.
  - The four change-round templates keep the self-check instruction (list each branch, field,
    refusal or behaviour the diff adds or changes, with the test that fails without it, and write
    the missing tests) and name neither the section's heading nor its format: those come from the
    last part. `review.md` keeps its one sentence telling the reviewer to check those lists.
  - `review.md` renders the affected-modules command with `--since origin/{{integration}}`, as the
    change rounds do, for the reviewer's part-lane run.
  - The reviewer brief names `ccp wt create --kind base --task <task_id> --sha <merge base> --
    <command>` (the merge base from `git merge-base origin/<integration> <PR head>`) for reading or
    running code at the base, and says never a hand-made checkout, `git archive` or `--kind mut` for it.
- **Ordering.** `depends_on` 0257, which rewrites every template one sentence per line and depends on
  every pending template task; clashes with 0219 and 0258, which edit `ccp/report.py`.

## Scope

- **In:** `templates/prompts/review.md`, `templates/prompts/implement.md`, `templates/prompts/fix.md`,
  `templates/prompts/merge.md`, `templates/prompts/ruling.md`, `plugin/agents/delivery-reviewer.md`,
  `ccp/report.py` (the new `SECTIONS` entry and its reader), `tests/test_prompt_tools.py`,
  `tests/test_worker_efficiency.py` (its three lines that pin the section's template wording),
  `tests/test_report_tests_section.py` (new).
- **Out:** `ccp suite affected` itself (unchanged), the verifier brief, the SPEC, the run record.

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

## Implementation notes

## Verification notes
