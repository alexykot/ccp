---
task_id: 0144-spec-paths-default-includes-docs-spec-md
title: task_log.spec_paths defaults to the same SPEC files as estimate.spec_paths, docs/SPEC.md included
status: done
kind: feature
depends_on: []
spec_refs: ["S3"]
review_point: R9
sign_off: brief
paths: ["ccp/config.py", "docs/spec/01-model.md", "tests/test_tasklog_spec_signoff.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-18
---

# Task: 0144-spec-paths-default-includes-docs-spec-md
## Intent

In a product adopted by `ccp init`, whose SPEC is `docs/SPEC.md`, a task whose `paths` name that file
is held to §3.5 like any other SPEC change: `ccp tasks check` warns when it carries neither a `brief`
sign-off nor `§31.1`, and `ccp verify spec-text` reads the lines the branch adds there.

## Context (not checked)

- Reported while re-adopting a product under an earlier plane generation; split out of task 0136
  because §3.5 states the default, so changing it changes a § rule.
- At `921507e`: `TASK_LOG_DEFAULTS` in `ccp/config.py` has `"spec_paths": ["docs/spec/", "SPEC.md"]`;
  the estimator's default (`def _spec_files` in `ccp/estimator.py`, and `ccp/config.py`'s
  estimate defaults) is `["docs/SPEC.md", "SPEC.md", "docs/spec/*.md", "spec/*.md"]`
  (`git grep -n spec_paths -- ccp/config.py ccp/estimator.py`). `ccp init` writes `docs/SPEC.md`
  (`COPIES` in `ccp/init.py`), which the task-log default does not meet.
- The task-log entries are paths and directory prefixes (an entry ending in `/`), the estimator's
  are globs; the new default names the same files in the task log's form.
- The default also widens what `ccp verify spec-text` reads (§15.2, `task_log.spec_paths`); a
  product that sets `task_log.spec_paths` sees no change. This repo's `docs/delivery/plane.json`
  sets none and has no `docs/SPEC.md` or `spec/`, so its own checks see no change.

## Rule changes (signed at tasking)

One § rule changes: §3.5's stated default for `task_log.spec_paths`. The exact CURRENT → PROPOSED
text is the first Scope item below, where `ccp verify spec-text` reads it.

## Scope

- **In:**
  - `docs/spec/01-model.md` §3.5. CURRENT (at `921507e`): "(plane.json `task_log.spec_paths`, default `["docs/spec/", "SPEC.md"]`;" PROPOSED:
    > (plane.json `task_log.spec_paths`, default `["docs/SPEC.md", "SPEC.md", "docs/spec/", "spec/"]`, the files `estimate.spec_paths` names by default;
  - `ccp/config.py` `TASK_LOG_DEFAULTS["spec_paths"]` to that list, with its comment.
  - `tests/test_tasklog_spec_signoff.py`: the check below.
- **Out:**
  - The estimator's default and matching rule.

## dod_checks

- id: `spec-01`
  story: As a lead of a product adopted by init, a task changing `docs/SPEC.md` is held to §3.5.
  setup: a fenced product with no `task_log.spec_paths` and three pending tasks whose `paths` are `["docs/SPEC.md"]`, `["spec/a.md"]` and `["docs/other.md"]`, none with a sign-off or `§31.1`.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 0 with exactly two sign-off warnings, for the first two tasks.
  dry run: n/a — at `921507e` the default meets neither `docs/SPEC.md` nor `spec/a.md`, so no warning is given.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- Fix round 1 (review MINOR): `contracts/plane_config.schema.json` still gave `task_log.spec_paths` the
  old default `["docs/spec/", "SPEC.md"]`; it now gives `["docs/SPEC.md", "SPEC.md", "docs/spec/",
  "spec/"]`, the default the code applies. A new test in `tests/test_tasklog_spec_signoff.py` compares
  the schema's default with `TASK_LOG_DEFAULTS["spec_paths"]`, so the two cannot drift apart silently.

## Verification notes

- 2026-11-18 — verifier, PR #161 head `c9b36f4` (squash `4451e40`): APPROVE. Passed: spec-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0144-spec-paths-default-includes-docs-spec-md.json.

- Built as scoped: `TASK_LOG_DEFAULTS["spec_paths"]` (with its comment) and §3.5's default text changed to
  `["docs/SPEC.md", "SPEC.md", "docs/spec/", "spec/"]`; one new test in `tests/test_tasklog_spec_signoff.py`
  runs the `spec-01` setup. Premises re-checked at `9a7103d`: the old default and the estimator's default
  are as the Context states. The estimator is untouched. The full suite (2329 tests) passed unchanged
  otherwise.
