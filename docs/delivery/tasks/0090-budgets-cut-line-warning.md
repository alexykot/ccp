---
task_id: 0090-budgets-cut-line-warning
title: ccp budgets check warns at a declared cut line before the limit
status: pending
kind: feature
depends_on: []
spec_refs: ["S20"]
review_point: R5
paths: ["ccp/rules.py", "ccp/cli.py", "ccp/config.py", "docs/spec/03-quality.md", "contracts/plane_config.schema.json", "tests/test_budgets*.py", "tests/test_rules.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0090-budgets-cut-line-warning

## Intent

A product with size budgets is told when a file crosses a declared cut line below its hard limit, so a cut is tasked before the limit fails the gate (§20.2).

## Context (not checked)

- Accepted plane proposal: only the limit is checked by a command, so a cut line was noticed by reading, or not at all.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** a budget rule may declare `cut_line` beside its limit; `ccp budgets check` warns, naming the file, its size, the cut line and the limit, for a file at or above the cut line and below the limit, and fails as today above the limit; §20.2 describes it.
- **Out:** filing the refactor task automatically.

## dod_checks

- id: `check-01`
  story: As a lead, a file nearing its limit is flagged.
  setup: a scratch product with a budget limit 100 and cut line 90, and a file of 95 lines.
  steps:
    1. Run `ccp budgets check`.
  expect: it warns, naming the file, 95, 90 and 100, and exits 0.
  dry run: on the merge base `cut_line` is refused or ignored.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
