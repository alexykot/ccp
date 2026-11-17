---
task_id: 0138-lead-tooling-fresh-product
title: A freshly adopted product's lead tools find the queue, say when a register is empty or a reading cannot be taken, and the idle hook lets a runner wait on its held task
status: pending
kind: feature
depends_on: []
spec_refs: ["S9", "S18", "S22", "S25"]
review_point: R9
paths: ["scripts/team.sh", "scripts/observability/spec_maintainer.py", "scripts/observability/team.py", "scripts/spec-maintainer-ask.sh", "ccp/cli.py", "ccp/usage.py", "plugin/hooks/runner-idle.sh", "tests/test_team_hosting.py", "tests/test_review_points.py", "tests/test_session_park.py", "tests/test_runner_idle_rotation.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0138-lead-tooling-fresh-product
## Intent

The lead of a product adopted a minute ago runs its first commands without guesswork: the seat
scripts find the queue the way `ccp` does, an empty review-point register and a spawn without a review
point say what they mean, a session wake that cannot sample names why, and a runner whose held task
waits on someone is let idle instead of being sent to a task it may not claim.

## Context (not checked)

Each finding was probed in a sandbox (`ccp sandbox create`, its `PROJECT_YAML` line exported, `QUEUE_ROOT` unset) at `921507e`:

- **Queue root.** `ccp` sets `QUEUE_ROOT` from the binding when it is unset (§9.2, `"def binding_queue_root"`
  in `ccp/cli.py`). `scripts/team.sh` does not: `team.py` takes the root from `spec_maintainer.root_dir`
  (`"def root_dir"` in `scripts/observability/spec_maintainer.py`), which dies without the variable.
  Probe `scripts/team.sh runner status`: `observability: set QUEUE_ROOT to the live queue dir outside
  product git`, while `ccp where` printed the queue. `spec-maintainer-ask.sh` uses the same function.
  §9.2's sentence names `ccp` only; making the two scripts agree with it changes no rule.
- **Empty register.** Probe `ccp review-points list` on a fresh product: exit 0 and no output at all;
  `--json` already gives `"review_points": []` (with `exists: false`). The text form needs the line.
- **Spawn without a review point.** Review points are optional (§22.1: "Review points are optional: a
  product uses them by keeping a register"). The spawn's JSON (`"spawn_recorded"` in `team.py`) carries
  no `review_point` key, so a lead cannot tell from it whether the scope has one.
- **Session wake.** `usage.sample_allowance` returns None when the binding has no
  `telemetry.allowance_cmd`, and `usage.session_wake` then gives the reason "no allowance sample yet
  (run with --sample)". Probe `ccp allowance session-wake --sample`: exactly that reason, though it was
  run with `--sample`. The README's adoption checklist already documents `telemetry.allowance_cmd`;
  shipping a command that prints the account's windows is out of this task (it reads the operator's
  account, not the product).
- **Idle hook.** §18.2: the hook keeps the runner working "when the task the runner holds is ready (not waiting on
  anyone), or, when it holds none, when a task in scope is ready". With one runner the hook does not
  look at what the runner holds: it takes the first ready task in scope (the `elif code == 2:` branch,
  "Scope not finished: … Carry on with it"). So a runner holding a task that waits on a gate is told to
  carry on with another, which its claim then refuses (§16.3: a claim by a runner that already holds a
  task not closed or released refuses). The code is out of line with §18.2; fixing it changes
  no rule. The runner holds the tasks in `work.json` `in_flight` (§16.3, "the active set").
- Removing plane-checkout paths from `ccp init --permissions` needs a rule change (§4.3, §4.4, §4.5)
  and is in task 0145.

## Scope

- **In:**
  - `scripts/observability/spec_maintainer.py` `root_dir`: with `QUEUE_ROOT` unset, it asks the plane's
    own `bin/ccp --root <dir> where` (the dir being `CLAUDE_PROJECT_DIR`, else the working directory)
    and takes its `queue_root`; with none, it dies as now, the message adding "no binding names this
    product: run `ccp init`, or set QUEUE_ROOT". `QUEUE_ROOT`, when set, wins as now. The usage headers of
    `scripts/team.sh` and `scripts/spec-maintainer-ask.sh` say so.
  - `ccp/cli.py` `cmd_review_points`: `list` with no review point in the register or on any task
    prints `no review points` (and the register's path, said to be absent when it is); exit 0.
  - `scripts/observability/team.py` spawn (real and `--dry-run`): the JSON carries `review_point` (the
    point, or null); with none, the spawn action's `detail` adds "This scope has no review point; none is
    required (SPEC §22.1)."
  - `ccp/usage.py` `session_wake`: with no `telemetry.allowance_cmd`, the reason is "no
    telemetry.allowance_cmd in the binding: no allowance sample can be taken (SPEC §25.1)", with or
    without `--sample`; `arm` is false.
  - `plugin/hooks/runner-idle.sh`, the single-runner path (no `runners` slots, `parallel` off): when
    `work.json` `in_flight` holds a task not done or dropped, only those tasks can be ready; when none of
    them is (each waits, or is held by a question or a gate), the hook exits 0 and resets its counter,
    as for an empty ready set.
- **Out:**
  - Shipping an allowance command, or `ccp init` writing one.
  - The several-runner paths of the hook (they already read the slot's held task).

## dod_checks

- id: `team-01`
  story: As a lead, my first team.sh call finds the queue.
  setup: a sandbox from `ccp sandbox create S`; only its `PROJECT_YAML` line exported, `QUEUE_ROOT` unset.
  steps:
    1. In `S/product`, run the plane's `scripts/team.sh runner status`.
    2. Run it again in a scratch git repository no binding names.
  expect: step 1 exits 0 and prints JSON (no "set QUEUE_ROOT" message); step 2 exits non-zero with the message naming `ccp init` and QUEUE_ROOT.
  dry run (`921507e`): step 1 printed `observability: set QUEUE_ROOT to the live queue dir outside product git`, non-zero.
- id: `rp-01`
  story: As a lead of a fresh product, an empty register says so.
  setup: the sandbox of team-01 (no register, no task carrying a review point).
  steps:
    1. Run `ccp review-points list`.
  expect: exit 0; the output holds `no review points`.
  dry run (`921507e`): exit 0, empty output.
- id: `rp-02`
  story: As a lead, a spawn tells me whether its scope has a review point.
  setup: a fenced team fixture with one pending task, no register.
  steps:
    1. Run `team.sh runner spawn --dry-run --scope <that task>`.
  expect: the JSON has `review_point: null`, and the spawn action's `detail` says the scope has no review point and none is required.
  dry run: n/a — added by this task.
- id: `wake-01`
  story: As a lead, a wake that cannot sample names the missing command.
  setup: the sandbox of team-01 (its binding has no `telemetry.allowance_cmd`), its `env` lines exported.
  steps:
    1. Run `ccp allowance session-wake --sample`.
  expect: the reason names `telemetry.allowance_cmd`; it does not say "run with --sample"; `arm` is false.
  dry run (`921507e`): reason `no allowance sample yet (run with --sample)`.
- id: `idle-01`
  story: As a runner holding a task that waits on a gate, I am let idle.
  setup: a fenced hook fixture, one runner, `work.json` `status: running`, scope two pending tasks A and B with no dependencies, `in_flight: [A]`, A's queue file `waiting_on: design_seat`, and an open gate on A to the design seat.
  steps:
    1. Feed the hook the runner's TeammateIdle input.
    2. Clear A's wait and close the gate; feed it again.
  expect: step 1 exits 0 with no stderr naming B; step 2 exits 2 naming A.
  dry run (`921507e`): by reading the hook's single-runner branch, step 1 exits 2 naming B.
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
