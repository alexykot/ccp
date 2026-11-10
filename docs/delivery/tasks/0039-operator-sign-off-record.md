---
task_id: 0039-operator-sign-off-record
title: Operator sign-off is a plane record that ccp tasks close enforces
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S10"]
review_point: R3
paths: ["ccp/lifecycle.py", "ccp/tasklog.py", "ccp/queue.py", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "contracts/", "plugin/skills/", "tests/test_sign_off*.py"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0039-operator-sign-off-record

## Intent

A task can carry text the operator must sign (a SPEC CURRENT → PROPOSED, a contract). The lead records the sign-off (who, when, the words, the head it covers), and `ccp tasks close` refuses a task that needs one without it. Text known when the task is written is signed before the claim; text the build finds is signed after verify.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §3 and §10.
- Any product where the operator owns a spec or contract needs merges blocked until the sign-off is on record; prose rules fail under load.
- **SPEC change (§31):** this task changes a § rule — the operator gates in §3 and claim and close in §10. It needs the operator's approval at build: the PR carries the CURRENT → PROPOSED text and quotes the ruling.

## Scope

- **In:** a task field declaring the sign-off needed; `ccp tasks sign-off` (or similar) records it in the ledger; `ccp tasks claim` refuses a brief-time sign-off still missing; `ccp tasks close` refuses a missing or stale one (head moved); §3 and §10 describe it; the `writing-tasks` skill shows the field.
- **Out:** how the operator is asked (task 0040).

## dod_checks

- id: `check-01`
  story: As an operator, an unsigned task cannot close.
  setup: a scratch task declaring a sign-off, verified, with none recorded.
  steps:
    1. Run `ccp tasks close`.
  expect: refused, naming the missing sign-off.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As an operator, a sign-off on an old head is stale.
  setup: a sign-off recorded for head A, the PR now at head B.
  steps:
    1. Run `ccp tasks close`.
  expect: refused as stale; after re-signing at B it closes.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-03`
  story: As a runner, a brief-time sign-off blocks the claim.
  setup: a task whose brief-time sign-off is missing.
  steps:
    1. Run `ccp tasks claim`.
  expect: refused.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
