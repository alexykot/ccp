---
task_id: 0015-flag-untriaged-proposals
title: Flag a tool proposal left untriaged for seven days
status: pending
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S31"]
adr_refs: ["0034 D11"]
review_point: R1
paths: ["ccp/plane.py", "ccp/board.py", "ccp/board_page.html", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0015-flag-untriaged-proposals

## Intent

A plane proposal untriaged for seven days is flagged in `ccp plane list` and on the board.

## Context (not checked)

- §31.4 states the rule; ADR-0034 D11 records the ruling (ADR-0018 D8 was the original).
- Age counts from the proposal's last `--again` or its creation, whichever is later; decide and state it.

## Scope

- **In:** the flag in the list command and the board, tests.
- **Out:** triage itself.

## dod_checks

- id: `flag-01`
  story: As the plane session, an old untriaged proposal stands out.
  setup: a temporary queue with a proposal created eight days ago and one created today.
  steps:
    1. Run `ccp plane list` and `ccp board build`.
  expect: the old one is flagged in both; the new one is not.
  dry run: n/a — the test this task adds builds the queue.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
