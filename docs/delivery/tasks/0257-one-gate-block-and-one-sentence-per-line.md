---
task_id: 0257-one-gate-block-and-one-sentence-per-line
title: The before-push gate block is written once for the four phases, prompt templates hold one sentence per line, and the writing-tasks skill names two check pitfalls
status: done
kind: feature
depends_on: ["0212-full-role-runs-the-gate-lane-and-a-pregate-lane", "0221-workers-reach-the-pr-host-through-ccp-pr", "0223-a-follow-up-is-tracked-not-left-in-notes", "0228-report-sections-as-one-table", "0233-briefs-point-at-the-evidence-rules", "0238-the-runner-runs-marked-checks-before-verify", "0240-plane-workers-run-the-head", "0244-tasks-check-runs-dry-runs"]
spec_refs: ["S5", "S13"]
review_refs: ["ar-20261121T020523Z-1d5f#F04", "ar-20261121T020523Z-1d5f#F13"]
rule_refs: ["E13", "E21"]
review_point: R17
paths: ["templates/prompts/", "ccp/prompt.py", "plugin/skills/writing-tasks/SKILL.md", "tests/test_prompt_gate_block.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-22
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
- No SPEC change: the skill's two bullets apply the task format (§5) and the briefs' fail-fast rule
  (§13.5) is rendered as before.
- **Out:** changing what any instruction says; the review, verify and estimate templates' own text
  beyond rewrapping.

## dod_checks

- id: `tp-01`
  story: As a plane developer, the before-push block is in one file.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -c '{{gate}}' -- templates/prompts`.
    2. Run `git grep -l 'Fail fast' -- templates/prompts`.
  expect: step 1 prints exactly four lines, `fix.md:1`, `implement.md:1`, `merge.md:1` and `ruling.md:1` under `templates/prompts/`; step 2 prints exactly one line, `templates/prompts/_gate.md`.
  dry run (`aaa81b2`): step 1 printed nothing; step 2 printed 4 lines (fix, implement, merge, ruling).
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
    1. Run `grep -c -e 'presence check' -e 'another task lands' plugin/skills/writing-tasks/SKILL.md`.
  expect: prints `2`.
  dry run (`aaa81b2`): printed `0`.

## Implementation notes

- `templates/prompts/_gate.md` holds the before-push block once: the catch-up (implement, fix), the full
  suite with the task and docs checks and the budgets, the implement round's self-check sentences, the
  fail-fast pre-gate and the line that it never stands in for the full suite. The four phase templates
  carry `{{gate}}` where the block stood.
- `ccp/prompt.py`: `GATE_FLAGS` sets three section flags per phase (`gate_catch_up` for implement and fix,
  `gate_pr` for implement, `gate_merge` for merge); `render_phase(phase, values)` renders `_gate.md` with
  them into `{{gate}}` (empty for a phase that does not push) and `build` renders through it.
- Every template under `templates/prompts/` is one sentence per line; a list item's further sentences go
  on indented continuation lines, as `_common.md` already did for the suite rule. Where two sections are
  alternatives on one line (`{{/own_worktree}}{{^own_worktree}}`, `cold_gate`, `has_old`, `resolution`),
  each section now carries its own line end, so no blank line is added or lost.
- Two sentences of `_gate.md` are longer than 600 characters with their section markup, so each carries one
  line break inside it, after a colon or a clause: "during the run:" (rendered in implement and fix) and
  "then" before "run a quick pre-gate" (rendered in implement with budgets). No word changes.
- Checked by rendering every template at the base and at the head under each flag off, one on, two on, all
  but one on and all on, with whitespace collapsed inside each paragraph: all 19888 renders equal, blank
  lines included.
- Tests that took one line of a rendered prompt as a rule (`test_suite`, `test_resolution_review`,
  `test_worker_efficiency`) now read the list item or the sentence, the same tokens expected.
- Fix round 1 (review findings):
  - `render_phase` decides whether a phase pushes by `runs.CHANGE_PHASES`, the one list of those phases,
    and takes its flags as `GATE_FLAGS[phase]`, so a pushing phase without flags raises instead of
    rendering an empty block. The gate test loops over `runs.CHANGE_PHASES` and checks that `GATE_FLAGS`
    names exactly those phases.
  - `test_prompt_tools`' guard against a mutation worktree or a discovery command now reads `_gate.md` too,
    where the before-push block moved.
  - The module docstring of `ccp/prompt.py` is reflowed to its old line width.

## Verification notes
- 2026-11-22 — verifier, PR #301 head `b98f08f` (squash `1795fd2`): APPROVE. Passed: tp-01, tp-02, tp-03, tp-04. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0257-one-gate-block-and-one-sentence-per-line.json.

