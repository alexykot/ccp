---
task_id: 0023-re-review-skip-paths
title: Declared paths a fix may touch without re-review, with a product proof hook
status: pending
kind: feature
depends_on: []
spec_refs: ["S15"]
adr_refs: ["0035 D4"]
review_point: R2
paths: ["ccp/prompt.py", "ccp/verify.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/02-delivery.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0023-re-review-skip-paths

## Intent

A generic setting lists paths a fix round may touch without a fresh review; a product-supplied proof hook, run on the fix diff, must pass before the runner goes straight to re-verify.

## Context (not checked)

- Comment-only or docstring-only fixes in tests cost a full review round.
- The prover (for example a language-aware comparison) is product tooling run through the hook.

## Scope

- **In:** the setting, the hook contract (command, exit 0 = proven), the review-gate change, SPEC §15.2 wording, tests.
- **Out:** any language-specific prover.

## dod_checks

- id: `skip-01`
  story: As a runner, a fix within the declared paths that the hook proves goes straight to re-verify.
  setup: a temporary queue and a hook that exits 0.
  steps:
    1. Run `ccp prompt verify <task>` after such a fix.
  expect: accepted without a new review round.
  dry run: n/a — built by the task's test.
- id: `skip-02`
  story: As a runner, an unproven fix still needs a review.
  setup: the same with a hook that exits 1, or a path outside the list.
  steps:
    1. Run `ccp prompt verify <task>`.
  expect: refused: review the fix first.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
