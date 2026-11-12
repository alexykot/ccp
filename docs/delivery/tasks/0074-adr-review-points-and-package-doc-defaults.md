---
task_id: 0074-adr-review-points-and-package-doc-defaults
title: Docs checks warn on untracked ADR review points and state package-doc defaults
status: done
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

- 2026-11-12 (implementer): `ccp adr check` (`adr.analyse`) adds one warning when any ADR carries
  `review_points` and no register file exists, naming the ADR ids and the register path; it goes to
  the warnings under `adr.strict` too, as the task warning does. `ccp docs check` prints it through
  `adr.warnings`. `pkgdocs.source_dirs` leaves out a directory whose source files all end `.md`
  unless `claude_md_dirs` lists it: "the product lists it" is read as `claude_md_dirs`, the existing
  list of directories that carry a doc, so no new key. SPEC §21.3, §21.4 and §22.3 say so; the schema
  and config comments name the defaults. Dry runs: on the merge base `ccp adr check` printed no
  register warning for an ADR with `review_points: [R1]`, and `ccp docs check` reported
  `notes: no .claude.md` for a `.md`-only `notes/`; on the head the first warns naming ADR-0001 and
  the second reports only the code directory.
- 2026-11-12 (implementer, second run): SPEC §6.7 lists the new warning under "Always warnings",
  where `ccp adr check`'s findings are enumerated. Re-ran the two new tests against the merge-base
  code: both fail there (no register warning; `notes` and `notes/deeper` reported), pass on the head.

## Verification notes

- 2026-11-12 — verifier, PR #84 head `a8d1b3e` (squash `781e81d`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0074-adr-review-points-and-package-doc-defaults.json.
