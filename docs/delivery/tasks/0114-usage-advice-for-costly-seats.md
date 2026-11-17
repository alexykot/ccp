---
task_id: 0114-usage-advice-for-costly-seats
title: ccp usage advises on short-lived cache writes, oversized context and the coordination share, naming the setting that fixes each
status: done
kind: feature
depends_on: []
spec_refs: ["S24"]
review_point: R7
paths: ["ccp/usage.py", "ccp/health.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/04-observability.md", "tests/test_usage*.py"]
adopt: "none: the advice appears by itself"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0114-usage-advice-for-costly-seats
## Intent

`ccp usage` tells a lead, without a manual analysis, when a seat is paying for short-lived cache
writes, re-reading an oversized context, or when coordination (lead plus runner) costs as much as the
workers, and names the setting that fixes each.

## Context (not checked)

- From an accepted plane proposal. Over 9–16 Nov `ccp usage` returned no advice while the runner spent most of its cost on 5-minute cache writes and the lead re-read a very large context on each request; a manual analysis found both (`ccp usage --system --since 2026-11-09` gives the per-seat rows it read).
- The settings: `subagentPromptCacheTtl` (task 0111), `autoCompactWindow` (task 0111), and the binding's `runner.rotate_at_context_tokens` (§10.2).
- The advice is description of this task's own feature with neutral thresholds (§31.1).

## Scope

- **In:**
  - `ccp/usage.py`: three advice lines, each naming the seat, the measure and the setting:
    - a seat whose 5-minute cache writes are more than `usage.advice.cache_5m_share` (default `0.5`) of its cache-write tokens: set `subagentPromptCacheTtl` to `1h`;
    - a seat whose median context tokens per request exceed `usage.advice.context_tokens` (default `300000`): for the lead, `autoCompactWindow`; for a runner, `runner.rotate_at_context_tokens`;
    - a coordination share (lead plus runner cost over all seats' cost) above `usage.advice.coordination_share` (default `0.4`).
  - `ccp health` carries the same lines in its usage summary.
  - Knobs in `ccp/config.py` and the schema; SPEC text describing them in §24, marked `§31.1`.
- **Out:**
  - Changing any setting automatically.

## dod_checks

- id: `cmd-01`
  story: As a lead, usage flags a runner on 5-minute cache writes.
  setup: a scratch usage sink where the runner seat has 70% of its cache-write tokens at 5 minutes.
  steps:
    1. Run `ccp usage`.
  expect: an advice line names the runner, the 70% share and `subagentPromptCacheTtl`.
  dry run: n/a.
- id: `cmd-02`
  story: As a lead, usage flags my oversized context and names the right setting per seat.
  setup: a scratch sink where the lead's median context is 500000 tokens and a runner's is 350000.
  steps:
    1. Run `ccp usage`.
  expect: one line names the lead and `autoCompactWindow`; one names the runner and `runner.rotate_at_context_tokens`.
  dry run: n/a.
- id: `cmd-03`
  story: As a lead, usage flags a high coordination share, and stays quiet below the thresholds.
  setup: two scratch sinks: one where lead plus runner are 50% of cost, one where every measure is under its threshold.
  steps:
    1. Run `ccp usage` on each.
  expect: the first prints the coordination line with 50%; the second prints none of the three lines.
  dry run: n/a.
- id: `cmd-04`
  story: As a product, I tune the thresholds.
  setup: the first sink of `cmd-03` and plane.json `usage.advice.coordination_share: 0.6`.
  steps:
    1. Run `ccp usage`.
  expect: no coordination line.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17, implementer: `usage.cost_advice` (ccp/usage.py) builds the three lines from the fold's
  per-seat figures and each seat's request contexts (input, cache read and cache written, as
  `CONTEXT_TOKENS`); `fold` adds them to `advice` only when given the knobs, which `ccp usage` and
  `ccp health` pass, so the board, the estimator and the forecast keep their advice as it was. Narrowest
  readings taken: the 5-minute share is `cache_creation_5m_tokens` over `cache_creation_tokens`, for every
  seat in the fold; the context line is only for `design-seat` and `runner`, the two seats the task names
  a setting for; "all seats' cost" is the sum over the fold's seats (unattributed requests excluded); the
  coordination line names no setting, as the task names none; each threshold is strict (more than).
  `ccp health` had no usage summary: it gains `usage_advice` (in --json) and a `Usage advice:` line each,
  from the queue's usage, skipped without QUEUE_ROOT. Knobs: plane.json `usage.advice` (config
  `USAGE_DEFAULTS`, merged key by key), in the schema; SPEC §24.6, a `usage` row in §8.1's block table and
  the CLI reference.

## Verification notes
- 2026-11-17 — verifier, PR #119 head `00e96cc` (squash `e152543`): APPROVE. Passed: cmd-01, cmd-02, cmd-03, cmd-04, suite-01. Gate: `scripts/gate.sh (ccp suite run --lane gate)` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0114-usage-advice-for-costly-seats.json.

