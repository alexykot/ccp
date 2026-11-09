---
task_id: 0044-ccp-mutate
title: ccp mutate proves a test bites
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S15"]
review_point: R3
paths: ["ccp/", "docs/spec/", "docs/cli/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0044-ccp-mutate

## Intent

`ccp mutate` tells 'the tests pass' from 'the tests check something', in any language: in a mutation worktree it applies one or more mutants (text substitutions or a patch), runs a product-declared test command per mutant, and records a mutant as killed only when the named test fails. The run is bound to the calling seat's run.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §12 and §15.
- Reviewers and verifiers in any product need to know a test checks the behaviour it names; products build their own language-specific wrappers for the same mechanism.

## Scope

- **In:** `ccp wt create --kind mut`; `ccp mutate --mutant <file:old=>new | patch> --test <id>` runs the product's `mutate.command` with the test id, restores the tree, and records killed or survived per mutant in the run; the verifier brief says when to use it; §12 and §15 describe it; a CLI doc page.
- **Out:** choosing mutants automatically; language-specific mutation operators.

## dod_checks

- id: `check-01`
  story: As a verifier, a mutant the test catches is killed.
  setup: a scratch product whose test checks `add(1,1)==2`, a mutant replacing `+` with `-`.
  steps:
    1. Run `ccp mutate`.
  expect: the mutant is recorded killed; the worktree is restored.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a verifier, a mutant the test misses survives.
  setup: a mutant in code the named test does not reach.
  steps:
    1. Run `ccp mutate`.
  expect: recorded survived.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-03`
  story: As a verifier, a different failing test does not count.
  setup: a mutant that breaks another test but not the named one.
  steps:
    1. Run `ccp mutate`.
  expect: recorded survived.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
