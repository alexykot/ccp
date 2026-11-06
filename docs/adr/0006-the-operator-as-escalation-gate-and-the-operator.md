---
id: ADR-0006
title: "The operator as escalation gate, and the operator gates"
status: accepted
date: "2026-09-15"
deciders: operator
spec_refs: [S3, S17]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
  - "D6 built"
notes: "2026-11-05: status proposed → accepted. 2026-11-06: D6 amended, the pre-rename aliases dropped (task 0025)."
---
# ADR-0006 — The operator as escalation gate, and the operator gates

## Context

A human who relays every message becomes the bottleneck and the bus. The human should be reached only for decisions only they can take, and the gates that need them must be listed, not implied.

## Decision

### D1. Gate, not bus

The operator is an escalation gate, not the message bus.

### D2. A fixed list of gates

Product intent, security, production promotion, destructive operations, legal questions, reauth and new credentials go to the operator.

### D3. Routine steps are not gated

Merges after a verifier approval, reviews and quota pauses need no operator.

### D4. The design seat filters

The design seat decides runner-facing gates and brings one to the operator only when it contradicts a recorded decision, needs the operator's hands, or is production promotion or irreversible without a verified backup.

### D5. Questions are classified

Every implementer question is implementation or spec (spec when unsure); only the design seat decides a question needs the operator.

### D6. One name for the role

The human role is called operator everywhere, in prose, schema values and commands. The pre-rename values are not read (2026-11-06): a product rewrites its old queue data before upgrading.

## Consequences

- The operator sees few, well-formed questions.
- The design seat carries the judgement the operator delegated.
