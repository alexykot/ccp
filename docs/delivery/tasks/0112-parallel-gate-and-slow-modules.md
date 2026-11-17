---
task_id: 0112-parallel-gate-and-slow-modules
title: The plane's gate runs test modules in parallel, and health reports the slowest modules and the time per test
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S27"]
review_point: R7
paths: ["scripts/gate.sh", "scripts/gate_result.py", "scripts/gate_parallel.py", "contracts/suite_result.schema.json", "ccp/health.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "tests/test_gate*.py", "tests/test_health_suite.py"]
adopt: "none for the plane itself; a product reads the new health lines with no change, and may copy the parallel gate"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0112-parallel-gate-and-slow-modules
## Intent

The plane's own gate finishes in a fraction of its serial time, and `ccp health` shows which test
modules are slowest and how the time per test is trending, so growth is seen before it costs hours.

## Context (not checked)

- From an accepted plane proposal. A telemetry analysis of 9–16 Nov reported that suite runs took most of the implementer's and verifier's active time, and that the full suite's time per test rose through the week (`ccp health --since 2026-11-09` shows the suite series it read).
- The serial gate is `scripts/gate.sh`: one `python3 -m unittest discover` process, then a check that no test left a `state/*` branch.
- Tests are fenced (`tests/__init__.py`): each makes its own scratch repositories and queue, so modules can run in separate processes. The implementer confirms no module shares state with another (a fixed path, a port, the real `HOME`), and runs any that does in a serial group.
- The gate-result contract only gains optional fields (§29.3), so the per-module timings are description of this task's own feature (§31.1); no rule changes.

## Scope

- **In:**
  - `scripts/gate_parallel.py` (new), called by `scripts/gate.sh`: runs each `tests/test_*.py` module in its own process, `GATE_WORKERS` at a time (default: the CPU count), with a `SERIAL` list in the script for modules that must run alone; prints each module's result and seconds; exits non-zero when any module fails or errors; the `state/*` check stays after all modules.
  - `scripts/gate_result.py`: the result file gains `modules`, a list of `{name, seconds, tests}`.
  - `contracts/suite_result.schema.json`: the optional `modules` field.
  - `ccp health` (`ccp/health.py`): from the latest cold gate runs that carry `modules`, the `health.slowest_modules` slowest (default 5) with seconds, and the median seconds per test over the last `health.suite_trend_runs` cold runs (default 10) with the first and latest; `suite_modules` in `--json`. Knobs in `ccp/config.py` and the schema.
  - SPEC text describing the new field (§14.3) and health lines (§27.2), marked `§31.1` in the PR body.
- **Out:**
  - A test cache (task 0113).
  - Changing any product's gate.

## dod_checks

- id: `speed-01`
  story: As a worker, the plane's gate finishes in at most half its serial time.
  setup: a checkout of the PR head on the operator's machine with nothing else running a suite.
  steps:
    1. Run the serial command `python3 -m unittest discover -s tests -t .` through `ccp suite run --lane part` and note its seconds.
    2. Run `scripts/gate.sh` through `ccp suite run --lane gate` and note its seconds.
  expect: the second run's seconds are at most 50% of the first's, and both pass with the same test count.
  dry run: n/a.
- id: `gate-01`
  story: As a verifier, a failing module fails the parallel gate.
  setup: a separate copy of the PR head (not the branch's worktree) with one assertion in one test module inverted.
  steps:
    1. Run `scripts/gate.sh` in that copy.
  expect: exit non-zero, naming the failing test and its module; the result file's counts show one failure.
  dry run: n/a.
- id: `gate-02`
  story: As a plane developer, the result file carries per-module timings.
  setup: the passing run of `speed-01`.
  steps:
    1. Read the run's result file.
  expect: `modules` lists every `tests/test_*.py` module, each with seconds and a test count, and the counts sum to the run's `tests`.
  dry run: n/a.
- id: `cmd-01`
  story: As a task-log owner, health shows the slowest modules and the trend.
  setup: a scratch queue with three cold gate runs carrying `modules`.
  steps:
    1. Run `ccp health` and `ccp health --json`.
  expect: the five slowest modules of the latest run with seconds, and the median seconds per test for the first and latest runs; the same data under `suite_modules` in JSON.
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

## Verification notes
