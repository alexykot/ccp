---
task_id: 0226-one-pr-host-module-github-only
title: One PR-host module owns every gh call and returns normalised PR facts, behaviour unchanged
status: pending
kind: refactor
depends_on: []
review_refs: ["sh-20261120T235116Z-eb9f#F01", "sh-20261120T235116Z-eb9f#F05", "sh-20261120T235116Z-eb9f#F07"]
rule_refs: ["E19", "E15", "E12"]
review_point: R15
paths: ["ccp/prhost.py", "ccp/lifecycle.py", "ccp/verify.py", "ccp/prompt.py", "ccp/config.py", "contracts/plane_config.schema.json", "tests/test_prhost.py", "tests/test_verify.py", "tests/test_verify_as_written.py", "tests/test_verify_producer.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0226-one-pr-host-module-github-only

## Intent

The first step of ADR-0040, taken as a refactor: every call the plane makes to the GitHub CLI moves
into one module, `ccp/prhost.py`, which returns a PR as plain normalised facts. Close, drop, the
catch-up, merge-ok and the review's body gate stop reading GitHub's JSON field names and state
values. Nothing a product sees changes; the feature tasks that follow (0220, 0221, 0222) then add
`ccp pr`, move the prompts and add the local adapter by touching one file.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0040 (`sh-20261120T235116Z-eb9f`): F01 (GitHub's PR JSON read across three
  modules), F05 (merge-ok's unit tests fake a subprocess), and the code half of F07 (the default
  merge argv written in four places).
- **The gh calls.** `git grep -n 'CCP_GH_BIN' -- ccp` at `8aefa59`: five lines in `ccp/lifecycle.py`
  (`def _gh`, `def _merge`), `ccp/prompt.py` (`def body_gate`) and `ccp/verify.py` (`def _pr_facts`).
  `def _pr_state` in `ccp/lifecycle.py` runs `gh pr view … --json state,headRefOid,headRefName,mergeCommit`.
- **GitHub's names outside the call sites.** `git grep -nE 'headRefName|mergeCommit|"MERGED"|"OPEN"' -- ccp`
  at `8aefa59` lists the readers: `tasks drop` (`_pr_state(cfg, pr).get("state") == "MERGED"`),
  close (`already = facts.get("state") == "MERGED"`, the merge commit's `oid`), the catch-up
  (`facts.get("headRefName")`) and `merge_ok` (`if state != "OPEN":`, `mergedAt`).
- **The test stubs** set `CCP_GH_BIN` (`git grep -l CCP_GH_BIN -- tests` at `8aefa59`: eight files)
  and keep working: the module reads it. Three verify modules write the same `cat pr.json` script to
  feed `merge_ok` four values (`tests/test_verify.py`, `tests/test_verify_as_written.py`,
  `tests/test_verify_producer.py`).
- **The default merge argv** is written in `docs/spec/02-delivery.md` §15.5, `ccp/config.py`
  (`MERGE_DEFAULTS`'s comment), `contracts/plane_config.schema.json` (`merge.command`'s description)
  and `ccp/lifecycle.py` (`_merge`'s docstring). The SPEC copy changes in 0220 (signed); this task
  moves the others to point at the adapter.
- A refactor: no SPEC change, no new command, no change to any refusal's wording except where it
  named `gh printed no JSON` (one message, from the module).

## Scope

- **In:** `ccp/prhost.py` (new), `ccp/lifecycle.py`, `ccp/verify.py`, `ccp/prompt.py`,
  `ccp/config.py`, `contracts/plane_config.schema.json`, `tests/test_prhost.py` (new),
  `tests/test_verify.py`, `tests/test_verify_as_written.py`, `tests/test_verify_producer.py`.
- **`ccp/prhost.py`**: a `PrFacts` value (`number`, `state` one of `open`, `merged`, `closed`,
  `head`, `branch`, `merged_at`, `merge_commit`, `body`), a `HostError` and its `HostUnavailable`
  subclass (replacing `verify.NoGh`), and the GitHub adapter's `view(cfg, pr)`, `merge(cfg, pr, head,
  task_id)` (with `merge.command` still overriding it, its child env unchanged) and `confirm(cfg,
  pr)`. It alone reads `CCP_GH_BIN`, and it alone holds the `gh pr merge … --squash
  --match-head-commit` argv.
- **The callers** (`_merge`, `_pr_state`, `tasks drop`, close, the catch-up, `_pr_facts`/`merge_ok`,
  `body_gate`) read only `PrFacts`.
- **merge-ok's decision** takes `PrFacts` and the record as plain values (`merge_ok_reasons(facts,
  rec, …)`), the read stays in `merge_ok`; the three verify test modules call the decision directly
  instead of writing a fake `gh`. The GitHub argv and JSON are tested once, in `tests/test_prhost.py`.
- `MERGE_DEFAULTS`' comment, the schema's `merge.command` description and `_merge`'s docstring name
  "the PR host's merge" instead of the argv.
- **Out:** `ccp pr` and the SPEC (0220), the prompts (0221), the local adapter (0222), the shared
  fake `gh` of `ToolkitFixture` (0227).

## dod_checks

- id: `pm-01`
  story: As a plane developer, the GitHub adapter is tested once, on its own.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prhost 2>&1 | tail -15`.
  expect: exit 0; tests for `view`, `merge` (with and without `merge.command`), `confirm` and a missing
    binary (`HostUnavailable`) are listed `ok`.
  dry run: n/a — the module is new.

- id: `pm-02`
  story: As the plane, no module but the PR-host module reaches gh or reads GitHub's names.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE 'CCP_GH_BIN|headRefOid|headRefName|mergeCommit' -- ccp ':(exclude)ccp/prhost.py'`.
  expect: prints nothing.
  dry run (`8aefa59`): prints eleven lines (six in `ccp/lifecycle.py`, two in `ccp/prompt.py`, three in `ccp/verify.py`).

- id: `pm-03`
  story: As a runner on a GitHub product, close, drop, merge-ok and the body gate behave as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_prompt_pr_body tests.test_verify tests.test_verify_as_written tests.test_verify_producer tests.test_wt tests.test_sign_off 2>&1 | tail -3`.
  expect: exit 0, `OK`; no expectation changed but the merge-ok tests' setup (plain values instead of a
    fake `gh`).
  dry run (`8aefa59`): `OK`.

- id: `pm-04`
  story: As a plane developer, the merge-ok decision's tests bite on plain values.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    decision no longer refuses a PR whose state is not `open`.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_verify`.
  expect: at least one failure.
  dry run: n/a — the decision function is new.

## Implementation notes

## Verification notes
