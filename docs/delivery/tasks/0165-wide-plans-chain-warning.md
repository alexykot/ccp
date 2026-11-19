---
task_id: 0165-wide-plans-chain-warning
title: ccp tasks check reports each review point's longest depends_on chain and width, warns on a deep plan, and the writing-tasks skill says to write wide plans
status: pending
kind: feature
depends_on: []
spec_refs: ["S21", "S19", "S5"]
adr_refs: ["0042 D6"]
review_point: R11
paths: ["ccp/plan.py", "ccp/cli.py", "docs/spec/03-quality.md", "plugin/skills/writing-tasks/SKILL.md", "plugin/skills/architect/SKILL.md", "plugin/skills/review-triage/SKILL.md", "tests/test_tasks_check_chain.py", "tests/test_estimator.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0165-wide-plans-chain-warning
## Intent

A task-log owner who writes a review point's tasks as a long chain, each depending on the one before,
is told so by `ccp tasks check` before any runner starts: it shows, for each review point with pending
tasks, the longest `depends_on` chain and how many tasks sit at each depth, and warns when the chain is
long and the plan narrow. The writing-tasks skill says how to write a wide plan instead, and the
architect's shape pass and review triage point to that one place rather than restating it.

## Context (not checked)

- ADR-0042 D6, accepted 2026-11-19. Shape `sh-20261119T072530Z-663f` names `plan._depths` as the single
  source for the longest chain, and the writing-tasks skill as the single source for the guidance.
- `"def _depths"` in `ccp/plan.py` already computes each task's longest chain of dependencies under it,
  walking the graph (a dependency may have a higher number), cutting a cycle. `plan.graph` calls it on
  open tasks for the board. `ccp/plan.py` imports `tasklog`, so the new reader lives in `plan.py` and
  `cmd_tasks_check` calls it, as it calls `parallel.scope_warnings` today; `tasklog` does not import `plan`.
- `ccp tasks check` today prints `warning:` lines (tasklog, review points, parallel) and `note:` lines
  (the estimator), and neither changes its exit code. `./bin/ccp --root . tasks check` at `b9e58ce`:
  `tasks: clean (160 tasks)`, no chain or width line.
- Guidance today: `git grep -n -i "wide\|chain" -- plugin/skills` at `b9e58ce`: no line about plan shape.
  The architect skill's shape mode asks for a `task_graph` "that could run in parallel where the code
  allows"; review triage's "After a shape" adjusts the ADR's task graph. Neither says to sequence only
  for a dependency or a clash.
- The rule is decided in Scope, below. Its thresholds are module constants, not a knob: the warning never
  fails the check.
- §31.1: the §21.1 sentence below describes this task's own warning; no rule changes.

## Scope

- **In:**
  - `ccp/plan.py`: `chain_report(cfg, tasks)` returns `(notes, warnings)`, reusing `_depths`. Per review
    point (tasks with no `review_point` form one group), over its `pending` tasks and the `depends_on` edges
    between them: `chain` is the number of tasks on the longest path (a task with no pending dependency in
    the group is depth 0, so `chain` is the greatest depth + 1), and `width` is the count of tasks at each
    depth. A note is printed for each group with at least 2 pending tasks. The warning fires when `chain` is
    at least 3 and the group has fewer than 2 × `chain` pending tasks (under 2 tasks per depth on average).
    A note reads `<point>: <n> pending tasks, longest depends_on chain <chain>, width by depth <w0>, <w1>, …`.
    A warning reads `<point>: the longest depends_on chain is <chain> tasks (<id> → <id> → …) and the plan is
    <x.x> tasks wide on average: sequence tasks only for a dependency or a clash (writing-tasks skill, Wide plans)`,
    the chain's ids in run order, first to last. Constants `CHAIN_WARN_MIN = 3`, `CHAIN_WARN_WIDTH = 2`.
  - `ccp/cli.py` `cmd_tasks_check`: prints the warnings as `  warning: …` with the others and the notes as
    `  note: …` with the estimator's; the exit code is unchanged.
  - `docs/spec/03-quality.md` §21.1, its closing paragraph (§31.1): one sentence: for each review point
    with pending tasks it notes the longest `depends_on` chain and the width at each depth, and warns when
    the chain is at least 3 tasks and the point has fewer than 2 tasks per depth on average.
  - `plugin/skills/writing-tasks/SKILL.md`: a section `## Wide plans, not deep chains` with ADR-0042 D6's
    three rules (sequence two tasks only for a dependency or a clash, never because they touch the same
    files; for a feature, one thin first task that fixes the interfaces, then tasks that build on it in
    parallel; smaller tasks where each piece still works on its own, with no hard size cap), and one
    line naming the `ccp tasks check` note and warning.
  - `plugin/skills/architect/SKILL.md` (shape mode's `task_graph` bullet) and
    `plugin/skills/review-triage/SKILL.md` ("After a shape"): one line each pointing to the writing-tasks
    skill's `Wide plans, not deep chains`, restating none of it.
  - `tests/test_tasks_check_chain.py` (new): the checks below, on fenced temp products.
  - `tests/test_estimator.py`: `test_with_auto_off_neither_command_notes_or_starts_an_estimator` asserts
    `assertNotIn("note:", out)`, and its fixture has 0005 depending on 0004, so the chain note now prints.
    Narrow that assertion to the estimates note (`assertNotIn("note: estimates", out)`); do not remove it.
  - ADR-0042 D6: this task marks it built (`ccp adr decide 42 D6 built`).
- **Out:**
  - Any refusal: the report and warning never change the exit code.
  - `clashes_with` (task 0164) and any change to `ccp tasks next` or the board's graph.
  - A plane.json knob for the thresholds.

## dod_checks

- id: `chain-01`
  story: As a task-log owner, I see how deep and wide each review point's pending plan is.
  setup: a fenced temp product with review point R1 holding 6 pending tasks: A, B (depends on A), C (depends on A), D (depends on B), E and F (no dependencies); and one done task in R1 that A depends on; the index rebuilt.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 0; stdout holds exactly one note for R1, reading `R1: 6 pending tasks, longest depends_on chain 3, width by depth 3, 2, 1`, and no chain warning (6 is not fewer than 2 × 3).
  dry run (`b9e58ce`): `./bin/ccp --root . tasks check` prints `tasks: clean (160 tasks)` and no `longest depends_on chain` line: the note does not exist yet.
- id: `chain-02`
  story: As a task-log owner, a review point written as a chain is flagged before a runner starts.
  setup: a fenced temp product with review point R2 holding 4 pending tasks in a chain (each depends on the one before, written with the dependency's number higher than its dependant's for one link) and 2 pending tasks with no dependencies; the index rebuilt.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 0; stdout holds one `warning:` line for R2 naming chain 4 and the four ids in run order joined by ` → `, and `1.5 tasks wide`.
  dry run: n/a — the warning does not exist yet.
- id: `chain-03`
  story: As a task-log owner, a wide plan or a short chain is not flagged.
  setup: a fenced temp product with R3 holding 8 pending tasks at chain 4 (widths 2, 2, 2, 2), R4 holding 2 pending tasks where one depends on the other, and 3 pending tasks with no review point and no dependencies; the index rebuilt.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 0; no chain warning; one note each for R3 (chain 4), R4 (chain 2) and the no-review-point group (chain 1, width 3).
  dry run: n/a.
- id: `doc-01`
  story: As a task-log owner, the wide-plan guidance lives in one skill and the others point to it.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n "Wide plans, not deep chains" -- plugin/skills`.
    2. Run `git grep -n "dependency or a clash" -- plugin/skills`.
  expect: step 1 prints exactly 3 lines: the heading in `plugin/skills/writing-tasks/SKILL.md` and one pointer each in `plugin/skills/architect/SKILL.md` and `plugin/skills/review-triage/SKILL.md`; step 2 prints exactly 1 line, in `plugin/skills/writing-tasks/SKILL.md`.
  dry run (`b9e58ce`): step 1 prints nothing and step 2 prints nothing.
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
