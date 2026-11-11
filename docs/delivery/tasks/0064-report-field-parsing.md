---
task_id: 0064-report-field-parsing
title: A declared report field is parsed strictly
status: pending
kind: bug
depends_on: []
spec_refs: ["S13"]
review_point: R4
paths: ["ccp/report.py", "tests/test_report_fields.py"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0064-report-field-parsing

## Intent

`ccp report` refuses a declared field whose value is the template placeholder, and refuses a report that states a declared field more than once, naming the field, so a verdict is never read from a pasted template or an ambiguous report.

## Context (not checked)

- From task 0041's review: the placeholder `required|not required` is accepted as `required`; with two lines for a field, the first wins silently.

## Scope

- **In:** a value that is not exactly one of the field's declared values is refused (the `a|b` template form included); a second line for the same field is refused. The refusal names the field and the line.
- **Out:** which fields products declare.

## dod_checks

- id: `check-01`
  story: As a runner, a pasted placeholder is not a verdict.
  setup: a scratch product declaring a field with values `required` and `not required`; a report stating the field as `required|not required`.
  steps:
    1. Run `ccp report` on it.
  expect: it is refused, naming the field.
  dry run: on the merge base it is accepted as `required`.
- id: `check-02`
  story: As a reviewer, a report cannot state a field twice.
  setup: the same product; a report with the field on two lines, `required` then `not required`.
  steps:
    1. Run `ccp report` on it.
  expect: it is refused, naming the field and both lines.
  dry run: on the merge base the first line wins silently.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 (implementer): `report.fields` now finds every line for a declared field. Two or more
  are refused with the field and each line's number and value (even when they agree). A matched value
  whose next character, after spaces and markup (`` ` ``, `*`, `_`), is `|` is refused as the pasted
  `a|b` template, naming the field and its line; the "says" refusal now also names the line. A reason
  after the value stays allowed (the existing tests pin it), so "exactly one value" is read as "one
  value, not the template's alternatives"; a `|` later in the reason is not refused. SPEC §13.4 is
  unchanged: the task gives no SPEC text for the "once" rule.

## Verification notes

*Append-only.*
