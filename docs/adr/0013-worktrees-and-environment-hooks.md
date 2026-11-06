---
id: ADR-0013
title: "Worktrees and environment hooks"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S12]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0013 — Worktrees and environment hooks

## Context

Worktree creation and lifecycle are generic, but environment setup (databases, local instances, URLs) is product-specific. The plane needs a generic lifecycle with integration points for the product's part. An adapter interface and a cloud-credential auth template were replaced.

## Decision

### D1. The plane owns worktrees

The plane creates, records and removes every worktree kind: implementer, reviewer, verifier, mutation copy and machine check.

### D2. Environment hooks

Product environments are driven by setup, teardown, up and down hooks, and a urls hook returning a dynamic list of named URLs.

### D3. A configurable merge step

The merge is a configurable step with a squash, head-pinned default.

### D4. Credential probes

Products declare credential probes, run before each claim; a failure refuses the claim and raises a reauth gate.

### D5. Cleanup

Closing a task removes its worktrees and branch; garbage collection prunes the rest.

## Consequences

- Products describe their environment once, as hooks.
- The verifier can browse whatever the product serves.
