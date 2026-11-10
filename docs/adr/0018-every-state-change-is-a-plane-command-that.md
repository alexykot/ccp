---
id: ADR-0018
title: "Every state change is a plane command that records itself; tool proposals and triage"
status: accepted
date: "2026-10-21"
deciders: operator
spec_refs: [S10, S31]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
  - "D6 live"
  - "D7 live"
  - "D8 built — task 0015, as ADR-0034 D11's seven days"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0018 — Every state change is a plane command that records itself; tool proposals and triage

## Context

A duty that exists only in a prompt is lost silently, and private scripts drift and emit nothing. The toolkit must make telemetry unavoidable and give seats a path to ask for tools. Triage by the product's lead was replaced.

## Decision

### D1. State changes are commands

Every step that changes delivery state is a plane command, and the command records its own telemetry.

### D2. Rendered prompts

Worker prompts are rendered by the plane from its templates plus a product fragment.

### D3. No private automation

No seat writes executable automation for a plane step; product helpers live in the product and are called through hooks.

### D4. Tool proposals

A seat that needs a tool proposes it through the plane and records each manual repeat.

### D5. Triage by the plane session

The session that develops the plane triages proposals and records the decision; the product's lead is told, never asked to record.

### D6. Rules over denies

Enforcement is a written rule plus checks and warnings, not a settings deny.

### D7. Queue commands for the lead

The lead's task ordering, holds, releases and drops are queue commands, not prose.

### D8. Stale proposals flagged

A proposal untriaged for a set period is flagged.

## Consequences

- Telemetry cannot be skipped by a seat that forgets.
- Missing tools surface as proposals instead of private scripts.
