---
task_id: 0019-parallel-doc-checks
title: Run docs.checks and architect.checks in parallel, opt-in
status: done
kind: feature
depends_on: []
spec_refs: ["S20", "S21"]
adr_refs: []
review_point: R2
paths: ["ccp/rules.py", "ccp/config.py", "contracts/plane_config.schema.json", "tests/"]
created: 2026-11-06
updated: 2026-11-10
---

# Task: 0019-parallel-doc-checks

## Intent

`ccp docs check` can run a product's check commands in parallel when the product sets a workers count; the default stays serial and the output order stays stable.

## Context (not checked)

- Checks run serially today; a product with many slow checks waits on their sum.
- Serving checks from a product's own cache is product work.
- Lead's ruling, 2026-11-10 (on the round-1 open question): "Add the proposed text to section 21.5
  in PR #15, replacing whatever there says the checks run serially: '`docs.workers` (default 1) is how
  many check commands (`docs.checks` and `architect.checks`) run at once, each under its own timeout;
  results are reported in declared order.' Also add `docs.workers` wherever the SPEC or docs/cli lists
  the `docs` block's keys. Record this ruling in task 0019's Context. Section 31: section 21.5's serial
  description is made false by the task's change. The knob is the task's own approved scope (parallel
  doc checks, from the triage the operator accepted, ADR-0035), so the operator's 2026-11-10 ruling
  covers it. Quote it and the old text in the PR body. No merge gate."

## Scope

- **In:** a `workers` setting for the shared check runner, ordered output, per-check timeouts kept, tests.
- **Out:** caching check results.

## dod_checks

- id: `par-01`
  story: As a product with slow checks, parallel workers cut the wait.
  setup: a temporary product with two checks that each sleep one second and `workers: 2`.
  steps:
    1. Time `ccp docs check`.
  expect: under two seconds; output in declared order; failures reported as before.
  dry run: n/a — built by the task's test.
- id: `par-02`
  story: As a product with architect checks, they run in parallel too, and the architect gate reads the same results.
  setup: the same product with two `architect.checks` that each sleep one second and `workers: 2`.
  steps:
    1. Time `ccp docs check` with only the architect checks declared.
  expect: under two seconds; each check's `check E<n>` result line unchanged.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): the knob is `docs.workers` (integer >= 1, default 1, so the default
  stays serial). It is checked in `ccp/config.py` `_docs` and is in the schema's `docs` block.
  `rules.run_checks` is the shared runner for `docs.checks` and `architect.checks`. With
  workers > 1 it runs each call's checks on a thread pool of that size, capped at the number of
  checks. Each check keeps its own `run_command` timeout and process group, and the failures are
  listed in declared order, whatever order the checks finish in. The two lists still run one after
  the other, in one pool per list, so the `check E<n>` and `docs check <id>` lines are the same as a
  serial run's. The task gives no SPEC text, so §21.5 still describes serial runs: the SPEC line for
  the knob is an open question for the lead.
- 2026-11-10 (implementer, round 2): per the lead's ruling in Context, §21.5 now carries the
  `docs.workers` sentence (it had no explicit serial wording, so the sentence is added after the
  process-group line), and §8.1's block table names `docs.checks` and `docs.workers`. docs/cli lists
  no `docs` block keys, so it is unchanged.

## Verification notes

- 2026-11-10 — verifier, PR #15 head `9465b80` (squash `b11f622`): APPROVE. Passed: par-01, par-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0019-parallel-doc-checks.json.
