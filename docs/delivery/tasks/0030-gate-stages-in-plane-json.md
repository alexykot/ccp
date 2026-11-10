---
task_id: 0030-gate-stages-in-plane-json
title: Gate stages are declared in plane.json and run by ccp
status: pending
kind: feature
depends_on: []
spec_refs: ["S8", "S14", "S21"]
review_point: R3
paths: ["ccp/", "docs/spec/", "templates/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0030-gate-stages-in-plane-json

## Intent

A product declares its gate as named stages in `plane.json` (name and command each). `ccp` runs them in order, times each one, stops at the first failure and records which stage failed in the gate result. The plane's own doc checks run as a stage `ccp` adds itself, so no product gate script calls `ccp`.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §8 and §14 and §21.
- Today a product's gate script calls `ccp docs check` itself, so renaming or reshaping a plane command changes product code and tests.
- Stage timings are what the shell-limit rule (task 0031) judges.

## Scope

- **In:** the `suite` (or a new `gate`) block in `plane.json` accepts an ordered list of `{name, cmd}` stages; `ccp suite run` runs them, records per-stage seconds and the failing stage in the gate-result JSON (§14); the plane's doc checks run as a built-in stage; a product with the old single-command lane keeps working; §8 and §14 describe the stages; the template `plane.json` shows them.
- **Out:** choosing a product's stages; parallel stages.

## dod_checks

- id: `check-01`
  story: As a product lead, a failing stage is named.
  setup: a scratch product with stages `lint` (passes) and `tests` (fails).
  steps:
    1. Run the gate through `ccp suite run`.
  expect: it stops after `tests`, the gate result names `tests` as failed and lists each stage's seconds; a later stage is not run.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a product lead, my gate never calls ccp.
  setup: a scratch product whose stages contain no `ccp` command.
  steps:
    1. Run the gate.
  expect: the plane's doc checks still run, as their own stage, and appear in the result.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-03`
  story: As an existing product, the old lane form still works.
  setup: a scratch product with `suite.lanes.gate` as today.
  steps:
    1. Run the gate.
  expect: it runs as one stage and passes as before.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): Stages live in the existing `suite.lanes` block: a lane's value is either
  today's argv or an ordered list of `{name, cmd}` stages (`name` a lane-like label, unique in the lane;
  `cmd` a shell string run by `/bin/sh -c` from the root, as `docs.checks` commands are). `ccp suite run
  --lane L` (no `--` command) resolves the lane to stages (`suite.resolve_stages`), runs them one by one
  in its own loop (`suite._run_stage`: the old spawn, signal, watchdog and pump code, now per stage),
  stops at the first non-zero exit or signal, and exits with that stage's code. The built-in stage is
  `plane-docs` (`config.PLANE_DOCS_STAGE`, refused as a product stage name): this `ccp`'s own `--root
  <root> docs check`, appended last, only to the gate role's lane (`suite.roles`), only when that lane
  is declared as stages; an argv lane runs as one stage named after the lane and gets no `plane-docs`,
  so it passes as before. The gate result: every lane run from plane.json records `stages` (`[{name,
  seconds, exit_code}]`, the stages that ran) and `failed_stage` (or null) on its `ended` row and
  `suite/recorded` event; a `--` command records neither. Each stage gets its own `CCP_SUITE_RESULT`
  file; valid results' counters are summed. A staged lane's summary carries a stages line (and marks
  each stage's start and end in the log, on stderr with `--full`); its `started` row says `cmd: stages`
  with the stage count as `argc`. A nested staged run executes the stages in order, unrecorded. SPEC
  edits: §8.1 table row and example, §14.1 (lane sentence), §14.2 (a new Stages bullet), §14.3
  (`stages`, `failed_stage`, summed results), §14.4 (row and event fields), §21.2 (one sentence). Also
  changed, outside the task's `paths`: `contracts/plane_config.schema.json` (lanes take either form)
  and `contracts/suite_result.schema.json` (`stages`, `failed_stage`), which the config and §14.3 cite.

## Verification notes

*Append-only.*
