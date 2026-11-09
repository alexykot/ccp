---
task_id: 0033-package-doc-convention-owned-by-the-plane
title: The plane owns the package-doc convention
status: pending
kind: feature
depends_on: []
spec_refs: ["S9", "S21"]
review_point: R3
paths: ["ccp/", "docs/spec/", "plugin/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0033-package-doc-convention-owned-by-the-plane

## Intent

The package-doc system becomes a plane feature with one definition: the tiers (the root `CLAUDE.md` always loaded; package docs auto-loaded under a source directory; dot-prefixed `.claude.md` docs read on demand); a package doc is a map of what exists, never a record of what a task did; no task, finding or ruling ids in package docs or code comments; every source directory covered and modules carry docstrings. `ccp docs check` checks all of it.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §9 and §21.
- Agent efficiency on any non-trivial codebase depends on discoverable, map-style package docs.
- The plane already checks coverage; products restate the rest in prose, each slightly differently.

## Scope

- **In:** §21 (and §9 for loading) states the tiers and the map rule; `ccp docs check` adds a check that flags task, finding and ruling ids (per the product's id patterns) in package docs and code comments, with a knob to turn it off; the orientation and `writing-tasks` skill point to §21 instead of restating it.
- **Out:** rewriting any product's docs; language packs beyond what exists.

## dod_checks

- id: `check-01`
  story: As a lead, a package doc citing a task id is flagged.
  setup: a scratch product whose package doc says 'added in 0012'.
  steps:
    1. Run `ccp docs check`.
  expect: it reports the file, the line and the id.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, a code comment citing a ruling id is flagged.
  setup: a source file with a comment naming a ruling id.
  steps:
    1. Run `ccp docs check`.
  expect: it reports it; with the knob off, it does not.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-03`
  story: As a plane developer, the plane's own tree passes.
  setup: the PR head.
  steps:
    1. Run `ccp docs check`.
  expect: clean.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
