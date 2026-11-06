---
id: ADR-0026
title: "Headless children strip API keys; prepaid login only"
status: accepted
date: "2026-09-17"
deciders: operator
spec_refs: [S30]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0026 — Headless children strip API keys; prepaid login only

## Context

Agent development and a product's runtime must draw from different wallets, and an ambient key silently moves agent spend onto the wrong one.

## Decision

### D1. Prepaid login for development

Development runs on the prepaid subscription login only; API credits pay only for a product's runtime calls.

### D2. Keys stripped

Every headless child process strips the known API key and token variables before launch.

### D3. No ambient product keys

Product API keys live only in process configuration the product loads, never in an ambient environment.

### D4. Ambient keys found by probes

A product declares a credential probe that detects forbidden ambient keys; the plane runs it before each claim, records its result and refuses the claim when it fails.

## Consequences

- Agent spend cannot leak onto a product's API bill.
