---
task_id: 0031-gate-fits-the-agent-shell-limit
title: The gate's run fits the agent's foreground shell limit
status: pending
kind: feature
depends_on: [0030-gate-stages-in-plane-json]
spec_refs: ["S14", "S20"]
review_point: R3
paths: ["ccp/", "docs/spec/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0031-gate-fits-the-agent-shell-limit

## Intent

A cold gate run fits the agent harness's foreground command limit (600 s in Claude Code today). A knob holds the limit and a lower line; a gate run above the line gets a refactor task, and one above the limit is reported as a health breach, judged on cold runs only.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §14 and §20.
- Every product whose gate an agent runs in its own shell meets the same harness limit; it is a property of the harness, not of a product.
- Uses the per-stage timings from task 0030.

## Scope

- **In:** knobs `gate.shell_limit_seconds` (default 600) and `gate.cut_line_seconds` (default 90% of the limit); the gate result records whether the run was cold; `ccp health` (§27) reports cold runs over the line and the slowest stages; §14 or §20 states the rule.
- **Out:** making any product's gate faster; warm-cache runs.

## dod_checks

- id: `check-01`
  story: As a lead, a slow cold gate is flagged.
  setup: a scratch product whose recorded cold gate run took above the line.
  steps:
    1. Run `ccp health`.
  expect: it reports the run, the line and the slowest stage; under the line it reports nothing.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, warm runs are not judged.
  setup: a recorded warm run above the line.
  steps:
    1. Run `ccp health`.
  expect: no finding.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): The knobs are a new plane.json block, `gate` (`config.GATE_DEFAULTS`,
  `config.gate_limits`): `shell_limit_seconds` (default 600) and `cut_line_seconds` (default null, read
  as 90% of the limit); the config refuses a limit at or below 0, a line at or below 0 or above the
  limit, and a non-number. Every suite `ended` row and its `suite/recorded` event carry `cold`
  (`suite.run_cold`: true for `cached` 0, false for any unit cached, null with no `cached` count);
  `suite.fold` now carries `cold`, `stages` and `failed_stage` onto the folded run. `ccp health`
  (`health.gate_time`) judges only the latest cold run of the gate role's lane (cold as §27.2's
  `classify` decides, with the cache's start), so a gate brought under the line clears the finding; over
  the line it reports the run, its seconds, the line, the limit and its slowest stage, over the limit
  with `over_limit` (a breach); it is in `--json` as `gate_time`, in the text output and in the
  architect's health summary. The refactor task itself is filed by the lead or the architect from that
  finding; nothing files it automatically. SPEC: a new §14.6 (written by the implementer, as the task
  carried no CURRENT -> PROPOSED text), the `gate` row in §8.1's table, `cold` in §14.4's field list and
  a pointer in §27.2. Outside the task's `paths`: `contracts/plane_config.schema.json`,
  `contracts/suite_result.schema.json` and `docs/cli/04-observability.md`.

## Verification notes

*Append-only.*
