---
id: ADR-0023
title: "The plugin delivers seats and hooks; products run main"
status: accepted
date: "2026-10-21"
deciders: operator
spec_refs: [S9, S29]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
  - "D6 live"
  - "D7 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0023 — The plugin delivers seats and hooks; products run main

## Context

Managed copies inside each product drift and need a commit at every plane change. The plane's footprint in a product should be minimal and static. Synced copies of briefs and protocols, and vendoring the CLI into products, were replaced.

## Decision

### D1. One plugin

One plugin carries the plane's agents, skills and hooks, including a role-neutral orientation at session start.

### D2. A static anchor

A product's anchor is two settings entries naming the plugin, not a version.

### D3. The CLI on PATH

The CLI runs from a clean run checkout; prompts and docs name the command, not a path.

### D4. Products run main

Products run main from a checkout that only fast-forwards, never from a development checkout.

### D5. A frozen index format

The generated task index's format is frozen; new fields go to the board.

### D6. One-line pointers

Product docs point at the plane in one line and restate none of it.

### D7. Local bindings

Per-installation bindings are local configuration outside version control until the store holds them.

## Consequences

- A plane change reaches products at their next session start without product commits.
- Products always run the latest released plane.
