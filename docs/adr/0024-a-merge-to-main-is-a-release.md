---
id: ADR-0024
title: "A merge to main is a release"
status: accepted
date: "2026-10-20"
deciders: operator
spec_refs: [S29, S31]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0024 — A merge to main is a release

## Context

A stable branch needs its own promotion criteria, and the pull request already is the gate. Because a merge can land while a task is in flight, formats must stay compatible.

## Decision

### D1. No stable branch

Merged is released.

### D2. The PR is the gate

The suite green, an independent review, and operator approval for any normative rule change.

### D3. Rule changes name what they replace

A change to a normative rule reaches main only as a PR naming the decision and, for each changed rule, the text it replaces.

### D4. Compatible formats

Runtime formats and the config schema only gain optional fields; anything more carries a schema version still read by new code.

### D5. Contract changes are announced

A change to the runner's contract says so in its PR.

## Consequences

- Releases are frequent and small.
- Every format change needs a compatibility path.
