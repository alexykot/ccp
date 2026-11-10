---
task_id: 0021-behind-tip-ignore-paths
title: Declared paths do not make a head behind the tip; verify refuses a stale head
status: pending
kind: feature
depends_on: []
spec_refs: ["S15", "S16"]
adr_refs: ["0035 D1", "0035 D2"]
review_point: R2
paths: ["ccp/lifecycle.py", "ccp/prompt.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/02-delivery.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0021-behind-tip-ignore-paths

## Intent

A product setting (empty by default) lists paths whose commits on the integration branch do not count as behind the tip at close; `ccp prompt verify` refuses a head that lacks the tip beyond those paths.

## Context (not checked)

- Today only the task log, INDEX and the reconcile log are skipped, so a history-only or doc-only commit forces a merge and a re-verify.

## Scope

- **In:** the setting, the behind-tip check at close and at verify launch, SPEC §15.6 and §16.5 wording, tests.
- **Out:** which paths a product lists.

## dod_checks

- id: `tip-01`
  story: As a runner, a doc-only commit on the tip does not cost a re-verify.
  setup: a temporary repo whose tip gained only a commit under a declared path.
  steps:
    1. Close the verified task.
  expect: close accepts the verified head.
  dry run: n/a — built by the task's test.
- id: `tip-02`
  story: As a runner, I cannot launch a verifier on a stale head.
  setup: a temporary repo whose tip gained a commit outside the declared paths.
  steps:
    1. Run `ccp prompt verify <task>`.
  expect: exit non-zero: merge the tip in first.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): The setting is plane.json `parallel.behind_tip_ignore` (paths relative to the
  product root, a directory covering everything under it; empty by default; validated in `ccp/config.py`
  and the schema). `lifecycle.behind_tip` is the one check, shared by `ccp tasks close` and
  `ccp prompt verify`; it adds the declared paths to the task-log exclusions of the `git log` pathspec.
  Close keeps its behaviour on an unreadable tip (refuse) or head (warn). `ccp prompt verify` runs the
  check only with several runners, as close does, refusing exit 4 with nothing opened; a tip or head it
  cannot fetch is a warning in its output, and close still checks. SPEC §15.6 rule 2 and §16.5 rule 4
  carry the rule, worded from ADR-0035 D1 and D2.

## Verification notes

*Append-only.*
