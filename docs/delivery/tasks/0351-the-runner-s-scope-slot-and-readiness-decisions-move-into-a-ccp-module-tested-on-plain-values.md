---
task_id: 0351-the-runner-s-scope-slot-and-readiness-decisions-move-into-a-ccp-module-tested-on-plain-values
title: The runner seat's scope, slot and readiness decisions move out of scripts/observability/team.py into ccp/runnerscope.py as functions on plain values, which team.py imports, and their branches are tested there on plain values
status: done
kind: refactor
depends_on: []
rule_refs: ["E7", "E15"]
review_refs: ["ar-20261125T184522Z-c248#F01"]
review_point: R39
paths: ["ccp/runnerscope.py", "ccp/CLAUDE.md", "scripts/observability/team.py", "scripts/observability/CLAUDE.md", "tests/test_runner_scope.py", "tests/test_team_dry_run.py", "tests/test_review_points.py", "tests/test_stale_context_audience.py"]
clashes_with: ["0191-the-grace-release-ends", "0355-headless-launches-build-their-argv-in-one-place-prompt-audits-are-written-through-one-function-and-a-rule-change-with-no-rule-is-reported-once"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0351-the-runner-s-scope-slot-and-readiness-decisions-move-into-a-ccp-module-tested-on-plain-values

## Intent

The runner seat's decisions (which tasks a spawn or respawn takes, which slots it makes, which tasks no slot holds,
and whether the plan is ready) are ccp functions on plain values, each branch unit-tested without a fixture repo or a
`team.sh` subprocess. `scripts/observability/team.py` keeps the reading, the writing and the process work and calls
them, as house rule E7 now says. Nothing a lead or runner sees changes.

## Context (not checked)

Finding F01 of architect pass `ar-20261125T184522Z-c248` (`docs/delivery/reviews/ar-20261125T184522Z-c248.md`), and
the operator's answer to that triage's question 1, given on 2026-11-25 through the lead:

> ccp module (Recommended)

That is option (b): "The decisions move into a `ccp` module as functions on plain values (E15), which `team.py`
imports; no new command." Triage `ar-20261125T202431Z-1a86` applied E7's ruled text to `docs/ENGINEERING.md`.

0191 (on hold; it removes the moved keys' fallback reads, and its `paths` hold all of `tests/`) rules on no decision this task moves; whichever lands second rebases.

Measured at `becb6417`:

- `wc -l scripts/observability/team.py` at `becb6417`: 1052 lines; `grep -c 'from ccp' scripts/observability/team.py`
  at `becb6417`: 21 import lines.
- The decisions, by symbol: `"def review_point_scope"` (§22, §22.5: the scope and warnings at a spawn; it also loads
  the config and the task log, prints notes and calls `die`), `"def respawn_scope"`, `"def tagged_open"`,
  `"def scope_warnings"` (plain already), `"def refactor_scope"` (§20.4: the refactors put on top; it also reads the
  task log), `"def slots_of"` (plain), `"def slot_tasks"` (reads each task's queue file), `cmd_slots`'s `spawn` branch
  (the slots a spawn makes, the `--count` cap refusal and the orphaned-task refusal, inline) and `"def readiness"`
  (§16.5: the dry run's checks; it also loads the task log, runs `tasklog.check` and `followups.closed_points` and
  probes the runner worktree with git).
- `git grep -l 'team.sh\|import team\|observability/team' -- tests | wc -l` at `becb6417`: 23 files. One plain-value
  test exists, `tests.test_stale_context_audience.RespawnScope.test_order_and_filters`, which puts
  `scripts/observability` on `sys.path` and imports `team`.

**Ruled.**

- `ccp/runnerscope.py` (new) holds, on plain values (lists, dicts and strings the caller has read; no file, git,
  config or process access, no printing):
  - `tagged_open`, `respawn_scope` and `scope_warnings`, moved as they are (the `in_scope` parameter goes: the module
    calls `tasklog.in_scope` itself);
  - `point_scope`: `review_point_scope`'s decision, given the loaded tasks, the register's entries (or None), the
    `--review-point` and `--scope` values, work.json's `review_point`, `scope` and `review_point_refactors`, and the
    two results the caller computes with `reviewpoints.problem(cfg, <point>, entries)` (`"def problem"`,
    `ccp/reviewpoints.py`, which needs the config): one for the `--review-point` value and one for the point the
    scope is for, each a message or None. It takes no config; it returns the scope and the warnings, and refuses
    with the `--review-point` message as now;
  - `refactor_scope`: `refactor_scope`'s choice, given whether the point is new, the waiting refactors, the pending
    task ids, work.json's refactor list and the scope; it returns the scope, the refactors added and the point's list;
  - `slots_of` (moved), `slot_tasks` (given work.json's `in_flight`, each task's state and the slot), `new_slots`
    (the slots a spawn makes, given the recorded slots, the runner's name, `--slot`, `--count` and the cap) and
    `orphans` (the in-flight tasks held by no slot, given the states, the recorded slots and the new ones);
  - `readiness_checks`: `readiness`'s `{check, ok, detail}` list, given the scope, the task ids, the `tasks check`
    errors, the closed-point failures (or None when the task log does not read) and the runner worktree's state
    (absent, a working tree, or a non-empty directory that is not one; None for several slots).
- Each refusal these decisions make (an unknown review point, no open tagged task, `--slot` naming no slot, `--count`
  above the cap, no slot left to make, an orphaned task) is raised as `QueueError` with exit 2 and the message
  `team.py` prints today, which `team.py` turns into its `die`. The messages and exit codes do not change.
- `scripts/observability/team.py` keeps every read and write (work.json, task states, the config, the task log, the
  register, git, `write-prompt-audit.sh`, events) and calls these functions; its own `respawn_scope`, `tagged_open`,
  `scope_warnings` and `slots_of` definitions go.
- Tests: `tests/test_runner_scope.py` (new) tests each branch of these functions on plain values.
  `tests.test_stale_context_audience.RespawnScope` moves there and no longer imports `team`. By E15, in the same
  change these end-to-end tests are cut, their branches now plain-value tested:
  `tests.test_team_dry_run.TestSpawnDryRun.test_a_scope_task_missing_from_the_log_is_not_ready`,
  `test_a_scope_entry_by_number_names_its_task` and `test_a_failing_tasks_check_is_not_ready`, and
  `tests.test_review_points.Spawn.test_with_scope_warns_both_ways`. Every other end-to-end test stays as the wiring.
  No other test expectation changes.
- `ccp/CLAUDE.md` names the new module; `scripts/observability/CLAUDE.md` says `team.py` takes its decisions from it.
- No SPEC change: `git grep -n 'team.py' -- docs/spec` at `becb6417` prints no line stating where these decisions
  live.

## Scope

- **In:** `ccp/runnerscope.py` (new); `ccp/CLAUDE.md`; `scripts/observability/team.py`;
  `scripts/observability/CLAUDE.md`; `tests/test_runner_scope.py` (new); `tests/test_team_dry_run.py`;
  `tests/test_review_points.py`; `tests/test_stale_context_audience.py`.
- **Out:** the write-prompt-audit calls and `keep_body` in `team.py` (0355); the gate ledger (`cmd_gate`); any new
  `ccp` command; the SPEC.

## dod_checks

- id: `code-01`
  story: As a maintainer, the runner's decisions are tested on plain values and the spawn paths still work.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_runner_scope tests.test_team_dry_run tests.test_review_points tests.test_stale_context_audience tests.test_parallel_slots`.
  expect: exit 0.
  dry run (`becb6417`): exit 1 (`ModuleNotFoundError: No module named 'tests.test_runner_scope'`).
- id: `code-02`
  story: As a maintainer, team.py no longer defines the decisions, and ccp does.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nwE 'def (tagged_open|respawn_scope|scope_warnings|slots_of)' -- scripts/observability/team.py`.
    2. Run `git grep -nwE 'def (tagged_open|respawn_scope|scope_warnings|point_scope|refactor_scope|slots_of|slot_tasks|new_slots|orphans|readiness_checks)' -- ccp/runnerscope.py`.
    3. Run `git grep -n 'runnerscope' -- scripts/observability/team.py`.
  expect: step 1 prints nothing (git grep's exit 1); step 2 prints ten lines, one per name; step 3 prints at least one line.
  dry run (`becb6417`): step 1 printed 4 lines; step 2 printed nothing (exit 1); step 3 printed nothing (exit 1).

## Implementation notes

- `ccp/runnerscope.py` holds the ruled functions. `team.py` keeps its reads and writes and calls them: `refusing(fn, ...)`
  turns a `QueueError` into `die(message, code)`, so messages and exit codes are as before; `task_states` reads the
  task files once for `slot_tasks` and `orphans`; `slot_tasks(root, w, slot)` stays in `team.py` as the reader around
  `runnerscope.slot_tasks`; `readiness` reads the log, `tasklog.check`, `followups.closed_points` and the worktree
  and passes them to `readiness_checks`.
- Narrowest readings where the task left a shape open: `orphans` raises the refusal itself (it returns nothing);
  `readiness_checks` takes the worktree as `(path, state)` with state `WORKTREE`, `ABSENT` or `OCCUPIED`, or None;
  `refactor_scope` takes `pending=None` for "no refactor log" and the waiting refactors only when the point is new;
  `point_scope` takes the caller's scope, `--scope` as a bool, and the two `reviewpoints.problem` results.
- Cut by E15: the four end-to-end tests the task names; `RespawnScope` moved to `tests/test_runner_scope.py`.

## Verification notes
- 2026-11-25 — verifier, PR #431 head `c73b583` (squash `b68093d`): APPROVE. Passed: code-01, code-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0351-the-runner-s-scope-slot-and-readiness-decisions-move-into-a-ccp-module-tested-on-plain-values.json.

