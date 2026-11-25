---
task_id: 0343-the-reviewer-and-verifier-definitions-leave-their-templates-instructions-to-them-and-the-lanes-line-gives-whole-commands
title: The reviewer and verifier definitions leave to the rendered prompt every instruction their phase template gives, §13.1's four rules kept, and the tests pin each in the template; the Lanes line gives a part lane declared as an argv as whole commands; the runner brief names a pending run's expiry; §11.1's Record lists expired_told_at
status: pending
kind: feature
depends_on: []
spec_refs: ["S11", "S13"]
rule_refs: ["E13"]
review_refs: ["ar-20261125T094654Z-c8a0#F01", "ar-20261125T094654Z-c8a0#F02"]
review_point: R37
paths: ["plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-runner.md", "ccp/prompt.py", "docs/spec/02-delivery.md", "tests/test_full_lane_prompt.py", "tests/test_sign_off_beyond_intent.py", "tests/test_verify_producer.py", "tests/test_verify.py", "tests/test_prompt_tools.py", "tests/test_worker_efficiency.py", "tests/test_plugin.py"]
clashes_with: ["0191-the-grace-release-ends", "0344-suite-affected-covers-the-suite-driving-tests-and-the-tests-share-one-current-run-clock"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0343-the-reviewer-and-verifier-definitions-leave-their-templates-instructions-to-them-and-the-lanes-line-gives-whole-commands

## Intent

A rule change to the review or verify phase edits one doc, the phase's template, and the test that pins it there:
the reviewer and verifier definitions no longer copy their templates, as the implementer's stopped doing in 0334. A
worker reading its prompt's Lanes line for a part lane declared as an argv sees each option as a whole command it
can run, so it no longer pairs `--lane` with `--affected` or passes test ids where module names go. A runner reading
its brief learns that a pending run expires, and the SPEC's run record lists the field 0340 added.

## Context (not checked)

Findings F01 and F02 of architect pass `ar-20261125T094654Z-c8a0` (`docs/delivery/reviews/ar-20261125T094654Z-c8a0.md`),
and two of the 0340 follow-ups the lead passed to that pass: the runner brief's pending-run line not naming expiry,
and §11.1's Record omitting `expired_told_at`.

Measured at `704ca8de`:

- **F01.** `cat plugin/agents/delivery-reviewer.md plugin/agents/delivery-verifier.md | grep -c -e 'Look for bugs' -e
  'redesign the task' -e 'spec_beyond_intent' -e 'produced_by' -e 'as_written'`: 5 lines. The copies the report
  names: the reviewer's "You have no implementer context, and that is the point …" (review.md line 2), "Look for bugs,
  missed edge cases …" (review.md "Look for bugs"), its refactor rule, "Don't redesign the task or propose new scope"
  (review.md "Do not redesign the task"), "Run a check's `ccp` command by hand …" and "Read only. Don't edit, commit,
  push, approve or merge"; the verifier's `spec_beyond_intent` bullet (verify.md "Every verdict on a task carries
  `spec_beyond_intent`"), its `produced_by`, `rests_on` and `as_written` bullets (verify.md "Each check's evidence
  follows SPEC §15.4") and its refactor DoD sentence. Tests that pin a definition's text:
  `tests/test_sign_off_beyond_intent.py` (`"def test_the_reviewer_is_asked_for_the_section_and_the_verifier_for_the_list"`,
  the verifier definition's `spec_beyond_intent`), `tests/test_verify_producer.py`
  (`"def test_the_briefs_name_the_field"`, the verifier's `produced_by`), and, for sentences this task keeps unless
  their template gives them, `tests/test_verify.py` (the example record's path), `tests/test_prompt_tools.py`
  (`--own-hooks`, the base worktree) and `tests/test_worker_efficiency.py` (the test-cache rule).
- **F02.** `"v[r] = f\"`--lane {lane}` with `{shlex.join(argv)} <modules>` after `--`\""` (`ccp/prompt.py`,
  `"def suite_lanes"`) renders, for this repo's part lane, "`--lane part` with `scripts/gate.sh <modules>` after `--`
  … , or `ccp suite run --affected` for the modules a change touches". §14.7 (`docs/spec/02-delivery.md`, "It takes no
  `--lane` and no command after `--`") already rules the two forms apart; no § changes for F02.
- **Runner brief.** `grep -c 'expir' plugin/agents/delivery-runner.md`: 0; its line "`ccp prompt` refuses while a run of
  the same agent type is still pending (opened, its agent not started)" predates 0340's expiry.
- **§11.1.** `"rec[\"expired_told_at\"] = iso()"` (`ccp/runs.py`) writes the field; §11.1's Record list does not name it.

**Ruled.**

- **F01.** From `plugin/agents/delivery-reviewer.md` and `plugin/agents/delivery-verifier.md`, cut each sentence the
  measurement above names, and any other sentence their phase template (`templates/prompts/review.md`,
  `templates/prompts/verify.md`) or `templates/prompts/_common.md` gives; keep §13.1's four rules and every sentence
  only the definition holds. A test that pins a cut sentence's token in a definition pins it in the template instead
  (E13: "a test pins an instruction where it is"); `tests/test_sign_off_beyond_intent.py` drops the definition from
  its tuple, `tests/test_verify_producer.py` reads `produced_by` from `templates/prompts/verify.md` (the runner brief
  half stays). The templates' text does not change for F01.
- **F02.** For a part lane declared as an argv, `suite_lanes` renders the lane as
  `` `<ccp> suite run --lane <lane> -- <argv> <module> …` (module names, not test ids) `` and its alternative as
  `` , or `<ccp> suite run --affected` (it picks the lane itself) for the modules a change touches ``, `<ccp>` being
  `ccp_command(cfg)` as now. Every other lane form is unchanged. New test
  `tests.test_full_lane_prompt.DeclaredPartLane.test_a_part_lane_declared_as_an_argv_is_given_as_whole_commands`: for
  every phase, the Lanes text holds `suite run --lane part -- scripts/gate.sh <module> …` and `(it picks the lane
  itself)`, and no `` `--lane part` with ``. The tests reading the old form (`PART_ARGV`) read the new one.
- **Runner brief.** In `plugin/agents/delivery-runner.md`, "`ccp prompt` refuses while a run of the same agent type is
  still pending (opened, its agent not started); `--supersede` abandons it when that launch never happened (SPEC
  §11.1, §16.4)." becomes "`ccp prompt` refuses while a run of the same agent type is still pending, until it binds
  or expires (SPEC §11.1); `--supersede` abandons it when that launch never happened (SPEC §11.1, §16.4)."
- No other test expectation changes.

## Scope

- **In:** `plugin/agents/delivery-reviewer.md`; `plugin/agents/delivery-verifier.md`; `plugin/agents/delivery-runner.md`
  (the pending-run sentence); `ccp/prompt.py` (`suite_lanes`); `tests/test_full_lane_prompt.py`;
  `tests/test_sign_off_beyond_intent.py`; `tests/test_verify_producer.py`; and `tests/test_verify.py`,
  `tests/test_prompt_tools.py`, `tests/test_worker_efficiency.py`, `tests/test_plugin.py` only where a pinned sentence
  moves to its template. The SPEC, describing 0340's accepted feature (§31.1):

  CURRENT (`docs/spec/02-delivery.md` at `704ca8de`), §11.1, the Record bullet:
  > `session_id`, `worktree`, `started_at`, `stopped_at`, `reported_at`, `abandoned_at`,
  > `abandoned_reason`, `abandoned_by`, `outcome`, `suite_tests`, `suite_seconds`, `severity`

  PROPOSED:
  > `session_id`, `worktree`, `started_at`, `stopped_at`, `reported_at`, `abandoned_at`, `abandoned_reason`,
  > `abandoned_by`, `expired_told_at` (when the slot that opened an expired run was told, *Binding*), `outcome`,
  > `suite_tests`, `suite_seconds`, `severity`

- **Out:** `templates/prompts/review.md`, `templates/prompts/verify.md` and `templates/prompts/_common.md` (their text
  is unchanged); `plugin/agents/delivery-implementer.md`
  (0334); `docs/ENGINEERING.md` (E13's text is unchanged); the full and gate lanes' rendered form; `ccp/runs.py`.

## dod_checks

- id: `code-01`
  story: As the lead, the reviewer and verifier definitions no longer copy their templates' instructions.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `cat plugin/agents/delivery-reviewer.md plugin/agents/delivery-verifier.md | grep -c -e 'Look for bugs' -e 'redesign the task' -e 'spec_beyond_intent' -e 'produced_by' -e 'as_written'`.
  expect: prints `0` (grep's exit 1, no match).
  dry run (`704ca8de`): printed `5`, exit 0.
- id: `code-02`
  story: As a worker, my prompt gives a part lane declared as an argv as whole commands I can run.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_full_lane_prompt.DeclaredPartLane.test_a_part_lane_declared_as_an_argv_is_given_as_whole_commands tests.test_full_lane_prompt`.
  expect: exit 0.
  dry run (`704ca8de`): exit 1 (`AttributeError: type object 'DeclaredPartLane' has no attribute 'test_a_part_lane_declared_as_an_argv_is_given_as_whole_commands'`).
- id: `doc-01`
  story: As a runner, my brief says a pending run expires.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'expir' plugin/agents/delivery-runner.md`.
  expect: prints `1`.
  dry run (`704ca8de`): printed `0`, exit 1.
- id: `spec-01`
  story: As the lead, §11.1's Record names the field the plane writes when it tells a slot of an expired run.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0343`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`704ca8de`, with this brief): exit 1, the PROPOSED passage missing.

## Implementation notes

## Verification notes
