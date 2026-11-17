---
task_id: 0109-upgrade-notes-and-status
title: Tasks name their adoption step; ccp upgrade notes and status show what a release asks of a product; a built proposal names its step
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S29"]
adr_refs: ["0041 D1", "0041 D2", "0041 D4"]
review_point: R7
sign_off: brief
paths: ["ccp/upgrade.py", "ccp/cli.py", "ccp/tasklog.py", "ccp/plane.py", "contracts/task_file.schema.json", "contracts/plane_config.schema.json", "plugin/skills/writing-tasks/SKILL.md", "docs/spec/01-model.md", "docs/spec/05-operations.md", "tests/test_upgrade*.py", "tests/test_plane*.py", "tests/test_tasklog*.py"]
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0109-upgrade-notes-and-status
## Intent

A product can see what each plane release asks of it. Every task names its adoption step,
`ccp upgrade notes` lists what arrived since a commit, `ccp upgrade status` lists what a product
has not adopted, and a proposal closed as built tells its proposer the step.

## Context (not checked)

- ADR-0041 D1, D2 and D4 (proposed with R7; the operator accepts it with this task's brief sign-off).
- From an accepted plane proposal on an upgrade strategy, and two from a product asking for init defaults (task 0111).
- Built features shipped off by default went unused for weeks, found only by a manual analysis (ADR-0041 Context).
- Settings the plane reads for `upgrade status`: the product's `docs/delivery/plane.json`, its binding, and its `.claude/settings.json`.

## Scope

- **In:**
  - `docs/spec/01-model.md` §5, the frontmatter table. CURRENT (at `7094dfe`): none; a new row after the `covers` row. PROPOSED:
    > | `adopt` | no (default `none`) | what a product must do to use what the task delivers: `none`, or one concrete step naming the file and key (ADR-0041 D1) |
  - `docs/spec/05-operations.md` §29.3. CURRENT (at `7094dfe`): none; a new bullet after the one that begins "Every release checks the bound products". PROPOSED:
    > - `ccp upgrade notes [--since <commit>]` lists the plane's tasks merged since that commit (default: the previous release of the run checkout), each with its title, its `adopt` step and the proposals it answers. `ccp upgrade status`, run in a product, lists each `adopt` step of a merged plane task that the product's plane.json, binding and `.claude/settings.json` do not show taken, with the task, the product's own proposal for it when there is one, and the change to make; plane.json `upgrade.declined` (task ids, each with a reason) leaves a step out. `ccp plane built <proposal> --task <id>` closes an accepted proposal as built by a merged task and copies the task's `adopt` step into the proposal's record, which `ccp plane list` shows.
  - `ccp/upgrade.py` (new), wired in `ccp/cli.py`: `upgrade notes`, `upgrade status`.
  - `ccp/tasklog.py`: the `adopt` key read and validated (a string; `none` when missing); a warning on a pending task whose `paths` name `contracts/plane_config.schema.json` or a settings template and that has no `adopt`.
  - `ccp/plane.py`: `plane built`.
  - `contracts/task_file.schema.json`, `contracts/plane_config.schema.json` (`upgrade.declined`).
  - The writing-tasks skill: the `adopt` key in its frontmatter table.
  - The `adopt` step is checked by its form only: `status` matches a step whose file and key it can read (plane.json key paths, binding keys, settings keys) and lists any other step as "check by hand".
- **Out:**
  - The release notice (task 0110) and init defaults (task 0111).
  - Back-filling `adopt` on done tasks: a missing key reads as `none`.

## dod_checks

- id: `cmd-01`
  story: As a lead, I list what arrived since a commit.
  setup: a scratch plane task log with three tasks done after commit X: one `adopt: none`, one `adopt: plane.json verify.accept_cache`, one with no `adopt`.
  steps:
    1. Run `ccp upgrade notes --since X`.
  expect: three entries, each with title and step; the third shows `none`; exit 0.
  dry run: n/a.
- id: `cmd-02`
  story: As a lead, I see what my product has not adopted.
  setup: a scratch product whose plane.json lacks `verify.accept_cache` and has `verify.skip_review_after_clean: true`; the plane's done tasks carry `adopt:` steps for both keys and one step `run the migration by hand`.
  steps:
    1. Run `ccp upgrade status`.
    2. Add the first task's id to plane.json `upgrade.declined` with a reason and run it again.
  expect: (1) lists the `verify.accept_cache` step and the by-hand step marked "check by hand", not `skip_review_after_clean`. (2) the `verify.accept_cache` step is gone.
  dry run: n/a.
- id: `cmd-03`
  story: As a proposer's lead, a built proposal tells me the step.
  setup: a scratch queue with an accepted proposal P and a done task T with `adopt: plane.json verify.accept_cache`.
  steps:
    1. Run `ccp plane built P --task T`, then `ccp plane list`.
    2. Run `ccp plane built P --task NOPE`.
  expect: (1) P shows built, with T and its step. (2) refused, naming the task, and P is unchanged.
  dry run: n/a.
- id: `check-01`
  story: As a task-log owner, I am warned when a knob task names no step.
  setup: a pending task whose `paths` include `contracts/plane_config.schema.json` and no `adopt`.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 0 with one warning naming the task and the `adopt` key.
  dry run: n/a.
- id: `check-02`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §5 and §29.3 edits with the PROPOSED text above.
  expect: they match word for word, and no other § rule changes.
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
