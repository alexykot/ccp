---
task_id: 0274-briefs-state-each-rule-once-and-tasks-name-the-mutation-copy
title: Worker briefs stop restating the follow-up and marked-check instructions, and the writing-tasks skill names the tool for a planted-fault copy
status: done
kind: refactor
depends_on: ["0257-one-gate-block-and-one-sentence-per-line"]
clashes_with: ["0260-review-tools-and-the-tests-for-new-behaviour-section"]
review_refs: ["ar-20261121T223646Z-f0a7#F02", "ar-20261121T223646Z-f0a7#F04"]
rule_refs: ["E13", "E21"]
review_point: R23
paths: ["plugin/agents/delivery-implementer.md", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "plugin/skills/writing-tasks/SKILL.md"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-22
---

# Task: 0274-briefs-state-each-rule-once-and-tasks-name-the-mutation-copy

## Intent

A change to the follow-up rule or to the operator-machine rule edits one place, not five. The
follow-up instruction is given only by the report table every rendered prompt ends with, and the
"not yours to run" instruction only by the `{{#marked_checks}}` blocks the implement and verify
prompts render. A task writer who needs a planted-fault copy in a dod_check is told which tool makes
it (`ccp mutate`, or a `ccp wt create --kind mut` worktree), so no new task asks a seat for the hand
`git worktree add` its prompt forbids.

## Context (not checked)

Measured at `8020446` unless a line says otherwise. Provenance: architect pass
`ar-20261121T223646Z-f0a7`, F02 and F04 (record in `docs/delivery/reviews/`). House rule E21's text,
amended by the triage, already says what a check names for a modified copy; this task brings the
plane's skill, which every product's task writer follows, in line.

- **F04, follow-ups.** `ccp/report.py`'s `follow_ups` section tells every phase what goes in
  `## Follow-ups` ("Out-of-scope work goes there, never only in notes or prose"), and
  `templates/prompts/implement.md` renders the rule-text case. The briefs say it again:
  `git grep -n '## Follow-ups' -- plugin/agents/delivery-implementer.md plugin/agents/delivery-reviewer.md plugin/agents/delivery-verifier.md` at `8020446`: 4 lines (implementer 2, reviewer 1, verifier 1).
  The runner brief's paragraph on deciding follow-ups (`plugin/agents/delivery-runner.md`) is the
  runner's procedure, not a restatement, and stays.
- **F04, marked checks.** `git grep -n 'not yours to run' -- plugin/agents templates/prompts` at
  `8020446`: one line each in `delivery-implementer.md`, `delivery-verifier.md`, `implement.md` and `verify.md`.
  The two template lines sit in the rendered `{{#marked_checks}}` blocks, which also say how a
  verifier records the check (`verify.md`: "record each as SPEC §15.4 says"); the two brief bullets
  restate them. The runner's verify step is its procedure and stays.
- **F02.** `git grep -c 'git worktree add' -- 'docs/delivery/tasks/*.md'` at `8020446`: 49 files, all
  done except 0254, whose two hits are Context lines quoting code, not a setup. The skill's bullet
  (`git grep -n 'separate copy' -- plugin/skills/writing-tasks/SKILL.md` at `8020446`: 1 line) names no
  tool; `templates/prompts/review.md` and `verify.md` say "Never `git worktree add` by hand", and
  `templates/prompts/_common.md` names `ccp wt create --kind mut` and `ccp mutate`.
- **Tests.** `git grep -n 'not yours to run\|never only in notes' -- tests` at `8020446`: no match;
  `tests/test_prompt_tools.py` pins the rendered implement prompt's "`## Follow-ups`, not the PR",
  which this task does not change.
- **Order.** 0257 (R17) rewraps every template and adds two bullets to the same skill list; this task
  edits after it. 0260 (R19) edits `plugin/agents/delivery-reviewer.md`'s tools bullets: a clash, not
  a dependency.

### Rulings for the build (the lead's)

- **The briefs.** Remove the implementer's two `## Follow-ups` bullets ("Rule text the task does not
  carry …" and "Any other work you find out of scope …"), the reviewer's and the verifier's
  "Work you find out of scope …" bullet, and the implementer's and verifier's "A dod_check marked
  `runs_on: operator-machine` is not yours to run …" bullet. Nothing replaces them: the rendered
  prompt carries each instruction (E13: briefs name the command and the §; they never restate a rule).
- **The skill.** The bullet "A check that changes a tracked file (a planted fault) does it in a
  separate copy, never in the branch's own worktree." becomes: "A check that changes a tracked file
  (a planted fault) names the copy: `ccp mutate --mutant` (or `--mutant-file`) when a test judges the
  fault, otherwise a `ccp wt create --kind mut` worktree at the head, removed with `ccp wt remove`;
  never the branch's own worktree and never a hand `git worktree add`."
- No `ccp tasks check` warning: the triage left it out (§21.1 text for no current hit).

## Scope

- **In:** `plugin/agents/delivery-implementer.md`, `plugin/agents/delivery-reviewer.md`,
  `plugin/agents/delivery-verifier.md` (the bullets named above), `plugin/skills/writing-tasks/SKILL.md`
  (the one bullet).
- **Out:** `plugin/agents/delivery-runner.md`; the prompt templates; `ccp/report.py`; the task log's
  done tasks; `ccp tasks check`.

## dod_checks

- id: `doc-01`
  story: As a plane developer, the follow-up instruction is given once, by the report table, not again in each brief.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -c 'never only in notes or prose' -- ccp/report.py`.
    2. Run `git grep -n '## Follow-ups' -- plugin/agents/delivery-implementer.md plugin/agents/delivery-reviewer.md plugin/agents/delivery-verifier.md`.
  expect: step 1 prints `ccp/report.py:1`; step 2 prints nothing (exit 1).
  dry run (`8020446`): step 1 printed `ccp/report.py:1`; step 2 printed 4 lines.
- id: `doc-02`
  story: As a plane developer, "not yours to run" is said only in the rendered marked-check blocks.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'not yours to run' -- plugin/agents templates/prompts`.
  expect: exactly two lines, one in `templates/prompts/implement.md` and one in `templates/prompts/verify.md`.
  dry run (`8020446`): printed 4 lines (`plugin/agents/delivery-implementer.md:23`, `plugin/agents/delivery-verifier.md:50`, `templates/prompts/implement.md:10`, `templates/prompts/verify.md:16`).
- id: `doc-03`
  story: As a task writer, the skill tells me which tool makes a planted-fault copy.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'kind mut' -- plugin/skills/writing-tasks/SKILL.md`.
    2. Run `git grep -n 'separate copy' -- plugin/skills/writing-tasks/SKILL.md`.
  expect: step 1 prints at least one line, in the "Commands and searches in checks" list; step 2 prints nothing (exit 1).
  dry run (`8020446`): step 1 printed nothing; step 2 printed 1 line (`plugin/skills/writing-tasks/SKILL.md:131`).

## Implementation notes

- Removed the bullets the task's rulings name: implementer (operator-machine; two follow-up bullets), reviewer and verifier (the follow-up bullet), verifier (operator-machine, four lines). Replaced the skill's planted-fault bullet with the ruled text. Nothing else touched.
- Premise re-run at 133fbf66: the Context counts held (`## Follow-ups` 4 lines, `not yours to run` 4 lines, `separate copy` 1 line, `ccp/report.py:1`). `git grep -c 'git worktree add' -- 'docs/delivery/tasks/*.md'` now lists 51 files (task said 49 at 8020446): the two extra are tasks written since, including this one; it does not bear on the build.
- doc-01..doc-03 run at the head: step outputs match each expect.

## Verification notes
- 2026-11-22 — verifier, PR #306 head `0443a75` (squash `6ab44d8`): APPROVE. Passed: doc-01, doc-02, doc-03. Gate: `scripts/gate.sh (ccp suite run --lane gate)` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0274-briefs-state-each-rule-once-and-tasks-name-the-mutation-copy.json.

