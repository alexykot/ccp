---
task_id: 0074-adr-review-points-and-package-doc-defaults
title: Docs checks warn on untracked ADR review points and state package-doc defaults
status: pending
kind: feature
depends_on: []
spec_refs: ["S6", "S21", "S22"]
review_point: R5
paths: ["ccp/adr.py", "ccp/pkgdocs.py", "ccp/config.py", "docs/spec/03-quality.md", "contracts/plane_config.schema.json", "tests/test_adr*.py", "tests/test_pkgdocs*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0074-adr-review-points-and-package-doc-defaults

## Intent

A product adopting with ADRs already tagged with review points is told it has no register, as tasks already are (§22.3), and a product configuring package docs can see the defaults it replaces, with document-only directories exempt by default (§21).

## Context (not checked)

- Accepted plane proposals from an adoption trial.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** `ccp adr check` warns, naming the ADRs, when ADRs carry `review_points` and the product has no review-point register; §21 states what `package_docs.exempt_dirs` and `source_suffixes` default to and that a list replaces both the core's and the language pack's; a directory holding only `.md` files needs no package doc unless the product lists it.
- **Out:** changing the language packs' own defaults.

## dod_checks

- id: `check-01`
  story: As a lead, untracked ADR review points are flagged.
  setup: a scratch product with one ADR carrying `review_points: [R1]` and no register.
  steps:
    1. Run `ccp adr check`.
  expect: it warns, naming the ADR and the missing register.
  dry run: on the merge base it says nothing.
- id: `check-02`
  story: As a product, a docs-only directory needs no package doc.
  setup: a scratch product with `package_docs` set and a `notes/` directory of `.md` files only.
  steps:
    1. Run `ccp docs check`.
  expect: no package-doc finding for `notes/`; a directory with code still needs one.
  dry run: on the merge base `notes/` is reported.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
