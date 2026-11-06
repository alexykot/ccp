---
task_id: 0001-hello-delivery-log
title: EXAMPLE — the durable log holds intent and walkable checks
status: pending
depends_on: []
spec_refs: ["docs/SPEC.md#overview"]
created: 2026-09-15
updated: 2026-09-30
---

# Task: 0001-hello-delivery-log

> **Example only** — not a product task. Shows frontmatter `depends_on` and a walkable `dod_checks`.

## Intent

Show that the durable log holds intent and verifier-walkable checks while runtime leases live under `.delivery-queue/`.

## Context (not checked)

EXAMPLE: any product policy that shapes implementation but is not a walkthrough belongs here.

## Scope

- **In:** EXAMPLE layout demonstration
- **Out:** real product behaviour

## dod_checks

- id: `other-01`
  story: As the lead, I open this EXAMPLE task so I can copy its shape.
  setup: Product or plane checkout with this file present.
  steps:
    1. Run `ccp tasks check` in the product.
  expect: It prints `tasks: clean`.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
