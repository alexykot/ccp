---
task_id: 0108-sign-rule-text-at-tasking
title: Rule text is signed when the task is written; new rule text found in the build goes to a follow-up; health shows the sign-off wait
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S5", "S27"]
review_point: R7
sign_off: brief
paths: ["ccp/tasklog.py", "ccp/config.py", "contracts/plane_config.schema.json", "ccp/health.py", "plugin/skills/writing-tasks/SKILL.md", "plugin/agents/delivery-implementer.md", "templates/prompts/implement.md", "docs/spec/01-model.md", "docs/spec/04-observability.md", "tests/test_tasklog*.py", "tests/test_health*.py", "tests/test_prompt*.py"]
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0108-sign-rule-text-at-tasking
## Intent

The operator signs § rule text when a task is written, not while a verified PR waits. A task that
changes a § rule carries its exact CURRENT → PROPOSED text and a `brief` sign-off; rule text the
build finds beyond that goes to a follow-up proposal, so the PR merges on the signed words; and
`ccp health` shows how long verified work waited on a sign-off, per review point.

## Context (not checked)

- From an accepted plane proposal (operator, 2026-11-16: all three parts accepted).
- A telemetry analysis of the plane's own runs, 9–16 Nov, reported that about half of task wall time was verified PRs waiting on a merge escalation, most for SPEC text beyond the task's PROPOSED sentence (`ccp health --since 2026-11-09` gives the per-task spans it read).
- Task 0095 removed the sign-off for text that only describes the task's own feature (§31.1). This task moves the remaining sign-offs ahead of the claim.
- The check below is a warning, not a refusal: a tightened check would make conforming products stale at release (§29.3).
- This R7 task log already follows the rule: every R7 task that changes a § rule carries `sign_off: brief`.

## Scope

- **In:**
  - `docs/spec/01-model.md` §3.5. CURRENT (at `7094dfe`): none; a new paragraph goes after "Any other value (no stage, or one that is not `brief` or `build`) fails `ccp tasks check`, and claim and close refuse the task until it is fixed." PROPOSED:
    > A task whose change adds or changes a § rule carries, in its Scope, the exact CURRENT → PROPOSED text of each passage and declares `sign_off: brief`, so the operator signs the words before the claim. `ccp tasks check` warns on a task not yet `done` or `dropped` whose `paths` name a SPEC file (plane.json `task_log.spec_paths`, default `["docs/spec/", "SPEC.md"]`) and that neither declares a `brief` sign-off nor says in its Scope that its SPEC text only describes its own feature (the word `§31.1` on a Scope line). Rule text the build finds that the brief does not carry goes to a follow-up proposal (`ccp plane propose`), and the PR merges on the signed text. Only text without which the code cannot be correct goes to the lead as a spec question, and then a `build` sign-off is due (below).
  - `docs/spec/04-observability.md` §27.1. CURRENT (at `7094dfe`): none; a new bullet goes before "**Diagnostic only.**". PROPOSED:
    > - **Sign-off wait:** per review point, the tasks that waited after their verified approve on an operator sign-off or a merge gate, with the median and the longest wait (from the latest approving verdict to the `build` sign-off or the gate's decision, whichever came first); `sign_off_wait` in `--json`.
  - `ccp tasks check` (`ccp/tasklog.py`): the warning above; the `task_log.spec_paths` knob in `ccp/config.py` and `contracts/plane_config.schema.json`.
  - `ccp health` (`ccp/health.py`): the sign-off wait, text and `--json`.
  - The writing-tasks skill (`plugin/skills/writing-tasks/SKILL.md`): under "Writing the brief", a task that changes a § rule declares `sign_off: brief`; one whose SPEC text only describes its feature says `§31.1` in its Scope.
  - The implementer brief (`plugin/agents/delivery-implementer.md`) and `templates/prompts/implement.md`: rule text the task does not carry goes to `ccp plane propose`, not the PR, unless the code cannot be correct without it (then a spec question).
- **Out:**
  - Changing how `build` sign-offs or `spec_beyond_intent` work (§3.5 as task 0095 left it).
  - Refusing, rather than warning.

## dod_checks

- id: `check-01`
  story: As a task-log owner, I am warned about a task that edits the SPEC without a brief sign-off.
  setup: a scratch product with three pending tasks: A declares `paths: ["docs/spec/01-model.md"]` and no `sign_off`; B the same with `sign_off: brief`; C the same with no `sign_off` and a Scope line containing `§31.1`.
  steps:
    1. Run `ccp tasks check`.
    2. Set plane.json `task_log.spec_paths` to `["spec/"]` and run it again.
  expect: (1) exit 0 and exactly one warning, naming A. (2) exit 0 and no warning about A, B or C.
  dry run: n/a.
- id: `check-02`
  story: As the operator, health shows how long verified work waited on me.
  setup: a scratch queue with review point R1 holding three closed tasks: one whose `build` sign-off came 60 minutes after its approving verdict, one whose merge gate was decided 180 minutes after it, and one with no wait.
  steps:
    1. Run `ccp health --json` and `ccp health`.
  expect: `sign_off_wait` for R1 lists two tasks, median 120 minutes, longest 180 minutes, and the text output carries the same line.
  dry run: n/a.
- id: `check-03`
  story: As an implementer, my prompt tells me where new rule text goes.
  setup: a checkout of the PR head.
  steps:
    1. Render an implement prompt with `ccp prompt implement` for a pending task.
  expect: the prompt says rule text the task does not carry goes to `ccp plane propose`, and that only text the code cannot be correct without goes to the lead as a spec question.
  dry run: n/a.
- id: `check-04`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §3.5 and §27.1 edits with the PROPOSED text above.
  expect: they match word for word, and no other § rule changes.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 (implementer): `ccp tasks check` warns (never refuses) through `tasklog.unsigned_spec_edit`, called from `warnings()`. A `paths` entry names the SPEC when it equals a `task_log.spec_paths` entry or lies under it as a directory (an entry ending in `/` is a prefix; one without is matched as itself or `<entry>/…`); a leading `./` is ignored, and a glob is matched by its literal prefix (`docs/spec/*.md` names the SPEC, `docs/**` does not). `brief` among the declared stages holds; `§31.1` counts anywhere in the Scope section, not elsewhere. The knob is `task_log.spec_paths` (default `["docs/spec/", "SPEC.md"]`), validated as a list of relative paths, in `ccp/config.py` and the schema.
- 2026-11-17 (implementer): `ccp health` adds `sign_off_wait` (`--json`: `{"R<n>": {"tasks": [{"task_id", "wait_s", "on": "sign_off"|"merge_gate"}], "median_s", "longest_s"}}`) and one text line per point. Rules chosen where §27.1 leaves them open (flagged in the report): the tasks are the merged ones in the window (`--since`), grouped by their task file's `review_point` (a task with none is in no point); an approving verdict is a `verify`/`recorded` ledger event with `approve` or the verification record's `checked_at` when it approves; the end is the first `build` `sign_off`/`recorded` event or the first `gate`/`decided` on a gate opened with class `merge` at or after the latest approve, by the event's `at`; a standing approval (`decided_by: standing`) waits on no one and is no end. A task with no end after its latest approve is not listed.
- 2026-11-17 (implementer): outside `paths`: `docs/cli/04-observability.md` (the `ccp health` row names `sign_off_wait`). §8.1's `task_log` row does not list `spec_paths`: the task gives no text for it (check-04).

## Verification notes
