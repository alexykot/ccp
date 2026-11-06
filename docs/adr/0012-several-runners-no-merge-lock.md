---
id: ADR-0012
title: "Several runners, no merge lock"
status: accepted
date: "2026-10-28"
deciders: operator
spec_refs: [S16]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 built"
  - "D6 built"
  - "D7 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0012 — Several runners, no merge lock

## Context

One-at-a-time delivery makes wall time the sum of task times, though unrelated tasks need not wait. Parallel work must spend the same tokens sooner, not more, and its correctness must not rest on agents' declarations. An earlier design with one runner holding several tasks was replaced.

## Decision

### D1. Opt-in parallelism

Parallel work is opt-in per product with a ceiling on tasks in flight; off is the single-runner behaviour.

### D2. Several runner teammates

The lead spawns several runners, each holding one task with its own worktree and workers.

### D3. Correctness from the tip

A task merges only from a head that contains the current tip, verified there; declared paths never carry correctness.

### D4. No merge lock

Git resolves concurrent merges; the later one fails and is fixed by its implementer.

### D5. Paths decide co-scheduling

Declared paths and a short list of exclusive paths decide only which tasks start together.

### D6. Exclusive test lanes

Exclusive test lanes sit behind a lock that answers at once when held.

### D7. Session headroom

A second task needs headroom in the session usage window (today the five-hour window); with no session window reported, the rule passes.

## Consequences

- Wall time drops for independent work.
- Occasional failed merges are fixed by the implementer rather than prevented.
