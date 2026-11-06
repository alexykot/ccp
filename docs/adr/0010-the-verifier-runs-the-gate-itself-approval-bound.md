---
id: ADR-0010
title: "The verifier runs the gate itself; approval bound to the head; merge pinned"
status: accepted
date: "2026-09-15"
deciders: operator
spec_refs: [S15]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
  - "D6 live"
  - "D7 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0010 — The verifier runs the gate itself; approval bound to the head; merge pinned

## Context

A gate result that nobody re-ran, or an approval that applies to a different commit, proves nothing. Merges must be traceable to a verdict on exactly the commit merged.

## Decision

### D1. The runner merges after approval

The runner merges, through the plane's close command, only after a verifier approval; integration merges need no operator approval.

### D2. The gate is the verifier's own run

The formal gate is the verifier's own run of the product's tests and the plane's checks at the PR head; a result it did not run is not a pass.

### D3. No CI required

The gate needs no continuous-integration service.

### D4. Approval at the head

Merge only on a committed approval at the head; a push after the verdict needs a new verdict, and a relayed or post-merge verdict is not an approval.

### D5. The merge is pinned

The merge is pinned to the approved head.

### D6. Every PR is verified

A PR that belongs to no task, docs-only included, needs its own verification record.

### D7. A settled head

Review starts on a settled head; a commit during review makes it stale and verify refuses it.

## Consequences

- Every merge on the integration branch traces to a verdict on its exact commit.
- A late push costs a new verify round.
