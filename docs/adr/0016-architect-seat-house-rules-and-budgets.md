---
id: ADR-0016
title: "Architect seat, house rules and budgets"
status: accepted
date: "2026-10-14"
deciders: operator
spec_refs: [S19, S20]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
  - "D6 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0016 — Architect seat, house rules and budgets

## Context

Each task's verifier checks that task, not the whole. Structural drift across code, tests, docs and process needs one owner, rules of the product's own, and triggers the plane enforces. A separate architecture-review seat and docs audit were folded in.

## Decision

### D1. One architect

One architect seat owns a product's structural health; passes are triggered by the plane on merged-task cadence and enforced at task selection.

### D2. House rules

House rules are product-owned, current-only and length-capped, each with a check.

### D3. Refactor capacity

A refactor task kind has reserved capacity; a refactor joins a scope only when a scope task depends on it.

### D4. Budgets on growth

Budgets in the house rules are gated on the files a change grew.

### D5. Diagnostics, not targets

Health measurements are diagnostics, never targets or definition-of-done items.

### D6. Shaping

Shaping is the architect's; a task citing an unshaped ADR waits unless it records a waiver with a reason.

## Consequences

- Drift is caught on a cadence, not by accident.
- Architect passes cost tokens on a schedule.
