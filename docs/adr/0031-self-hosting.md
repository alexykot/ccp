---
id: ADR-0031
title: "Self-hosting"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S4, S31]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built — release rule (a), operator 2026-11-21"
notes: |-
  2026-11-05: status proposed → accepted
  2026-11-21: D4 added, the release rule for runner-driven self-hosting, from architect pass
  ar-20261121T132817Z-d5e5 (F04), option (a). Operator: "release rule - (a)" (2026-11-21)
---
# ADR-0031 — Self-hosting

## Context

The plane should be the reference example of a managed project, which also proves its generality. Its standing decisions should be recorded the way it asks products to record theirs.

## Decision

### D1. The plane manages itself

The plane's own development is recorded with the plane's task log, ADRs and house rules; runner-driven development comes later.

### D2. No separate examples

The examples directory is removed in favour of the plane itself.

### D3. Rulings as ADRs

The operator's standing rulings are kept as the plane's own ADRs, with no private detail.

### D4. A release happens at any time

Runner-driven self-hosting is in place: a lead and runner teammates deliver the plane's own tasks
through `ccp`. A merge to main is a release (ADR-0024), made at any time, whatever tasks are in
flight. Tasks in flight carry on: their workers run the head they change (task 0240), and only the
runners' and the lead's own `ccp` calls move to the new release. No release waits for tasks to drain,
and none is held for a review point's close. This retires D1's "runner-driven development comes
later" and the open release rule in the Consequences.

## Consequences

- Every plane format is exercised on the plane first.
- Releasing moves the checkout that runs the plane's own tasks; D4 is the rule for tasks in flight.
