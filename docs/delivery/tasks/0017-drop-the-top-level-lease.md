---
task_id: 0017-drop-the-top-level-lease
title: Drop work.json's top-level lease
status: done
kind: feature
depends_on: []
spec_refs: ["S16", "S23"]
adr_refs: []
review_point: R2
paths: ["ccp/lifecycle.py", "ccp/queue.py", "ccp/forecast.py", "scripts/observability/lib.py", "contracts/", "tests/"]
created: 2026-11-06
updated: 2026-11-10
---

# Task: 0017-drop-the-top-level-lease

## Intent

`work.json` keeps no top-level `lease`: each runner slot keeps its own, so a closed task's lease never lingers at the top level. An old `work.json` with the field still reads.

## Context (not checked)

- `_leave_work` returns early when the task is neither the current task nor in flight, so the top-level lease survived close.
- One home per fact (ADR-0003): the slots hold the leases.
- Ruling sm-20261110T084025Z-9716 (spec commit 18df9cc): "In PR #13, with this ruling in task 0017's Context: section 16.4 becomes '`task_id` and `phase` in `work.json` mean "the task a runner acted on last"; no decision rests on them alone. Each runner slot keeps its own lease.' Section 31: the operator ruled in the lead session on 2026-11-10 that their accepted triage (ADR-0035) is the approval for SPEC passages an R2 task's change makes false. Quote ADR-0035, this ruling and the old text in the PR body. No merge gate."

## Scope

- **In:** writers and readers of the top-level `lease`, the snapshot and board, schemas, tests.
- **Out:** per-slot leases.

## dod_checks

- id: `lease-01`
  story: As a runner, closing a task leaves no lease behind at the top level.
  setup: a temporary queue after a claim and a close.
  steps:
    1. Read `work.json`.
  expect: no top-level `lease` key; the slot's own lease cleared.
  dry run: n/a — built by the task's test.
- id: `code-01`
  story: As a plane developer, nothing writes the top-level lease.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -E "\\[.lease.\\]|\\.get\\(.lease.\\)" -- ccp scripts`.
  expect: only readers that tolerate an old field, each with a comment.
  dry run (`a6dcca1`): 6 hits, incl. the forecast's read of `work["lease"]`.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): `ccp tasks claim` no longer writes work.json `lease`; the lease is the task's own
  (`tasks/<id>.json` `lease_holder`). Claim (`save_work(drop=...)`), `_leave_work` (release, drop, sync) and
  close remove an old file's top-level `lease`, whichever task it names; `_leave_work` now writes when only
  that key is there, so the early return no longer leaves it behind. The forecast's `_flight_elapsed` still
  reads an old file's `lease` (after `claimed_at`), commented as the tolerant reader (E9). `code-01` now
  shows that single hit. Open: SPEC §16.4 still names `lease` among work.json's "acted on last" fields; the
  task carries no SPEC edit, so it is left for the lead.
- 2026-11-10 (implementer, round 2): per ruling sm-20261110T084025Z-9716 (in Context), SPEC §16.4 now reads
  "`task_id` and `phase` in `work.json` mean ...; Each runner slot keeps its own lease." A grep of `docs/` and
  `plugin/` found no other passage that puts a lease in `work.json`; the rest name the task's lease beside it.

## Verification notes

- 2026-11-10 — verifier, PR #13 head `aa593e4` (squash `110c964`): APPROVE. Passed: lease-01, code-01. Gate: `scripts/gate.sh` exit 0, `ccp tasks check && ccp docs check` exit 0. Record: verification/0017-drop-the-top-level-lease.json.
