---
task_id: 0151-rotation-refills-the-slot
title: A runner being rotated out takes no new task, and a slot left empty after a rotation is named to the lead until it is refilled
status: pending
kind: feature
depends_on: []
spec_refs: ["S10", "S16", "S18"]
review_point: R10
sign_off: brief
paths: ["ccp/lifecycle.py", "scripts/observability/team.py", "plugin/hooks/runner-idle.sh", "plugin/agents/delivery-runner.md", "plugin/skills/spec-maintainer/SKILL.md", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_rotation.py", "tests/test_runner_idle_rotation.py", "tests/test_parallel_merging.py", "tests/test_tasks_drop.py", "tests/test_rotation_refill.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0151-rotation-refills-the-slot
## Intent

A rotation bounds a runner's context as meant: from the moment the lead records it until the fresh
runner is bound, the slot takes no new task, so the outgoing runner cannot start one and hand the
fresh runner a task mid-flight. A slot whose rotation was recorded and never respawned does not stay
empty unnoticed: each close or release names it, the runner tells the lead, and the lead's rotate
output says the slot stays empty until the spawn runs.

## Context (not checked)

- **The outgoing runner can claim (proposal `c0e2`).** `rotation_due` in `ccp/lifecycle.py` returns None
  once the rotation is recorded (`"if rotated:\n        return None"`), and `claim` refuses only on
  `rotation_due`. So between `team.sh runner rotate` and the respawn, the slot's claim is allowed again,
  and the holder is the slot, not the teammate: the outgoing runner's claim succeeds. A test pins exactly
  that path today: `tests/test_rotation.py` `test_one_runner_is_held_to_it_too` runs `team.sh runner
  rotate` and then expects the claim to pass with no spawn in between. After a respawn, `bind_pending` is
  true until the lead binds (`"bind_pending": bool(was.get("rotated_at"))` in
  `scripts/observability/team.py`), but claim does not read it either.
- **What wakes the outgoing runner.** `plugin/hooks/runner-idle.sh` skips a slot with `bind_pending`
  (respawned, not bound) but not a slot whose rotation is recorded and not yet respawned, and
  `rotation-due` answers "not due" for it; so the hook keeps the outgoing runner working on ready scope,
  which is how it reaches the claim.
- **Rotate already says how to refill (proposal `9b5a`, partly false).** `team.sh runner rotate --slot`
  returns a `respawn` action with `cmd` `team.sh runner spawn --slot <slot>` (`"action": "respawn"` in
  `cmd_slots`). It does not run the spawn itself, and should not: §10.2's Rotate step has the lead spawn "only
  once it is gone", and the spawn records the slot's `spawned_at` and resets `tasks_done`. In the proposal's
  case the lead chose to leave the slot empty and nothing reminded anyone. What is missing is a notice,
  not the command.
- **Where the notice goes.** `idle_runners` (§16.5 rule 7), which `ccp tasks close`, `release` and `drop`
  print, lists every slot holding no task, a rotated one included, and the runner messages each bound
  name: a message to the rotated teammate, which is gone, wakes no one. Those outputs are the place where
  a freed slot is already noticed, so they also name the slot that has no runner.
- **Is rotation a § rule?** Yes: §10.2's Rotate step states when claim refuses and the rotate, shutdown, spawn
  and bind order; §16.5's freed-slot rule states `idle_runners`. The claim change is a rule change, carried below for
  signing; `vacant_slots` is this task's own feature, described under §31.1.

## Scope

- **In:**
  - `ccp/lifecycle.py` `claim`: a new claim (not a resume) by a slot whose rotation is recorded and whose
    fresh runner is not yet bound refuses (exit 7), naming the slot and the step left (`team.sh runner
    spawn --slot <slot>`, or `team.sh runner bind --name <name> --as <slot>`). With slots: the slot's
    `rotated_at` set, or its `bind_pending` true. With one runner: `runner_rotated_at` at or after
    `runner_spawned_at`, or `runner_bind_pending` true. A resume is never refused, as today.
  - `plugin/hooks/runner-idle.sh`: a slot whose `rotated_at` is set (one runner: rotated since its spawn)
    is not kept working, as a `bind_pending` one is not.
  - `ccp/lifecycle.py` `idle_runners` leaves out a slot whose `rotated_at` is set; close, release and drop
    add `vacant_slots`, the slots whose `rotated_at` is set, when there are any.
  - `scripts/observability/team.py`: `rotate --slot`'s `respawn` action's detail says the slot holds no
    runner until that spawn runs, and that `team.sh runner stop --slot <slot>` is the way to run fewer
    runners; `runner status` marks such a slot `vacant: true`.
  - `plugin/agents/delivery-runner.md` rule 5 and `plugin/skills/spec-maintainer/SKILL.md` (its
    `idle_runners` line): on `vacant_slots`, the runner (or the lead after its own release) sends the lead
    one message naming each slot and `team.sh runner spawn --slot <slot>`.
  - `docs/spec/02-delivery.md` §10.2 step 4. CURRENT (at `85d388b`): "`ccp tasks claim` refuses the slot a new task until the lead rotates it." PROPOSED:
    > `ccp tasks claim` refuses the slot a new task until the lead rotates it, and from the rotation until the lead binds the fresh runner (`team.sh runner bind`), so the runner being rotated out takes no new task.
  - `docs/spec/02-delivery.md` §10.2 step 4. CURRENT (at `85d388b`): "Until that bind no teammate is kept working (§18.2)." PROPOSED:
    > From the rotation until that bind no teammate of the slot is kept working (§18.2).
  - Each PROPOSED passage goes in on a line of its own, unwrapped, so `ccp verify spec-text` finds it.
  - §31.1: §16.5 rule 7, one sentence: close and release also name `vacant_slots`, the slots rotated and
    not respawned, which `idle_runners` leaves out, and the runner tells the lead. `docs/cli/02-delivery.md`:
    the close and release rows, one clause.
  - Tests: `tests/test_rotation.py` (`test_one_runner_is_held_to_it_too` pins the old path; the tests that
    rotate, respawn and claim now bind first), `tests/test_runner_idle_rotation.py`,
    `tests/test_parallel_merging.py` and `tests/test_tasks_drop.py` where they pin `idle_runners`, and
    `tests/test_rotation_refill.py` (new).
- **Out:**
  - Running the spawn inside `rotate` (§10.2's order stays: shut down, then spawn).
  - An idle-slot notice outside close, release and drop (a timer or the board).

## dod_checks

- id: `rot-01`
  story: As a rotation, I keep the outgoing runner from starting a new task.
  setup: a scratch product with runner slots `runner-1` and `runner-2`, `runner.rotate_after_tasks` 2, `runner-1` at `tasks_done` 2, and a ready task.
  steps:
    1. Run `team.sh runner rotate --slot runner-1`.
    2. Run `ccp tasks claim <task> --holder runner-1`.
    3. Run `team.sh runner spawn --slot runner-1`, then step 2 again.
    4. Run `team.sh runner bind --name runner-1-b --as runner-1`, then step 2 again.
  expect: steps 2 and 3's claims exit 7, each naming the step left (spawn, then bind), with nothing leased; step 4's claim exits 0.
  dry run: n/a — at `85d388b` step 2's claim exits 0.
- id: `rot-02`
  story: As one runner, I am held the same way.
  setup: a scratch product with one runner (no slots), `runner_tasks_done` at its threshold, and a ready task.
  steps:
    1. Run `team.sh runner rotate`, then `ccp tasks claim <task>`.
  expect: the claim exits 7 naming `team.sh runner spawn`; nothing leased.
  dry run: n/a — this is the path `test_one_runner_is_held_to_it_too` passes today.
- id: `rot-03`
  story: As the outgoing runner, the idle hook lets me go.
  setup: the product of rot-01 after step 1, `runner-1`'s bound name `runner-1`, a ready task in scope.
  steps:
    1. Feed `plugin/hooks/runner-idle.sh` a TeammateIdle input for `runner-1`.
  expect: exit 0 (not 2): it is not kept working.
  dry run: n/a.
- id: `vac-01`
  story: As the lead, I hear about a slot left empty after a rotation.
  setup: the product of rot-01 after step 1 (no respawn), `runner-2` holding a task that is verified and ready to close.
  steps:
    1. Run `ccp tasks close <runner-2's task> --pr <n> --summary "done."`.
    2. Run `team.sh runner status`.
  expect: close's JSON has `vacant_slots` `["runner-1"]` and `idle_runners` without `runner-1`; status marks `runner-1` `vacant: true`.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, `ccp verify spec-text 0151`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
