---
task_id: 0041-product-declared-report-fields
title: Products declare required report fields that ccp report checks
status: done
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

- 2026-11-10 (implementer): plane.json gains a `report` block, `required_fields: [{name, values}]`
  (default none; `ccp/config.py` validates it, `contracts/plane_config.schema.json` lists it). A name is a
  letter then up to 39 letters, digits, spaces, `_` or `-`, unique without regard to case, and none of the
  lines `ccp report` already reads; values are a non-empty list of distinct one-line strings.
- `ccp report` (`ccp/report.py` `fields`) requires each declared field on implement and fix reports with
  `Outcome: done` only (as `PR:` and `Head:`): the line `<name>: <value>`, the name without regard to case
  (bold or a bullet allowed), the value the longest declared one the line starts with, followed by the
  line's end or a non-word character (so a reason may follow). Missing or another value: refused, naming the
  field and its allowed values. Accepted values are kept on the run as `fields` and printed by `ccp report`.
- Prompts: implement and fix list each declared field with its values in the report lines; the review prompt
  shows the task's latest done implement or fix report's verdicts (`not stated` for a report from before the
  declaration) and `ccp prompt review` prints them as `report_fields`, which is how the runner sees them
  (the plane renders no runner prompt; `plugin/agents/delivery-runner.md` says so). The verify prompt is not
  changed: the task names the implementer, runner and reviewer only.
- SPEC: the task gave no CURRENT -> PROPOSED text; §13.4 gains a bullet describing the feature and §8.1's
  block table a `report` row, written by the implementer as description of the task's own feature (§31.1);
  flagged in the report.

## Verification notes

- 2026-11-10 — verifier, PR #42 head `c007759` (squash `487a489`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0041-product-declared-report-fields.json.
