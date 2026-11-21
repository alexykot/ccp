---
task_id: 0257-one-gate-block-and-one-sentence-per-line
title: The before-push gate block is written once for the four phases, prompt templates hold one sentence per line, and the writing-tasks skill names two check pitfalls
status: pending
kind: refactor
depends_on: ["0212-full-role-runs-the-gate-lane-and-a-pregate-lane", "0221-workers-reach-the-pr-host-through-ccp-pr", "0223-a-follow-up-is-tracked-not-left-in-notes", "0228-report-sections-as-one-table", "0233-briefs-point-at-the-evidence-rules", "0238-the-runner-runs-marked-checks-before-verify", "0240-plane-workers-run-the-head", "0244-tasks-check-runs-dry-runs"]
clashes_with: ["0224-checks-only-the-operator-s-machine-can-run", "0252-the-task-check-reports-a-decision-built-before-its-prerequisite"]
review_refs: ["ar-20261121T020523Z-1d5f#F04", "ar-20261121T020523Z-1d5f#F13"]
rule_refs: ["E13", "E21"]
review_point: R17
paths: ["templates/prompts/", "ccp/prompt.py", "plugin/skills/writing-tasks/SKILL.md", "tests/test_prompt_gate_block.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0257-one-gate-block-and-one-sentence-per-line

## Intent

The instructions the implement, fix, merge and ruling phases share before a push (the full suite,
the task and docs checks, the budgets, the pre-gate) are written once and rendered into each phase,
so a change to them edits one file. Every prompt template holds one sentence per line, so two tasks
that change different sentences of a template merge cleanly instead of colliding on one long line.
The writing-tasks skill tells a task writer not to pin a doc sentence in a check and not to write an
expect that moves when another task lands. What each phase's rendered prompt says is unchanged.

## Context (not checked)

From architect pass `ar-20261121T020523Z-1d5f`, findings F04 and F13, triaged by the lead on
2026-11-21, with the triage's amendment to house rule E13 (already in docs/ENGINEERING.md: "An
instruction several phases share is written once, in `_common.md` or a shared part, and template text
is one sentence per line"). Measured at `aaa81b2`. `depends_on` every pending task that edits
`templates/prompts/` (0212, 0221, 0223, 0228, 0233, 0238, 0240, 0244): rewrapping the templates
before them would conflict with each, so this task runs after them, on their text.

- **F04, the copies.** `git grep -c 'Fail fast first' -- templates/prompts` at `aaa81b2`: 4 files (fix, implement, merge, ruling), 1 each; the same for
  `git grep -c 'The pre-gate never stands in for the full suite' -- templates/prompts`.
  `ccp/prompt.py` already renders a shared part, `_common.md`, after each phase template
  (`grep -n '_common.md' ccp/prompt.py` at `aaa81b2`: line 755). Ruling: a new part,
  `templates/prompts/_gate.md`, holds the before-push block; `ccp/prompt.py` renders it with the
  phase's values into a `{{gate}}` placeholder that the four templates carry where the block stands
  today. A difference between phases is a section flag in `_gate.md`, set per phase in
  `ccp/prompt.py`. The block's wording is the one at this task's base, after the tasks it depends on.
- **F04, long lines.** `awk 'length > 600' templates/prompts/*.md | wc -l` at `aaa81b2`: 21 lines.
  Ruling: every template under `templates/prompts/` is rewrapped at one sentence per line (a list
  item or table row stays one line); no word changes.
- **F13.** Dod_checks that `grep -c` a whole SPEC sentence, and expects derived from other tasks'
  frontmatter, cost reviewer rounds (friction from the 0199 and 0202 reviews). House rule E21 already
  says, for this repo, that a doc grep pins one token; the plane's writing-tasks skill, which every
  product's task writer follows, says neither. Ruling: two bullets added under the skill's
  "Commands and searches in checks":
  - "**A doc presence check pins the token the rule turns on** (the flag, the key, the § cite), never a
    whole sentence or a table row; signed SPEC text is proved by `ccp verify spec-text`."
  - "**An expect counts only what the task changes**, never a figure that moves when another task
    lands (another task's status, frontmatter or count)."

## Scope

- **In:** `templates/prompts/_gate.md` (new), the four phase templates, every other template under
  `templates/prompts/` (rewrapped), `ccp/prompt.py` (render `_gate.md`), `tests/test_prompt_gate_block.py`
  (new), `plugin/skills/writing-tasks/SKILL.md` (two bullets).
- **Out:** changing what any instruction says; the review, verify and estimate templates' own text
  beyond rewrapping.

## dod_checks

- id: `tp-01`
  story: As a plane developer, the before-push block is in one file.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -c 'Fail fast first' -- templates/prompts`.
    2. Run `git grep -c 'The pre-gate never stands in for the full suite' -- templates/prompts`.
  expect: each step prints exactly one line, `templates/prompts/_gate.md:1`.
  dry run (`aaa81b2`): each step printed 4 lines (fix, implement, merge, ruling).
- id: `tp-02`
  story: As a plane developer, every phase that pushes still gets the block, and no other phase does; the test bites.
  setup: a checkout of the PR head; then a separate copy of it where `ccp/prompt.py` renders `_gate.md` as empty for the fix phase.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_prompt_gate_block tests.test_full_lane_prompt tests.test_prompt_rounds tests.test_prompt_end`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_prompt_gate_block`.
  expect: step 1 exits 0, its new module rendering the implement, fix, merge and ruling prompts with `Fail fast first` once each and the review and verify prompts without it; step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `tp-03`
  story: As a task writer, templates hold one sentence per line.
  setup: a checkout of the PR head.
  steps:
    1. Run `awk 'length > 600' templates/prompts/*.md | wc -l`.
  expect: prints `0`.
  dry run (`aaa81b2`): printed `21`.
- id: `tp-04`
  story: As a task writer in any product, the skill warns against sentence pins and expects that move with other tasks.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -c -e 'pins the token the rule turns on' -e 'moves when another task' plugin/skills/writing-tasks/SKILL.md`.
  expect: prints `2`.
  dry run (`aaa81b2`): printed `0`.

## Implementation notes

## Verification notes
