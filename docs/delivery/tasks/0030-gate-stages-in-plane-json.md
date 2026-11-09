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

## Verification notes

*Append-only.*
