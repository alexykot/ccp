---
task_id: 0093-runner-rotation-is-enforced
title: Runner rotation is enforced, by task count and by context size, and the runner's model is checked
status: pending
kind: feature
depends_on: []
spec_refs: ["S2", "S16", "S24"]
review_point: R5
paths: ["ccp/lifecycle.py", "ccp/health.py", "ccp/usage.py", "ccp/config.py", "scripts/observability/team.py", "plugin/agents/delivery-runner.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "contracts/project.schema.json", "tests/test_rotation*.py", "tests/test_health*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0093-runner-rotation-is-enforced

## Intent

A runner is rotated when its slot reaches the rotation threshold, whether or not it asks, so a
long-lived runner does not carry an ever-growing context into every request (§2, §16.5).

## Context (not checked)

- Accepted plane proposal. A managed product's delivery data showed runners lasting about twice
  `rotate_after_tasks` on average, because rotation happens only when the runner asks; the runner
  seat was among the largest spenders per task, at a large per-request context.
- The same data attributed requests on a larger model to the runner seat, although
  `plugin/agents/delivery-runner.md` declares `model: claude-sonnet-5-5`. Either the usage
  attribution is wrong or the teammate runs on the lead's model.
- §31.1: making rotation enforced, and the context-size trigger, are new rules beyond the current
  "the runner asks" text, so the § text below waits for the operator's approval at a merge gate.

## Scope

- **In:**
  - `ccp tasks claim` refuses (exit 7, naming the slot and the rotation command) a new claim by a
    slot whose `tasks_done` has reached `runner.rotate_after_tasks`, until `team.sh runner rotate`
    records its rotation; a resume of a held task is never refused.
  - `runner.rotate_at_context_tokens` (binding, default null = off): when the runner seat's latest
    per-request context in usage telemetry (§24) reaches it, rotation is due the same way.
  - `ccp health` reports a slot that is due and not rotated, and the count of rotations against
    tasks done.
  - The model check: find where the runner teammate's model comes from (its agent definition, or
    the lead's model at spawn) and where telemetry attributes requests to the runner seat; fix the
    plane's side (attribution, or the spawn passing the declared model), and record the finding in
    Implementation notes.
  - §2 step 4, CURRENT: "When its context gets heavy, or its slot's `tasks_done` reaches
    `runner.rotate_after_tasks` (default 4), the runner finishes the current phase, writes
    `work.json` and asks the lead to rotate it." PROPOSED: "When its slot's `tasks_done` reaches
    `runner.rotate_after_tasks` (default 4), or the runner seat's request context reaches
    `runner.rotate_at_context_tokens` (default off), rotation is due: `ccp tasks claim` refuses the
    slot a new task until the lead rotates it. The runner finishes the current phase, writes
    `work.json` and asks the lead to rotate it, as it also may sooner when its context gets heavy."
    §8.3 names the new knob.
- **Out:** rotating mid-task.

## dod_checks

- id: `check-01`
  story: As a lead, a runner past its threshold cannot take another task.
  setup: a scratch product with `runner.rotate_after_tasks: 2` and a slot whose `tasks_done` is 2.
  steps:
    1. Run `ccp tasks claim <next> --holder <slot>`.
    2. Run `team.sh runner rotate --slot <slot>`, respawn, and claim again.
  expect: the first claim is refused (exit 7) naming the rotation; after the rotation it succeeds.
  dry run: on the merge base the first claim succeeds.
- id: `check-02`
  story: As a lead, a large context also makes rotation due.
  setup: as check-01 with `tasks_done` 0, `runner.rotate_at_context_tokens: 100000`, and a usage
    sample for the runner seat at 120000 context tokens.
  steps:
    1. Run `ccp tasks claim <next> --holder <slot>`, then `ccp health`.
  expect: the claim is refused naming the context trigger; health reports the slot as due.
  dry run: n/a — the knob does not exist yet.
- id: `check-03`
  story: As the operator, the runner runs on the model it declares.
  setup: a checkout of the PR head.
  steps:
    1. Read the Implementation notes' finding and the test that pins it.
  expect: the finding names the cause; a test fails if the runner seat's requests are attributed to
    or spawned on a model other than the agent's declared one.
  dry run: n/a.
- id: `check-04`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12 (implementer): **Rotation enforced.** `lifecycle.rotation_due(q, slot)` decides it: with
  slots, the slot's `tasks_done`, `spawned_at` and `rotated_at`; with one runner, `runner_tasks_done`,
  `runner_spawned_at` and `runner_rotated_at` (rotated when at or after the spawn). Due when
  `tasks_done` reaches `runner.rotate_after_tasks` (default 4), or when `runner.rotate_at_context_tokens`
  is set and the slot's teammate's latest request since its spawn sent at least that many tokens
  (input + cache read + cache written), read from `board/usage-spans.jsonl` by the span's
  `<bound name>@session-…` agent id (`usage.runner_context`). A recorded rotation clears it; the
  respawn resets the counters. `ccp tasks claim` refuses a new claim of a due slot with exit 7, naming
  the trigger and the rotate command; a resume is never refused. `ccp health` (`rotation` in `--json`,
  lines in the text view) lists the due slots and the ledger's `runner`/`rotate` events against
  distinct tasks moved to `done`. The binding contract has the new knob; §10.2 step 4 and §8.3 carry
  the task's text.
- 2026-11-12 (implementer): **The model finding (check-03).** The runner teammate runs on its
  declared model: its spawn (`team.sh runner spawn`) prints an Agent call with `subagent_type` and no
  `model`, and every request whose span names the runner teammate (`<name>@session-…`) was on the
  definition's model. The larger-model requests on the runner seat came from attribution: a call with
  no `agent_id` is placed by its session's cwd (§24.4), and a headless `claude -p` session
  (`query_source: sdk`) run from a runner's checkout, not matched to a recorded headless session, was
  counted as the runner seat. Fix: `usage._main_seat` puts an `sdk` call from a runner's checkout in
  `headless-untagged`, as it already did for one with no cwd. Pinned by
  `tests/test_rotation_model.py` (the fold's runner seat shows only the declared model; the spawn
  actions carry no `model`). docs/design/board.md says so. §24.4's "a runner's merge checkout is that
  runner's" now has this exception in code only: its SPEC wording is left for a ruling.

## Verification notes

*Append-only.*
