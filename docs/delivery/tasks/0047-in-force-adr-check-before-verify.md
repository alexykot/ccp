---
task_id: 0047-in-force-adr-check-before-verify
title: The in-force ADR check runs before the verdict, not only at close
status: pending
kind: feature
depends_on: []
spec_refs: ["S6", "S15"]
review_point: R3
paths: ["ccp/", "plugin/agents/", "docs/spec/", "tests/"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0047-in-force-adr-check-before-verify

## Intent

A task whose change needs an ADR decision marked `built` (or otherwise moved) fails before its
verdict, not after its merge: the check that `ccp tasks close` runs under `adr.strict` (§6) also runs
on the task's PR head when the verifier records its verdict (§15), so an approve cannot be recorded
for a head that would turn the integration branch red at close.

## Context (not checked)

- Twice in one review point, a task passed review and verify and then failed the in-force ADR check
  on the integration branch after its merge, because the check runs only at close. Each needed a
  separate fix PR. Accepted plane proposal: the same check belongs before the verdict.
- The working practice since then is that a task flips its ADR decision inside its own PR; this task
  makes the plane enforce it.

## Scope

- **In:** `ccp verify record` (or the verify gate it reads) runs the same in-force ADR check that close
  runs, on the PR head, and refuses an `APPROVE` while it fails, naming the decision and the
  `ccp adr decide` command to fix it; the verifier brief says so; §6 and §15 say where the check runs.
- **Out:** changing what the in-force check itself requires.

## dod_checks

- id: `check-01`
  story: As a verifier, I cannot approve a head that would fail the ADR check at close.
  setup: a scratch product with `adr.strict: true`, an ADR decision `not_built`, and a task whose
    change the in-force check says needs it `built`; the decision is not flipped on the PR head.
  steps:
    1. Record an `APPROVE` verdict for that head with `ccp verify record`.
  expect: it is refused, and the message names the decision and the `ccp adr decide` command.
  dry run: n/a — today the approve is recorded and close fails later.
- id: `check-02`
  story: As a verifier, a head with the decision flipped is approved as before.
  setup: as check-01, with the decision flipped to `built` on the PR head.
  steps:
    1. Record the same `APPROVE`.
  expect: it is recorded.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
