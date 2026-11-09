---
task_id: 0035-the-judge-never-produces-its-evidence
title: The seat that rules never produces the evidence it rules on
status: pending
kind: feature
depends_on: []
spec_refs: ["S2", "S15"]
review_point: R3
paths: ["docs/spec/", "plugin/", "ccp/", "contracts/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0035-the-judge-never-produces-its-evidence

## Intent

Separation of duties becomes a plane rule: the seat that rules on a task (the lead, or a runner at a gate) never produces the evidence its verdict rests on, except an operator step the operator approved. The verify record names who produced each piece of evidence, and `ccp verify` refuses a record whose evidence came from the ruling seat.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §2 and §15.
- Any team with a ruling seat and an evidence-producing seat needs the judge kept apart from the evidence; today products keep this as prose.
- **SPEC change (§31):** this task changes a § rule — the seat duties in §2 and the verification record in §15. It needs the operator's approval at build: the PR carries the CURRENT → PROPOSED text and quotes the ruling.

## Scope

- **In:** §2 and §15 state the rule; the verification record schema gains a producer per evidence item; `ccp verify` rejects evidence produced by the ruling seat unless it is an approved operator step; the runner and verifier briefs state it.
- **Out:** seats beyond the existing ones.

## dod_checks

- id: `check-01`
  story: As a reviewer of the process, self-produced evidence is refused.
  setup: a verify record where the ruling seat produced an evidence item.
  steps:
    1. Record it with `ccp verify`.
  expect: it is refused, naming the item and the seat.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As an operator, my approved step counts.
  setup: evidence from an approved operator step.
  steps:
    1. Record it.
  expect: accepted.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
