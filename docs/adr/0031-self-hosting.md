---
id: ADR-0031
title: "Self-hosting"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S4, S31]
decisions: ["D1 built", "D2 built", "D3 built"]
notes: "2026-11-05: status proposed → accepted"
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

## Consequences

- Every plane format is exercised on the plane first.
- Releasing moves the checkout that runs the plane's own tasks, so runner-driven work needs its own release rule.
