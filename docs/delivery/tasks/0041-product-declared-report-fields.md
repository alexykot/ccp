---
task_id: 0041-product-declared-report-fields
title: Products declare required report fields that ccp report checks
status: pending
kind: feature
depends_on: []
spec_refs: ["S8", "S13"]
review_point: R3
paths: ["ccp/report.py", "ccp/prompt.py", "docs/spec/02-delivery.md", "plugin/agents/", "tests/test_report*.py"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0041-product-declared-report-fields

## Intent

A product declares verdict lines every implementer report must state (for example whether the change needs a migration or a deploy step). `ccp report` refuses a report missing one, and the runner and reviewer see the declared verdicts.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §8 and §13.
- Products have verdicts every change must state; declaring them once beats prose in every prompt.

## Scope

- **In:** a `report.required_fields` list in `plane.json` (name, allowed values); `ccp report` validates them; the prompts the plane renders for the implementer, runner and reviewer list them; §13 describes it.
- **Out:** judging whether a verdict is right.

## dod_checks

- id: `check-01`
  story: As a runner, a report missing a declared verdict is refused.
  setup: a scratch product declaring `migration: required|not required`.
  steps:
    1. Submit a report without it.
  expect: refused, naming the field and its allowed values.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a reviewer, I see the verdict.
  setup: a report with the field.
  steps:
    1. Render the reviewer prompt.
  expect: it shows the verdict.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
