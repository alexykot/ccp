---
task_id: 0053-run-order-follows-dependencies
title: The run order follows depends_on, not the file number
status: done
kind: feature
depends_on: []
spec_refs: ["S5", "S10"]
review_point: R4
paths: ["ccp/tasklog.py", "ccp/selection.py", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "templates/docs-delivery/WRITING-tasks.md", "tests/test_tasklog*.py", "tests/test_selection*.py"]
created: 2026-11-10
updated: 2026-11-11
---

# Task: 0053-run-order-follows-dependencies

## Intent

A task's `depends_on` may name a later-numbered task: `ccp tasks next` and the board order tasks by the dependency graph, ties broken by number, and `ccp tasks check` refuses only cycles and missing ids, so re-planning mid-flight no longer means dropping and renumbering every pending task downstream (§5, §10.3).

## Context (not checked)

- Raised by a managed product: a newly accepted decision needed a task before pending ones, and the only way was to drop and recreate every downstream task under new numbers, leaving stale references in other briefs.
- Today `ccp tasks check` refuses a `depends_on` that runs later (filesystem order is execution order), and §10.3 returns the lowest-numbered ready task.
- §31: this task changes § text, so its merge waits on the operator's approval of the PROPOSED text.

## Scope

- **In:** §10.3's order and §5's `depends_on` rule change as PROPOSED below; `ccp tasks check` drops the 'runs later' refusal and adds a cycle check naming the cycle; selection ranks ready tasks so a task never comes before a dependency, by number otherwise; WRITING-tasks.md drops the 'sorts after it' advice. CURRENT §10.3: "returns the lowest-numbered `pending` task whose `depends_on` are all `done`". PROPOSED: "returns, of the `pending` tasks whose `depends_on` are all `done`, the lowest-numbered; a dependency may have a higher number than its dependant". §5: a `depends_on` naming a later task is allowed; a cycle or a missing id is refused.
- **Out:** the lead's preference list and refactors (§10.3 steps 1–2), unchanged.

## dod_checks

- id: `check-01`
  story: As a lead re-planning, a new task can come first without renumbering.
  setup: a scratch task log with pending 0003 depending on a new pending 0005, 0005 ready.
  steps:
    1. Run `ccp tasks check`, then `ccp tasks next`.
  expect: check passes; next returns 0005.
  dry run: on the merge base check refuses 0003's `depends_on` as running later.
- id: `check-02`
  story: As a lead, a cycle is refused.
  setup: 0003 depends on 0005 and 0005 on 0003.
  steps:
    1. Run `ccp tasks check`.
  expect: it fails, naming the cycle.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 (implementer): `ccp tasks check` drops the 'runs later' refusal; `tasklog.dependency_cycles`
  finds the cycles `depends_on` forms (a self-dependency included), and check fails once per cycle at
  its lowest-numbered task, naming it (`0003-c → 0005-e → 0003-c`). `ranked` already ranked only ready
  tasks (every dependency done), so no task can come before a dependency; it now sorts the ready tasks
  by number itself instead of trusting the caller's list order. SPEC: §10.3 takes the PROPOSED text;
  §5.2's `depends_on` cell takes the task's §5 sentence, and §5.1 drops "filesystem order is execution
  order". Beyond `paths`, for the same rule: §21.1's refusal bullet ("does not sort earlier" → a
  cycle) and its prose-prerequisite advice ("superseded" → `depends_on`); the 'sorts after it' advice
  lives in the plugin's `writing-tasks` skill and in `warnings()`'s message (the WRITING-tasks.md
  templates hold none), both changed; `templates/docs-delivery/README.md`'s "NNNN in intended run
  order"; and the board graph's depth (`ccp/plan.py`), which walked file order and now walks the graph.
- 2026-11-11 (implementer, fix round 1, from the review): `contracts/task_file.schema.json`'s
  `depends_on` description no longer says "sort earlier"; `ccp tasks list` help and its CLI doc say
  "number order", not "execution order"; the prose-prerequisite warning says "which has a higher
  number", not "which runs later"; two lines this task wrote are rewrapped (§10.3's sentence, the
  skill's refusal list), with no change to their words.

## Verification notes

- 2026-11-11 — verifier, PR #65 head `95633f3` (squash `9290ea6`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0053-run-order-follows-dependencies.json.
