---
id: ADR-0032
title: "Around-the-clock operation"
status: accepted
date: "2026-09-15"
deciders: operator
spec_refs: [S18]
decisions: ["D1 live", "D2 built"]
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0032 — Around-the-clock operation

## Context

Seats should work whenever there is ready work and allowance, without invented quiet hours. An early per-task runaway backstop guarded against a system that could get stuck; that risk is now covered by the team's own liveness signals.

## Decision

### D1. No quiet hours

Seats run around the clock; nothing invents quiet hours or slows down overnight.

### D2. The runaway backstop is retired

The per-task twelve-hour backstop is removed from the code, the SPEC and the runner brief.

## Consequences

- Work continues while the operator is away.
- A stuck task is caught by idle and failure signals, not by a wall-clock limit.
