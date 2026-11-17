---
task_id: 0117-tool-bug-fixes
title: wt create resolves a symbolic sha, the catch-up gate gets the task worktree's environment, mutate leaves no stale bytecode, close reads counts safely, and an unclosed fence is reported
status: pending
kind: feature
depends_on: []
spec_refs: ["S4", "S12", "S16", "S20"]
review_point: R7
paths: ["ccp/wt.py", "ccp/lifecycle.py", "ccp/mutate.py", "ccp/rules.py", "ccp/docrules.py", "scripts/observability/team.py", "tests/test_wt.py", "tests/test_tasks_close*.py", "tests/test_mutate.py", "tests/test_fence.py", "tests/test_rules.py", "tests/test_team*.py"]
adopt: "none: a product can drop its workaround for the catch-up gate environment"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0117-tool-bug-fixes
## Intent

Five small faults stop: `ccp wt create --sha HEAD` means the caller's HEAD, close's catch-up gate
runs with the task worktree's environment, `ccp mutate` cannot leave a stale bytecode file that
misreports later runs, `ccp tasks close` reads a malformed runner count safely, and a rules document
with an unclosed code fence says so instead of silently dropping the rules after it.

## Context (not checked)

- From five accepted proposals (three from a product, two from the plane's own runs).
- `ccp wt create --sha HEAD` stores the literal `HEAD`, which later resolves in the main checkout.
- Close's catch-up gate (§16.5) runs the gate lane with the caller's environment only, so a product whose gate needs a per-worktree variable (a scratch database name, a port) fails the stage with command-not-found. The worktree's env hooks (§12) already produce that environment for the task's own runs.
- `ccp mutate` restores a source file with its original mtime and size, so a same-size mutant's compiled bytecode stays valid and later runs read it.
- `ccp tasks close` still does an unguarded `int()` on a runner's `tasks_done`; claim, `rotation-due` and health read a malformed value as 0. The spawn's integration-ref check reads the local tracking ref without fetching.
- Since task 0102 the rules parser skips fenced code; an unclosed fence hides every rule after it. Reported as a warning, so products stay conforming (§29.3).
- All describe the accepted fixes (§31.1); no rule changes.

## Scope

- **In:**
  - `ccp/wt.py`: a `--sha` that is not a full sha is resolved to one in the caller's checkout at create time; one that does not resolve is refused (exit 2). This is a bug fix, not a new rule: `--sha` already names a commit (§12.1), and a value that names none could never have been honoured.
  - `ccp/lifecycle.py` catch-up gate: runs with the environment the task worktree's env hooks produced (the `CCP_WT_*` values and the hook's exports), as the task's own gate runs do; `tasks_done` read with the same safe reader claim uses.
  - `scripts/observability/team.py`: the spawn fetches the integration branch before checking the integration branch's remote ref.
  - `ccp/mutate.py`: after restoring a Python file, remove its `__pycache__` entries; runs set `PYTHONDONTWRITEBYTECODE=1`.
  - `ccp/rules.py` / `ccp/docrules.py`: an unclosed fence in a rules document is a warning in `ccp docs check` and `ccp init --adopt`, naming the file and the fence's line.
- **Out:**
  - Refusing on an unclosed fence.

## dod_checks

- id: `cmd-01`
  story: As a seat, `--sha HEAD` means my own head.
  setup: a scratch repository whose main checkout is at commit A and a linked worktree at commit B.
  steps:
    1. From the linked worktree, run `ccp wt create --kind mut --task T --sha HEAD`, then read the worktree record.
    2. Run it with `--sha nope`.
  expect: (1) the record holds B's full sha. (2) exit 2 naming `nope`, nothing made.
  dry run: n/a.
- id: `cmd-02`
  story: As a runner, the catch-up gate sees the worktree's environment.
  setup: a scratch product whose gate stage fails unless a variable set by its env hook is present; a verified task behind the tip by a disjoint commit.
  steps:
    1. Run `ccp tasks close` with no such variable in the caller's environment.
  expect: the catch-up gate passes and the task merges.
  dry run: n/a.
- id: `cmd-03`
  story: As a reviewer, a same-size mutant leaves no stale bytecode.
  setup: a scratch Python product with a test that imports a module; a mutant of the same byte size.
  steps:
    1. Run `ccp mutate` with that mutant, then run the test through `ccp suite run`.
  expect: the second run passes against the restored source, and no `__pycache__` entry for the module is newer than the restore.
  dry run: n/a.
- id: `cmd-04`
  story: As a runner, close survives a malformed count.
  setup: a scratch queue whose runner state holds `tasks_done: "x"` and a verified task.
  steps:
    1. Run `ccp tasks close`.
  expect: no traceback; the count reads as 0 as in claim.
  dry run: n/a.
- id: `cmd-05`
  story: As a task-log owner, an unclosed fence is reported.
  setup: a scratch rules document with a rule, an opening fence and no closing one, then two more rules.
  steps:
    1. Run `ccp docs check`.
  expect: exit 0 with a warning naming the file and the fence's line.
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
