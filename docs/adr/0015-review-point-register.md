---
id: ADR-0015
title: "Review-point register"
status: accepted
date: "2026-10-22"
deciders: operator
spec_refs: [S22]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0015 — Review-point register

## Context

The operator reviews progress at functional milestones, not task by task. Those milestones need stable ids, names and goals, and scope must be attached when planning, not guessed afterwards.

## Decision

### D1. Review points

A review point is a batch of tasks and ADRs the runner works through and stops at for operator review.

### D2. A register

Each product that uses them keeps a register: strict id, short name, goal, status, at most one current.

### D3. Names come from people

Names are written by the task-log owner with the operator; no tool or seat invents one.

### D4. Attached at planning

Tasks and ADRs are attached at planning time; close stamps the runner's point only as a fallback.

### D5. Scope from a point

A runner's scope may be taken from the tasks tagged to a point.

## Consequences

- The operator reviews meaningful increments.
- Planning carries the extra step of tagging work to a point.
