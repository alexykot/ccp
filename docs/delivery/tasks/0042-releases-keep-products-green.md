---
task_id: 0042-releases-keep-products-green
title: A plane release keeps conforming products green
status: pending
kind: feature
depends_on: []
spec_refs: ["S29"]
review_point: R3
paths: ["scripts/", "ccp/", "docs/spec/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0042-releases-keep-products-green

## Intent

When a plane release is installed, `ccp` checks each bound product's integration branch against the new rules and tells the lead what is now stale. A plane change that would make a conforming product fail ships its own fix-up (a migrate or regenerate command) and says so in the release notes.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §29.
- A release that renames a generator or tightens a check turns a product's integration branch red with no product commit; the first to notice is a verifier mid-task.

## Scope

- **In:** `sync-product-docs.sh` (or `run-checkout.sh update`) runs `ccp docs check`, `ccp adr check` and `ccp tasks check` per bound product read-only and prints what fails; §29 adds the rule that a breaking plane change ships a migrate command; the PR template asks whether the change breaks conforming products.
- **Out:** fixing a product's repo from the plane.

## dod_checks

- id: `check-01`
  story: As a lead, a release tells me what went stale.
  setup: a scratch product that passes the old checks and fails a tightened one.
  steps:
    1. Run the install step.
  expect: it names the product and the failing check, and writes nothing to the product.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, a green product stays quiet.
  setup: a conforming product.
  steps:
    1. Run the install step.
  expect: it reports the product as clean.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
