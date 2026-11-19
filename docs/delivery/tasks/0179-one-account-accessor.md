---
task_id: 0179-one-account-accessor
title: One accessor reads the account's allowance command, weekly stop, windows and session knobs
status: pending
kind: refactor
depends_on: []
spec_refs: ["S25"]
review_refs: ["sh-20261119T170325Z-8142#F02"]
rule_refs: ["E12"]
review_point: R12
paths: ["ccp/usage.py", "ccp/parallel.py", "tests/test_account_accessor.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0179-one-account-accessor

## Intent

The facts about the Claude account on the machine (the allowance command, the weekly stop, the usage
windows, the session park and wake, the parallel session ceiling) are read through one function in
`ccp/usage.py`, so when ADR-0043 moves them from each product's plane.json to one file per machine
(0186) it changes that function and no reader. Nothing the plane does changes.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, preparatory refactor P8 (it serves ADR-0043 D8; the shape cites no
  finding for it, so this task cites F02, the one-source finding it follows).
- The readers, `git grep -nE "get\(\"(allowance_cmd|allowance_stop_weekly|session_park_pct|session_wake_arm_pct|session_wake_margin_s)\"|\[\"session_ceiling_pct\"\]|get\(\"windows\"\) or \{\}" -- ccp ':(exclude)ccp/config.py'`
  at `e9ff0fc`: 10 lines: `ccp/parallel.py` 2 (`allowance_cmd` in the usage-rule test, `session_ceiling_pct`
  in rule 5), `ccp/usage.py` 8 (the windows, the sampler, the park and wake, the status line).
- `telemetry.design_seat` is not an account fact and is not read through it (0187 derives it from the
  lead's model).
- Decided here: `usage.account(cfg) -> dict` returns `allowance_cmd`, `stop_weekly`, `windows` (the
  two built-in windows merged with `telemetry.windows`, as the windows reader builds them today),
  `park_pct`, `wake_arm_pct`, `wake_margin_s` and `ceiling_pct`, each with today's default and
  today's handling of a null or bad value. Every reader above takes its value from it.
- No SPEC change: the SPEC names the keys, not the function
  (`git grep -n "def account\|usage.account" -- docs/spec` at `e9ff0fc` prints nothing).

## Scope

- **In:**
  - `ccp/usage.py`: `account(cfg)`; its readers through it.
  - `ccp/parallel.py`: the usage-rule test and rule 5's ceiling through it.
  - `tests/test_account_accessor.py` (new): `account` for a config with no telemetry or parallel
    block, with each key set, and with `session_park_pct: null`.
- **Out:**
  - Where the facts live (0186), and any default (the weekly stop's 90% is 0186's).

## dod_checks

- id: `acct-01`
  story: As a plane developer, the account facts are read in one function.
  setup: a checkout of the PR head.
  steps:
    1. Run the `git grep -nE …` command in Context against the head.
  expect: every line printed is in `ccp/usage.py`, inside `def account`.
  dry run (`e9ff0fc`): 10 lines, 2 in `ccp/parallel.py` and 8 in `ccp/usage.py` in five functions.
- id: `acct-02`
  story: As a plane developer, the accessor gives today's values.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -c "from ccp import usage, config; from pathlib import Path; c = config.Config(root=Path('.'), project_id='x', task_log={}, package_docs=None, telemetry=config.TELEMETRY_DEFAULTS, parallel=config.PARALLEL_DEFAULTS); a = usage.account(c); print(a['park_pct'], a['wake_arm_pct'], a['wake_margin_s'], a['ceiling_pct'], a['stop_weekly'], a['allowance_cmd'])"`.
  expect: the six values printed equal 95, 50, 180, 60, None and None (each number an int or a float).
  dry run (`e9ff0fc`): raised `AttributeError: module 'ccp.usage' has no attribute 'account'`.
- id: `acct-03`
  story: As a plane developer, the usage, park and parallel rules behave as before, and the tests bite.
  setup: a checkout of the PR head; then a separate copy with `account` returning `ceiling_pct` 100 always.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_account_accessor tests.test_usage tests.test_allowance_windows tests.test_allowance_lapse tests.test_session_park tests.test_parallel_slots tests.test_forecast`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_parallel_slots tests.test_account_accessor`.
  expect: step 1 exits 0; step 2 exits non-zero.
  dry run (`e9ff0fc`): step 1's existing modules pass at the base.

## Implementation notes

*Append-only, newest last.*

- `usage.account(cfg)` builds all seven facts eagerly from `cfg.telemetry` and `cfg.parallel`, each with the
  default and the null/bad-value handling its reader had (`park_pct` and `wake_arm_pct` through `_num_or_none`,
  the arm falling back to the default on 0 or null; `wake_margin_s` an int or the default; `windows` the
  merge `window_rules` built). `window_rules` and `session_settings` now return from it.
- `ceiling_pct` is the raw `parallel.session_ceiling_pct`; rule 5 still applies `float()` to it, as before.
  It reads `getattr(cfg, "parallel", None)`, because several existing tests pass a `SimpleNamespace`
  carrying only `telemetry` to `session_settings`; a `Config` always has the attribute.
- `ccp/parallel.py` now imports `ccp.usage` at module level (it had no import of it; `usage` imports
  `parallel` only inside functions, so no cycle).
- `tests/test_account_accessor.py` (new) covers the defaults (no block, `None`, the built-in defaults),
  each key set, `session_park_pct: null`, bad wake values, the window merge, and the two `parallel` readers.

## Verification notes
