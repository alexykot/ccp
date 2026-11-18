---
task_id: 0150-runner-loop-fixes
title: The runner tries verify first after a fix of a clean review, next passes over a task held back only by a path clash, the PR body names the task, and a cleared wait clears its detail
status: pending
kind: feature
depends_on: []
spec_refs: ["S16", "S15", "S10"]
review_point: R10
sign_off: brief
paths: ["plugin/agents/delivery-runner.md", "ccp/parallel.py", "ccp/cli.py", "ccp/plan.py", "templates/prompts/implement.md", "scripts/observability/set-waiting-on.sh", "ccp/lifecycle.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_parallel_claims.py", "tests/test_parallel_slots.py", "tests/test_prompt_pr_body.py", "tests/test_next_passes_over.py", "tests/test_wait_detail.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0150-runner-loop-fixes
## Intent

Four places where a runner loses a turn or reads something stale are closed. After a fix round that
answers a clean review, the runner asks for the verify first and opens a new review only when `ccp
prompt verify` refuses, so `verify.skip_review_after_clean` saves the review it is meant to save. With
several runners, `ccp tasks next` no longer stops at a ready task held back only because its paths meet
an in-flight task's: it offers the first task after it that may run now, without starving the one it
passed over, and names it. The implementer's PR body carries the full task id from the start, so `ccp
prompt review` does not refuse it. A cleared wait leaves no stale detail in `work.json`.

## Context (not checked)

- **Minor-only fix path (proposal `257d`).** `plugin/agents/delivery-runner.md`'s Review step says "When it finds a
  BLOCKER or MAJOR, `ccp prompt fix …` launches the implementer on the findings, then review again", and
  names `verify.skip_review_after_clean` only inside the sentence on what `ccp prompt verify` refuses
  (`git grep -n "skip_review_after_clean" -- plugin/agents/delivery-runner.md` at `85d388b`: 1 line). A
  runner that fixed a clean review's MINOR findings followed "review again" and never tried verify: the
  proposal reports two tasks that went fix, review-2, verify with no verify refusal recorded. The code is
  right: `ccp prompt verify` already opens the verify for such a head and refuses (exit 4) one that needs a
  review (`ccp/verify.py`, `"skip_review_after_clean took it as a fix of a clean review's minor findings"`).
  Only the brief changes.
- **Head of line (proposal `6eae`).** `parallel.next_choice` takes the first ready task not in flight only
  when it may join the tasks in flight, "and nothing behind it is taken instead" (its docstring); §16.3
  says so ("head of line: no task waits forever behind smaller ones"). The proposal: with one task in
  flight and a preferred task whose path met it, `next` reported slots full and never offered a later task
  that met nothing in flight. The rule exists against starvation. A task held back only by the path rule (a path
  meets an in-flight task's) waits for that in-flight task to close; it starves only if a task taken
  instead also meets its paths. So `next` may pass over a rule-3 task as long as what it takes meets none
  of the passed-over tasks' paths. A task held back by any other claim rule still holds the line: a task that
  must run alone (`parallel: false`, no path, an exclusive path) would starve behind any task taken past it. This changes a § rule, carried
  below for signing.
- **PR body (proposals `7380` and the PR-body half of `8f65`).** `ccp prompt review` refuses (exit 2) a PR
  whose body does not contain the task id (§15.2; `tests/test_prompt_pr_body.py`), and the runner then
  repairs the body with `gh pr edit`. `templates/prompts/implement.md` gives the PR's title ("Task
  {{nnnn}}: <short title>", the short number) and says nothing of its body
  (`git grep -n "body" -- templates/prompts/implement.md` at `85d388b`: no line). Ruled: the prompt gives
  the body's first line with the full id; `ccp prompt review` keeps reading the full id, so §15.2 is
  unchanged. The other half of `8f65` (the run-checkout self-check reading the wrong checkout) is not this
  task's.
- **Wait detail (proposal `557d`).** `scripts/observability/set-waiting-on.sh` writes `work.json`
  `waiting_on_detail` only `if detail:` and never removes it, so a `clear` (or a later `set` without
  `--detail`) leaves the old detail beside `waiting_on: null`: this repo's `work.json` holds
  `waiting_on: null` with `waiting_on_detail` naming an old ruling, read 2026-11-18. Close and release
  (`_leave_work`, `closed` in `ccp/lifecycle.py`) copy the next task's wait from `WAIT_KEYS`, which has no
  detail key, so they leave it too. `team.sh runner status` prints `waiting_on_detail` for one runner.

## Scope

- **In:**
  - `plugin/agents/delivery-runner.md` step 7: its own instruction, ahead of the refusal text: after a fix
    round, run `ccp prompt verify` first; it opens the verify when the fix needs no new review (a clean
    review's MINOR and NIT fix under `verify.skip_review_after_clean`, or a fix `verify.skip_review` or a
    review prover proves), and refuses (exit 4), naming why, when it needs one: then run `ccp prompt
    review` on the new head. "Then review again" goes.
  - `ccp/parallel.py` `next_choice`: with tasks in flight, walk the ready tasks not in flight in rank order.
    A task that may join is returned, unless one of its paths meets a path of a task already passed over:
    then it is passed over too (it waits behind that task). A task that fails rule 3 and no other rule is
    passed over and the walk goes on. Any other task that
    may not join (rules 1, 2, 4 or 5) ends the walk with none, as today; `slots_full` keeps
    `head` as the first ready task. Rule 5 is judged as today.
  - `ccp/cli.py` `ccp tasks next`: one stderr line per task passed over, `ccp tasks next: passed over
    <id>: <the rule-3 reason>`; `--json` adds `passed_over`, a list of `{task_id, why}`, to the task it
    returns, and to the `slots_full` body when nothing was returned. `ccp/plan.py` (the board) takes the
    same choice and only its docstring changes.
  - `templates/prompts/implement.md`: the PR's body begins with the line `Task: {{task_id}}` (the full
    id), beside the title instruction.
  - `scripts/observability/set-waiting-on.sh`: when it writes `work.json`, `waiting_on_detail` is the
    `--detail` value on a `set` and null on a `set` without one and on every `clear`. `ccp/lifecycle.py`:
    `WAIT_KEYS` gains `waiting_on_detail`, so close and release set it from the next task's state (which
    has none: null).
  - `docs/spec/02-delivery.md` §16.3. CURRENT (at `85d388b`, over two lines): "**`ccp tasks next`** ranks as before (§10.3), then: if the first ready task not in A could not be claimed beside A, it returns none (head of line: no task waits forever behind smaller ones); otherwise it returns that task." PROPOSED:
    > **`ccp tasks next`** ranks as before (§10.3), then walks the ready tasks not in A in that order and returns the first that could be claimed beside A and none of whose paths meets a path of a task it passed over; it passes over, naming each, a task that rule 3 alone keeps from joining A and a task whose path meets one it passed over; a task that any other rule keeps from joining A ends the walk with none (head of line: no task waits forever behind smaller ones, and a task passed over waits only for the in-flight tasks its paths meet).
  - The PROPOSED passage replaces both CURRENT lines, on one unwrapped line, so `ccp verify spec-text`
    finds it. `docs/cli/02-delivery.md`'s `ccp tasks next` row: one clause naming the passed-over lines.
  - `tests/test_parallel_claims.py`'s `test_meeting_paths_are_refused_and_the_head_of_line_waits` (it
    pins the old rule: its `next` expects slots full with a later task ready); `tests/test_parallel_slots.py`
    where it pins the head; `tests/test_next_passes_over.py` (new); `tests/test_prompt_pr_body.py`;
    `tests/test_wait_detail.py` (new).
- **Out:**
  - `ccp tasks claim`'s rules (unchanged: a claim is judged as today).
  - The forecast's model of the head of line (§16.7), and `ccp prompt review` accepting a short id.
  - A note from `ccp prompt review` that the skip would apply (the brief change is enough).

## dod_checks

- id: `brief-01`
  story: As a runner after a fix of a clean review, my brief sends me to verify first.
  setup: a checkout of the PR head.
  steps:
    1. Read step 7 of `plugin/agents/delivery-runner.md`.
  expect: step 7 has an instruction that after a fix round the runner runs `ccp prompt verify` first and runs `ccp prompt review` on the new head only when verify refuses (exit 4); the words "then review again" do not occur in it.
  dry run (`85d388b`): step 7 says "launches the implementer on the findings, then review again" (fails, as it should).
- id: `next-01`
  story: As a second runner, I get a task that meets nothing in flight, even when the preferred one clashes.
  setup: a scratch product with `parallel.max_in_flight` 2 and tasks A (in flight, path `src/a.py`), B (pending, preferred first, path `src/a.py`), C (pending, path `src/c.py`).
  steps:
    1. Run `ccp tasks next --json`.
  expect: exit 0; the task returned is C; `passed_over` is one entry, B, whose `why` names `src/a.py` and A; stderr has the `passed over` line for B.
  dry run: n/a — at `85d388b` it exits 7 with `head` B.
- id: `next-02`
  story: As a task passed over, I am not starved by a task that clashes with me, and a task that runs alone still holds the line.
  setup: a scratch product with `parallel.max_in_flight` 2 and task A in flight (path `src/a.py`).
  steps:
    1. With B (paths `src/a.py`, `src/b.py`), D (path `src/b.py`) and C (path `src/c.py`) pending in that rank order, run `ccp tasks next --json`.
    2. With only E (`parallel: false`) and C pending, E first, run `ccp tasks next --json`.
  expect: step 1 exits 0 returning C, with `passed_over` B then D (D's `src/b.py` meets B's); step 2 exits 7 with `slots_full` true and `head` E.
  dry run: n/a.
- id: `prm-01`
  story: As an implementer, my prompt gives my PR body's first line with the full task id.
  setup: a scratch product with a task claimed.
  steps:
    1. Run `ccp prompt implement <task>` and read the rendered prompt file.
  expect: the prompt holds the line `Task: <the full task id>` as the PR body's first line.
  dry run: n/a.
- id: `wait-01`
  story: As a runner reading work.json, a cleared wait leaves no detail behind.
  setup: a scratch queue with a task claimed as the current task.
  steps:
    1. Run `ccp tasks wait <task> spec_maintainer --detail Q1`, then `ccp tasks resume <task> spec_maintainer`.
    2. Run `ccp tasks wait <task> spec_maintainer --detail Q2`, then `ccp tasks wait <task> runner`.
  expect: after step 1, `work.json` has `waiting_on` null and `waiting_on_detail` null; after step 2, `waiting_on` is `runner` and `waiting_on_detail` null.
  dry run: n/a — at `85d388b` step 1 leaves `waiting_on_detail` `Q1`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, `ccp verify spec-text 0150`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
