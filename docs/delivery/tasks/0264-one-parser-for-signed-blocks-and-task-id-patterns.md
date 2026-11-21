---
task_id: 0264-one-parser-for-signed-blocks-and-task-id-patterns
title: The task check warns on a PROPOSED that verify spec-text cannot read, through one signed-block parser in tasklog, and task-id and decision-marker patterns each have one source
status: pending
kind: feature
depends_on: ["0223-a-follow-up-is-tracked-not-left-in-notes", "0234-one-check-parser-and-one-file-at-rev-reader"]
clashes_with: ["0240-plane-workers-run-the-head", "0244-tasks-check-runs-dry-runs"]
spec_refs: ["S3", "S15"]
review_refs: ["ar-20261121T111633Z-4e26#F09", "ar-20261121T111633Z-4e26#F10"]
rule_refs: ["E22", "E23"]
review_point: R19
paths: ["ccp/tasklog.py", "ccp/verify.py", "ccp/refs.py", "ccp/health.py", "ccp/lifecycle.py", "ccp/adr.py", "docs/spec/01-model.md", "docs/ENGINEERING.md", "plugin/skills/writing-tasks/SKILL.md", "tests/test_signed_blocks_check.py", "tests/test_refs.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0264-one-parser-for-signed-blocks-and-task-id-patterns

## Intent

A task writer learns when the task is written, not when three seats hand-search the SPEC, that a
`PROPOSED:` given inline cannot be read by `ccp verify spec-text`: `ccp tasks check` warns on it.
The grammar of signed blocks is read by one function of the task-file parser, which `verify` calls.
And the task-id patterns `health` keeps, and the two descriptions of an ADR decision's marker line
in `adr`, each have one source, as house rule E23 says.

## Context (not checked)

Measured at `1aa5e3f`.

- From architect pass `ar-20261121T111633Z-4e26`, F09 and F10 (the record is in
  `docs/delivery/reviews/`).
- **Signed blocks.** `"def signed_blocks"`, `"def _signed_sections"` and `"def _block_names"` are in
  `ccp/verify.py`. Its docstring: "A `PROPOSED:` with no blockquote under it (one quoted inline, or
  the word in prose) carries none." `ccp/tasklog.py`'s only CURRENT/PROPOSED check is the
  missing-sign-off warning (`"def unsigned_spec_edit"`). Task 0204 carried its PROPOSED inline and
  all three of its seats searched the SPEC by hand (friction notes, quoted in the pass).
  `git grep -n 'signed_blocks' -- ccp tests | wc -l` at `1aa5e3f`: 7 lines.
- **Task-id patterns.** `"def _merge_task_re"` and `"def _branch_task_re"` in `ccp/health.py`;
  `ccp/lifecycle.py` calls `health._branch_task_re`. House rule E23's known-intentional list names
  only health's squash-subject pattern (`_written_task_re`), which stays.
- **Decision markers.** `ccp/adr.py` holds `_MARK_PARTS`/`_HEAD_PARTS` (matching with groups) and
  `_DEC_HEAD`/`_DEC_MARK`/`_DEC_ANY` (finding a given id): two descriptions of one line grammar.
- **Rulings for the build** (the lead's):
  - `signed_blocks` and its helpers move to `ccp/tasklog.py`, unchanged in what they return;
    `ccp/verify.py` calls `tasklog.signed_blocks`, with no copy left.
  - `ccp tasks check` warns (never fails), for a task not yet `done` or `dropped`, on each line in its
    Scope, or in a section whose heading begins `Rule changes`, that holds `PROPOSED:` and is not
    followed at once by a `> ` line, naming the task file and line and saying to put the text in a
    `> ` blockquote under it. A `PROPOSED:` inside a code span or a fenced block is not read.
  - `refs.Ids` gains the merge-subject and branch task-id patterns (built from `ids.task.width`);
    `health` and `lifecycle` call them, and `health` keeps no task-id regex but the squash pattern.
  - `ccp/adr.py`: one id-parameterised pattern each for a decision heading and a decision mark;
    the matching patterns with groups and the finding patterns are built from them. The
    known-intentional line of `docs/ENGINEERING.md` is updated to the names that remain.
  - `plugin/skills/writing-tasks/SKILL.md`'s "Rule text is signed when the task is written" bullet
    says that every PROPOSED, §31.1 text included, goes in a `> ` blockquote under a `PROPOSED:` line.
- **Ordering.** `depends_on` 0234 (it makes `ccp/tasklog.py` the one check parser and edits
  `ccp/verify.py` and `ccp/adr.py`) and 0223 (it edits the same §3.5 paragraph). Clashes with 0240
  (`ccp/verify.py`) and 0244 (`ccp/tasklog.py`, the writing-tasks skill).
- **Rule text.** The §3.5 sentence below is signed in the brief (§31).

## Scope

- **In:**
  - `ccp/tasklog.py`, `ccp/verify.py`, `ccp/refs.py`, `ccp/health.py`, `ccp/lifecycle.py`,
    `ccp/adr.py`, `docs/ENGINEERING.md` (the known-intentional line only),
    `plugin/skills/writing-tasks/SKILL.md`, `tests/test_signed_blocks_check.py` (new), `tests/test_refs.py`.
  - Signed before the claim (`sign_off: brief`): `docs/spec/01-model.md` §3.5, a sentence added
    after the one that ends "(the word `§31.1` on a Scope line).":

    CURRENT (`docs/spec/01-model.md` at `1aa5e3f`):
    > `brief` sign-off nor says in its Scope that its SPEC text only describes its own feature (the word
    > `§31.1` on a Scope line).

    PROPOSED:
    > `brief` sign-off nor says in its Scope that its SPEC text only describes its own feature (the word
    > `§31.1` on a Scope line). It also warns on a task not yet `done` or `dropped` whose Scope, or a
    > section whose heading begins `Rule changes`, has a line `ccp verify spec-text` cannot read
    > (§15.2): one holding `PROPOSED:` with no `> ` blockquote line under it.
- **Out:** `ccp verify spec-text`'s matching (unchanged); health's squash-subject pattern; the
  ADR-link and task-reference parsers already in `ccp/refs.py`.

## dod_checks

- id: `sb-01`
  story: As a task writer, `ccp tasks check` warns on an inline PROPOSED and is silent on a blockquoted one.
  setup: A checkout of the PR head; then a separate copy of it with the warning's call in `ccp/tasklog.py` removed.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_signed_blocks_check 2>&1 | tail -7`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_signed_blocks_check`.
  expect: step 1 exits 0, listing as `ok` tests for: an inline `PROPOSED: "…"` in Scope warns, naming the file and line; a `PROPOSED:` followed by `> ` lines does not; one in a `Rule changes` section warns the same; one in a code span or fenced block does not; a `done` task does not; the warning leaves the exit code 0. Step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `sb-02`
  story: As a plane developer, the signed-block grammar is read in one module.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nE 'def (signed_blocks|_signed_sections|_block_names)' -- ccp`.
  expect: three lines, all in `ccp/tasklog.py`.
  dry run (`1aa5e3f`): printed three lines, all in `ccp/verify.py`.
- id: `sb-03`
  story: As a plane developer, health and lifecycle take their task-id patterns from refs.py.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nE '_merge_task_re|_branch_task_re' -- ccp`.
    2. Run `git grep -nE 'def _written_task_re' -- ccp/health.py | wc -l`.
  expect: step 1 prints nothing; step 2 prints `1` (the squash pattern stays where E23 lists it).
  dry run (`1aa5e3f`): step 1 printed 5 lines (`ccp/health.py` 4, `ccp/lifecycle.py` 1); step 2 printed `1`.
- id: `sb-04`
  story: As a plane developer, adr.py describes a decision's heading and mark once, and the refs and ADR tests hold.
  setup: A checkout of the PR head; then a separate copy of it with the mark pattern's `\*\*` alternatives removed.
  steps:
    1. Run `git grep -nE '^_DEC_(HEAD|MARK) = r' -- ccp/adr.py | wc -l`.
    2. On the head, run `python3 -B -m unittest -q tests.test_refs tests.test_adr`.
    3. In the copy, run `python3 -B -m unittest -q tests.test_adr`.
  expect: step 1 prints `0` (no second hand-written description); step 2 exits 0; step 3 exits non-zero.
  dry run (`1aa5e3f`): step 1 printed `2`; step 2 exited 0; step 3 n/a (the shared pattern lands with the task).
- id: `sb-05`
  story: As the operator, §3.5 reads as I signed it.
  setup: A checkout of the PR head; the brief sign-off recorded.
  steps:
    1. Run `./bin/ccp verify spec-text 0264`.
  expect: exit 0, the PROPOSED passage found in `docs/spec/01-model.md`.
  dry run (simulated, the passage applied to `docs/spec/01-model.md` on a scratch branch off `1aa5e3f`): exit 0, the passage found in `docs/spec/01-model.md`.

## Implementation notes

## Verification notes
