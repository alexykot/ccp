---
task_id: 0013-prompt-bodies-opt-in
title: Make full prompt bodies opt-in, with retention by age
status: pending
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S23"]
adr_refs: ["0034 D8"]
review_point: R1
paths: ["scripts/observability/write-prompt-audit.sh", "scripts/observability/prune-prompts.sh", "ccp/prompt.py", "ccp/config.py", "contracts/prompt_audit.schema.json", "contracts/plane_config.schema.json", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0013-prompt-bodies-opt-in

## Intent

A prompt audit records ids, refs and the prompt's hash; the full prompt text is kept only when the product opts in (off by default), and audits older than a configured age are pruned.

## Context (not checked)

- §23.8 states the target rule; ADR-0034 D8 records it, amending ADR-0019.
- The run binding and reports must not depend on `prompt_body` being present.

## Scope

- **In:** a `prompts.keep_body` knob (default false), the audit writer, an age-based retention knob and its pruning, schema, tests.
- **Out:** telemetry (already ids and numbers only).

## dod_checks

- id: `audit-01`
  story: As an operator, a default product's audits carry no prompt text.
  setup: a temporary product with default config; one `ccp prompt` render.
  steps:
    1. Read the written audit file.
  expect: no `prompt_body`; the sha256 is present.
  dry run: n/a — the test this task adds renders the prompt.
- id: `audit-02`
  story: As an operator who opts in, the body is kept, and old audits are pruned.
  setup: the same with `prompts.keep_body: true` and a retention age, plus an audit older than it.
  steps:
    1. Render a prompt; run the pruning.
  expect: the new audit holds `prompt_body`; the old one is gone.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-09 (implementer): Two knobs in plane.json `prompts`. `keep_body` (bool, default false).
  `audit_keep_days` (int >= 1 or null, default null = keep all). Both are checked in `ccp/config.py`
  and named in `contracts/plane_config.schema.json`.
  - `write-prompt-audit.sh` writes `prompt_body` only with `--keep-body`. It always writes
    `prompt_sha256` and a new `prompt_chars`. Without the body, an argv entry that is the prompt
    itself becomes `<prompt>`; the architect passes its prompt in argv.
  - `contracts/prompt_audit.schema.json`: `prompt_body` is optional and `prompt_chars` is added.
  - `ccp prompt` passes `--keep-body` from the knob. After writing its audit it removes audits older
    than `audit_keep_days`, across `prompts/**` and judged by the UTC stamp in the file name
    (`prompt.prune_audits`). Rendered prompts, env files and other names stay.
  - Outside the listed paths: `ccp/architect.py` and `ccp/estimator.py` pass `--keep-body` from the
    same knob. `ccp/health.py` reads `prompt_chars` for the §27.1 prompt sizes and falls back to
    the body's length for older audits (E9). `team.py`'s runner-spawn and runner-scope audits keep
    the default, with no body.
  - `prune-prompts.sh` keeps its behaviour as the on-demand tool. Only its "alpha keep-all" framing
    changed.
  - `tests/test_architect.py` now reads the prompt from the stub's argv rather than the audit's
    `prompt_body`; the assertions are unchanged.
  - ADR-0034 D8 is recorded as built.
  - Open: the SPEC passages still say "code: task 0013" (§23.8, §23.9), and §8.1's `prompts` row does
    not name the knobs. The default retention age is also open. All are in the run report.

## Verification notes

*Append-only.*
