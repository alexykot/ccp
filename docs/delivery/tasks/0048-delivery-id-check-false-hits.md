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

`ccp docs check` flags a task id in package docs and comments only when it names a task that exists in
the product's task log, so the delivery-id check that is now on by default (§21.3) does not fail a
product's docs on ordinary numbers, file modes, migration file names or years.

## Context (not checked)

- Task 0033 turned the delivery-id check on by default wherever `package_docs` is set. Its reviewer
  found false hits: `chmod 0644`, `0001-init.sql`, `task 2026`, `plan 2026-q3-review`. The only
  escape, `package_docs.no_delivery_ids: false`, also drops the real ids, so the first `ccp docs check`
  after upgrading can fail on a product's docs.
- A pattern alone cannot tell `0001-init.sql` or `2026-q3-review` from a real `NNNN-slug` task id; the
  task log can. The task log is tracked in the product repo, so `ccp docs check` can read its ids.
- Comments are read only for files under `docstring_globs`, through the language pack; a product without
  them gets no comment check (reviewer MINOR on 0033). This task documents that as it is.

## Scope

- **In:**
  - Every task-number form the check reads (a `NNNN-slug` id, `task N` / `Task: N`, a bare zero-padded
    number, with or without a following full stop) matches only when the number names a task in the
    task log. `ccp docs check` loads the task ids once per run.
  - A name followed by a file extension (such as `0001-init.sql`) never matches.
  - The plane's own stamp ids (`ar-…`, `sh-…`, with or without `#F<n>`, and `sm-…`, as in
    `ccp/refs.py`) always match. Product patterns in `delivery_id_patterns` are unchanged.
  - The same narrowing applies to `rules.no_ids`, which shares `refs.task_mention_patterns`.
  - §21.3 states this, replacing its current description of the forms that match, and states that
    comments are read only under `docstring_globs`.
  - `no_delivery_ids: false` stays the off switch.
- **Out:** other doc rules, and the language packs' comment readers.

§31: the §21.3 edit changes which forms the default-on check flags, so the merge waits for the
operator's approval of the new text.

## dod_checks

- id: `check-01`
  story: As a product upgrading the plane, ordinary numbers in my package docs do not fail the check.
  setup: a scratch product with `package_docs` set, tasks `0001-setup` and `0007-add-login` in its
    task log, and a package doc holding `chmod 0644`, `0001-init.sql`, `task 2026` and
    `plan 2026-q3-review`.
  steps:
    1. Run `ccp docs check`.
  expect: no delivery-id finding for any of them.
  dry run: on the merge base the same doc gets delivery-id findings for all four.
- id: `check-02`
  story: As a plane maintainer, real ids are still caught.
  setup: the same product, with a package doc naming `0007-add-login`, `task 7`, `0007.` and a spec
    question id `sm-20261110T000000Z-abcd`.
  steps:
    1. Run `ccp docs check`.
  expect: each is flagged.
  dry run: n/a — they are flagged before and after.
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
