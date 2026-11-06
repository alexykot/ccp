---
id: ADR-0029
title: "Pluggable merge strategy"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S15]
decisions:
  - "D1 not_built"
  - "D2 not_built"
  - "D3 not_built"
  - "D4 not_built"
  - "D5 not_built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0029 — Pluggable merge strategy

## Context

How a PR reaches the integration branch varies by project. Today the merge is a configurable step whose default squashes a task PR pinned to its approved head (ADR-0013 D3), and closing a task deletes its branch and worktrees (ADR-0013 D5). What is missing is a strategy the plane owns end to end, including PRs no task opened and the hosting service's own settings.

## Decision

### D1. A strategy interface

Merge handling is a pluggable strategy owned by the plane; a product names its strategy in config.

### D2. Squash onto the tip, as a named strategy

The shipped strategy squashes each PR onto the integration tip as one commit, with linear history on the integration branch enforced through the repository's settings.

### D3. Repository settings from the plane

`cpl repo check` and `cpl repo apply` read and set the hosting service's merge settings (allowed merge methods, delete-branch-on-merge, linear history), reporting any setting its API cannot change.

### D4. Every merged branch is deleted

Every merged PR's branch is deleted locally, remotely and in worktrees, whatever opened the PR.

### D5. Strategy-specific branch rules

Any other strategy needs its own rule for bringing the tip into a branch.

## Consequences

- Products with other merge habits get their own strategy without plane changes.
- The existing squash default and close-time cleanup become the first strategy's behaviour rather than special cases.
