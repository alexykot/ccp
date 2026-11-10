---
id: ADR-0037
title: "The plane names when the operator is notified; the product names the channel"
status: accepted
date: "2026-11-10"
deciders: operator
spec_refs: [S3, S17]
amends: ["ADR-0034 D13"]
notes: |-
  Proposed with task 0040; the operator's approval of that task's PR, its merge gate (SPEC §31), accepts it.
  2026-11-10: status proposed → accepted: the operator's approval of task 0040's PR at its merge gate (SPEC §31)
supersedes: ["ADR-0004 D5"]
decisions: ["D1 built", "D2 built"]
---
# ADR-0037 — The plane names when the operator is notified; the product names the channel

## Context

ADR-0004 D5 said nothing sends email, and ADR-0034 D13 repeated it for credit problems: whatever
needs the operator is raised in the lead's session. Every operator needs to hear about blockers and
decisions, but how depends on the operator's setup, not the plane, so a product that wanted another
channel had to override a plane rule. The plane triaged a proposal to this effect from a managed
product's tool proposals: the plane defines when the operator is notified, and a product setting
names the channel. Task 0040 builds it; the operator's approval of task 0040's merge gate is the
decision.

## Decision

### D1. The plane names the triggers

The plane names when the operator must hear (SPEC §3.6): a blocker only the operator clears, a
decision the operator must take, a review point done and the allowance checkpoint. Every other wait
is not a trigger.

### D2. The product names the channel

A product's `notify.command` (plane.json, §8.1) is the channel. With none, the lead's session is the
only route, as before. With one, `ccp` runs it on each trigger, besides the lead's session, with the
trigger and ids only, never a brief, a question's text or file content. The plane ships no email or
chat client, and no seat sends email itself.

## Consequences

- ADR-0004 D5 (nothing sends email) is superseded by D2.
- ADR-0034 D13 still holds that credit misuse and low API credit reach the lead as a gate; its
  "nothing emails" now reads as D2: the plane sends nothing itself, and a gate that needs the operator
  reaches the product's channel only on a §3.6 trigger.
- A product's channel command can lose a notice (a failure or timeout is a warning on the step); the
  lead's session still carries every trigger.
