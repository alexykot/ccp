---
task_id: 0164-clashes-with-and-schedule
title: A task may record clashes_with, and parallel.schedule clashes lets tasks whose paths meet run together unless they clash
status: pending
kind: feature
depends_on: ["0161-paths-meet-and-parallel-defaults"]
spec_refs: ["S5", "S16", "S10"]
adr_refs: ["0042 D1", "0042 D2"]
review_point: R11
paths: ["ccp/parallel.py", "ccp/config.py", "ccp/tasklog.py", "contracts/task_file.schema.json", "contracts/plane_config.schema.json", "README.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "templates/docs-delivery/TEMPLATE-task.md", "plugin/skills/writing-tasks/SKILL.md", "tests/test_clashes_with.py", "tests/test_parallel_claims.py", "tests/test_next_passes_over.py"]
adopt: "plane.json parallel.schedule"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0164-clashes-with-and-schedule
## Intent

A product running several runners can let two tasks that only touch the same files (the SPEC, a CLI
entry point, a package doc) run together, and keep apart only the tasks its task-log owner says clash.
The writer records a clash in the task's frontmatter as `clashes_with: [<ids>]`; `ccp tasks check`
refuses an id that names no task. With plane.json `parallel.schedule: clashes`, claim rule 3 and the
`ccp tasks next` walk keep apart only tasks that clash; with `paths`, the default, nothing changes.

## Context (not checked)

- ADR-0042 D1 and D2, accepted 2026-11-19; shape `sh-20261119T072530Z-663f` (F05, F07, single sources).
- Depends on 0161, which renames `parallel.clash` to `paths_meet`, routes the path rule (`join_refusal`) and
  the passed-over walk (`next_choice`) through one pairwise co-scheduling predicate in `ccp/parallel.py`
  (`kept_apart`), and makes `parallel.settings` fall back to `config.PARALLEL_DEFAULTS`, with a test holding the plane.json
  schema's `parallel` properties and defaults to that dict. This task adds the `schedule` branch inside
  that one predicate, so the claim rule and the walk change together and nowhere else.
- Callers at `b9e58ce`: `git grep -n "clash(" -- ccp` → 3 lines in `ccp/parallel.py` (definition, claim, walk).
  The board's `next` (`plan.ready_queue`) calls `next_choice`, so it follows without an edit.
- `depends_on` ids are checked in `tasklog.check` (its message: depends_on `<id>`, which does not exist); the shape
  names one id-list validator for both lists. Today an unknown frontmatter key is ignored: a fenced
  product whose pending task carries `clashes_with: ["0099-none"]` passes `ccp tasks check` (its only
  failure the fixture's stale INDEX.yaml; no line names `0099-none`), dry run at `b9e58ce`.
- Today `parallel.schedule` loads with a warning, `unknown key(s) parallel.schedule ignored`, dry run at
  `b9e58ce`.
- What stays under `clashes` (D1), all in §16.3: the slot count; the run-alone rule (a task with no path and
  no `parallel: true` still runs alone: its paths feed `exclusive` and the forecast); `parallel.exclusive`;
  the session ceiling. `parallel.shared` keeps its meaning at close (§16.5); at the claim's path rule under
  `clashes` it has nothing left to lift.
- Decided here: the relation is symmetric, so a clash recorded on either task keeps both apart; a task naming
  itself is refused; `parallel: true` does not lift a recorded clash (the writer's word wins); a clash with a
  task that is done or dropped holds nothing back. Under `paths`, `clashes_with` is not read at all.
- §10.3 needs no edit: its only words on this are "With several runners `next` also applies §16.3 (head of
  line, exit 7).", which stays true. The `next` walk's rule lives in §16.3, changed below.
- The forecast (§16.7) and close's catch-up (§16.5) are tasks 0170 and 0167.
- The SPEC passages below change claim rule 3, the walk and §16.1's intent line: `sign_off: brief`.

## Scope

- **In:**
  - `contracts/task_file.schema.json`: `clashes_with`, an array of task ids, described as symmetric
    (either order, never together; read only under `parallel.schedule: clashes`, §16.3).
  - `ccp/tasklog.py`: one validator for a frontmatter list of task ids, used for `depends_on` and
    `clashes_with`: an id that names no task is refused (`clashes_with \`<id>\`, which does not exist`), and so
    is `clashes_with` naming the task itself. The `depends_on` message is unchanged.
  - `ccp/config.py`: `PARALLEL_DEFAULTS` gains `"schedule": "paths"`; validation refuses any value but `paths`
    or `clashes`, naming the key. `contracts/plane_config.schema.json` `parallel.schedule`: enum
    `["paths", "clashes"]`, default `paths`, so 0161's `tests/test_parallel_defaults.py` still holds.
  - `ccp/parallel.py`: 0161's pairwise co-scheduling predicate, `kept_apart`, branches on `parallel.schedule`. Under
    `paths`, it is 0161's behaviour exactly. Under `clashes`, two tasks are kept apart when either names the
    other in `clashes_with`; their paths are not compared. Rule 3's refusal then reads `<C> clashes with
    in-flight <T> (clashes_with, rule 3)`, and a task passed over behind another passed-over task reads
    `<C> clashes with passed-over <T>`. The module docstring says which rule 3 each schedule applies.
  - `README.md`: the adoption checklist gains a `parallel.schedule` row (`clashes`: tasks whose paths meet
    run together unless one names the other in `clashes_with`; when `max_in_flight` is above 1 and most
    tasks meet on hub files).
  - `templates/docs-delivery/TEMPLATE-task.md`: after the commented `paths:` example, two comment lines: what
    `clashes_with` is (tasks that change the same logic in different ways; read under `parallel.schedule:
    clashes`, plane SPEC §16.3) and an example `# clashes_with: ["0007-other-task"]`.
  - `plugin/skills/writing-tasks/SKILL.md`: the frontmatter table gains a `clashes_with` row (what a clash is,
    symmetric, read only under `parallel.schedule: clashes`, an id naming no task refused).
  - `docs/spec/01-model.md` §5.2: CURRENT: none (a new table row, inserted after the `parallel` row, which stays as it is: "| `parallel` | no | whether it may run beside other tasks (§16) |"). PROPOSED:
    > | `clashes_with` | no | ids of tasks it clashes with: both change the same logic in different ways, so they run in either order, never together; the relation is symmetric, a clash recorded on either task holds for both. Read only under `parallel.schedule: clashes` (§16.3); an id that names no task, or the task itself, is refused |
  - `docs/spec/02-delivery.md` §16.1: CURRENT (at `b9e58ce`): "Declared paths only decide what to start together." PROPOSED:
    > Under `parallel.schedule: paths`, the default, declared paths decide what to start together; under `clashes`, the writer's `clashes_with` does, and paths still decide what `parallel.exclusive` keeps alone (§16.3).
  - `docs/spec/02-delivery.md` §16.2: CURRENT (at `b9e58ce`): "A path may not be both `shared` and `exclusive`." PROPOSED:
    > A path may not be both `shared` and `exclusive`. `schedule` picks claim rule 3 (§16.3): `paths`, the default, keeps apart tasks whose paths meet; `clashes` keeps apart only tasks that clash (`clashes_with`, §5), whatever their paths, and `shared` then matters only at close (§16.5 rule 4). Any other value is refused.
  - `docs/spec/02-delivery.md` §16.3 rule 3: CURRENT (at `b9e58ce`): "3. No path of C meets a path of a task in A (equal, one a directory holding the other, or a glob or bare name of one matching the other), unless both are covered by a `parallel.shared` entry." PROPOSED:
    > 3. Under `parallel.schedule: paths`, no path of C meets a path of a task in A (equal, one a directory holding the other, or a glob or bare name of one matching the other), unless both are covered by a `parallel.shared` entry. Under `clashes`, C clashes with no task in A: neither names the other in `clashes_with` (§5), whether or not their paths meet.
  - `docs/spec/02-delivery.md` §16.3, the `ccp tasks next` walk: CURRENT (at `b9e58ce`): "returns the first that could be claimed beside A and none of whose paths meets a path of a task it passed over; it passes over, naming each, a task that rule 3 alone keeps from joining A and a task whose path meets one it passed over;" PROPOSED:
    > returns the first that could be claimed beside A and that rule 3 would not keep from joining any task it passed over; it passes over, naming each, a task that rule 3 alone keeps from joining A and a task that rule 3 would keep from joining one it passed over;
  - `docs/spec/02-delivery.md` §16.3, the same paragraph: CURRENT (at `b9e58ce`): "(head of line: no task waits forever behind smaller ones, and a task passed over waits only for the in-flight tasks its paths meet)." PROPOSED:
    > (head of line: no task waits forever behind smaller ones, and a task passed over waits only for the in-flight tasks rule 3 keeps it from: those its paths meet, or under `clashes` those it clashes with).
  - `tests/test_clashes_with.py` (new): the checks below. `tests/test_parallel_claims.py` and
    `tests/test_next_passes_over.py` change only where a message they assert changes wording.
- **Out:**
  - Close's catch-up and its sign-off carry under `clashes` (task 0167), the forecast (task 0170), conflict
    counts (task 0169).
  - Changing the default schedule (a later decision, ADR-0042 D1), and setting `parallel.schedule` in this
    repo's own plane.json.
  - `docs/spec/03-quality.md` §21.1's list of refusals (its `depends_on` bullet stays; §5.2 states the refusal).

## dod_checks

- id: `fm-01`
  story: As a task-log owner, a clash naming no task is caught when I write it.
  setup: a fenced temp product with tasks 0002, 0003 and 0004 pending; 0003 carries `clashes_with: ["0099-none"]`, 0004 carries `clashes_with: ["0004-fourth"]` (its own id), and 0002 carries `clashes_with: ["0003-third"]`; the index rebuilt.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 1 with exactly two failures: one naming 0003's file and `0099-none`, one naming 0004's file and `0004-fourth`; no failure names 0002's file.
  dry run (`b9e58ce`): the same product (0003 with `clashes_with: ["0099-none"]`) exits 1 only for the fixture's stale INDEX.yaml; no line names `0099-none`.
- id: `cfg-01`
  story: As an operator, the schedule knob takes only its two values, and the default is today's rule.
  setup: fenced temp products whose plane.json `parallel` is `{"max_in_flight": 2}`, then adds `"schedule": "clashes"`, then `"schedule": "files"`.
  steps:
    1. Load each with `config.load` and read `parallel.settings(cfg)["schedule"]`.
  expect: `paths` for the first, `clashes` for the second with no unknown-key warning; the third is refused with an error naming `parallel.schedule`.
  dry run (`b9e58ce`): the second loads with `unknown key(s) parallel.schedule ignored` on stderr.
- id: `claim-01`
  story: As a runner under `clashes`, a task whose paths meet the one in flight still starts, and a recorded clash keeps one apart.
  setup: a fenced product (the `test_parallel_claims` fixture shape) with `parallel` `{"max_in_flight": 3, "schedule": "clashes"}`; 0002 in flight with Scope path `src/app/pool.py`; 0004 pending with Scope path `src/app/pool.py`; 0003 pending with Scope path `src/app/views.py` and `clashes_with: ["0002-second"]`; 0006 pending with no path and no `parallel: true`.
  steps:
    1. Run `ccp tasks claim 0004`.
    2. Run `ccp tasks claim 0003`.
    3. Run `ccp tasks claim 0006`.
  expect: step 1 exits 0; step 2 exits 7 and stderr names `0002-second`, `clashes_with` and `rule 3`; step 3 exits 7 naming `rule 2`.
  dry run (`b9e58ce`): with `schedule` absent (it is ignored today), claiming 0004 beside 0002 exits 7: "0004-fourth's `src/app/pool.py` meets in-flight 0002-second's `src/app/pool.py` (rule 3)".
- id: `next-01`
  story: As a runner under `clashes`, `next` passes over a task held back by a clash, and a later task never overtakes an earlier one it clashes with.
  setup: the product of `claim-01` before its steps, with 0002 in flight; pending 0003 (`clashes_with: ["0002-second"]`), 0004 (`clashes_with: ["0003-third"]`, Scope path `src/app/pool.py`), 0008 (Scope path `src/app/pool.py`); no other task pending, so these three are the ready tasks, in that rank order.
  steps:
    1. Run `ccp tasks next --json`.
  expect: exit 0; `task_id` is the 0008 task's; `passed_over` lists 0003 then 0004, 0003's `why` naming `0002-second`, 0004's naming passed-over `0003-third`.
  dry run: n/a — `clashes_with` is not read at `b9e58ce`.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed, and the default schedule changes nothing.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0164-clashes-with-and-schedule --base origin/main`.
    2. Run the modules `tests.test_parallel_claims` and `tests.test_next_passes_over` through `ccp suite run --lane part`.
  expect: step 1 exits 0 with all six passages found; step 2 passes.
  dry run (`b9e58ce`): step 2's modules, run with `python3 -m unittest`, pass at the base (29 tests, OK).
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
