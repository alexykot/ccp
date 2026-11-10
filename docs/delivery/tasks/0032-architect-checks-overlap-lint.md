---
task_id: 0032-architect-checks-overlap-lint
title: ccp refuses architect checks that cover the same test twice
status: done
kind: feature
depends_on: []
spec_refs: ["S19"]
review_point: R3
paths: ["ccp/", "tests/"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0032-architect-checks-overlap-lint

## Intent

`ccp` checks its own `architect.checks` config: two checks that select the same test module or class are refused, so a test is not run twice in one gate and a failure is not blamed on two checks.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §19.
- The config is the plane's, so the plane lints it; without this, each product writes its own test of plane config.

## Scope

- **In:** config validation (or `ccp architect check`) resolves each check's test selectors and fails when two overlap, naming both checks and the shared module or class; §19 notes it.
- **Out:** judging whether a check is useful.

## dod_checks

- id: `check-01`
  story: As a lead, an overlapping config is refused.
  setup: a scratch product with two checks both selecting `tests.test_a`.
  steps:
    1. Validate the config.
  expect: it fails and names both checks and `tests.test_a`.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, disjoint checks pass.
  setup: two checks selecting different modules.
  steps:
    1. Validate the config.
  expect: it passes.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): The lint runs in config validation (`config._architect` via
  `_check_overlaps`), so `ccp` refuses an overlapping `architect` block with exit 2 on every command,
  `ccp docs check` included. There is no `ccp architect check` command, and none was added. Selectors
  come from each check's `cmd`: dotted names and `tests/…py[::Case[::test]]` paths
  (`docrules.test_selectors`, next to the opt-in rule's `test_modules`, using the same patterns).
  Two checks overlap when a selector of one equals or contains, by dotted component, a selector of
  the other. The refusal names both check ids and the narrower selector. Two different classes of
  one module do not overlap. `discover` and directories resolve to nothing and are not judged. Only
  `architect.checks` is linted. The opt-in `package_docs.rules.no_overlap` (module level, both check
  lists) is unchanged. A managed product's current `architect.checks` loads clean (checked
  read-only). The §19.11 paragraph is the implementer's draft: the task named no SPEC text (see the
  report).

## Verification notes

- 2026-11-10 — verifier, PR #24 head `fe682fa` (squash `affd2c9`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0032-architect-checks-overlap-lint.json.
