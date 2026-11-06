---
id: ADR-0020
title: "Allowance checkpoint and usage windows"
status: accepted
date: "2026-10-21"
deciders: operator
spec_refs: [S25]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 built"
  - "D5 built"
  - "D6 built"
  - "D7 live"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0020 — Allowance checkpoint and usage windows

## Context

Spend limits are guidance where the operator weighs time to reset and other plans, not hard walls. Providers expose different usage windows, so the rules must be generic per window. A hard allowance gate and a fixed five-hour park rule were replaced.

## Decision

### D1. A checkpoint

A weekly window's threshold is a checkpoint: new claims stop, and the lead asks the operator and records their decision to continue to a new level.

### D2. Only the operator decides

Only the lead records a continue decision, and only the operator's.

### D3. Decisions lapse

A decision lapses at the window's end or at a detected counter reset.

### D4. Named windows

The allowance input reports any number of named windows; each is weekly (stop) or session (park), with its own threshold.

### D5. Park and wake

At a session window's park threshold, work parks until the reported reset plus a margin, then wakes.

### D6. Unknown is not zero

An unknown reading is recorded as unknown, never zero; a missing session figure means no session limit.

### D7. Quota is a wait

Quota pauses are waits, never failures.

## Consequences

- The operator keeps control of spend without babysitting it.
- A provider with other windows is configured, not coded.
