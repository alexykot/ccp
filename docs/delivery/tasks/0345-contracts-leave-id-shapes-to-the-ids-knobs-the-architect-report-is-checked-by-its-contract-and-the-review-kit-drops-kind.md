---
task_id: 0345-contracts-leave-id-shapes-to-the-ids-knobs-the-architect-report-is-checked-by-its-contract-and-the-review-kit-drops-kind
title: The architect report, triage and plane_config contracts hold no task-id or rule-id pattern the ids knobs make the product's, and no code edits a contract before using it; the architect report is checked through ccp/schema.py, not by a hand list of its keys; the review kit drops its one-instance Kind
status: pending
kind: feature
depends_on: []
spec_refs: ["S7", "S19"]
rule_refs: ["E12"]
review_refs: ["ar-20261125T094654Z-c8a0#F05", "ar-20261125T094654Z-c8a0#F10"]
review_point: R37
paths: ["contracts/architect_report.schema.json", "contracts/architecture_review_triage.schema.json", "contracts/plane_config.schema.json", "ccp/architecture_review.py", "ccp/architect.py", "tests/test_architect_triage_schema.py", "tests/test_rules.py", "tests/test_obs_ids.py"]
clashes_with: ["0191-the-grace-release-ends"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0345-contracts-leave-id-shapes-to-the-ids-knobs-the-architect-report-is-checked-by-its-contract-and-the-review-kit-drops-kind

## Intent

A product that sets its own rule ids (`ids.rule.pattern`) or task-id width (`ids.task.width`) has contracts that
accept its valid records: an architect report, a triage and a plane.json citing its rule ids validate against the
contracts as they are, with no code editing a contract first. The architect report is checked by the same schema
checker as the triage, so a report the contract refuses is refused, and the review kit no longer threads a
one-instance `Kind` through every call.

## Context (not checked)

Findings F05 and F10 of architect pass `ar-20261125T094654Z-c8a0` (`docs/delivery/reviews/ar-20261125T094654Z-c8a0.md`),
and house rule E12 as that pass's triage amended it (`docs/ENGINEERING.md`). F05 also answers the 0331
follow-up the lead passed to that pass (contract id patterns not tied to the §7.1 `ids` knobs).

The contract change only loosens: every record valid before stays valid, so no stored record needs rewriting. The
contracts' descriptions name the knob that decides each id's shape, and the code checks those values by `ids`, as
`validate_triage` does today.

Measured at `b6c2bc17`:

- **F05, patterns.** `git grep -nF -e '"pattern": "^E[0-9]+$"' -e '"pattern": "^[0-9]{4}-[a-z0-9-]+$"' -e '"pattern":
  "^[0-9]{4}(-|$)"' -- contracts`: 6 lines: `architect_report.schema.json` (a rule change's `rule`),
  `architecture_review_triage.schema.json` (`tasks_created` items and a rule change's `rule`),
  `plane_config.schema.json` (`architect.shape_from_task` and the two `architect` rule-id `id` keys). The finding id
  (`^F[0-9]{2}$`) and the review ids are no knob's and stay.
- **F05, edits.** `git grep -n '\.pop("pattern"' -- ccp`: 2 lines, `"def _triage_contract"` (`ccp/architecture_review.py`).
- **F05, the report.** `"def validate_report"` checks a finding's keys by a hand tuple (`for k in ("id", "title",
  "category", …`) and never calls `schema.schema_errors`; a finding with `"severity": "urgent"` passes it.
- **F10.** `git grep -n -e 'kind: Kind' -e 'class Kind(' -e 'ar.Kind(' -- ccp tests`: 16 lines (14 kit functions, the
  class, `ARCH` in `ccp/architect.py`). Tests reading the instance: `tests/test_rules.py`
  (`architect.ARCH.categories`), `tests/test_obs_ids.py` (`architect.ARCH.rid_re`). Only `ccp/architect.py` calls the
  kit's functions (`git grep -n 'ar\.\(validate_report\|lock_take\|triage\)(' -- ccp tests`).

**Ruled.**

- **F05.** Remove the six `"pattern"` members above; each `description` names its knob (`ids.rule.pattern`,
  `ids.task.width`). Remove `_triage_contract`: `validate_triage` passes the contract as read. `validate_report` runs
  `schema.schema_errors(r, <architect_report contract>, at="report")` in place of its hand tuple of finding keys, and
  keeps what the contract cannot say (the review id, the category within the lenses, low confidence, a rule-cost
  finding's decision, secrets), plus a rule change's `rule` checked by `ids.is_rule_id`: it gains an `ids` parameter
  (default `refs.DEFAULT`), which `ccp/architect.py` passes from the product's config. New tests
  `tests.test_architect_triage_schema.ReportContract.test_a_report_the_contract_refuses_is_refused` (a finding with
  `"severity": "urgent"`: an error naming `severity`) and
  `tests.test_architect_triage_schema.ReportContract.test_a_report_and_a_plane_json_in_the_products_rule_ids_pass` (a
  report whose rule change cites `HR-1` under `ids.rule.pattern` `HR-[0-9]+` passes `validate_report`, and a plane.json
  `architect.checks` entry with id `HR-1` passes `schema_errors` against `contracts/plane_config.schema.json`).
- **F10.** Delete `Kind`. Its one instance's fields become constants of `ccp/architecture_review.py`, which serves the
  architect seat alone: `EVENT`, `LABEL`, `PREFIXES` (`("ar", "sh")`), `STATE`, `LOCK`, `AUDIT_TASK`, `TRIAGE_CMD`
  and `RID_RE`. `LENSES` moves from `ccp/architect.py` to the kit, with `CATEGORIES` (every lens's categories, in
  order); the kit's present `CATEGORIES` (the structure lens's) becomes `STRUCTURE_CATEGORIES`. `ccp/architect.py`
  imports `LENSES` from the kit, so `architect.LENSES` still reads. The 14 functions lose their `kind` parameter.
  `tests/test_rules.py` reads `ar.CATEGORIES`, `tests/test_obs_ids.py` reads `ar.RID_RE`. The triage contract's `da`
  review-id prefix stays (E9: old records stay readable).
- **E12.** Its text, naming the ids knobs' patterns and the one schema checker, was applied by the triage PR; this
  task builds what it says and leaves `docs/ENGINEERING.md` alone.
- No other test expectation changes; `tests.test_plane_config_defaults` compares keys and defaults, not patterns.
- "No SPEC change" is measured: `git grep -n 'E\[0-9\]' -- docs/spec` at `b6c2bc17` names only §7.1's `ids` table
  (the knob's default), which stands.

## Scope

- **In:** `contracts/architect_report.schema.json`; `contracts/architecture_review_triage.schema.json`;
  `contracts/plane_config.schema.json` (the three `pattern` members, their descriptions); `ccp/architecture_review.py`;
  `ccp/architect.py`; `tests/test_architect_triage_schema.py`; `tests/test_rules.py`;
  `tests/test_obs_ids.py`.
- **Out:** `docs/ENGINEERING.md` (E12's text landed with the triage); `ccp/config.py` (it checks `architect.checks` ids by `ids.is_rule_id` already); the finding-id and review-id
  patterns; the other contracts; the SPEC.

## dod_checks

- id: `data-01`
  story: As a product with its own id shapes, no contract pins the plane's default task-id or rule-id shape, and no code edits a contract before use.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nF -e '"pattern": "^E[0-9]+$"' -e '"pattern": "^[0-9]{4}-[a-z0-9-]+$"' -e '"pattern": "^[0-9]{4}(-|$)"' -- contracts`.
    2. Run `git grep -n '\.pop("pattern"' -- ccp`.
  expect: step 1 prints nothing and step 2 prints nothing (each git grep's exit 1, no match).
  dry run (`b6c2bc17`): step 1 printed 6 lines, exit 0; step 2 printed 2 lines, exit 0.
- id: `code-01`
  story: As the plane, an architect report is held to its contract, and one in the product's rule ids passes.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_architect_triage_schema.ReportContract.test_a_report_the_contract_refuses_is_refused tests.test_architect_triage_schema.ReportContract.test_a_report_and_a_plane_json_in_the_products_rule_ids_pass tests.test_architect_triage_schema`.
  expect: exit 0.
  dry run (`b6c2bc17`): exit 1 (`AttributeError: module 'tests.test_architect_triage_schema' has no attribute 'ReportContract'`).
- id: `code-02`
  story: As a maintainer, the review kit no longer threads a one-instance Kind through its calls.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n -e 'kind: Kind' -e 'class Kind(' -e 'ar.Kind(' -- ccp tests`.
  expect: prints nothing (git grep's exit 1, no match).
  dry run (`b6c2bc17`): printed 16 lines, exit 0.
## Implementation notes

## Verification notes
