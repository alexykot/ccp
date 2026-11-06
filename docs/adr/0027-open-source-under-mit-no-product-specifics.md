---
id: ADR-0027
title: "Open source under MIT; no product specifics"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S1, S31]
decisions:
  - "D1 built — LICENSE added at the root; copyright names the operator"
  - "D2 not_built"
  - "D3 not_built"
  - "D4 built"
  - "D5 not_built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0027 — Open source under MIT; no product specifics

## Context

The plane is reusable only if it carries nothing of the products it was developed against. Renaming is not enough: domain, stack, spend and scale leak through the text.

## Decision

### D1. MIT licence

The plane is published under the MIT licence.

### D2. A fresh public history

The public repository starts from a squashed history; the private history is not published.

### D3. Product rulings leave the spec

Each product ruling becomes a generic rule, a knob with a neutral default, or nothing.

### D4. A leak check

A leak check against an untracked denylist runs before publishing.

### D5. A normative spec

The SPEC holds normative rules only; implementation notes and history move out.

## Consequences

- Anyone can adopt the plane without inheriting another product's conventions.
- Publishing waits on the spec restructure and the scrub.
