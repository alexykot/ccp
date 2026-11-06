---
id: ADR-0005
title: "Seats and separation of duties"
status: accepted
date: "2026-09-15"
deciders: operator
spec_refs: [S2, S13, S17]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
  - "D6 live"
  - "D7 built"
  - "D8 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0005 — Seats and separation of duties

## Context

Independent judgement is only independent if the seat that judges did not produce what it judges, and if no seat quietly takes over another's duties. Seat configuration must not depend on whoever happens to run the lead session. A headless spec maintainer resumed under a lock, and a combined seat that both ruled and ran tasks, were replaced.

## Decision

### D1. The lead is the design seat

The lead is spec maintainer, task-log owner, gate approver and the only route to the operator.

### D2. The runner orchestrates

The runner claims, prompts, reports, merges and reconciles one task at a time; it never invents intent or approves its own gates.

### D3. Workers are separate

Implementer, reviewer and verifier are worker subagents with separate contexts; the reviewer never shares the implementer's.

### D4. No combined seats

A seat does not take another seat's duties.

### D5. Judges do not produce evidence

The seat that rules on a task does not produce the evidence it is judged on; the lead never runs a task's checks.

### D6. Pinned models

Each seat's model and effort are pinned in its own definition by full model id, never inherited or overridden at launch.

### D7. The lead's model is the operator's

The lead's own model and effort are the operator's choice; the plane only advises when observed values differ.

### D8. The lead answers spec questions

Spec questions are answered in the lead's own session; there is no separate headless spec-maintainer process.

## Consequences

- Reviews and verification stay independent by construction.
- More seats cost more tokens than one combined agent.
