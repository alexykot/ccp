---
task_id: 0048-delivery-id-check-false-hits
title: The default-on delivery-id check matches only the ids the plane writes
status: pending
kind: bug
depends_on: [0033-package-doc-convention-owned-by-the-plane]
spec_refs: ["S21"]
review_point: R3
paths: ["ccp/", "docs/spec/03-quality.md", "tests/"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0048-delivery-id-check-false-hits

## Intent

`ccp docs check` flags a delivery id in package docs and comments only when the text is an id the
plane writes, so the check that is now on by default (§21.3) does not fail a product's docs on ordinary
numbers, file modes, migration file names or years.

## Context (not checked)

- Task 0033 turned the delivery-id check on by default wherever `package_docs` is set. Its reviewer
  found false hits: `chmod 0644`, `0001-init.sql`, `task 2026`, `plan 2026-q3-review`, and with
  `rules.no_ids` also `0042.`. The only escape, `package_docs.no_delivery_ids: false`, also drops the
  real ids, so the first `ccp docs check` after upgrading can fail on a product's docs.
- Comments are read only for files under `docstring_globs`; a product without them gets no comment
  check (reviewer MINOR on 0033).

## Scope

- **In:** narrow the pattern to the forms the plane writes: a task id `NNNN-kebab-slug` naming a task
  that exists in the task log, a finding or ruling id in the plane's own formats (`sm-…`, `pp-…`,
  `rv-…`/`da-…` style ids) and explicit references such as `task NNNN` or `Task: NNNN` where NNNN is
  a known task. A bare number, a file name with an extension, a year or a date does not match. Keep
  `no_delivery_ids: false` as the off switch. §21.3 states which forms match and that comments are read
  under `docstring_globs` only (or falls back to the language pack's source files, the simpler of the
  two, stated either way).
- **Out:** other doc rules.

## dod_checks

- id: `check-01`
  story: As a product upgrading the plane, ordinary numbers in my package docs do not fail the check.
  setup: a scratch product with `package_docs` set and a package doc holding `chmod 0644`,
    `0001-init.sql`, `task 2026`, `plan 2026-q3-review` and `0042.` (with `rules.no_ids` on).
  steps:
    1. Run `ccp docs check`.
  expect: no delivery-id finding for any of them.
  dry run: on the merge base the same doc fails with delivery-id findings.
- id: `check-02`
  story: As a plane maintainer, real ids are still caught.
  setup: the same product with a task `0007-add-login` in its task log and a package doc naming
    `0007-add-login`, `task 0007` and a spec question id `sm-20261110T000000Z-abcd`.
  steps:
    1. Run `ccp docs check`.
  expect: each is flagged.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
