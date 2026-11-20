---
task_id: 0185-architect-on-by-default
title: The architect runs without a block, from the product's adoption point, and only "architect": false turns it off
status: done
kind: feature
depends_on: ["0172-fixtures-name-their-config", "0173-plane-json-block-registry", "0174-config-readers-go-through-ccp", "0177-architect-on-and-adoption-point", "0182-language-is-a-required-key"]
spec_refs: ["S4", "S5", "S8", "S19", "S20"]
adr_refs: ["0043 D7"]
review_point: R12
paths: ["ccp/config.py", "ccp/architect.py", "ccp/init.py", "ccp/cli.py", "ccp/upgrade.py", "ccp/tasklog.py", "contracts/plane_config.schema.json", "templates/docs-delivery/example-plane.json", "README.md", "docs/spec/01-model.md", "docs/spec/03-quality.md", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md", "tests/helpers.py", "tests/test_architect_default_on.py", "tests/"]
clashes_with: ["0181-models-block-and-role-defaults", "0184-init-turns-telemetry-on"]
adopt: "required: plane.json architect.shape_from_task (the adoption point: the next task number; or \"architect\": false to keep the seat off)"
sign_off: brief
created: 2026-11-19
updated: 2026-11-20
---

# Task: 0185-architect-on-by-default

## Intent

A product gets the architect without configuring it: with no `architect` block the seat is on, with
its defaults, and only `"architect": false` turns it off. Everything the seat enforces (shaping, the
kind and refactor-reference checks of the task log, the cadence and its blocks at `next`) starts at the
product's adoption point, the next task number when the seat turned on, so no finished task is judged
by rules written after it and a product with history owes no pass at once. A new product gets its
adoption point and the starter house rules from `ccp init`; a product with history records the point
by an upgrade step in its own repo.

## Context (not checked)

- ADR-0043 D7, accepted 2026-11-19.
- Depends on 0177, which routes every "architect off" test through `config.architect_on(cfg)` and every
  adoption-point read through `config.adoption_point(cfg)` (the key keeps the name `shape_from_task`);
  this task changes what those two return. Depends on 0174 (no raw reader of the `architect` block
  is left outside `ccp`), 0173 (the block registry holds the architect defaults), 0172 (the fixtures
  name their configuration) and 0182 (init's required-key lines and starter config, which this task
  extends).
- Today, at `e9ff0fc`: a fresh sandbox (`ccp sandbox create`; plane.json with no `architect` block)
  answers `ccp architect due` with `"enabled": false` and
  `"reason": "no architect block in docs/delivery/plane.json"` (dry run below); `"architect": false`
  is a configuration error, `` `architect` must be an object `` (probe:
  `python3 -B -c "…config.load(d)…"` on a plane.json with `"architect": false` at `e9ff0fc`).
- Already true at `e9ff0fc`, kept: a pass that fails twice in a row stops blocking until one succeeds
  (`failed_in_a_row` in `ccp architect due`'s output); `grace_tasks` and `triage_grace_tasks` block
  `next` as §19.6 states. The shape's D7 item proposing the two-failure rule as new is already built.
- Decided here:
  - **On, off, adopted.** `architect_on(cfg)` is true unless plane.json has `"architect": false`.
    `adoption_point(cfg)` is `architect.shape_from_task`, or None when unset. With the seat on and no
    adoption point, nothing the seat enforces applies (no cadence, no block at `next`, no kind or
    shaping check), and `ccp architect due` reports `"reason": "no adoption point: record
    architect.shape_from_task (the next task number) or set \"architect\": false"`; `ccp upgrade status`
    lists the step. An on-demand pass (`ccp architect run --force`, `--mode shape`) still runs.
  - **From the adoption point.** The cadence counts the tasks merged at or after the adoption point
    since the last pass (none before it); the kind and refactor-reference checks of `ccp tasks check`
    and the shaping check read only tasks numbered from it.
  - **`ccp init`** records `architect.shape_from_task` as the next task number of the product it
    adopts (`0001` for an empty task log), and writes the starter house rules as `--starter-rules` does
    today unless the product already has the rules doc; `--no-starter-rules` skips them.
    `--starter-rules` stays accepted and changes nothing.
  - **`rules_doc`** defaults to `docs/ENGINEERING.md`. When the doc is missing, a pass runs without house
    rules and its prompt and `ccp architect due` say so (`"rules_doc": "missing: docs/ENGINEERING.md"`).
  - The fixtures that build products with no `architect` block and assert the seat off gain
    `"architect": false`.
- **The plane's own repo** has no `architect` block and no adoption point: after this merges its seat
  is on and unadopted, so nothing changes for it until its own adoption point is recorded (a separate task in this review point).
- This task marks ADR-0043 D7 built in its own PR.

## Scope

- **In:**
  - `ccp/config.py`: `"architect": false` accepted; `architect_on` and `adoption_point` as decided;
    `rules_doc` default.
  - `ccp/architect.py`: the unadopted reason, the cadence from the adoption point, the missing rules
    doc.
  - `ccp/tasklog.py`: the kind checks from the adoption point.
  - `ccp/init.py`, `ccp/cli.py`: the adoption point, the starter rules by default, `--no-starter-rules`.
  - `ccp/upgrade.py`: this task's step.
  - `contracts/plane_config.schema.json` (`architect`: an object or `false`),
    `templates/docs-delivery/example-plane.json`, `README.md` (the checklist: the architect is on; the
    adoption point is required for a product with history).
  - `tests/helpers.py`, the fixtures that need the seat off; `tests/test_architect_default_on.py` (new).
  - `docs/spec/03-quality.md` §19.11: CURRENT (at `e9ff0fc`): "The seat is on when `plane.json` has an `architect` block (§8):" PROPOSED:
    > The seat is on unless `plane.json` sets `"architect": false` (§8); an `architect` block holds its settings, and without one it runs with its defaults. Everything it enforces (the triggers and their blocks at `next`, §19.6; shaping; the kinds, §20.3) starts at the product's **adoption point**, `shape_from_task`: the next task number when the seat turned on. `ccp init` records it (§4.5); a product with history records it by an upgrade step (§29.3). With no adoption point the seat enforces nothing, and `ccp architect due` says so.
  - `docs/spec/03-quality.md` §19.11, the table row: CURRENT (at `e9ff0fc`): "| `rules_doc`, `rules_max_lines` | —, 150 | The house rules (§20.1), for example `docs/ENGINEERING.md` |" PROPOSED:
    > | `rules_doc`, `rules_max_lines` | `docs/ENGINEERING.md`, 150 | The house rules (§20.1); when the doc is missing a pass runs without them and says so |
  - `docs/spec/03-quality.md` §19.11, the table row: CURRENT (at `e9ff0fc`): "| `shape_adrs`, `shape_from_task` | off, — | The shaping check (§19.6) |" PROPOSED:
    > | `shape_adrs`, `shape_from_task` | off, — | The shaping check (§19.6); `shape_from_task` is the adoption point |
  - `docs/spec/03-quality.md` §19.6: CURRENT (at `e9ff0fc`): "1. **Cadence.** `every_n_tasks` tasks (default 4) have merged since the last pass," PROPOSED:
    > 1. **Cadence.** `every_n_tasks` tasks (default 4) numbered from the adoption point (§19.11) have merged since the last pass,
  - `docs/spec/03-quality.md` §19.6: CURRENT (at `e9ff0fc`): "**Enforcement at `ccp tasks next`.** With an `architect` block, `ccp tasks next` needs `QUEUE_ROOT`" PROPOSED:
    > **Enforcement at `ccp tasks next`.** With the seat on and an adoption point, `ccp tasks next` needs `QUEUE_ROOT`
  - `docs/spec/03-quality.md` §20.5: CURRENT (at `e9ff0fc`): "`ccp init --starter-rules` writes the set to `docs/ENGINEERING.md` and, in a
    `plane.json` it writes, `docs.starter_rules` and the `package_docs` settings its `docs` checks name
    (§4.5)." PROPOSED:
    > `ccp init` writes the set to `docs/ENGINEERING.md` when the product has no such file (`--no-starter-rules` skips it) and, in a `plane.json` it writes, `docs.starter_rules` and the `package_docs` settings its `docs` checks name (§4.5).
  - `docs/spec/03-quality.md` §20.5: CURRENT (at `e9ff0fc`): "It does not set `architect.rules_doc`: until the product sets it
    to the rules doc, no architect judges the `pass` rules." PROPOSED:
    > `architect.rules_doc` defaults to that doc, so the architect judges the `pass` rules.
  - `docs/spec/01-model.md` §5.2, the `kind` row: CURRENT (at `e9ff0fc`): "| `kind` | no (default `feature`) | a key of `task_log.kinds`; read with the architect block on (§20) |" PROPOSED:
    > | `kind` | no (default `feature`) | a key of `task_log.kinds`; read with the architect seat on, for tasks from its adoption point (§19.11, §20) |
  - `docs/spec/01-model.md` §5.4: CURRENT (at `e9ff0fc`): "`task_log.kinds`, read with the architect block on." PROPOSED:
    > `task_log.kinds`, read with the architect seat on, for tasks from its adoption point (§19.11).
  - `docs/spec/01-model.md` §4.5: CURRENT: none (a new list item, after the plane.json item). PROPOSED:
    > - in a `plane.json` it writes, the architect's adoption point (`architect.shape_from_task`, the next task number, §19.11), and the starter house rules unless the product has a rules doc (§20.5);
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D7 marked built; `docs/adr/INDEX.md`.
  - Any other SPEC sentence that says the seat needs a block is corrected under §31.1 and quoted in the PR body.
- **Out:**
  - The plane's own adoption point (0190). Renaming `shape_from_task`. New architect triggers.

## dod_checks

- id: `arc-01`
  story: As an operator of a new product, the architect is on and adopted from its first task.
  setup: a checkout of the PR head; `ccp sandbox create <dir>`; its `PROJECT_YAML`, `QUEUE_ROOT` and `CCP_BINDINGS_DIR` exported.
  steps:
    1. Read `<dir>/product/docs/delivery/plane.json` and list `<dir>/product/docs`.
    2. In the product root, run `ccp architect due`.
  expect: step 1 shows `architect.shape_from_task` `0001` and `docs/ENGINEERING.md` present; step 2 prints `"enabled": true` and no `no architect block` reason.
  dry run (`e9ff0fc`): step 1 plane.json is `project_id` and `worktrees` only, `docs` holds `PROJECT.md`, `SPEC.md`, `delivery`; step 2 `"enabled": false`, `"reason": "no architect block in docs/delivery/plane.json"`.
- id: `arc-02`
  story: As an operator, `"architect": false` turns the seat off.
  setup: a checkout of the PR head; a temp product whose plane.json is `{"project_id": "demo", "architect": false}`.
  steps:
    1. Run `python3 -B -c "from ccp import config; c=config.load('<dir>'); print(config.architect_on(c))"`.
  expect: prints `False`, no error.
  dry run (`e9ff0fc`): `ConfigError: … `architect` must be an object` (and `architect_on` comes with 0177).
- id: `arc-03`
  story: As the lead of a product with history, turning the seat on judges no old task and owes no pass at once, and an unadopted seat says so.
  setup: a checkout of the PR head; then a separate copy where `adoption_point(cfg)` always returns `1`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_architect_default_on`.
    2. In the copy, run the same.
  expect: step 1 exits 0, its tests covering: a product with ten done tasks, no block and no adoption point (`due` false, the no-adoption-point reason, `next` not blocked, a done refactor citing `spec_refs` passing `tasks check`); the same with `shape_from_task` `0011` (not due; due after four more merges); a missing rules doc reported; step 2 exits non-zero.
  dry run: n/a — new module.
- id: `arc-04`
  story: As a plane developer, the tests that held the seat's behaviour still pass, with the seat off where they assumed no block.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_architect tests.test_kinds tests.test_rules tests.test_init tests.test_board_quality`.
  expect: exits 0.
  dry run (`e9ff0fc`): 5 modules, among the 626 tests that passed in one run.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed, and D7 is recorded as built.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0185-architect-on-by-default --base origin/main`.
    2. Run `grep -n '"D7 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: step 1 exits 0 with every passage found; step 2's output contains `- "D7 built"`.
  dry run (`e9ff0fc`): step 2 printed `- "D7 not_built"`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- Representation: `cfg.architect` is the merged settings dict whenever the seat is on (no block, `{}` or a block) and
  None only for `"architect": false`, so `architect_on` stays `cfg.architect is not None` and the truthiness tests of
  the architect config the runner's note names (forecast, rules, tasklog, quality) route through `architect_on`.
  `"architect": true` is a configuration error. New `config.architect_adopted(cfg)` (on and an adoption point): the
  seat enforces only then. `Config.rules_doc_set` records whether plane.json names `rules_doc` itself.
- Gated on adoption, beyond the cadence the Context names: the `next` gate and its QUEUE_ROOT requirement, the review-point,
  notes, drift and budget triggers of `ccp architect due`, a report awaiting triage (no block while unadopted), the kind and
  refactor-reference checks (per task, `tasklog.seat_reads`), and the refactor lane (`ranked`, `refactor_reach`,
  `waiting_refactors`, the forecast, the review point's refactors in `selection`, the board's waiting refactors): a product
  with history and refactor tasks would otherwise see its order change at the merge. A product with a block and no
  `shape_from_task` is unadopted too: the seat stops enforcing until the step is taken.
- The default `rules_doc` (`docs/ENGINEERING.md`): missing is no failure of `ccp docs check` unless plane.json names it;
  present, the default doc is judged only once the seat is adopted. `ccp architect due` carries `rules_doc` (`missing: <path>`)
  and `adoption_point`; the prompt says the pass runs without house rules.
- `ccp init`: `starter_rules` defaults on; the doc is never overwritten (`--force` included) and its plane.json settings are
  left out when the product's own rules doc exists; the adoption point is the next number from the task files' names.
  Re-running on a kept plane.json lists `--starter-rules` as not applied only when it wrote the doc that run.
- Tests: `BASE_PLANE` gains `"architect": false`; the architect blocks of the modules that exercise enforcement name
  `"shape_from_task": "0001"`.
- §31.1 corrections beyond the quoted passages (no new rule): 01-model §4.5 (`--starter-rules` bullets), 03-quality §19.6
  item 5 (on demand "with the seat off"), §20.3 (kinds), §20.3's board line (`refactors_waiting` null unless adopted);
  README, `docs/cli/01-model.md`, the starter-rules and ENGINEERING templates, `contracts/task_file.schema.json`.
- Fix round 1: the refactor lane reads a task's `kind` only from the adoption point, as the kind checks do:
  `tasklog.lane_refactor(cfg, t)` (kind refactor and `seat_reads`) replaces `kind_of(t) == "refactor"` in `ranked`,
  `refactor_reach`, `waiting_refactors`, `features_since_refactor`, the forecast's replay and the board's waiting
  refactors, so an old pending refactor numbered below the point is an ordinary task. Workers are sent to the house rules
  doc only when the file exists (`prompt.rules_doc_for`). `ccp init` refuses `--starter-rules` with `--no-starter-rules`
  (exit 2). The stale "with an `architect` block" wording in `tasks next`'s help, the verifier agent, the runner-idle hook,
  the board design doc, `tasklog`'s docstring and `docs/ENGINEERING.md` now says the seat is adopted or on; the extra
  blank line in §19.11 is gone. SPEC §20.3's board line (`refactors_waiting` null unless adopted) still reads true.

## Verification notes
- 2026-11-20 — verifier, PR #214 head `59b8a53` (squash `9ffab51`): APPROVE. Passed: arc-01, arc-02, arc-03, arc-04, spec-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp suite run --lane part -- python3 -B -m unittest -q tests.test_architect_default_on tests.test_architect tests.test_kinds tests.test_rules tests.test_init tests.test_board_quality tests.test_prompt_tools` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0185-architect-on-by-default.json.

