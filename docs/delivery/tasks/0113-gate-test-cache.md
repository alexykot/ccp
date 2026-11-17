---
task_id: 0113-gate-test-cache
title: The plane's gate keeps a content-keyed test cache, and the plane accepts it at verify
status: pending
kind: feature
depends_on: ["0112-parallel-gate-and-slow-modules"]
spec_refs: ["S14", "S15"]
review_point: R7
paths: ["scripts/gate.sh", "scripts/gate_parallel.py", "scripts/gate_result.py", "docs/delivery/plane.json", "tests/test_gate*.py"]
adopt: "none for products; the plane sets verify.accept_cache for itself"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0113-gate-test-cache
## Intent

A verifier gating the head the implementer already gated green is served from a cache instead of
re-running the whole suite, and a change that touches one test module re-runs only what it can
affect. The plane turns on `verify.accept_cache` for itself.

## Context (not checked)

- From an accepted plane proposal. A telemetry analysis of 9–16 Nov reported that verifiers spent many hours re-running full suites at heads already gated green (`ccp usage` by seat gives the verifier's suite time).
- `verify.accept_cache` (§15) counts a test unit the verifier's gate run reports as a cache hit as run and passed. The plane's gate has no cache, so the knob is off for the plane.
- The cache key is the task's choice and must be sound: a module's result is reused only when nothing it can read has changed. The key below is deliberately coarse: everything tracked except other test modules.
- Cold runs: `ccp suite run --cold` (§15) asks the product's cold option; the gate reads it and uses no cache.

## Scope

- **In:**
  - `scripts/gate_parallel.py`: before running a module, look up its key: the SHA-256 of the module file's content plus `git ls-files -s` of every tracked path except `tests/test_*.py` (staged and working-tree changes folded in through `git stash create` or the index, so an uncommitted edit changes the key). A hit whose recorded result passed is reported as cached and not run. A miss runs and records `{key, passed, tests, seconds, at}` on a pass. The cache directory is `GATE_CACHE_DIR`, default `~/.cache/ccp-gate/<repo id>`, outside the repository.
  - The cold option: the gate takes the plane's existing cold flag from `ccp suite run --cold` and then reads and writes no cache.
  - `scripts/gate_result.py`: `ran` and `cached` module counts, as §15 reads them.
  - `docs/delivery/plane.json`: `verify.accept_cache: {"max_age_days": 7}`.
- **Out:**
  - A finer key (per-module imports): this task keeps the coarse key.

## dod_checks

- id: `cache-01`
  story: As a verifier, a repeat gate at unchanged inputs is served from the cache.
  setup: a checkout of the PR head with an empty cache directory.
  steps:
    1. Run `scripts/gate.sh` through `ccp suite run --lane gate` twice.
  expect: the first reports `cached 0`; the second reports every module cached, `ran 0`, and passes; `git status --porcelain` and `git stash list` print the same before and after both runs (computing the key leaves the index and stash list unchanged).
  dry run: n/a.
- id: `cache-02`
  story: As an implementer, editing one test module re-runs only it.
  setup: after `cache-01`, in a separate copy of the head with the same cache directory, one test module edited by a comment line.
  steps:
    1. Run `scripts/gate.sh` there.
  expect: exactly that module ran; every other module is cached.
  dry run: n/a.
- id: `cache-03`
  story: As a verifier, a source change invalidates every module.
  setup: after `cache-01`, in a separate copy of the head, one line of a `ccp/` module changed by a comment.
  steps:
    1. Run `scripts/gate.sh` there.
  expect: `cached 0`.
  dry run: n/a.
- id: `cache-04`
  story: As a verifier with a cold task, the cold option uses no cache.
  setup: after `cache-01`.
  steps:
    1. Run the gate through `ccp suite run --lane gate --cold`.
  expect: `cached 0` and the run is recorded `cold: true`.
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
