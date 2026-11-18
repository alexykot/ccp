---
task_id: 0156-plane-hygiene
title: The plane's self-check reads its own checkout, a kept binding's shape is read by nesting, the idle runner is told of a due architect pass, and a claim's start has one time
status: pending
kind: feature
depends_on: []
spec_refs: ["S29", "S8", "S18", "S19", "S10"]
review_point: R10
paths: ["ccp/cli.py", "ccp/init.py", "ccp/queue.py", "ccp/lifecycle.py", "plugin/hooks/runner-idle.sh", "tests/test_plugin.py", "tests/test_init.py", "tests/test_runner_idle_rotation.py", "tests/test_release.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0156-plane-hygiene
## Intent

Four plane follow-ups that make its warnings and readings true:
- The §29 self-check warns only when the plane checkout `ccp` runs from has drifted, never because of
  the caller's checkout, so a worker can trust it.
- A kept binding's shape warnings name exactly the keys it lacks or carries at the depth they belong.
- A runner whose only task waits is told to start a due architect pass instead of idling past it.
- A claim's recorded start is one instant, so a release-and-claim reading never splits across a second.

## Context (not checked)

- **Self-check.** `checkout_warning` in `ccp/cli.py` runs `git -C <PLANE>` with the caller's environment.
  A `GIT_DIR` set in that environment overrides `-C`, so git reads the caller's repository. Probe at
  `85d388b`, from a task worktree of this repo: `GIT_DIR=<that worktree's git dir> ccp --root <it>
  tasks list --json` printed "running from <run checkout>, but it is on <the worktree's branch>, not
  main". The same command without `GIT_DIR` printed no warning. This matches what implementers see:
  the run checkout's path with a `task/...` branch and "local changes". Which tool sets `GIT_DIR`
  for the worker (a git hook, the harness) is not known. The fix does not depend on it.
- **Binding shape.** `_binding_keys` in `ccp/init.py` appends every indented key, at any depth, to its
  top-level key. Probe at `85d388b` (`python3 -c` with `init._binding_keys` and
  `init.binding_shape_warnings`) on a binding with `runner:` holding `agent_type` and
  `slots: {a: {name: r1}}`, and `seats:` holding `lead: {runner: x}`. It reads `runner` as
  `['agent_type', 'slots', 'a', 'name']`, so it misses that `runner.name` is absent. It also warns
  that the binding carries `seats.runner`, which is two levels deep. `upgrade.binding_keys` in
  `ccp/upgrade.py` already reads the binding as nested objects by indentation.
- **Idle runner.** `plugin/hooks/runner-idle.sh` asks `ccp tasks next` (where an architect pass due
  shows) only `if ready and (parallel_on or has_architect)`. A runner whose held task waits has
  nothing ready, so the hook lets it idle and never names a due pass. `ccp architect due` exits 0 with
  the reason when a pass is due, and 3 when none is (`"0 if info[\"due\"] else 3"` in
  `ccp/architect.py`). Its JSON carries `failed_in_a_row`, and `architect.gate` stops blocking on a
  pass once two in a row have failed.
- **Claim time.** `claim` in `ccp/lifecycle.py` stamps `claimed_at` from `t = now()` and then writes
  the `lease`/`set` event through `emit`, which takes its own `iso()`. Across a second boundary the
  two differ by a second. `drill.collect` starts an open task at the earlier of the two, so
  `tests.test_release` `test_the_task_starts_at_the_claim_after_a_release` fails once in a while: it
  failed one verifier gate and passed alone.
- **Left out on purpose.** SPEC §14.4 ("`cold` is filled as `true` when the cited run has `cached == 0`")
  and §15.3 ("a cited suite run with `cached == 0` gives it") have been true since task 0146 only for
  rows written after it. `fill_gate` now also needs the row's own `cold` to be `true`, so a legacy row
  with a zero `cached` and no `cold` is not filled. Correcting that text is not §31.1 for this task: §31.1
  covers passages the task's own change makes false, and this task's change does not touch them. It
  needs its own signed CURRENT → PROPOSED.

## Scope

- **In:**
  - `ccp/cli.py` `checkout_warning`: its git calls run with `GIT_DIR`, `GIT_WORK_TREE`,
    `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY` and `GIT_ALTERNATE_OBJECT_DIRECTORIES`
    removed from their environment, so `-C <PLANE>` decides the repository.
  - `ccp/init.py`: `binding_shape_warnings` reads the binding with `upgrade.binding_keys` (nested by
    indentation). A top-level key's children are only its first-level keys. `IGNORED_NESTED`
    (`<top>.<child>`) matches only a first-level child. `_binding_keys` is removed.
  - `plugin/hooks/runner-idle.sh`: when nothing is ready, the scope has a task that waits (a
    `waiting_on`, or held by an open question or gate), the product has an `architect` block, and no
    rotation is due, the hook runs `ccp architect due` (with `QUEUE_ROOT`). When it exits 0 and its
    `failed_in_a_row` is below 2, the hook blocks (exit 2, counted against `idle_block_limit` as any
    block) with: "<reason>. Run `ccp architect run --detach` (SPEC §19.6) while <the waiting task>
    waits, then report." Its header comment says so.
  - `ccp/queue.py` `emit` takes an optional `at` (an ISO string) used as the event's time. `claim` in
    `ccp/lifecycle.py` passes `iso(t)`, the same instant as `claimed_at` and `lease_since`, to its
    `lease`/`set` and `phase`/`transition` events.
  - Tests for each: `tests/test_plugin.py` (the self-check), `tests/test_init.py` (the binding),
    `tests/test_runner_idle_rotation.py` (the hook), `tests/test_release.py` (the claim time).
- **Out:**
  - Other `git -C <PLANE>` callers (`ccp/upgrade.py` `_git`).
  - The `Task: <id>` line in PR bodies, the other half of the same proposal.
  - The §14.4 and §15.3 text (Context).
  - The queue-file follow-ups of task 0135, which are task 0160.

## dod_checks

- id: `chk-01`
  story: As an implementer, the plane's self-check does not report my worktree's state as the plane's.
  setup: a scratch plane checkout on `main`, clean and level with its `origin/main`, and a second scratch repository on branch `task/x` with an uncommitted change to a tracked file.
  steps:
    1. With `PLANE` patched to the scratch plane, `CCP_DEV` unset and `GIT_DIR` and `GIT_WORK_TREE` set to the second repository's, call `cli.checkout_warning()`.
  expect: it returns None.
  dry run: n/a.
- id: `bind-01`
  story: As a lead re-adopting with a kept binding, its shape warnings are read by depth.
  setup: the binding of the Context probe: `runner:` with `agent_type` and `slots: {a: {name: r1}}`, and `seats:` holding `lead: {runner: x}`, plus every required top-level key.
  steps:
    1. Call `init.binding_shape_warnings(<path>, <text>)`.
  expect: one warning names `runner.name` as lacking; no warning names `seats.runner`.
  dry run (`85d388b`, the probe): no `runner.name` warning, and a `seats.runner` warning.
- id: `hook-01`
  story: As a runner holding only a waiting task, I am told to start a due architect pass.
  setup: the fixture of `tests/test_runner_idle_rotation.py`'s held-task tests (`test_a_held_task_on_a_gate_lets_the_runner_idle_until_the_gate_closes`): one runner holding a task that waits on an open gate; plane.json with an `architect` block and the queue's architect state making a pass due.
  steps:
    1. Run the hook with the runner's TeammateIdle input.
  expect: exit 2; stderr names `ccp architect run --detach` and the waiting task.
  dry run: n/a.
- id: `hook-02`
  story: As a runner holding only a waiting task, I am let idle when no pass is due.
  setup: the fixture of hook-01 with no pass due; then, separately, with a pass due whose last two attempts failed.
  steps:
    1. Run the hook with the runner's TeammateIdle input in each case.
  expect: exit 0 in both cases.
  dry run: n/a.
- id: `time-01`
  story: As the drill-down, a claim's start is one instant.
  setup: a scratch queue (`ToolkitFixture`) with task 0002 pending; `lifecycle.now` patched to return 12:00:00.9Z and `queue.iso` patched to return 12:00:01Z when called with no argument.
  steps:
    1. Run `ccp tasks claim 0002` in process.
  expect: the task state's `claimed_at` equals the `at` of the `lease`/`set` event written by the claim.
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

## Verification notes
