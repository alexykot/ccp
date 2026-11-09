---
task_id: 0040-operator-notification-triggers
title: The plane defines when the operator is notified; a product setting names the channel
status: pending
kind: feature
depends_on: [0039-operator-sign-off-record]
spec_refs: ["S3", "S17"]
review_point: R3
paths: ["docs/spec/", "ccp/", "plugin/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0040-operator-notification-triggers

## Intent

The plane defines when the lead must notify the operator (a blocker, a decision needed, a review point done, an allowance checkpoint), and a product setting gives the channel (the interactive session by default; email, a chat message or another command when configured). The blanket rule that nothing emails is replaced by this.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §3 and §17.
- Every operator needs to hear about blockers and decisions; how depends on the operator's setup, not the plane.
- Today the SPEC says nothing emails (§1, §8, §17), so a product that wants another channel overrides a plane rule.
- **SPEC change (§31):** this task changes a § rule — the no-email statements in §1, §8 and §17 and the operator channel in §3. It needs the operator's approval at build: the PR carries the CURRENT → PROPOSED text and quotes the ruling.

## Scope

- **In:** §3 and §17 list the triggers; a `notify` block in the binding or `plane.json` names a channel command (default: the lead's session, as today); `ccp` calls it with the trigger and ids only on each trigger; the no-email statements in §1, §8 and §17 are rewritten.
- **Out:** shipping an email or chat client; message content beyond trigger, ids and a link.

## dod_checks

- id: `check-01`
  story: As an operator, a blocker reaches my channel.
  setup: a scratch product whose notify command appends to a file.
  steps:
    1. Raise a blocker.
  expect: the file gets one line naming the trigger and the task id.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As an operator with no channel set, nothing changes.
  setup: no notify block.
  steps:
    1. Raise a blocker.
  expect: it is raised in the lead's session as today; no command runs.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
