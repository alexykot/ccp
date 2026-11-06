---
id: ADR-0028
title: "Hosted multi-user store and dashboard"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S23, S28]
decisions: ["D1 not_built", "D2 not_built", "D3 not_built"]
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0028 — Hosted multi-user store and dashboard

## Context

Files in git and a local page are makeshift for live state. Project management and the dashboard need a shared, online backend that serves more than one user and project.

## Decision

### D1. A store interface

A store interface over the current file-backed queue.

### D2. A hosted backend

A hosted, multi-user, multi-project backend for live state that also serves the dashboard.

### D3. Bindings in the store

Local bindings move into the store.

## Consequences

- Several people and projects can share one plane.
- Hooks need a local outbox so an outage never stalls a runner.
