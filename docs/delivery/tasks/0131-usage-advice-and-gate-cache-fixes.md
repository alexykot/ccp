---
task_id: 0131-usage-advice-and-gate-cache-fixes
title: Usage advice waits for a worker run and counts only the lead's own calls, and the gate cache records a pass only after the branch check
status: done
kind: feature
depends_on: []
spec_refs: ["S24", "S27"]
review_point: R8
paths: ["ccp/usage.py", "ccp/health.py", "scripts/gate.sh", "scripts/gate_parallel.py", "tests/test_usage*.py", "tests/test_health.py", "tests/test_gate_cache.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0131-usage-advice-and-gate-cache-fixes
## Intent

`ccp usage` advice is right when it fires, health's guards are pinned by tests, and the plane's
gate cache never serves a pass for a module whose run failed the gate's `state/*` check.

## Context (not checked)

- The coordination-share advice fires at a full share when no worker has run yet; the lead's median context
  includes helper calls (requests on a model other than the session's main model).
- No test pins health's two `None` guards (a damaged telemetry sink; no `QUEUE_ROOT`).
- A docstring in the usage module was spliced into the middle of another.
- The gate cache records a module's pass before `scripts/gate.sh` checks for leaked `state/*`
  branches, so a module that leaked one is later served from cache once the branch is gone.
- `FROM_PKG_RE` (`from tests import x`, `from . import x`) is pinned by no test; an untracked nested
  directory turns the cache off for the run.
- No SPEC change: `git grep -n -E 'coordination_share|accept_cache' -- docs/spec/` at `b4de6ad`
  finds the knobs, and neither rule says when advice fires with no worker run or what the cache
  records before the branch check; the fixes match the rules' intent.

## Scope

- **In:**
  - `ccp/usage.py`: the coordination advice needs at least one worker run in the window; the lead's
    median context counts only requests on the session's main model; the spliced docstring fixed.
  - `tests/test_health.py`: the two `None` guards pinned.
  - `scripts/gate.sh`, `scripts/gate_parallel.py` (the cache): a module's pass is recorded only after the
    `state/*` check passes; files in an untracked nested directory are hashed into the key instead of
    turning the cache off; an unreadable untracked file still turns it off, named on stderr.
  - `tests/test_gate_cache.py`: `FROM_PKG_RE`'s two forms pinned.
- **Out:**
  - The advice thresholds' defaults.

## dod_checks

- id: `usage-01`
  story: As a lead, I get no coordination advice before any worker ran.
  setup: a scratch telemetry sink holding only lead and runner requests.
  steps:
    1. Run `ccp usage --json`.
  expect: no coordination-share advice; with one implementer request added, the share is computed and advised past its threshold.
  dry run: n/a.
- id: `usage-02`
  story: As a lead, my median counts my own calls.
  setup: a sink with three lead requests on the main model at contexts 100000, 200000, 300000 and two on another model at 1000.
  steps:
    1. Run `ccp usage --json`.
  expect: the lead's median context is 200000.
  dry run: n/a.
- id: `health-01`
  story: As a developer, health's guards stay.
  setup: a checkout of the PR head.
  steps:
    1. Run the two new tests in `tests/test_health.py` with each guard removed in a scratch copy.
  expect: each test fails with its guard removed and passes with it.
  dry run: n/a.
- id: `cache-01`
  story: As a gate, a leaking module is never cached.
  setup: a scratch repo with the plane's gate and a test module that passes but leaves a `state/x` branch.
  steps:
    1. Run the gate, delete `state/x`, run the gate again.
  expect: both runs fail the branch check or run the module; the second never serves it from cache.
  dry run: n/a.
- id: `cache-02`
  story: As a gate, an untracked nested directory keeps the cache on.
  setup: the plane's checkout with an untracked `tests/tmpdir/x.txt`.
  steps:
    1. Run the gate twice, and the `FROM_PKG_RE` tests.
  expect: the second run serves cached modules and its stderr does not say the cache is off; changing `x.txt` changes the key; the tests pass.
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

- 2026-11-17, implementer: `ccp/usage.py`: `cost_advice` takes `worker_runs` (the runs with requests in the
  fold) and gives the coordination line only when it is at least one. The lead's (`design-seat`) contexts
  are kept apart in the fold and filtered by `main_model_contexts`: per `session_id`, the main model is the
  one carrying most of that session's tokens (ties broken by model name); only calls on it enter the
  lead's median. The runner's and workers' contexts are unchanged. The module docstring's cost-advice
  sentence now ends its paragraph and the "It also keeps" text is its own paragraph.
- `tests/test_health.py` `UsageAdviceGuards`: a sink of bytes that are not text makes `usage.fold` raise,
  so the `try` guard is what keeps `usage_advice` at `None`; the no-queue guard is pinned by asserting
  `usage_advice` is never called with no queue (without the `if q` the `try` would hide the `TypeError`).
- `scripts/gate_parallel.py`: `run_one` no longer records; after every module has ended `main` records the
  passes only when `git branch --list 'state/*'` prints nothing (`branches_left`; a git failure counts as
  a branch left). gate.sh's check stays the gate's failure.
- Premise found narrower than stated: a plain untracked directory (`tests/tmpdir/x.txt`) already kept the
  cache on at e130905, since `git ls-files -o` lists its files one by one. The cache went off only for a
  directory git lists whole, a nested repository (`tests/tmpdir/`), whose `read_bytes` raised
  `IsADirectoryError`. Such a directory is now walked (`_files_under`): every file folded in by content,
  its `.git` left out, a symbolic link hashed as a link and never followed. An unreadable file still
  raises `OSError`, whose message names the path, so the cache is off for the run with the file named on
  stderr, as before; no new code for it, one test pins it.

## Verification notes
- 2026-11-17 — verifier, PR #138 head `beae7f7` (squash `96d36f7`): APPROVE. Passed: usage-01, usage-02, health-01, cache-01, cache-02, suite-01. Gate: `ccp suite run --lane gate (scripts/gate.sh)` exit 0. Record: verification/0131-usage-advice-and-gate-cache-fixes.json.

