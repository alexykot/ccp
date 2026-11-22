---
task_id: 0001-an-example-task
title: An example task that adds one export format
status: pending
kind: feature
depends_on: []
spec_refs: ["S5"]
paths: ["src/exports/csv.py", "tests/test_exports.py"]
adopt: "none"
created: 2026-01-05
updated: 2026-01-05
---

# Task: 0001-an-example-task

## Intent

A user can export a report as a CSV file, and the file opens in a spreadsheet with one row per entry.

## Context (not checked)

- The report's entries are already listed by `src/exports/base.py`; this task adds the one format.

## Scope

- **In:** `src/exports/csv.py` (the writer), `tests/test_exports.py` (its test).
- **Out:** every other export format.

## dod_checks

- id: `cmd-01`
  story: As a user, I export a report as CSV and read one row per entry.
  setup: A checkout of the PR head, any seat.
  steps:
    1. Run `python3 -m unittest tests.test_exports`.
  expect: exit 0, and the CSV test is listed as `ok`.
  dry run: n/a — the test is new.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only, per check id: pass or fail, with evidence.*
