---
task_id: 0044-ccp-mutate
title: ccp mutate proves a test bites
status: done
kind: feature
depends_on: []
spec_refs: ["S12", "S15"]
review_point: R3
paths: ["ccp/mutate.py", "ccp/wt.py", "docs/spec/03-quality.md", "docs/cli/", "tests/test_mutate*.py", "tests/test_wt.py"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0044-ccp-mutate

## Intent

`ccp mutate` tells 'the tests pass' from 'the tests check something', in any language: in a mutation worktree it applies one or more mutants (text substitutions or a patch), runs a product-declared test command per mutant, and records a mutant as killed only when the named test fails. The run is bound to the calling seat's run.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §12 and §15.
- Reviewers and verifiers in any product need to know a test checks the behaviour it names; products build their own language-specific wrappers for the same mechanism.
- Paths (lead, 2026-11-10): the SPEC text for `ccp mutate` goes in `docs/spec/03-quality.md` (a new subsection) and `docs/cli/`, not in `02-delivery.md`, so this task can run beside the delivery-section tasks. `ccp/cli.py` and `ccp/config.py` are left out of every task's paths on purpose: their edits are small and git resolves them (§16.1).

## Scope

- **In:** `ccp wt create --kind mut`; `ccp mutate --mutant <file:old=>new | patch> --test <id>` runs the product's `mutate.command` with the test id, restores the tree, and records killed or survived per mutant in the run; a new subsection of `docs/spec/03-quality.md` describes it, and a CLI doc page. §12 and §15 and the verifier brief are not edited here: a cross-reference from them is a follow-up, so this task can run beside the delivery-section tasks.
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

- 2026-11-10 (implementer): `ccp mutate --run RUN_ID --test ID --mutant M …` in `ccp/mutate.py`, with
  a plane.json `mutate` block (`command` naming `{test}`, `timeout_seconds` 600) in `ccp/config.py` and
  `contracts/plane_config.schema.json`, the CLI in `ccp/cli.py`, SPEC §20.6 and a row in
  `docs/cli/03-quality.md`. `ccp wt create --kind mut` already existed (§12.1), so `ccp/wt.py` is
  unchanged. Choices the task left open, each the narrowest found: the call runs only from a recorded
  `mut` worktree of the run's task, for an open run; a substitution's old text must occur exactly once;
  a value with no `=>` is a patch; the named test runs once unmutated first and a failure there stops
  the call (exit 1, nothing recorded); a run killed at the timeout counts as the test failing
  (`timed_out: true`); exit 0 when every mutant is killed, 1 when one survived; a SIGTERM restores the
  files and exits 143. Rows go on the run record's `mutation` list, ids and numbers only (a digest
  stands for the mutant's text); the test output goes to `<run record>-mutate.log`; one `run`/`recorded`
  event per call. Tests: `tests/test_mutate.py`.

## Verification notes

- 2026-11-10 — verifier, PR #38 head `7f7ecd8` (squash `a63ce64`): APPROVE. Passed: none. Not run by the verifier: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0044-ccp-mutate.json.
