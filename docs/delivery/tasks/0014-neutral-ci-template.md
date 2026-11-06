---
task_id: 0014-neutral-ci-template
title: Neutral defaults in the CI template
status: pending
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S15"]
adr_refs: ["0034 D12"]
review_point: R1
paths: ["templates/github/workflows/formal-unit-lint.yml", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0014-neutral-ci-template

## Intent

The optional CI template ships no database service, an empty `STORE_TEST_PATTERN` and `EXPECT_STORE_TESTS=0`; a product with store tests adds its own service and settings.

## Context (not checked)

- §15.7 states the target rule; ADR-0034 D12 records it.

## Scope

- **In:** the template and any test that reads it.
- **Out:** products' own workflow copies.

## dod_checks

- id: `tmpl-01`
  story: As a product adopting the template, nothing product-shaped comes with it.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n -E 'services:|pgvector|STORE_TEST_PATTERN|EXPECT_STORE_TESTS' templates/github/workflows/formal-unit-lint.yml`.
  expect: no service block; the pattern empty; `EXPECT_STORE_TESTS` `0`.
  dry run (`216cda1`): a database service and a store pattern are present.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
