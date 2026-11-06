---
id: ADR-0001
title: "Project-agnostic plane; products bind by config and hooks"
status: accepted
date: "2026-09-15"
deciders: operator
spec_refs: [S1, S4, S8, S12]
decisions:
  - "D1 live"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0001 — Project-agnostic plane; products bind by config and hooks

## Context

A delivery plane that grows around its first product absorbs that product's conventions and becomes unusable for any other. The boundary between what the plane owns and what a project supplies has to be explicit and enforced, not left to prose. An earlier per-product adapter interface was replaced by configuration, hooks and a merge step.

## Decision

### D1. Products bind through config and hooks

The plane is project-agnostic; a product binds to it only through its own configuration file and hooks.

### D2. The plane owns the mechanisms

The plane owns formats, lifecycles and mechanisms; a project supplies content, conventions (configuration) and environment (hooks).

### D3. No parsing of product text

The plane never parses product prose or tool output: a product declares a fact in configuration or reports it as JSON.

### D4. Product actions are hooks

An action the plane needs from a product is a hook with a defined context, timeout and failure behaviour, never an instruction in prompt prose.

### D5. Canonical formats

Plane formats are canonical and documented; projects adapt to them, not the other way round.

## Consequences

- Adding a product means writing configuration and hooks, not changing plane code.
- Product-specific defaults in plane code are defects to remove.
- Some convenience is lost where a product would have liked the plane to read its own conventions.
