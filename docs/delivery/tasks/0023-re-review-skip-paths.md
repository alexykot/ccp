---
task_id: 0023-re-review-skip-paths
title: Declared paths a fix may touch without re-review, with a product proof hook
status: done
kind: feature
depends_on: []
spec_refs: ["S15"]
adr_refs: ["0035 D4"]
review_point: R2
paths: ["ccp/prompt.py", "ccp/verify.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/02-delivery.md", "tests/"]
created: 2026-11-06
updated: 2026-11-10
---

# Task: 0023-re-review-skip-paths

## Intent

A generic setting lists paths a fix round may touch without a fresh review; a product-supplied proof hook, run on the fix diff, must pass before the runner goes straight to re-verify.

## Context (not checked)

- Comment-only or docstring-only fixes in tests cost a full review round.
- The prover (for example a language-aware comparison) is product tooling run through the hook.

## Scope

- **In:** the setting, the hook contract (command, exit 0 = proven), the review-gate change, SPEC §15.2 wording, tests.
- **Out:** any language-specific prover.

## dod_checks

- id: `skip-01`
  story: As a runner, a fix within the declared paths that the hook proves goes straight to re-verify.
  setup: a temporary queue and a hook that exits 0.
  steps:
    1. Run `ccp prompt verify <task>` after such a fix.
  expect: accepted without a new review round.
  dry run: n/a — built by the task's test.
- id: `skip-02`
  story: As a runner, an unproven fix still needs a review.
  setup: the same with a hook that exits 1, or a path outside the list.
  steps:
    1. Run `ccp prompt verify <task>`.
  expect: refused: review the fix first.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): The setting is plane.json `verify.skip_review`: `{"paths": [...], "proof": "<command>"}`,
  null (off) by default, beside `verify.accept_cache` because it governs what `ccp prompt verify` and
  `ccp verify record` accept, as the cache rule does; `merge.*` is about the head against the tip.
  `paths` are git pathspecs relative to the product root, validated like `merge.behind_tip_ignore`
  (no empty, absolute, `..` or `:`-magic entry) and also refusing `.` or anything that normalises to it;
  both keys are required. The hook contract: `proof` runs in the product root (through `rules.run_command`,
  600 s, a timeout proves nothing) with `{task_id}`, `{reviewed}`, `{head}` and `{from}` filled in; exit 0
  = proven. The fix diff runs from `{from}`, the tree of `git merge-tree --write-tree <reviewed>
  <merge-base(head, origin/<integration>)>` (the reviewed change on the head's base), to the head, so an
  integration merge in between is not counted as the fix's; a reviewed change that does not merge
  cleanly onto that base is reviewed again. The skip needs a fix run opened since the last review that
  reported done, and a fix diff touching at least one file (`--no-renames`, so a rename names both
  paths), all under `paths`. A proven skip is recorded on the verify run as `review_skip` (`reviewed`,
  `head`, `fix`, `files`: ids and a count), and `ccp verify record` takes an approve at that head; a
  refusal names why the skip did not apply. The logic is `verify.skip_review`; `prompt.review_gate` calls
  it only when `runs.unreviewed_fix` would refuse. Also edited: SPEC §15.2 (and the §8 config table in
  `docs/spec/01-model.md`), the runner brief step 7 (`plugin/agents/delivery-runner.md`), ADR-0035 D4
  flipped to built.

## Verification notes

- 2026-11-10 — verifier, PR #20 head `5e639c6` (squash `e7545b7`): APPROVE. Passed: skip-01, skip-02. Gate: `scripts/gate.sh (ccp suite run --lane gate)` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0023-re-review-skip-paths.json.
