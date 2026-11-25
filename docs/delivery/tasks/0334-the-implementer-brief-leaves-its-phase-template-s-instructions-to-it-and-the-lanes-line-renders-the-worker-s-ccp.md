---
task_id: 0334-the-implementer-brief-leaves-its-phase-template-s-instructions-to-it-and-the-lanes-line-renders-the-worker-s-ccp
title: The worker definitions leave to the rendered prompt every instruction its implement template or common part gives, §13.1's four rules kept, and E13 says so; the implement template states the narrowest-reading rule once; a test pins each rule in the one doc that holds it; the Lanes line names suite run --affected through the worker's own ccp command
status: pending
kind: feature
depends_on: []
spec_refs: ["S13"]
rule_refs: ["E13", "E4"]
review_refs: ["ar-20261124T234643Z-3c95#F01"]
review_point: R35
paths: ["plugin/agents/delivery-implementer.md", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "templates/prompts/implement.md", "ccp/prompt.py", "tests/test_plugin.py", "tests/test_full_lane_prompt.py", "docs/ENGINEERING.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0334-the-implementer-brief-leaves-its-phase-template-s-instructions-to-it-and-the-lanes-line-renders-the-worker-s-ccp

## Intent

A change to a worker instruction edits one doc: the implementer, reviewer and verifier definitions keep §13.1's four
generic rules and what their rendered prompt does not give, and leave every instruction the implement template or the
common part gives to the prompt, which every worker reads. The implement template states the narrowest-reading rule
once, a test pins each rule in the one doc that holds it, and house rule E13 says so. A worker in a worktree reads the
part lane's `--affected` command in the same form as every other `ccp` command its prompt gives.

## Context (not checked)

Finding F01 of architect pass `ar-20261124T234643Z-3c95` (`docs/delivery/reviews/ar-20261124T234643Z-3c95.md`) and the
follow-up of 0328's review that the lead passed to this pass (`0328-…/review#1`: the Lanes line writes a literal
`ccp suite run --affected` where the rest of the prompt renders `{{ccp}}`). The architect proposed E13's amendment;
this triage accepted it and this task lands it.

Measured at `1a575497`:

- **F01.** `grep -c -e 'redesign' -e 'Before you build' -e 'narrowest' -e 'foreground' -e 'never merge' -e 'git add -A' -e 'denies you' -e 'script, helper or wrapper' -e 'Work only in' plugin/agents/delivery-implementer.md`:
  9 lines, each an instruction `templates/prompts/implement.md` or `_common.md` gives (build exactly what the task
  says; the measured premise; the narrowest reading; foreground commands; never merge; stage by path; a denied
  action; no script of your own; the worktree), besides the refactor bullet, the house-rules bullet and the ruling
  bullet, which the template gives too. `grep -c -e 'foreground' -e 'script, helper or wrapper' plugin/agents/delivery-reviewer.md plugin/agents/delivery-verifier.md`:
  2 each. `grep -c narrowest templates/prompts/implement.md`: 2. `python3 -B -c 'from tests import test_plugin as t; print(len(t.PREMISE_DOCS), sum(len(v) for v in t.PREMISE_DOCS.values()))'`:
  `3 16` (three docs, sixteen tokens, line wraps among them); `LESSON_BRIEFS` pins the foreground lesson in the three
  worker briefs.
- **0328 follow-up.** `"def suite_lanes"` (`ccp/prompt.py`) appends `` `ccp suite run --affected` `` as a literal in
  both part-lane branches, while every other command the prompt gives renders as `{{ccp}}` (`"def ccp_command"`:
  `ccp wt exec --` in a checkout that carries `bin/ccp`). The literal in §13.5 is the operator's signed text (0328) and
  stays; only the prompt's rendering changes. `tests.test_full_lane_prompt.DeclaredPartLane.test_a_staged_part_lane_names_suite_run_affected`
  pins the literal.
- No SPEC change: `git grep -n 'suite run --affected' -- docs/spec` names §13.5 and §14.7, which describe the command,
  not its rendering; §13.1 keeps the four rules in the definitions.
- **Ruled.**
  - `plugin/agents/delivery-implementer.md` keeps: its opening sentences up to "the task file says what to build and
    how it is checked."; §13.1's four rules (the test module a change breaks, a test failing under load, stale line
    numbers, a recorded test run); the `--affected` run after a merge; the catch-up merge before the last push; the
    interrupted-command check; the questions bullet's first three sentences (questions go in the report). Every other
    bullet goes, and "Build exactly that, diligently, and don't redesign around it." goes from the opening.
  - `plugin/agents/delivery-reviewer.md` and `delivery-verifier.md` drop their foreground bullet and their "Never write
    a script, helper or wrapper" bullet (`_common.md` gives both).
  - `templates/prompts/implement.md`: the line "Questions: an implementation choice the task leaves open is yours: take
    the narrowest reading and flag it in your report." goes; line "Where the task leaves something open, …" stays.
  - `tests/test_plugin.py`: `PREMISE_DOCS` maps two docs to one token each, the writing-tasks skill to `sets scope` and
    `templates/prompts/implement.md` to `Before you build, re-run at {{base}}`, each asserted present once;
    `LESSON_BRIEFS` drops the three worker briefs, and one assertion pins `foreground` once in
    `templates/prompts/_common.md`. `WORKER_RULES` (§13.1) is unchanged.
  - `"def suite_lanes"` renders both part-lane clauses with the worker's own command:
    `` `{ccp} suite run --affected` `` where `{ccp}` is `ccp_command(cfg)`. The test above is renamed
    `test_a_staged_part_lane_names_suite_run_affected_through_the_workers_ccp` and asserts
    `f"{ccp_command(cfg)} suite run --affected"` in the implement and review Lanes lines.
  - **E13** (`docs/ENGINEERING.md`): its nine lines are replaced by these ten (the triage freed the line):

    > - **E13** Briefs and prompt templates name the command and the § that decides; they never restate a rule's conditions,
    >   a tool's quirk a `ccp` command can absorb, or a sample record (a sample lives in contracts/ as `*.example.json`, and
    >   a test runs it through the command). The report's lines and sections are given once, in the rendered prompt's last
    >   part, from the parser's own table. An instruction several phases share is written once, in `_common.md` or a shared
    >   part, and template text is one sentence per line. The command's refusal names the condition that failed. A worker
    >   definition never restates its phase's template (§13.1's four rules excepted); a test pins an instruction where it is.
    >   check: pass, plus command — architect.checks `E13`: `awk 'length > 600' templates/prompts/*.md` prints nothing, a
    >   proxy for one sentence per line, not a rule of its own; the architect compares each plugin/agents brief with its
    >   phase's template, `_common.md` and the § rules they cite, ccp/report.py's sections, and looks for inline sample
    >   records, sentences repeated across templates and tests pinning one instruction in several docs
- No other test expectation changes.

## Scope

- **In:** `plugin/agents/delivery-implementer.md`, `plugin/agents/delivery-reviewer.md`,
  `plugin/agents/delivery-verifier.md`; `templates/prompts/implement.md`; `ccp/prompt.py` (`suite_lanes`);
  `tests/test_plugin.py` (`PREMISE_DOCS`, `LESSON_BRIEFS`); `tests/test_full_lane_prompt.py` (the test named above);
  `docs/ENGINEERING.md` (E13, the text above).
- **Out:** the SPEC (§13.5's signed text included); `templates/prompts/_common.md`; the runner brief and
  `plugin/orientation.md`; `WORKER_RULES`.

## dod_checks

- id: `doc-01`
  story: As an implementer, my definition no longer restates what my rendered prompt gives me.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c -e 'redesign' -e 'Before you build' -e 'narrowest' -e 'foreground' -e 'never merge' -e 'git add -A' -e 'denies you' -e 'script, helper or wrapper' -e 'Work only in' plugin/agents/delivery-implementer.md`.
    2. Run `grep -c -e 'foreground' -e 'script, helper or wrapper' plugin/agents/delivery-reviewer.md plugin/agents/delivery-verifier.md`.
  expect: step 1 prints `0`; step 2 prints `plugin/agents/delivery-reviewer.md:0` and `plugin/agents/delivery-verifier.md:0`.
  dry run (`1a575497`): step 1 printed `9`; step 2 printed `plugin/agents/delivery-reviewer.md:2` and `plugin/agents/delivery-verifier.md:2`.
- id: `doc-02`
  story: As an implementer, my prompt states the narrowest-reading rule once.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c narrowest templates/prompts/implement.md`.
  expect: prints `1`.
  dry run (`1a575497`): printed `2`.
- id: `code-01`
  story: As a plane developer, a one-rule change edits one doc and one pin: the premise rule is pinned once per doc that holds it.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `python3 -B -c 'from tests import test_plugin as t; print(len(t.PREMISE_DOCS), sum(len(v) for v in t.PREMISE_DOCS.values()))'`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_plugin`.
  expect: step 1 prints `2 2`; step 2 exits 0.
  dry run (`1a575497`): step 1 printed `3 16`; step 2 exit 0.
- id: `code-02`
  story: As a worker in a worktree, the Lanes line gives suite run --affected through my own ccp command, and the signed §13.5 text is unchanged.
  setup: As `code-01`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_full_lane_prompt.DeclaredPartLane.test_a_staged_part_lane_names_suite_run_affected_through_the_workers_ccp`.
    2. Run `git diff origin/main...HEAD -- docs/spec`.
  expect: step 1 exits 0; step 2 prints nothing.
  dry run (`1a575497`): step 1 exit 1 (`AttributeError: type object 'DeclaredPartLane' has no attribute 'test_a_staged_part_lane_names_suite_run_affected_through_the_workers_ccp'`); step 2 printed nothing.
- id: `rule-01`
  story: As the architect, E13 states that a worker definition never restates its phase's template.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c "never restates its phase's template" docs/ENGINEERING.md`.
  expect: prints `1`.
  dry run (`1a575497`): printed `0`, exit 1.

## Implementation notes

## Verification notes
