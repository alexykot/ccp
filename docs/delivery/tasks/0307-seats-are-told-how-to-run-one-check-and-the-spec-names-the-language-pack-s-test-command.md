---
task_id: 0307-seats-are-told-how-to-run-one-check-and-the-spec-names-the-language-pack-s-test-command
title: Worker prompts name ccp tasks dry-run --check --here and ccp docs check --only, and §21.4 names the language pack's test command and did-not-build lines that §20.6 cites
status: pending
kind: feature
depends_on: ["0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes"]
spec_refs: ["S21", "S20", "S13"]
rule_refs: ["E13", "E18"]
review_point: R28
clashes_with: ["0191-the-grace-release-ends", "0299-the-pre-gate-and-review-run-what-the-branch-touches-and-every-recorded-suite-run-keeps-a-log", "0300-mutant-file-texts-end-where-written-a-revert-takes-several-ranges-and-mutate-s-refusal-copies-go", "0301-tasks-check-warns-on-a-bare-test-runner-and-a-brief-sign-off-shows-what-changed-since-measured"]
paths: ["templates/prompts/_common.md", "tests/test_prompt_tools.py", "docs/spec/03-quality.md"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0307-seats-are-told-how-to-run-one-check-and-the-spec-names-the-language-pack-s-test-command

## Intent

A worker, reviewer or verifier who wants to walk one of its task's dod_checks, or one house-rule check,
exactly as the plane runs it, is told the command in its prompt: `ccp tasks dry-run <task> --check <id>
--here` and `ccp docs check --only <id>`, which 0285 built and which no prompt names yet. And the SPEC's
language-pack section says what a pack gives beyond its doc rules: the language's test command, which
`ccp mutate` falls back to as the per-test runner §20.6 cites, and the did-not-build lines.

## Context (not checked)

From the lead's notes on architect pass `ar-20261122T162238Z-9098` (the record is in `docs/delivery/reviews/`),
items (c) and (e). Measured at `0f44fb3` (origin/main) unless a line says otherwise.

- **No prompt names 0285's two commands.** 0285 (done, PR #354, squash `0bb5470`) added
  `ccp tasks dry-run <id> --check <check-id> --here` (§21.1) and `ccp docs check --only <id>` (§20.1), and edited
  `templates/prompts/_common.md`, `templates/prompts/verify.md`, the three worker agent briefs and the
  writing-tasks skill, none of them to name the two. `git grep -n -e 'dry-run' -e 'docs check --only' -- templates plugin/agents`
  at `0f44fb3`: no line (`plugin/skills/writing-tasks/SKILL.md` names `ccp tasks dry-run` for the task writer,
  without `--here`). House rule E13: briefs and prompt templates name the command and the § that decides.
  The line goes in `_common.md`, the part every worker prompt shares, so it is written once.
- **§21.4 and the pack's test command.** §20.6 (`docs/spec/03-quality.md`, the **The product's command** bullet) says "With no command it runs the language pack's per-test runner (§21.4), its test command followed by the test id", and the `unbuilt` rule reads "unset, the language pack's did-not-build lines". §21.4 says the pack "reads the product's test output (§14.1) and the tests a change touches (§14.7)", and nothing of a test command or did-not-build lines: `git grep -n -e 'test command' -e 'did-not-build' -e 'did not build' -- docs/spec/03-quality.md` at `0f44fb3`: 2 lines, both in §20.6. The pack's fields are `ccp/doclang/__init__.py` `Pack.test_command` and `Pack.unbuilt_re` (since 0267). No value is named in the SPEC (house rule E10: a default lives in code).
- **Other tasks.** 0299 (pending, signed) changes the prompts' affected run and its tests in
  `tests/test_prompt_tools.py`; 0300 (pending, signed) and 0301 (claimed) change other passages of
  `docs/spec/03-quality.md`; 0191 (pending) lists test globs. Different logic; recorded as clashes since the
  files meet.

### Rulings for the build (the lead's)

- `templates/prompts/_common.md` gains one line, right after the bullet that starts "Give `{{ccp}} suite run` and
  `{{ccp}} mutate` the Bash tool's full limit" and its sub-lines, reading as quoted here (not signed text):

  > - To walk one of your task's dod_checks at your own head as the dry run does, run `QUEUE_ROOT={{queue_root}} {{ccp}} tasks dry-run {{task_id}} --check <check id> --here` (SPEC §21.1); to run one house-rule or docs check by its id as `{{ccp}} docs check` does, run `{{ccp}} docs check --only <id>` (SPEC §20.1).

  No other template or brief changes.
- `tests/test_prompt_tools.py` gains `test_every_worker_prompt_names_how_to_run_one_check` in
  `PromptsNameTheTools`: the implement, review and verify prompts each hold `tasks dry-run 0002-second --check`
  and `docs check --only`.

## Scope

- **In:** `templates/prompts/_common.md`, `tests/test_prompt_tools.py`, `docs/spec/03-quality.md`.
- **SPEC, signed before the claim (`sign_off: brief`):** one passage in `docs/spec/03-quality.md`, CURRENT at
  `0f44fb3`.

    CURRENT (`docs/spec/03-quality.md` at `0f44fb3`), §21.4, the first paragraph:
    > The pack also reads the product's test output (§14.1) and the tests a change touches (§14.7).

    PROPOSED:
    > The pack also reads the product's test output (§14.1) and the tests a change touches (§14.7), and gives the language's test command, where it has one, which runs test modules, or one test, by name (the per-test runner `ccp mutate` falls back to), and the lines that say the code did not build or import (§20.6).
- **Out:** the agent briefs and the writing-tasks skill; `ccp tasks dry-run` and `ccp docs check` themselves
  (0285); the packs' values; §20.6's text.

## dod_checks

- id: `spec-01`
  story: As the operator, §21.4 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0307`.
  expect: exit 0, the one PROPOSED passage found.
  dry run (`0f44fb3`): n/a — the passage lands with the build; the CURRENT text is found once in `docs/spec/03-quality.md` (whitespace-normalised, a `python3 -c` search at `0f44fb3`).
- id: `cmd-01`
  story: As a worker, my prompt tells me how to run one dod_check and one house-rule check as the plane does.
  setup: A checkout of the PR head, in your own worktree, with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_prompt_tools`.
    2. Run `grep -e how_to_run_one_check -e '^OK' <the log step 1 names>`.
    3. Run `git grep -c -e 'QUEUE_ROOT={{queue_root}} {{ccp}} tasks dry-run {{task_id}} --check <check id> --here' -e 'docs check --only <id>' -- templates/prompts/_common.md`.
  expect: step 1 exits 0; step 2 lists `test_every_worker_prompt_names_how_to_run_one_check` `ok`, then `OK`; step 3 prints `templates/prompts/_common.md:1` (both on the one line).
  dry run (`0f44fb3`): step 3 printed nothing (exit 1); steps 1 and 2: n/a — the test is new.

## Implementation notes

## Verification notes
