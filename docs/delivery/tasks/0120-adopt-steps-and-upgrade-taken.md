---
task_id: 0120-adopt-steps-and-upgrade-taken
title: Every opt-in feature carries a real adopt step, and a product can record a step as taken
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S29"]
review_point: R8
sign_off: brief
paths: ["ccp/upgrade.py", "ccp/tasklog.py", "ccp/config.py", "contracts/plane_config.schema.json", "contracts/task_file.schema.json", "docs/spec/01-model.md", "docs/spec/05-operations.md", "plugin/skills/writing-tasks/SKILL.md", "docs/delivery/tasks/", "tests/test_upgrade*.py", "tests/test_tasklog*.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0120-adopt-steps-and-upgrade-taken
## Intent

A product adopted with the plane's defaults runs `ccp upgrade status` and sees every opt-in feature
the plane has built, each as a step it can take, decline, or record as already taken by hand. No
step hides behind an `adopt` value that starts with `none`.

## Context (not checked)

- Since the task that added `adopt` (ADR-0041 D1), a value whose first word is `none` reads as no
  step (`tasklog.asks_nothing`). Several tasks with an off-by-default knob carry
  `none: off by default; <knob> turns it on`, which hides exactly what `ccp upgrade status` exists to
  show. Tasks merged before the `adopt` key existed carry none at all.
- `ccp upgrade status` checks a step it can parse (`<file> <dotted key> [value]`, the file one of
  `plane.json`, `binding`, `settings`) by the key's presence; any other step reads "check by hand".
  A product that took a by-hand step can today only list it under `upgrade.declined`, which misreads
  a taken step as a refused one.
- The knobs below are off, or unset, by default; the task that last shaped each is where its step
  goes (`git grep -l <knob> -- docs/delivery/tasks/` at `b4de6ad` names them).
- Done-task files are edited here for their `adopt:` line only.

## Scope

- **In:**
  - `adopt:` set, in the frontmatter of each done task below, to a parseable step:
    - `0013-prompt-bodies-opt-in`: `none` (keeping prompt bodies is a debugging choice, not a step).
    - `0019-*`: `plane.json docs.workers 4`.
    - `0034-*`: `plane.json docs.starter_rules {} to adopt the starter house rules`.
    - `0047-*`: `plane.json adr.strict true, for a product that keeps ADRs`.
    - `0049-*`: `plane.json parallel.max_in_flight 2, to run two runners`.
    - `0068-*`: `plane.json notify.lead with tool and to naming the lead's message channel`.
    - `0073-*`: `plane.json estimate.auto true`.
    - `0093-*`: `binding runner.rotate_at_context_tokens 200000`.
    - `0094-*`: `plane.json verify.skip_review_after_clean true`.
    - `0111-*`: `settings subagentPromptCacheTtl 1h, with autoCompactWindow beside it`.
    - `0112-*`: `run the gate's test modules in parallel processes, as the plane's scripts/gate_parallel.py does` (by hand).
    - `0113-*`: `plane.json verify.accept_cache true, once the product's gate keeps a content-keyed test cache`.
    - `0114-*`: `none: the advice appears by itself`.
    - `0119-*`: `plane.json workers.implementer_model small and refactor set to an alias, once the plane's trial reports`.
    - any other done task whose file `ccp tasks check` warns about after this task's warning lands: `adopt: none`, or a step when it shipped an off-by-default knob.
  - `ccp/config.py`, `contracts/plane_config.schema.json`: plane.json `upgrade.taken`, an object of
    task ids, each with a reason, beside `upgrade.declined`.
  - `ccp/upgrade.py`: `status` leaves a taken task's step out of `steps` and lists it under `taken`
    with its reason.
  - `ccp/tasklog.py`: `ccp tasks check` warns on a task whose `adopt` value's first word is `none`
    and which names a dotted key whose first part is a plane.json block or a binding block
    (`runner`, `lead`), or a settings key `ccp init` writes.
  - `docs/spec/05-operations.md` §29.3. CURRENT (at `b4de6ad`): "plane.json `upgrade.declined` (task ids, each with a reason) leaves a step out." PROPOSED:
    > plane.json `upgrade.declined` (task ids, each with a reason) leaves a step out; `upgrade.taken` (task ids, each with a reason) leaves out a step the product took in a way the command cannot see, and `ccp upgrade status` lists it under `taken` with its reason.
  - `docs/spec/01-model.md` §5, the `adopt` row. CURRENT (at `b4de6ad`): "| `adopt` | no (default `none`) | what a product must do to use what the task delivers: `none`, or one concrete step naming the file and key (ADR-0041 D1) |" PROPOSED:
    > | `adopt` | no (default `none`) | what a product must do to use what the task delivers: `none`, or one concrete step naming the file and key (ADR-0041 D1). A task that ships an off-by-default knob carries its step, never `none`; `ccp tasks check` warns on a `none` value that names a plane.json, binding or settings key |
  - `plugin/skills/writing-tasks/SKILL.md`: the same rule in one line.
- **Out:**
  - Changing any knob's default.
  - Steps for features with no knob.

## dod_checks

- id: `cmd-01`
  story: As a product adopted with defaults, I see every opt-in step.
  setup: a scratch product made by `ccp init` with the default plane.json, binding and settings, at the PR head.
  steps:
    1. Run `ccp upgrade status --json` there.
  expect: `steps` holds one entry each for the tasks listed in Scope with a step (0019, 0034, 0047, 0049, 0068, 0073, 0093, 0094, 0112, 0113, 0119), each `not taken` or `check by hand`; 0111's is absent, since init wrote its key.
  dry run: n/a — the steps are written by this task.
- id: `cmd-02`
  story: As a product that took a step by hand, I record it as taken.
  setup: the scratch product of cmd-01, with plane.json `upgrade.taken` holding `0112-parallel-gate-and-slow-modules` with reason "gate already parallel".
  steps:
    1. Run `ccp upgrade status --json`.
  expect: 0112 is absent from `steps` and present under `taken` with that reason; a task under `upgrade.declined` is in neither.
  dry run: n/a.
- id: `cmd-03`
  story: As a task writer, a step hidden behind `none` is caught.
  setup: a scratch task log with a pending task whose `adopt` is `none: off by default; plane.json verify.accept_cache turns it on`, and one whose `adopt` is `none: the advice appears by itself`.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 0, one warning naming the first task and `verify.accept_cache`, none for the second.
  dry run: n/a.
- id: `cmd-04`
  story: As the plane's maintainer, the task log stays quiet.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp tasks check`.
  expect: no warning about any task's `adopt` value.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §29.3 and §5 edits with the PROPOSED text above.
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

- 2026-11-17 (implementer): `upgrade.taken` sits beside `upgrade.declined` (config, schema), validated the
  same way. `ccp upgrade status` returns `taken` (task, title, adopt, reason) beside `steps`; a task in
  `declined` is in neither, `declined` winning when a product lists a task in both; a recorded id whose
  step is `none` is not listed. The step file `settings` now parses as `.claude/settings.json` (the
  Context named it parseable; at 459bb77 only `.claude/settings.json` did), so 0111's step reads as taken
  in an init'ed product. plane.json's top-level block names moved to `config.BLOCKS`, which the unknown-key
  check and the new warning share. `tasklog.hidden_step` warns on any task but a dropped one: it reads the
  `adopt` value's words, outside paths, for a dotted key under a plane.json block or `runner`/`lead`, or a
  settings key `ccp init` writes (the anchor's keys and the two session settings, bare or dotted). After
  the edits no task in the log draws the warning, so no further done task needed a new `adopt:` line.
  `ccp upgrade status` takes no `--json` (it always prints JSON); cmd-01 and cmd-02 run it as written
  otherwise.

## Verification notes
