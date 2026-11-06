---
id: ADR-0033
title: "SPEC layout: parts in docs/spec, renumbered, design notes apart"
status: accepted
date: "2026-11-06"
deciders: operator
spec_refs: [S31]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
notes: "2026-11-06: status proposed → accepted"
---
# ADR-0033 — SPEC layout: parts in docs/spec, renumbered, design notes apart

## Context

The SPEC grew in the order the plane was built: one long file whose sections follow build order, with implementation notes, spikes, acceptance walk-throughs, amendment layers and history mixed in with the rules. A reader can't tell a rule from its back-story, and every change edits the one file every other change touches.

## Decision

### D1. Parts in docs/spec, with SPEC.md an index

The SPEC is five parts, one file each in `docs/spec/` (model, delivery, quality, observability and spend, operations). `SPEC.md` at the repo root is a short index of the parts.

### D2. Renumbered by topic, with a published map

Sections are numbered continuously across the parts by topic (§1–§N, subsections §N.M). `docs/spec/MAP.md` maps every old section to its new place, and references in code, contracts, briefs and records are rewritten from it.

### D3. Normative rules only

The SPEC states rules. Implementation notes, spikes and acceptance walk-throughs move to `docs/design/`; the command reference moves to `docs/cli.md`; history and incident narratives are dropped. An amendment is folded into the rule it amends.

### D4. Meaning changes go to the operator

The restructure keeps every rule's meaning. A rule found obsolete or contradictory on the way is not changed silently: it is listed for the operator's ruling.

## Consequences

- Each part can be rewritten on its own, in parallel.
- Every reference to a section number changes once, mechanically, when the switch lands; products that cite plane sections update theirs from the map.
- The SPEC gets shorter and reads as rules; the reasons live in the ADRs and `docs/design/`.

<!-- spec-refs: historical -->
