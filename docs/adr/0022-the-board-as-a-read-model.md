---
id: ADR-0022
title: "The board as a read model"
status: accepted
date: "2026-10-21"
deciders: operator
spec_refs: [S28]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0022 — The board as a read model

## Context

Asking the most expensive seat what is happening costs tokens and turns the operator back into the bus. State should be readable without waking any agent. An earlier snapshot file, rendered status file and status script were replaced.

## Decision

### D1. One summary per project

One JSON summary per project, built without a model call from the ledger, runs, usage, queue, task log and git.

### D2. Always current

A self-refreshing page reads it; a timer and every state-changing command rebuild it.

### D3. Priorities

Time and tokens come first, then live state, plane health, quality, then plan and backlog.

### D4. Diagnostics only

Numbers on the board are diagnostics, never definition-of-done items or worker goals.

### D5. Model drift flagged

The board flags an observed model or effort that differs from a seat's pinned values.

## Consequences

- The operator reads state without spending tokens.
- The read model moves to the hosted dashboard when the store exists.
