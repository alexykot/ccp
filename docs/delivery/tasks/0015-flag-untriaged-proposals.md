---
task_id: 0015-flag-untriaged-proposals
title: Flag a tool proposal left untriaged for seven days
status: done
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S31"]
adr_refs: ["0034 D11"]
review_point: R1
paths: ["ccp/plane.py", "ccp/board.py", "ccp/board_page.html", "tests/"]
created: 2026-11-06
updated: 2026-11-10
---

# Task: 0015-flag-untriaged-proposals

## Intent

A plane proposal untriaged for seven days is flagged in `ccp plane list` and on the board.

## Context (not checked)

- §31.4 states the rule; ADR-0034 D11 records the ruling (ADR-0018 D8 was the original).
- Age counts from the proposal's last `--again` or its creation, whichever is later; decide and state it.
- The lead's standing ruling for R1: this task carries out the operator ruling in
  `docs/spec/RULINGS.md` (the §28.10 → §31.4 row names it), so the PR also removes or rewords, without
  asking, every SPEC or docs passage the change makes false, such as a transitional "task 0015"
  marker. Each edit is listed with its old text in the PR body's "Operator approval (SPEC §31)"
  section, citing that row. History records (ADRs, done tasks, RULINGS, the spec map's history
  columns) stay as written.

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

- 2026-11-10, implementer: `ccp/plane.py`'s fold marks every proposal `stale` (a bool): open, and
  `STALE_DAYS` (7) or more since the later of its creation and its last `--again`. A repeat restarts
  the seven days, as the Context reads; a triaged proposal and one whose times do not parse are never
  stale. `ccp plane list` carries the flag on each row and the stale ids in a top-level `stale` list
  (with `--open` too). The board's `health.proposals_open` rows carry the same field from the fold;
  the Plane health card marks a stale one "untriaged 7+ days", and each stale one counts in the tab's
  warning badge. It is not a `board status` blocker. §31.4 now states the age rule in place of its
  "not built yet: task 0015" marker; ADR-0034 D11 and ADR-0018 D8 (the original ruling) are recorded
  built. Tests: `tests/test_plane_stale_proposals.py` (list and board.json) and a page test in
  `tests/test_board_layout.py`.

## Verification notes

- 2026-11-10 — verifier, PR #9 head `85db6df` (squash `fac5e76`): APPROVE. Passed: flag-01. Gate: `env -u QUEUE_ROOT scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0015-flag-untriaged-proposals.json.
