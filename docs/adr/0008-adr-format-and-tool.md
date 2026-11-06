---
id: ADR-0008
title: "ADR format and tool"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S6]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 built"
  - "D6 built"
  - "D7 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0008 — ADR format and tool

## Context

Free-text notes on what is in force cannot be checked and rot. Design decisions need one marker, a recorded build state per decision and links verified both ways.

## Decision

### D1. The plane's format

ADRs are wholly the plane's format and tool, the same for every product.

### D2. One decision marker

Decisions are headings `### D<n>. Title`; other styles are read, warned about and migratable.

### D3. A build state per decision

Each decision records not_built, built, live or retired.

### D4. Checked links

Supersession and amendment links may target a whole ADR or one decision; each must resolve, and the reverse link is checked.

### D5. Configurable lifecycle

Statuses and allowed transitions are configurable vocabulary with defaults.

### D6. An in-force check

A done task citing a decision still recorded not_built is flagged.

### D7. The old importer is retired

A one-off importer of an older header format is removed.

## Consequences

- Whether a decision is built is a fact the plane can check, not a sentence.
- Products migrate their existing ADRs once.
