---
task_id: 0174-config-readers-go-through-ccp
title: Hooks and scripts read plane.json through ccp's loaded configuration, never raw with their own defaults
status: pending
kind: refactor
depends_on: []
spec_refs: ["S8"]
review_refs: ["sh-20261119T170325Z-8142#F01"]
rule_refs: ["E16"]
review_point: R12
paths: ["plugin/hooks/runner-idle.sh", "scripts/observability/team.py", "scripts/gate_parallel.py", "scripts/sync-product-docs.sh", "docs/delivery/plane.json", "tests/test_parallel_hook.py", "tests/test_team_hosting.py", "tests/test_gate_cache.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0174-config-readers-go-through-ccp

## Intent

Every hook and script that needs a plane.json setting gets it from `ccp.config` as loaded, defaults
included, so when ADR-0043 changes a default (three tasks in flight, the architect on), the runner's
idle hook, the runner spawn and the gate agree with `ccp`. A docs check keeps raw plane.json reads out
of `plugin/` and `scripts/`. Nothing the plane does changes.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, finding F01 and preparatory refactor P3; house rule E16 (added in
  this triage: only `ccp/config.py` reads plane.json).
- The raw readers, `git grep -nE 'plane\.json"\)\.read_text' -- plugin scripts` at `e9ff0fc`: 4 lines.
  The shape names three; the fourth is `scripts/sync-product-docs.sh` (`architect.rules_doc`).
  - `plugin/hooks/runner-idle.sh`: `has_architect = … "architect" in pj` and
    `parallel_on = int(par.get("max_in_flight", 1)) > 1`.
  - `scripts/observability/team.py` `def max_in_flight(root)`: `max(1, int(par.get("max_in_flight", 1)))`.
  - `scripts/gate_parallel.py` `def max_age_days()`: `verify.accept_cache.max_age_days`.
  - `scripts/sync-product-docs.sh`: `architect.rules_doc`.
- How each reaches the config (decided here):
  - `team.py` and `sync-product-docs.sh` already have the plane's root (`HERE.parents[1]`, `plane`):
    they import `ccp.config` and call `config.load(<product root>)`, as `team.py`'s `refactor_log`
    does today.
  - `gate_parallel.py` runs in the checkout it gates, which is the plane's own repository: it imports
    `ccp.config` from its `ROOT`.
  - `runner-idle.sh` already asks `ccp where` for the plane's checkout (`plane`): its Python imports
    `ccp.config` from there (`sys.path.insert(0, plane)`) and reads `cfg.architect is not None` and
    `parallel.settings(cfg)["max_in_flight"]`. A managed copy run with `--ccp` and no `plane` keeps the
    fallback below.
  - Every reader keeps today's fallback when the configuration does not load (no plane.json, invalid
    JSON, a `ConfigError`): one slot, no architect, no cache age limit, no rules doc. A load's warnings
    (stderr) are not printed by the hook or the scripts, so their output is unchanged.
- The check is a `docs.checks` entry in this repo's own `docs/delivery/plane.json`, id `config-reader`,
  command `! git grep -nE 'plane\.json"\)\.read_text' -- plugin scripts`, as E14's `merge-helper` entry
  is.
- No SPEC change: the SPEC describes what the hook and spawn decide (§16.2, §19.6), not how they read
  it (`git grep -n "read_text\|raw plane.json" -- docs/spec` at `e9ff0fc` prints nothing).

## Scope

- **In:**
  - `plugin/hooks/runner-idle.sh`, `scripts/observability/team.py` (`max_in_flight`),
    `scripts/gate_parallel.py` (`max_age_days`), `scripts/sync-product-docs.sh` (`rules_doc`): each
    reads the loaded configuration as above.
  - `docs/delivery/plane.json`: the `config-reader` docs check.
  - Tests: one per reader, in the modules named in `paths`, showing it follows a value `ccp.config`
    gives (a patched default) rather than its own.
- **Out:**
  - Any default value (0180, 0185).
  - Hooks that read no plane.json setting (`orientation.sh`, `run-binding.sh`).

## dod_checks

- id: `cfg-01`
  story: As a plane developer, no hook or script reads plane.json itself, and a check keeps it so.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE 'plane\.json"\)\.read_text' -- plugin scripts`.
    2. Run `./bin/ccp --root . docs check`.
  expect: step 1 prints nothing; step 2 exits 0 and its run includes the `config-reader` check.
  dry run (`e9ff0fc`): step 1 printed 4 lines (`plugin/hooks/runner-idle.sh:232`, `scripts/gate_parallel.py:182`, `scripts/observability/team.py:66`, `scripts/sync-product-docs.sh:182`); step 2 printed `docs: clean` without a `config-reader` check.
- id: `cfg-02`
  story: As a runner, the idle hook and the spawn follow ccp's default, not a copy of it.
  setup: a separate copy of the PR head with `config.PARALLEL_DEFAULTS["max_in_flight"]` set to 2.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_parallel_hook tests.test_team_hosting`.
  expect: exits non-zero, with a failure in a test that reads `max_in_flight` for a product with no `parallel` block (the reader followed the patched default).
  dry run (`e9ff0fc`): with the same patch, both modules pass (the readers keep their own default of 1), so the expect fails today.
- id: `cfg-03`
  story: As a plane developer, the readers behave as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_parallel_hook tests.test_runner_idle_rotation tests.test_team_hosting tests.test_gate_cache tests.test_plugin`.
    2. Run `python3 -B -c "import sys; sys.path.insert(0, 'scripts'); import gate_parallel as g; print(g.max_age_days())"`.
  expect: step 1 exits 0; step 2 prints `7` (this repo's `verify.accept_cache.max_age_days`).
  dry run (`e9ff0fc`): step 2 printed `7`; step 1's modules pass (a regression guard).

## Implementation notes

*Append-only, newest last.*

## Verification notes
