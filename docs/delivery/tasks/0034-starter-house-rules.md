---
task_id: 0034-starter-house-rules
title: The plane ships an optional starter set of house rules
status: pending
kind: feature
depends_on: [0033-package-doc-convention-owned-by-the-plane]
spec_refs: ["S20"]
review_point: R3
paths: ["docs/", "templates/", "ccp/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0034-starter-house-rules

## Intent

The plane ships a starter set of generic house rules a product may adopt or decline, each with the check that enforces it: one owner for every count or list (docs name the owner); tests check behaviour, never quoted text; current-only docs, with history marked by a git attribute and excluded from absence checks; package docs are maps (task 0033); one home per fact; every reference resolves; deterministic tests (clock, HEAD, load).

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §20.
- These rules are about how agent-maintained code and docs stay correct, not about any product's domain; every product rediscovers them through architect findings.

## Scope

- **In:** a template house-rules file listing each rule, its purpose and its check; `ccp init` (or the template) offers it; where a check is mechanical, it exists in `ccp docs check` or as a documented docs.checks entry; §20 says how a product adopts, declines or overrides a starter rule.
- **Out:** making any rule mandatory.

## dod_checks

- id: `check-01`
  story: As a new product, I can adopt the starter rules.
  setup: a scratch product created from the template.
  steps:
    1. Open the house-rules template.
  expect: each rule names its check, and each named check exists and runs.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, declining a rule is recorded.
  setup: a product that declines one starter rule.
  steps:
    1. Run `ccp docs check`.
  expect: the declined rule's check does not run; the others do.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
