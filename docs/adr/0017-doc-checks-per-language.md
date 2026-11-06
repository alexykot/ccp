---
id: ADR-0017
title: "Doc checks per language"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S21]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0017 — Doc checks per language

## Context

Documentation standards differ by language; a check hard-coded for one language cannot serve others. A neutral core with pluggable packs keeps the plane generic.

## Decision

### D1. A neutral core

Package docs must exist, carry a title, stay within a size ratio and avoid plan headings.

### D2. Language packs

Language packs are chosen by config, one shipped first; none runs the core alone.

### D3. Product commands

Product commands run as doc checks, reported by id.

### D4. Opt-in rules

Citation resolution, no delivery ids in code, a history attribute and non-overlapping checks are opt-in.

### D5. Dry-run records

A check whose steps run a command may be required to record a dry run, off by default.

## Consequences

- Other languages arrive as packs, not core changes.
