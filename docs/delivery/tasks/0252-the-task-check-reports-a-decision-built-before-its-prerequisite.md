---
task_id: 0252-the-task-check-reports-a-decision-built-before-its-prerequisite
title: ccp tasks check reports a pending task that could build a decision before its prerequisite
status: pending
kind: feature
depends_on: ["0251-adr-check-holds-the-requires-links", "0250-generic-cycles-and-closure-helpers"]
clashes_with: ["0224-checks-only-the-operator-s-machine-can-run", "0231-a-review-point-does-not-close-over-an-undecided-follow-up", "0244-tasks-check-runs-dry-runs"]
spec_refs: ["S21"]
adr_refs: ["0046 D3"]
review_point: R15
paths: ["ccp/tasklog.py", "ccp/adr.py", "docs/spec/03-quality.md", "plugin/skills/writing-tasks/SKILL.md", "plugin/skills/architect/SKILL.md", "docs/adr/0046-decisions-may-depend-on-other-adrs-decisions.md", "tests/test_tasklog_requires.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0252-the-task-check-reports-a-decision-built-before-its-prerequisite

## Intent

With `requires` held (0225, 0251), nothing yet stops a task building a decision before the one it
rests on. After this task `ccp tasks check` reports a pending task citing a decision whose
prerequisite is neither built nor cited by the task or a task in its `depends_on` closure, naming
the `depends_on` to add or the task to write; under `adr.strict` it fails. Ordering stays in
`depends_on`, and `ccp tasks next` does not change. The writing-tasks and architect skills read
`requires` when they order a plan.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0046 D3, accepted by the operator on 2026-11-20. Its Options explain why the check runs
  when the tasks are written rather than as a runtime hold.
- **Shaped** by `sh-20261121T001225Z-7dbe`; its refactors are 0239 (one ADR-reference parser and the
  decision index) and 0250 (the graph helpers).
  - F04: D3 has one home, a function in `tasklog.py` reading 0239's decision index, called from
    `check()` under `adr.strict` and from `warnings()` otherwise. A whole-ADR citation (`"0046"`)
    cites each of its body decisions. The existing in-force checks (`adr.unbuilt_cited`,
    `in_force_at`) read only `NNNN Dn` citations, a narrower question (is the cited decision itself
    unbuilt), and keep that reading.
  - F07: the closure uses 0250's `graph.closure`.
  - F05 is the operator's (the verifier's gate rejecting on whole-tree failures that a reconcile
    excuses): a strict D3 failure that a tip change causes would stop an unrelated task's verify. This
    task does not change the gate; its strict failure fires only on pending tasks citing `requires`
    links, of which there are none today (`grep -rl '^requires:' docs/adr | wc -l` at `8aefa59`: 0).
- **The skills.** `plugin/skills/writing-tasks/SKILL.md` (Wide plans) and the architect skill's shape
  mode order tasks by `depends_on`; neither mentions `requires`.
- **Limit** (ADR-0046 Notes): a decision built by several tasks reads `built` after the first merges;
  the writer adds an explicit `depends_on` for the rest.
- §21.1's "It warns" paragraph is extended by R16's 0244 (a stale-Context warning) and 0231 (a
  sentence at its end); 0224 adds a failure bullet in the list above it. This task's text is a
  paragraph of its own between the failure list and the warnings, since it is a failure or a warning
  by `adr.strict`; the passage is only that paragraph, so it is found in any merge order. The clashes
  stay: the four tasks edit neighbouring lines of §21.1.

## Scope

- **In:** `ccp/tasklog.py`, `ccp/adr.py`, `docs/spec/03-quality.md`,
  `plugin/skills/writing-tasks/SKILL.md`, `plugin/skills/architect/SKILL.md`,
  `docs/adr/0046-decisions-may-depend-on-other-adrs-decisions.md`, `tests/test_tasklog_requires.py` (new).
- **`tasklog.requires_report(tasks, index, strict) -> list[str]`** on plain values: for each pending
  task, each decision it cites (a whole ADR citing each of its decisions), and each prerequisite
  resolved through `DecisionIndex.resolve`: when it is not recorded `built` or `live`, and neither the
  task nor its `depends_on` closure cites it, one line naming the task, the decision, the prerequisite
  and both remedies (a `depends_on` on a task that cites it; or, when no task cites it, a task for it
  or `ccp adr decide`).
- `check()` adds the lines under `adr.strict`; `warnings()` otherwise.
- The writing-tasks skill (Wide plans) and the architect skill's shape mode say to read `requires`
  when ordering a plan's tasks.
- ADR-0046 D3 recorded `built`.
- **Tests** in `tests/test_tasklog_requires.py` (new), on plain values: the report for an uncited
  prerequisite; cleared by a `depends_on` task citing it; cleared once it is `built`; a whole-ADR
  citation; a retired prerequisite resolved to its replacement; failure under strict, warning without.

### SPEC changes (signed in the brief, §31)

**a. §21.1, a paragraph after the failure list (before the warnings paragraph).**

CURRENT (`docs/spec/03-quality.md` at `8aefa59`):
> - with a review-point register, an unknown point (§22.3); with `shape_adrs`, an unshaped ADR
>   citation (§19.6).

PROPOSED: (a new paragraph after it)
> It reports a pending task citing a decision whose prerequisite (`requires`, resolved through
> `retired by`, §6.5) is neither recorded `built` or `live` nor cited by the task or a task in its
> `depends_on` closure, naming the remedies; a failure under `adr.strict`, a warning otherwise. `ccp
> tasks next` does not read `requires`.

- **Out:** a runtime hold in `ccp tasks next` or the plan, the board's dependency graph, and the
  verifier gate's handling of tip failures (the operator's decision).

## dod_checks

- id: `tr-01`
  story: As a task-log owner, a task that could run before its prerequisite is reported where I write it.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_tasklog_requires 2>&1 | tail -10`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `tr-02`
  story: As a plane developer, the report bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `requires_report` no longer follows the `depends_on` closure.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_tasklog_requires`.
  expect: at least one failure (the report cleared by a `depends_on` task).
  dry run: n/a — the module is new.

- id: `tr-03`
  story: As a task-log owner, the task log with no `requires` checks as before.
  setup: a checkout of the PR head; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . tasks check 2>&1 | grep '^tasks:'`.
  expect: one line starting `tasks: clean`.
  dry run (`8aefa59`): `tasks: clean (209 tasks)` on `origin/main`.

- id: `tr-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0252 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`8aefa59`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
