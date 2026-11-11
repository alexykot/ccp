---
id: ADR-0039
title: "Only the lead sends a plane-rendered notice over a configured channel"
status: accepted
date: "2026-11-11"
deciders: operator
spec_refs: [S3, S8, S17]
amends: ["ADR-0037 D2"]
notes: |-
  Proposed with task 0068; the operator's approval of that task's PR, its merge gate (SPEC §31), accepts it.
  2026-11-11: status proposed → accepted: the operator's approval of task 0068's PR at its merge gate (SPEC §31)
decisions: ["D1 built", "D2 built"]
---
# ADR-0039 — Only the lead sends a plane-rendered notice over a configured channel

## Context

ADR-0037 D2 made the product's `notify.command`, a shell command `ccp` runs, the only channel besides
the lead's session, and said no seat sends email itself. A channel that exists only as a tool in a
Claude session (an MCP mail or chat server) cannot be called from a shell, so a product with one
could not use `notify.command`, and its lead had to override the plane to reach the operator. The
rule that the design seat never emails dates from when it only ruled spec questions; the lead now
leads delivery and is the operator's only route. The operator agreed the shape on a managed product's
proposal: the plane owns the trigger, the content and the record; the lead dispatches; the channel is
configuration. The four triggers and how often they repeat stay as they are, and the lead may still
send on its own judgment when something unexpected shows up. Task 0068 builds it.

## Decision

### D1. The plane renders and records every notice

When a SPEC §3.6 trigger fires, `ccp` records a pending notice in the ledger and prints it with the
channel to use. `ccp notify render` gives the one form every notice takes: a subject and a body of
ids and a short reason, never a brief, a question's text or file content. Every send is recorded
(`ccp notify sent`), and `ccp notify pending` lists what fired and was not yet sent.

### D2. Only the lead sends, over a configured channel

Of the seats, only the lead sends a notice: the plane-rendered one, over the channel plane.json
`notify` configures. `notify.command` stays the unattended channel `ccp` runs and records itself; a
`notify.lead` tool (`tool`, `to`) is one the lead sends with from its own session; with neither, the
lead's session is the route. The lead may also send on its own judgment, as trigger `other` with a
one-line note. The runner and the workers never send. The plane still ships no email or chat client.

## Consequences

- ADR-0037 D2 reads with this amendment: the product names the channel, and the lead, not only
  `ccp`'s command, may send over it.
- A notice the command failed to send stays pending for the lead, so a failure no longer leaves the
  lead's session as the only trace.
- A product with a session-only tool needs no override of the plane to reach the operator.
- Repeated sends are unchanged: each firing is recorded, and one send clears the notice.
