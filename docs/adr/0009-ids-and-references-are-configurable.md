---
id: ADR-0009
title: "Ids and references are configurable"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S7]
decisions: ["D1 built", "D2 built", "D3 built"]
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0009 — Ids and references are configurable

## Context

Scattered regular expressions for ids drift apart and hard-code one product's conventions. One resolver with configurable patterns keeps parsing consistent and portable.

## Decision

### D1. One resolver

One resolver parses every id and reference the plane reads in a product's docs.

### D2. Configurable patterns

Patterns for tasks, ADRs, spec sections, house rules and review points come from an optional config block; absent keys keep the defaults.

### D3. Shared by every reader

The estimator, doc checks and ADR lookup read ids through the same resolver.

## Consequences

- A product with other id conventions configures them once.
- Every reader agrees on what an id is.
