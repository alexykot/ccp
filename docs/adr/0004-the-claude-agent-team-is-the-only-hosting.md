---
id: ADR-0004
title: "The Claude agent team is the only hosting"
status: accepted
date: "2026-09-30"
deciders: operator
spec_refs: [S2, S9, S18]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 built"
  - "D5 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0004 — The Claude agent team is the only hosting

## Context

Seats that must exist at the same time cannot share one interactive context without merging ruling and execution. An agent-team runtime gives each long-lived seat its own session and a mailbox, and one hosting is simpler to reason about than several. An original hosting on an external bot platform, with cron routines, a watchdog seat and email escalation, and a later switchable-hosting design were both removed.

## Decision

### D1. An agent team

The plane runs as a Claude Code agent team: the lead is the design seat, a runner is a teammate, workers are the runner's subagents.

### D2. Mailbox for talk, queue for record

Seats talk through the team mailbox; queue files remain the record.

### D3. Liveness from the team

Idle and failure notices and an idle hook give liveness; there is no watchdog seat.

### D4. No hosting switch

There is no hosting key and no switch; a leftover binding line is ignored.

### D5. No email

Nothing sends email; whatever needs the operator is raised in the lead's session.

## Consequences

- One runtime, one set of briefs and hooks to maintain.
- A runtime the CLI cannot drive cannot host seats.
