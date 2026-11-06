---
id: ADR-0002
title: "Three-layer product docs; task log in product git; runtime queue outside it"
status: accepted
date: "2026-09-15"
deciders: operator
spec_refs: [S4, S5, S10]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0002 — Three-layer product docs; task log in product git; runtime queue outside it

## Context

Agents drift when the goal, the behavioural truth and the unit of work are mixed or live only in chat. Durable intent must survive sessions, while leases and heartbeats must not pollute the product's history.

## Decision

### D1. Three layers

Each product keeps a stable project goal, a behavioural spec and a task log below them, in its own repository.

### D2. Tasks cite the spec

Every task cites the spec sections it answers to and never contradicts the project goal without escalating.

### D3. The task log is permanent

Tasks are never deleted or renumbered; the log stays in product git.

### D4. Runtime state stays outside git

Leases, sessions, heartbeats, auth status and in-flight questions live in a per-project queue outside product git and are never committed.

### D5. The verifier's packet

The verifier always receives the goal excerpt, the cited spec sections, the task, its checks and the PR.

## Consequences

- History of intent is reviewable and survives any session.
- The queue can be rebuilt or moved without touching the product's history.
