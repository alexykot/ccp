---
id: ADR-0030
title: "Normative-rule approval as review approval once public"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S31]
amends: ["ADR-0024 D3"]
decisions: ["D1 not_built", "D2 not_built", "D3 not_built"]
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0030 — Normative-rule approval as review approval once public

## Context

Quoting the operator's words in public PR bodies would leak private reasoning, and outside contributors cannot produce such a quote. Approval must stay recorded without it.

## Decision

### D1. Review approval

A normative rule change is approved by the operator's review approval on the PR.

### D2. The body states the change

The PR body states each change and the text it replaces.

### D3. Private reasoning stays private

Private reasoning is kept out of public PRs.

## Consequences

- The approval trail stays public without exposing private context.
