---
task_id: 0314-task-writers-leave-a-line-between-a-revert-check-s-hunks-and-an-implementer-s-questions-go-in-its-report
title: The writing-tasks skill says a revert check's fixture leaves an unchanged line between the hunks it tells apart, and the implement prompt and the implementer and runner briefs say an implementer's questions go in its report
status: done
kind: feature
depends_on: []
spec_refs: ["S5", "S13", "S17"]
rule_refs: ["E13"]
review_point: R31
paths: ["plugin/skills/writing-tasks/SKILL.md", "plugin/agents/delivery-implementer.md", "plugin/agents/delivery-runner.md", "templates/prompts/implement.md", "tests/test_prompt_note_env.py"]
clashes_with: []
adopt: "none"
created: 2026-11-23
updated: 2026-11-24
---

# Task: 0314-task-writers-leave-a-line-between-a-revert-check-s-hunks-and-an-implementer-s-questions-go-in-its-report

## Intent

Two briefs stop setting workers up to fail. A task writer who asks for a revert check that puts back one change
and keeps another is told to leave an unchanged line between them, so the check can be built. And an implementer
with a question puts it in its report instead of sending it and waiting: the runner is inside the implementer's
Agent call until it ends, so a mid-task message reaches no one and the implementer stalls. The runner brief says
the same from its side: the implementer's questions come in its report, and the runner answers in the next round.

## Context (not checked)

Covers these follow-ups (`ccp --root . tasks follow-ups --open`), and the lead's friction item:

- `0300-…/implement#1`, `0300-…/review#2`, `0300-…/fix#1` and `0300-…/verify#1`: 0300's `code-02` asked for changes
  at lines 2 and 5 with line 3's other change kept, which `git diff -U0` cannot give; the guidance should say a revert
  check's fixture leaves unchanged lines between hunks.
- The lead's friction item: an implementer's mid-task question cannot reach the runner while the runner is inside the
  Agent call. Ruled: a brief edit on both sides (below), not a drop, since the runner brief tells the runner to answer
  by `SendMessage`, which a worker that waits never receives.

Not covered here: `0300-…/implement#2` and `0300-…/review#1` (the `ccp mutate` row of `docs/cli/03-quality.md` saying
"a file or line range"). 0300's own squash `ec6c068` already made it "of a file or of line ranges"
(`git log --oneline -S 'of line ranges' -- docs/cli/03-quality.md` at `b09de675`: that commit only), so they are dropped.

Measured at `b09de675` (origin/main).

- **The hunks.** `ccp mutate --revert <path>:<ranges>` puts back the hunks `git diff -U0` shows that a range overlaps
  (§20.6, `docs/spec/03-quality.md`). A probe at `b09de675`, `git diff --no-index -U0 a.txt b.txt` on a six-line file with
  lines 2, 3 and 5 changed, printed two hunks, `@@ -2,2 +2,2 @@` and `@@ -5 +5 @@`: lines 2 and 3 are one hunk.
  `grep -c 'U0' plugin/skills/writing-tasks/SKILL.md` at `b09de675`: 0.
- **The questions.** In `plugin/agents/delivery-runner.md`, the step **Questions from the implementer** reads
  "Implementation choices are yours: answer by `SendMessage`." (`grep -n 'answer by .SendMessage' plugin/agents/delivery-runner.md` at `b09de675`: 1 line). The
  runner's own brief says "The Agent call returns when the worker ends". `plugin/agents/delivery-implementer.md` sends a
  product question to the report but says nothing about waiting on a message
  (`grep -c 'Agent call' plugin/agents/delivery-implementer.md` at `b09de675`: 0). The implement prompt says the opposite:
  `templates/prompts/implement.md` reads "Questions: an implementation choice (how to build it) is the runner's." and then
  "Send it to `{{runner}}` with SendMessage and carry on with what does not depend on the answer; if no answer has come by
  the time you would finish, make the choice, document it and flag it."
  (`grep -c 'with SendMessage' templates/prompts/implement.md` at `b09de675`: 1 line). Its next line, "A product or spec
  question: stop that part and put it in your report.", already sends the rest to the report.
- **The prompt's test.** `tests/test_prompt_note_env.py` `"def test_workers_message_the_runner_by_its_bound_name"` asserts
  `"Send it to `runner-2` with SendMessage"`, the implement.md line that goes, beside two assertions on `_common.md`'s lines
  (`"no messages to anyone except the runner teammate, `runner-2`."` and `"Send the runner teammate, `runner-2`, a message"`),
  which already hold the bound name (`grep -c 'runner-2' tests/test_prompt_note_env.py` at `b09de675`: 5 lines).
- **No SPEC change.** §17.1 says an implementation question "is answered by the runner (no source edits by it) and the
  worker resumes"; the next round (the fix round, with the runner's choice in its `--note`) is that resumption, and an
  implementer that takes the narrowest reading and flags it has not stopped. `git grep -n 'SendMessage' -- docs/spec` at `b09de675`: 6
  lines, each about the tool list or a worker naming its report, none about a question. `git grep -nE 'U0|hunk' -- docs/spec`
  at `b09de675` finds §20.6's revert rule, which this keeps.
- **Pinned text.** `tests/test_plugin.py` pins tokens in both briefs (`LESSON_BRIEFS`, `PREMISE_DOCS`: "scope
  question", "changed materially", "background command stalls" among them). The edits below keep every one.
- **Clashes.** A script over the pending tasks' `paths` at `b09de675` found: 0191 (`delivery-runner.md`: its model and
  key lines; and `tests/` whole, for its own `tests/test_grace_ended.py`) and 0310 (`delivery-implementer.md`: the
  `ccp suite affected` bullet). 0307 names `templates/prompts/_common.md`, not `implement.md`. None touches that step, the
  question bullet, the skill, implement.md's question lines or `tests/test_prompt_note_env.py`
  (`git grep -nE 'Questions from the implementer|SendMessage|open question|writing-tasks|implement\.md|test_prompt_note_env' -- <0191, 0307 and 0310's task files>` at `b09de675`: 3 lines,
  all 0307's, naming the writing-tasks skill only to keep it in its **Out:**). So `clashes_with` is empty.

### Rulings for the build (the lead's)

- **The skill.** In `plugin/skills/writing-tasks/SKILL.md`, directly after the bullet that starts
  `- **A behaviour-preserving change**`, a new bullet, exactly, its line breaks as here:

  > - **A revert check leaves an unchanged line between the changes it tells apart.** `ccp mutate --revert
  >   <path>:<ranges>` puts back the hunks `git diff -U0` shows, and `-U0` joins changes on adjacent lines into one
  >   hunk. So a fixture whose check reverts one change and keeps another puts at least one unchanged line between
  >   them: changes at lines 2, 4 and 6 of a seven-line file, never at 2, 3 and 5.

- **The implementer brief.** In `plugin/agents/delivery-implementer.md`, the bullet that starts "A product question you
  can't answer" becomes, exactly, its line breaks as here:

  > - Ask nothing mid-task and wait on no message: the runner is inside your Agent call until you end, so a question
  >   goes in your report. A product question you can't answer from the task file, the cited SPEC or the product docs
  >   is an open question there: the runner answers it or takes it to the lead. Don't guess intent. An implementation
  >   choice the task leaves open: take the narrowest reading, say so in your report, and go on.

- **The runner brief.** In `plugin/agents/delivery-runner.md`, the step **Questions from the implementer** becomes, exactly, its line breaks as here:

  > 6. **Questions from the implementer** come in its report: you are inside its Agent call until it ends. On an
  >    implementation choice the implementer takes the narrowest reading and flags it: accept it, or give your choice in
  >    the fix round's `--note` (`ccp prompt fix`) once review has run. Spec questions go to the lead (below). Unsure: spec.

- **The implement prompt.** In `templates/prompts/implement.md`, the two lines that start "Questions: an implementation
  choice (how to build it)" and "Send it to `{{runner}}`" become, exactly, these two lines (the line after them, "A product
  or spec question: …", goes too, since the second line below replaces it):

  > Questions: an implementation choice the task leaves open is yours: take the narrowest reading and flag it in your report.
  > A product or spec question: stop that part and put it in your report.

- **The prompt's test.** In `"def test_workers_message_the_runner_by_its_bound_name"`, the assertion
  `"Send it to `runner-2` with SendMessage"` goes; the two `_common.md` assertions on `runner-2` stay and hold the bound
  name. No other test expectation changes.

## Scope

- **In:** `plugin/skills/writing-tasks/SKILL.md` (one bullet), `plugin/agents/delivery-implementer.md` (one bullet),
  `plugin/agents/delivery-runner.md` (the step **Questions from the implementer**), `templates/prompts/implement.md`
  (the question lines), `tests/test_prompt_note_env.py` (one assertion).
- No SPEC change (measured in Context).
- **Out:** the fix prompt and `_common.md`; the reviewer's and verifier's briefs; `docs/cli/03-quality.md`.

## dod_checks

- id: `doc-01`
  story: As a task writer, the skill tells me a revert check's fixture leaves an unchanged line between the hunks it tells apart.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `grep -n -e 'U0' -e 'A behaviour-preserving change' -e 'A speed check' plugin/skills/writing-tasks/SKILL.md`.
    2. Run `grep -c 'never at 2, 3 and 5' plugin/skills/writing-tasks/SKILL.md`.
  expect: step 1 prints three lines, in this order: the behaviour-preserving bullet's first line, one line holding `git diff -U0` (the ruled bullet's second line), the speed-check bullet's first line; step 2 prints `1`.
  dry run (`b09de675`): step 1 printed 2 lines (lines 129 and 135, the behaviour-preserving and the speed-check bullets), no `U0` line; step 2 printed `0`.
- id: `doc-02`
  story: As an implementer, my brief and my prompt tell me to put a question in my report and not wait; as a runner, my brief tells me it comes there.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `grep -c 'answer by .SendMessage' plugin/agents/delivery-runner.md`.
    2. Run `grep -c -e 'wait on no message' -e 'narrowest reading' plugin/agents/delivery-implementer.md`.
    3. Run `grep -n 'Questions from the implementer\*\* come in its report' plugin/agents/delivery-runner.md`.
    4. Run `grep -c 'with SendMessage' templates/prompts/implement.md`.
    5. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_plugin tests.test_prompt_note_env`.
  expect: step 1 prints `0`; step 2 prints `2`; step 3 prints one line; step 4 prints `0`; step 5 exits 0.
  dry run (`b09de675`): step 1 printed `1`; step 2 printed `0`; step 3 printed nothing (exit 1); step 4 printed `1`; step 5 (scratch QUEUE_ROOT) printed `passed, exit 0, lane part … 44 tests`.

## Implementation notes

- Built the five edits exactly as ruled. Re-measured at `c8aa9c30`: every figure in Context holds (the one commit since
  `b09de675`, 0310's squash, touched `delivery-implementer.md`'s `ccp suite affected` bullet only, not the question bullet).
- `{{runner}}` is no longer used in `templates/prompts/implement.md`; `_common.md` still binds it, and the test's two
  `runner-2` assertions on `_common.md` stay.

## Verification notes
- 2026-11-24 — verifier, PR #382 head `3b13bd9` (squash `f255dfe`): APPROVE. Passed: doc-01, doc-02. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0314-task-writers-leave-a-line-between-a-revert-check-s-hunks-and-an-implementer-s-questions-go-in-its-report.json.

