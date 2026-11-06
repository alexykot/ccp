---
id: ADR-0011
title: "Merge rules: merge the tip in, re-verify by patch id"
status: accepted
date: "2026-10-31"
deciders: operator
spec_refs: [S15, S16]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 built"
  - "D6 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0011 — Merge rules: merge the tip in, re-verify by patch id

## Context

A branch must contain the current integration tip before it merges, but rebasing needs a force-push that sandboxed agents cannot do. Re-reviewing an unchanged change after a tip merge costs effort without adding assurance. An earlier rule to rebase onto the tip was replaced.

## Decision

### D1. Merge the tip in

A task branch takes the integration branch by merging it in, never by rebasing; this is safe because PRs squash-merge.

### D2. Review judges the PR's own change

A head that moved only by an integration merge, with the same patch id, needs no new review.

### D3. The verdict is still at the head

The verifier reruns the gate at the new head and records each check not rerun as resting on the prior approval.

### D4. Real changes are re-verified

A merge with a conflict, or one whose own change moved, is reviewed and verified in full.

### D5. Leftovers are recorded

A minor finding that could cost a later cycle is fixed before the merge (amended by ADR-0034 D4). Minor findings not fixed before merge, and the reason for any repeated verify round, go in the verifier's record.

### D6. One route for code

Code from outside the runner reaches the integration branch through the task log.

## Consequences

- Branches stay mergeable without force-pushes.
- The rule depends on the squash merge strategy (ADR-0029).
