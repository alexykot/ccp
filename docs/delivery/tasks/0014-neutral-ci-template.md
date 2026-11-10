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
- The lead's standing ruling for R1: this task carries out the operator ruling in
  `docs/spec/RULINGS.md` (the §27.1 row names it), so the PR also removes or rewords, without asking,
  every SPEC or docs passage the change makes false, such as a transitional "task 0014" marker. Each
  edit is listed with its old text in the PR body's "Operator approval (SPEC §31)" section, citing
  that row. History records (ADRs, done tasks, RULINGS, the spec map's history columns) stay as
  written.

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

- 2026-11-09, implementer: `templates/github/workflows/formal-unit-lint.yml` now has no `services`
  block and no `DATABASE_URL`. Its job `env` sets `STORE_TEST_PATTERN: ""` and
  `EXPECT_STORE_TESTS: "0"`, and its header comment says how a product with store tests opts in
  (§15.7). The store step no longer falls back to a built-in pattern. With an empty pattern it checks
  nothing and passes, and it fails when `EXPECT_STORE_TESTS=1` comes with an empty pattern. With a
  pattern set, the skip and no-match failures are unchanged. No test read the template before this,
  so the new `tests/test_ci_template.py` reads the job's keys and env and runs the step's embedded
  Python against sample `unit.out` files.

- 2026-11-10, implementer: an empty `STORE_TEST_PATTERN` with `EXPECT_STORE_TESTS=1` fails the
  store step (exit 1), and with the defaults (empty pattern, `0`) it passes (exit 0); the runner
  confirmed this as the narrowest rule consistent with §15.7. §15.7's last sentence, the
  parenthetical saying the template still carries a database default, is deleted under the standing
  ruling above. ADR-0034 D12 is recorded as built (`ccp adr decide 34 D12 built`).

## Verification notes

*Append-only.*
