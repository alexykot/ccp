---
id: ADR-0003
title: "One home per fact: knowledge in git, live state in the store"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S1, S4, S23]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 not_built"
  - "D5 not_built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0003 — One home per fact: knowledge in git, live state in the store

## Context

When the same fact is written in two places, the copies diverge and nobody knows which wins. Knowledge and outcomes need review and history; operational state needs fast, frequent writes, so they belong in different homes. Task files used to carry in-flight statuses; older files that still do are read as pending.

## Decision

### D1. Knowledge and outcomes in git

Task intent, terminal status, verification notes, ADRs and their decision states live in git.

### D2. Live state in the store

Who works on what, and in which phase, lives in the plane's store, never in task files.

### D3. Task files carry no in-flight status

A task file's status is only pending, done or dropped.

### D4. The store indexes git read-only

The store holds a rebuildable, read-only projection of the knowledge in git.

### D5. The task index leaves git

The generated task index stops being committed once the store serves it.

## Consequences

- Nothing needs keeping in sync by hand; each fact has one writer.
- Browsing intent and outcomes still works with ordinary git tools.
- Live status is read through the plane, not from files.
