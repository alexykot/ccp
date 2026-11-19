---
task_id: 0189-spec-states-behaviour
title: The SPEC states behaviour, not default numbers, and names no constant as a setting, in one text the operator signs once
status: pending
kind: feature
depends_on: ["0171-affected-says-run-the-full-lane", "0173-plane-json-block-registry", "0180-parallel-by-default", "0181-models-block-and-role-defaults", "0182-language-is-a-required-key", "0183-gate-lane-is-required", "0184-init-turns-telemetry-on", "0185-architect-on-by-default", "0186-account-facts-on-the-machine", "0187-short-plane-json", "0188-short-binding"]
spec_refs: ["S2", "S3", "S5", "S8", "S10", "S12", "S14", "S15", "S16", "S19", "S20", "S21", "S22", "S24", "S25", "S26", "S28", "S30"]
adr_refs: ["0043 D1"]
review_point: R12
paths: ["docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/spec/04-observability.md", "docs/spec/05-operations.md", "docs/spec/map/", "README.md", "contracts/plane_config.schema.json", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md"]
adopt: none
sign_off: build
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0189-spec-states-behaviour

## Intent

A default lives in one place, the code and the schema that the tests hold together, so changing it
never means finding every SPEC sentence that restates it. The SPEC says what the plane does by default
("one further merge", "the product's `WORKERS.md`", "every role's model"), never the knob's number,
and names no constant as something a product sets. The operator signs the whole rewrite once.

## Context (not checked)

- ADR-0043 D1, accepted 2026-11-19, with the operator's ruling on shape F10 (2026-11-19, "2 yes"):
  house rule E10 is amended to "a rule and its knob, stated as behaviour; a default's value lives in
  code and the schema (E12), not in SPEC text", and one bulk SPEC change replaces the default numbers
  with behaviour, signed once; each other ADR-0043 task edits only the § text for its own behaviour.
- D1's other half, one owner per default in code with a test against the schema, is built by 0173
  (the block registry and the generic schema-defaults test, house rule E12 as amended). This task is
  the SPEC half and marks D1 built.
- Depends on every other ADR-0043 feature task: each changes SPEC passages this rewrite reads, so its
  CURRENT text exists only once they merge. That is why this brief cannot quote CURRENT → PROPOSED
  passage by passage, and declares `sign_off: build`: the operator signs the build's whole SPEC diff,
  once, after verify, at the head that merges (§3.5).
- Today, at `e9ff0fc`: `grep -o "(default [^)]*)" docs/spec/0*.md | wc -l` prints 50 (the shape's 51
  counted `RULINGS.md`, a record of past rulings that this task does not edit);
  `git grep -cwP 'grace_tasks|triage_grace_tasks|rules_max_lines|shell_limit_seconds|cut_line_seconds|small_task_lines|max_new_tasks|call_timeout_minutes|small_estimate_minutes|log_keep_days|refresh_minutes' -- 'docs/spec/0*.md'`
  counts 25 lines (10, 5, 8 and 2 in `01`–`04`).
- Decided here, the rules of the rewrite:
  - A parenthetical default `(default N)` on a product setting becomes the behaviour it gives ("by
    default, two tasks run at once" becomes "several tasks run at once, up to the product's
    `parallel.max_in_flight`"), or is deleted where the sentence already says it; the value is in the
    schema's `default`, which the SPEC names once, in §8.1: "Each key's default is in the schema
    (`contracts/plane_config.schema.json`), which the plane's tests hold to the code."
  - A constant (0187, 0186, 0188) is described by what it does, with its value when the value is the
    behaviour ("a pass due for one further merge blocks `next`"), and never as a key a product sets.
    The §8 tables list only the keys that remain settings.
  - Exit codes, protocol numbers, limits that are not knobs (`at most 6 checks`) and the plane's own
    fixed thresholds that are not plane.json keys stay as they are.
  - `README.md`'s configuration table gives no default numbers either.
  - Nothing else changes: a sentence's rule stays the same rule. A rule this rewrite would have to
    change is left as it is and named in the PR body for a follow-up.
- `docs/spec/map/` is regenerated or edited to match (`ccp docs check` checks it).

## Scope

- **In:**
  - `docs/spec/01-model.md` … `05-operations.md`, `docs/spec/map/`, `README.md`: the rewrite.
  - `contracts/plane_config.schema.json`: only a `description` that this rewrite moves a default's
    explanation into.
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D1 marked built; `docs/adr/INDEX.md`.
- **Out:**
  - Code. `docs/spec/RULINGS.md`. ADR text. Any change to a rule.

## dod_checks

- id: `doc-01`
  story: As a plane developer, no SPEC sentence restates a default's number.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -o "(default [^)]*)" docs/spec/0*.md | wc -l`.
  expect: prints `0`.
  dry run (`e9ff0fc`): printed `50`.
- id: `doc-02`
  story: As a plane developer, no SPEC sentence offers a constant as a setting.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -cwP 'grace_tasks|triage_grace_tasks|rules_max_lines|shell_limit_seconds|cut_line_seconds|small_task_lines|max_new_tasks|call_timeout_minutes|small_estimate_minutes|log_keep_days|refresh_minutes' -- 'docs/spec/0*.md'`.
  expect: prints nothing.
  dry run (`e9ff0fc`): 25 lines across `01-model.md` (10), `02-delivery.md` (5), `03-quality.md` (8), `04-observability.md` (2).
- id: `doc-03`
  story: As the operator, the SPEC names where defaults live, once.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -c "Each key's default is in the schema" docs/spec/01-model.md`.
  expect: prints `1`.
  dry run (`e9ff0fc`): printed `0`.
- id: `doc-04`
  story: As the operator, the rewrite changed no code and no rule I did not sign, and D1 is recorded as built.
  setup: a checkout of the PR head, after the build sign-off is recorded.
  steps:
    1. Run `git diff --name-only origin/main...HEAD`.
    2. Run `grep -n '"D1 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: step 1 lists only files in this task's `paths`, plus the task file and `docs/delivery/INDEX.yaml`; step 2 prints `- "D1 built"`.
  dry run (`e9ff0fc`): step 2 printed `- "D1 not_built"`.
- id: `suite-01`
  story: As a plane developer, the docs still check.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp docs check`, `ccp tasks check` and `ccp adr check`.
  expect: all three exit 0.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
