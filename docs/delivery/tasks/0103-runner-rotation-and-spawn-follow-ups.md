---
task_id: 0103-runner-rotation-and-spawn-follow-ups
title: The idle hook knows both rotation triggers, rotation reads its counts safely, and a spawn dry run checks the integration ref
status: pending
kind: fix
depends_on: []
spec_refs: ["S2", "S10", "S16"]
review_point: R6
paths: ["plugin/hooks/runner-idle.sh", "ccp/lifecycle.py", "scripts/observability/team.py", "scripts/team.sh", "tests/test_rotation*.py", "tests/test_team_dry_run.py", "tests/test_team_hosting.py", "tests/test_orientation*.py", "tests/test_runner_idle*.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0103-runner-rotation-and-spawn-follow-ups

## Intent

A runner that is due for rotation is due for the same reason everywhere:
- The idle hook stops driving a runner that has reached either trigger, not only the task count.
- `rotation_due` reads its counts without crashing.
- A slot's spawn dry run says a runner worktree "would be made" only when it could be.

## Context (not checked)

- Three accepted plane proposals (operator, 2026-11-16: all approved).
- `plugin/hooks/runner-idle.sh` checks only `rotate_after_tasks`. Claim also enforces
  `runner.rotate_at_context_tokens`, so the hook keeps driving a runner that claim will refuse.
- `rotation_due` casts `tasks_done` with an unguarded `int()`. A missing `runner_spawned_at` counts
  every span of the name, not only the current one.
- The dry run's `runner_worktree` check says "would be made" without checking that
  `origin/<integration>` resolves. A real spawn does not check it either.
- Untested: the `--slot` respawn and `--review-point` dry-run paths, and the orientation hook with
  `CLAUDE_PLUGIN_ROOT` set.

## Scope

- **In:**
  - The idle hook judges rotation through the same rule claim uses, by calling `ccp` (a
    `rotation_due`-backed command or flag) rather than restating it. A runner due under either trigger
    is let idle and report.
  - `rotation_due`: a `tasks_done` that is not an integer reads as 0, with a warning. A missing
    `runner_spawned_at` counts only spans since the slot's last spawn event, or none when there is
    none. The implementer states the choice and tests it.
  - `team.sh runner spawn` (dry run and real) checks that the integration branch's remote ref resolves before it
    makes or promises a runner worktree, and refuses naming the ref when it does not.
  - Tests for the `--slot` respawn and `--review-point` dry-run paths, and for the orientation hook
    with `CLAUDE_PLUGIN_ROOT` set.
- **Out:**
  - Changing the rotation thresholds or their defaults.

## dod_checks

- id: `check-01`
  story: As a lead, the idle hook does not drive a runner that claim would refuse.
  setup: a throwaway queue with a bound slot whose latest request's context is above
    `runner.rotate_at_context_tokens` and whose `tasks_done` is below `rotate_after_tasks`, with
    scope left.
  steps:
    1. Run the idle hook as the slot's teammate.
  expect: exit 0, with no prompt to claim. The same setup below both thresholds drives the runner as
    today.
  dry run: n/a.
- id: `check-02`
  story: As a lead, a malformed slot record does not crash rotation.
  setup: a slot whose `tasks_done` is `"x"`, and a slot with no `runner_spawned_at`.
  steps:
    1. Run `ccp tasks claim` for each.
  expect: no traceback. The first warns and reads 0. The second counts as the implementer documented.
  dry run: n/a.
- id: `check-03`
  story: As a lead, a dry run does not promise a worktree it cannot make.
  setup: a throwaway product whose origin has no integration branch.
  steps:
    1. Run `team.sh runner spawn --slot runner-1 --review-point R1 --dry-run`.
  expect: refuses, naming `origin/<integration>`, and nothing is made.
  dry run: this check is the dry run.
- id: `check-04`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-16 (implementer):
  - **The hook asks claim's rule.** New `ccp tasks rotation-due [--holder <slot>]`
    (`lifecycle.rotation_check`, backed by `rotation_due`) prints `{"due": false, "slot": …}` or
    `{"due": true, …}` with the trigger and the rotation to run, exit 0; a holder that is no runner
    slot refuses (exit 2), as claim does. `runner-idle.sh` calls it (with `--holder` the slot, or the
    bound runner) and lets a due runner idle; an answer that does not read (old `ccp`, non-zero exit,
    bad JSON) reads as not due, so the hook drives as before and claim still refuses. The hook no
    longer reads `rotate_after_tasks` itself. This touches `ccp/cli.py` and `docs/cli/02-delivery.md`,
    beyond the declared paths.
  - **`rotation_due` reads its counts safely.** `tasks_done` (slot) or `runner_tasks_done`: a whole
    number, or one written as digits, counts; anything else (`"x"`, a list, `true`, `2.5`) reads as 0
    with `warning: work.json <field> is …` on stderr. A record with no spawn time (`spawned_at`, or
    `runner_spawned_at` for one runner) counts only the requests since that slot's latest
    `runner`/`spawn` ledger event (one runner: the latest spawn event with no `slot`); with no such
    event it counts none, so the context trigger cannot fire. The rotated-since-spawn test is unchanged.
  - **The spawn checks the integration ref.** `team.sh runner spawn`, dry run and real, single runner
    and slots, refuses (exit 3, naming `origin/<integration_branch>`) before any write when the ref
    does not resolve in the product's main checkout and the spawn would make or promise a runner
    worktree: the binding's `runner.worktree` (one runner) or the slot's recorded or
    `<runner.worktree>-<slot>` worktree, and only when that path is not a working tree already. It
    reads the local remote-tracking ref and fetches nothing. With no runner worktree named, or one
    that exists, nothing is checked. check-03's setup therefore names a `runner.worktree` in the
    binding (`TestSpawnNeedsTheIntegrationRef`).
  - **Tests.** Idle hook: `tests/test_runner_idle_rotation.py`. Counts and the command:
    `tests/test_rotation.py` (helpers moved into `RotationFixture`). Spawn, `--slot` respawn and
    `--review-point` dry runs: `tests/test_team_dry_run.py`. Orientation with `CLAUDE_PLUGIN_ROOT`:
    `tests/test_orientation_hook.py`; `test_orientation_command.hook_text` now unsets it so the
    comparison reads this checkout's plugin. `TeamCase.origin()` gives a test product a bare origin;
    the existing runner-worktree dry-run test and `test_parallel_slots.LeadSlots` use it, since their
    spawns now need `origin/main` (expectations unchanged).

## Verification notes
