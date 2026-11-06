---
id: ADR-0025
title: "Tests are fenced from live state"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S29]
decisions: ["D1 built", "D2 built"]
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0025 — Tests are fenced from live state

## Context

Tests that touch a live queue, a real repository or a hosting service can corrupt real state. The fence must be structural, not a convention.

## Decision

### D1. A structural fence

The test suite refuses to touch a live queue, the real plane repository or the hosting service.

### D2. No leftover branches

After a run, no state branches may exist.

## Consequences

- The suite is safe to run anywhere.
- Code that needs real services is tested against fixtures.
