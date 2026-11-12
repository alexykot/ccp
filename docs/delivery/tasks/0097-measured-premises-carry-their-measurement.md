---
task_id: 0097-measured-premises-carry-their-measurement
title: A brief's measured premises name the command and commit they came from, and the implementer re-checks them
status: pending
kind: chore
depends_on: []
spec_refs: ["S5", "S13"]
review_point: R5
paths: ["plugin/skills/writing-tasks/", "plugin/agents/delivery-implementer.md", "templates/prompts/", "ccp/tasklog.py", "tests/test_tasklog*.py", "tests/test_plugin.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0097-measured-premises-carry-their-measurement

## Intent

A count, size, list of sites or "X already/never happens" claim in a task brief names the command
that measured it and the commit it ran at, and the implementer re-runs it at its base before
building, so a premise that moved between writing and claim costs a scope question, not a wasted
round (§5, §13).

## Context (not checked)

- Accepted plane proposal. A managed product's friction notes showed briefs whose factual premises
  were wrong at claim, each costing a probe, a scope question or an extra round. The plane's own
  tasks had the same: three this week rested on a false premise.
- §31.1: skill and brief guidance plus an optional warning describing its own feature; no merge
  gate.

## Scope

- **In:**
  - The writing-tasks skill: any count, size, site list or "already/never happens" claim in a brief
    names, in Context, the command that measured it and the commit it was run at.
  - The implementer brief and implement prompt: the first step re-runs those commands at the base,
    and if a figure changed materially, stops with a scope question before building.
  - `ccp tasks check` warns (not fails) on a pending task whose Context states a number with no
    backticked command on the same line.
- **Out:** checking that the command's output matches.

## dod_checks

- id: `check-01`
  story: As a task writer, an unmeasured number is flagged.
  setup: a scratch product with a pending task whose Context says "only 2 call sites exist" and
    another saying "`git grep -c foo` at abc1234: 2 call sites".
  steps:
    1. Run `ccp tasks check`.
  expect: a warning names the first task's line; none for the second; the check still passes.
  dry run: on the merge base no warning is given.
- id: `check-02`
  story: As an implementer, I re-check premises first.
  setup: a checkout of the PR head.
  steps:
    1. Read the implementer brief, the implement prompt and the writing-tasks skill.
  expect: each states the rule as above.
  dry run: n/a.
- id: `check-03`
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
