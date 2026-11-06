---
id: ADR-0019
title: "Telemetry carries numbers and ids only"
status: accepted
date: "2026-10-21"
deciders: operator
spec_refs: [S24]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 built"
  - "D6 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0019 — Telemetry carries numbers and ids only

## Context

Usage data is needed to see where time and tokens go, but prompts, responses and file content are sensitive. The collector must be useful without ever holding content.

## Decision

### D1. Figures from the harness

Token, model and effort figures come from the harness's OpenTelemetry export, never from an agent's account of itself.

### D2. A whitelist

The receiver stores a whitelist of numeric fields and ids; no content is stored.

### D3. Content logging stays off

Prompt and tool-detail logging stay off, and the status command warns when either is set. ADR-0034 D8 amends this: the plane's own prompt audit is to keep the full prompt text only when a product opts in, off by default; that is decided but not yet built (task 0013).

### D4. Routed per project

Telemetry is enabled at user level and routed per project by a resource label, then by session directory, else to a system sink; nothing is dropped.

### D5. Local opt-out

A project may switch exporting off locally.

### D6. Local and JSON only

The receiver binds to localhost and accepts only JSON content.

## Consequences

- Usage is visible without any sensitive content leaving the session.
- Analyses limited to numbers cannot explain why a session behaved as it did.
