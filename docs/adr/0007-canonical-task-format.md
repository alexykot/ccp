---
id: ADR-0007
title: "Canonical task format"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S5]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0007 — Canonical task format

## Context

Every tool, brief and check that reads a task depends on its shape. A per-product grammar forces the plane to guess; one documented format lets the plane read and write tasks reliably.

## Decision

### D1. One format

The task file is the plane's format, the same for every product, with a published frontmatter schema.

### D2. Fixed sections

Intent, Context (not checked), Scope, checks, Implementation notes and Verification notes, in that order.

### D3. Fixed names, extensible requirements

Section names, the check grammar and the statuses are fixed; a product may require more keys and sections, never rename them.

### D4. Declared paths

A task may declare the paths it touches; runtime keys are refused in the file.

### D5. Who writes the notes

Implementation notes come from the implementer's output; verification notes are written from the verifier's record at close.

## Consequences

- Tools and briefs read every product's tasks the same way.
- A product with a different habit adapts its tasks.
