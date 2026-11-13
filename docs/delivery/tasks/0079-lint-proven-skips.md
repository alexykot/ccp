---
task_id: 0079-lint-proven-skips
title: A product's prover command can skip a step it makes redundant, recorded on the run
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S15"]
review_point: R5
paths: ["ccp/verify.py", "ccp/suite.py", "ccp/config.py", "contracts/", "docs/spec/02-delivery.md", "tests/test_review_skip*.py", "tests/test_suite_stages.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0079-lint-proven-skips

## Intent

A change that a cheap, declared check proves harmless (a comment-only diff, a docs-only diff, a diff confined to declared paths) skips the step it makes redundant (a re-review, or a gate stage such as the suite), and the skip and its proof are recorded on the run (§14, §15).

## Context (not checked)

- Accepted plane proposal. Its triage records the operator's ruling of 11 Nov 2026, "if some gates can be skipped on that, they should be", as the acceptance.
- Generalises `verify.skip_review` (one proof for one skip) into declared provers.
- §31: this task adds or changes a § rule beyond describing its own feature, so its merge waits on the operator's approval of the final text at its merge gate (§31.1).

## Scope

- **In:** plane.json `verify.provers`: a list of `{name, command, skips}` where `skips` names one step (`review` or a gate stage name); when the command exits 0 on the task's or fix round's diff, `ccp` skips that step and records the prover's name, command and exit on the run; `verify.skip_review` keeps working as one such prover; §14.2 and §15.2 state the rule (PROPOSED: "a declared prover that exits 0 on the diff skips the step it names, recorded on the run").
- **Out:** shipping provers for any language.

## dod_checks

- id: `check-01`
  story: As a runner, a docs-only diff skips the suite stage.
  setup: a scratch product with a prover `docs-only` that skips stage `suite` and exits 0 when the diff touches only `docs/`; a task whose diff touches only `docs/`.
  steps:
    1. Run the gate lane for the task.
  expect: the suite stage is skipped and the run records the prover's name and exit.
  dry run: on the merge base `verify.provers` is refused as an unknown key.
- id: `check-02`
  story: As a runner, a failing prover skips nothing.
  setup: as check-01 with a diff touching `src/`.
  steps:
    1. Run the gate lane.
  expect: the suite stage runs.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-13 (implementer): plane.json `verify.provers` (`[{name, command, skips}]`, default `[]`) in
  `ccp/config.py` and `contracts/plane_config.schema.json`. `skips` is `review` or a stage that the gate
  role's lane declares. That excludes `plane-docs` and argv lanes. Names are unique labels. Gate
  stages (`ccp/suite.py`): before a stage starts, on a run of the gate role's staged lane that is
  recorded and names its task, its provers run in order with `{task_id}`, `{from}` (merge base with
  `origin/<integration>`) and `{head}` filled in. The first that exits 0 skips the stage. The
  `ended` row records `proven_skips` (`stage, prover, command, exit_code`). The event records the same
  without `command`, since the ledger holds ids and numbers only. A checkout with uncommitted
  changes, or a head with no merge base, runs no prover. A signal while proving stops the run before
  the stage. Review (`ccp/verify.py`): `skip_review` computes the fix diff once and tries
  `verify.skip_review` first, unchanged with its record as before. It then tries each review prover;
  a prover's skip adds `prover`, `command` and `exit_code` to `review_skip`. The refusal names the
  settings in force (`review_proof_label`). SPEC §14.2, §14.4 and §15.2 carry the PROPOSED rule and
  describe the feature. §01 table, README git floor and runner brief name the new key.

## Verification notes

*Append-only.*
