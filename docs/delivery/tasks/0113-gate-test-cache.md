---
task_id: 0113-gate-test-cache
title: The plane's gate keeps a content-keyed test cache, and the plane accepts it at verify
status: done
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
- Lead ruling sm-20261117T092207Z-a36b (commit 083207b), verbatim: (1) cache-04 holds in the form `GATE_COLD=1 ccp suite run --lane gate`. The verifier records it as_written: false, held_instead naming that form, ruling naming this question. (2) Accepted: a test module imported by another test module is shared input and joins every module's key; untracked files and sys.version in the key are acceptable. The implementer appends an Implementation note to the task file citing this ruling. No SPEC change beyond describing the cache as built. Also append the note to the task file's Context (not checked) section. Make no other change.

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

- 2026-11-17 (implementer): `scripts/gate_parallel.py` keys each module on the SHA-256 of its own
  content, its name, the interpreter's version and one digest of the shared inputs: `git ls-files -s`
  of every tracked path with the working tree's edits (`git ls-files -m`) and untracked, unignored
  files (`git ls-files -o --exclude-standard`) folded in as the blob git would stage, read-only (no
  index, object or stash write; an unchanged file folds to its own index entry, so stat data never
  moves the key). Left out of the shared digest: the test modules no other test module names. A test
  module another imports (by `tests.test_x`, `from tests import`, `from .`) is a shared input: 69
  modules import one, so the literal "except tests/test_*.py" would serve stale passes after an
  edit to a helper such as `tests/test_toolkit.py` (flagged to the runner). Untracked files are in
  the key too, for the same soundness. An entry is `{key, passed, tests, seconds, at}` in
  `GATE_CACHE_DIR` (default `~/.cache/ccp-gate/<sha256 of the root commits, 16 hex>`, shared by
  every worktree and clone; one inside the repo exits 2); one older than plane.json
  `verify.accept_cache.max_age_days` is no hit. A git failure runs with no cache.
- The cold option is the gate's own `GATE_COLD=1` (`GATE_COLD=1 ccp suite run --lane gate`): `ccp
  suite run` has no `--cold` flag at 73457e8, and adding one is outside this task's paths (open
  question in the report). A cold run reads and writes nothing and counts `cached 0`, which `ccp`
  records `cold: true`.
- `scripts/gate_result.py` gives `ran`, `cached` and `cached_tests`; a cached module is in neither
  `tests` nor `modules` (health's module times stay those of modules that ran).
- Outside the paths, docs only: `scripts/CLAUDE.md` names the cache and its knobs; `docs/ENGINEERING.md`'s
  known-intentional line "no per-module cache" became false and now describes the coarse key.
- 2026-11-17 (implementer, ruling round 1): ruling sm-20261117T092207Z-a36b (commit 083207b)
  settles both open questions with no code change. (1) `cache-04` holds in the form
  `GATE_COLD=1 ccp suite run --lane gate`, the gate's own cold option as built; the verifier records
  it `as_written: false` with `held_instead` naming that form. (2) The key as built is accepted: a
  test module another test module imports is shared input and joins every module's key, and
  untracked files and `sys.version` stay in the key. No SPEC change: the ruling allows one only to
  describe the cache as built, and none was needed.

## Verification notes
- 2026-11-17 — verifier, PR #120 head `a0cbbbc` (close's catch-up of the approved `7ac21d2`, gate run st-20261117T100951Z-4b21b5) (squash `5ed024a`): APPROVE. Passed: cache-01, cache-02, cache-03, cache-04, suite-01. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0113-gate-test-cache.json.

