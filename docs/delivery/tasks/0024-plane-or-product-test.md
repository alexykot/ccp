---
task_id: 0024-plane-or-product-test
title: The plane-or-product test for tool proposals
status: done
kind: feature
depends_on: []
spec_refs: ["S31"]
adr_refs: ["0035 D8"]
review_point: R1
paths: ["docs/spec/05-operations.md", "cpl/plane.py", "cpl/cli.py", "plugin/agents/delivery-runner.md", "plugin/orientation.md", "plugin/skills/review-triage/SKILL.md", "templates/prompts/_common.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0024-plane-or-product-test

## Intent

Seats file a plane proposal only for a need any product would have; `cpl plane propose` requires `--generic` saying why; product needs become product tasks, wired in through the product's own checks and hooks.

## Context (not checked)

- A batch of proposals turned out to be the product's own business; nothing told seats where the line was.

## Scope

- **In:** SPEC §31.4, the propose command, the runner brief, the orientation, the review-triage skill, the worker prompts, tests.
- **Out:** triage itself.

## dod_checks

- id: `gen-01`
  story: As a seat, a proposal without a reason it is generic is refused.
  setup: a temporary queue.
  steps:
    1. Run `cpl plane propose --need "x"`.
  expect: exit non-zero, pointing at product work; with `--generic "…"` it is recorded with that field.
  dry run: n/a — built by the task's test.
- id: `doc-01`
  story: As a seat, every brief that tells me to propose also tells me the test.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'plane propose' -- plugin templates`.
  expect: each hit shows `--generic` or sits beside the plane-or-product test.
  dry run (`cf3ef8c`): three hits, none with the test.

## Implementation notes

*Append-only, newest last.*

- 2026-11-06: SPEC §31.4 opens with the plane-or-product test and examples on each side; `cpl plane
  propose` refuses a proposal without `--generic` (stored on the row; `--again` exempt). The test is
  repeated in the runner brief, the orientation, the review-triage skill and the worker prompts'
  Friction rule.

## Verification notes

*Append-only.*

- 2026-11-06 — `gen-01` pass — tests/test_toolkit.py: a propose without `--generic` exits 2 naming
  product work; with it, the row carries `generic`.
- 2026-11-06 — `doc-01` pass — every `plane propose` in plugin/ and templates/ shows `--generic` or
  sits beside the test.
