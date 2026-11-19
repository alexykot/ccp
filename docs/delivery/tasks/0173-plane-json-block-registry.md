---
task_id: 0173-plane-json-block-registry
title: One registry of plane.json blocks and their defaults, and one test that holds the schema to it
status: pending
kind: refactor
depends_on: []
spec_refs: ["S8"]
review_refs: ["sh-20261119T170325Z-8142#F02"]
rule_refs: ["E12"]
review_point: R12
paths: ["ccp/config.py", "contracts/plane_config.schema.json", "tests/test_plane_config_defaults.py", "tests/test_parallel_defaults.py", "tests/test_toolkit.py", "tests/test_adr.py", "tests/test_health.py", "tests/test_mutate.py", "tests/test_report_fields.py", "tests/test_rules.py", "tests/test_usage_advice.py", "tests/test_prompt_audit.py"]
clashes_with: ["0176-language-pack-owns-test-facts"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0173-plane-json-block-registry

## Intent

Each plane.json block's keys and defaults are written once, in one registry in `ccp/config.py`; the
block list and the merge of each block derive from it; and one test compares every block's keys and
defaults with `contracts/plane_config.schema.json`. When ADR-0043 removes keys, merges them or makes
them constants, each change is checked as it lands. Nothing the plane does changes.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, finding F02 and preparatory refactor P2; house rule E12 (amended in
  this triage: one test compares every block's keys and defaults with the schema).
- At `e9ff0fc`:
  - The block list is written three times: `BLOCKS` in `ccp/config.py`, the hand-written
    `_merge(<BLOCK>_DEFAULTS, raw.get(...), ...)` lines in `_toolkit`
    (`git grep -n '_merge(' -- ccp/config.py | wc -l`: 29 lines, definition and calls), and the
    schema's `properties`.
  - The schema has 106 `default` entries (counted by walking the JSON).
  - Key sets are already compared for about 16 blocks, by separate tests in separate modules:
    `git grep -nE 'schema\["properties"\]\["[a-z_]+"\]\["properties"\]' -- tests` lists 20 lines (adr,
    health, mutate, parallel, prompts, report, verify, architect, usage and others). Default values
    are compared for `parallel` alone (`tests/test_parallel_defaults.py`). The shape's "one block of
    28" counts default values, not key sets.
  - Drift between code and schema, measured by comparing each `<BLOCK>_DEFAULTS` with the schema
    (a one-off script at `e9ff0fc`): key sets agree for every block except `estimate`
    (`estimate.calibration` is in `ESTIMATE_DEFAULTS` and read by `ccp/calibrate.py`, and the schema
    has no such property); no `default` value disagrees; 31 keys carry no `default` in the schema
    (task_log 1, prompts 4, reconcile 2, adapter 3, worktrees 2, env 5, merge 1, auth_check 1,
    telemetry 4, board 1, usage 1, suite 5, verify 1). `ids` has its defaults in
    `ccp/refs.py` (`IDS_DEFAULTS`), not in config.
- Decided here:
  - The registry is `config.BLOCK_DEFAULTS`, a dict from block name to its defaults dict, in the
    order `BLOCKS` has today. `BLOCKS` is `tuple(BLOCK_DEFAULTS)`. `ids` maps to `refs.IDS_DEFAULTS`.
    The `*_DEFAULTS` names stay, as the registry's values, so no caller changes.
  - `_toolkit` merges every block whose loader is the plain `_merge` in one loop over the registry;
    the blocks with their own loader (`suite`, `usage`, `task_log`, `package_docs`, `architect`,
    `adr`, `docs`, `upgrade`, `ids`) keep it.
  - The schema follows the code, never the reverse: it gains `estimate.calibration` (an object of
    `half_life`, `min_pairs`, `k`, with the code's defaults) and a `default` on each of the 31 keys,
    equal to the code's value. This adds only an optional key (§29.3).
  - `tests/test_plane_config_defaults.py` (new) is the one comparison: for every block in the
    registry, the schema's property names equal the defaults' keys, and each schema `default` equals
    the code's value; nested defaults (`usage.advice`, `estimate.calibration`,
    `verify.accept_cache`, `suite.summary`) are compared the same way where the code has a dict for
    them. The per-block key-set asserts it replaces are removed: `tests/test_toolkit.py`
    (`test_plane_config_schema_lists_every_block`), `tests/test_adr.py`, `tests/test_health.py`,
    `tests/test_mutate.py`, `tests/test_report_fields.py`, `tests/test_rules.py`
    (`test_plane_config_schema_has_every_architect_key`), `tests/test_usage_advice.py`,
    `tests/test_prompt_audit.py`, and the schema half of `tests/test_parallel_defaults.py` (its
    `parallel.settings` half stays). These are the only test expectations this refactor changes.
- No SPEC change: the SPEC names neither `BLOCKS` nor the merge (`git grep -n "BLOCKS\|_toolkit" -- docs/spec`
  at `e9ff0fc` prints nothing). §8.1's block table is unchanged.

## Scope

- **In:**
  - `ccp/config.py`: `BLOCK_DEFAULTS`; `BLOCKS` derived; `_toolkit`'s plain merges in one loop.
  - `contracts/plane_config.schema.json`: `estimate.calibration`; a `default` on the 31 keys.
  - `tests/test_plane_config_defaults.py` (new); the removals listed in Context.
- **Out:**
  - Removing, merging or moving any key, and any default value change (0180 onwards).
  - `contracts/project.schema.json` (0175).

## dod_checks

- id: `reg-01`
  story: As a plane developer, the block list and the merges come from one registry.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -c "from ccp import config; print(config.BLOCKS == tuple(config.BLOCK_DEFAULTS))"`.
    2. Run `git grep -n '_merge(' -- ccp/config.py | wc -l`.
  expect: step 1 prints `True`; step 2 prints a number below 12.
  dry run (`e9ff0fc`): step 1 raised `AttributeError: module 'ccp.config' has no attribute 'BLOCK_DEFAULTS'`; step 2 printed 29.
- id: `reg-02`
  story: As a plane developer, one test holds every block's keys and defaults to the code, and the schema already agrees.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_plane_config_defaults`.
    2. Run `python3 -B -c "import json; s=json.load(open('contracts/plane_config.schema.json')); print('calibration' in s['properties']['estimate']['properties'])"`.
  expect: step 1 exits 0; step 2 prints `True`.
  dry run (`e9ff0fc`): step 1 n/a (new module); step 2 printed `False`.
- id: `reg-03`
  story: As a plane developer, the test bites on a key and on a default.
  setup: two separate copies of the PR head: one with the schema's `suite.log_keep_days` default changed from 14 to 15; one with a key `"extra": 1` added to `config.HEALTH_DEFAULTS`.
  steps:
    1. In each copy, run `python3 -B -m unittest -q tests.test_plane_config_defaults`.
  expect: each run exits non-zero, the failure naming the block (`suite`, `health`).
  dry run: n/a — new module.
- id: `reg-04`
  story: As a plane developer, the per-block copies of the comparison are gone, and loading behaves as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE 'set\(schema\["properties"\]\["[a-z_]+"\]\["properties"\]\)' -- tests`.
    2. Run `python3 -B -m unittest -q tests.test_toolkit tests.test_config_unknown_keys tests.test_parallel_defaults tests.test_adr tests.test_rules`.
    3. Run `git diff --name-only origin/main...HEAD -- ccp scripts plugin docs`.
  expect: step 1 prints nothing; step 2 exits 0; step 3 prints only `ccp/config.py`.
  dry run (`e9ff0fc`): step 1 printed 7 lines (`tests/test_adr.py:146`, `tests/test_health.py:336`, `tests/test_mutate.py:880`, `tests/test_report_fields.py:284`, `tests/test_rules.py:397`, `tests/test_usage_advice.py:301`, `tests/test_prompt_audit.py:97`); step 2's modules pass.

## Implementation notes

*Append-only, newest last.*

## Verification notes
