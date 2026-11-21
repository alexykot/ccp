---
task_id: 0233-briefs-point-at-the-evidence-rules
title: The briefs and the verify prompt cite §15.4 and the example contract instead of restating the evidence rules
status: pending
kind: refactor
depends_on: []
clashes_with: ["0221-workers-reach-the-pr-host-through-ccp-pr", "0228-report-sections-as-one-table", "0223-a-follow-up-is-tracked-not-left-in-notes"]
review_refs: ["sh-20261121T000350Z-5ef1#F03"]
rule_refs: ["E13"]
review_point: R15
paths: ["templates/prompts/verify.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-runner.md", "ccp/verify.py", "tests/test_verify_producer.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0233-briefs-point-at-the-evidence-rules

## Intent

What evidence a check not run may rest on, and who may produce evidence, is §15.4's rule and
`ccp verify record` enforces it. The verify prompt, the verifier's and the runner's briefs and
`ccp/verify.py`'s module docstring each restate it, with a sample check that rests on "the operator's
live run" which ADR-0045 is about to refuse. After this task they name `ccp verify record` and §15.4
and keep no samples; the one sample is `contracts/verification.example.json`, which the test
validates. ADR-0045's evidence change (0237) then edits the SPEC, the code and the example only.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0045 (`sh-20261121T000350Z-5ef1`), F03.
- **The copies.** `templates/prompts/verify.md` (the paragraph that opens "Each check names the seat"),
  `plugin/agents/delivery-verifier.md` (the three `rests_on` forms and the `data-01` sample), the
  runner's brief (the producer rule and the `operator_step` exception), `ccp/verify.py`'s docstring.
- **The test** `test_the_example_checks_the_verifier_is_shown_are_valid` in
  `tests/test_verify_producer.py` parses the samples out of the prompt and the brief:
  `grep -c 'def test_the_example_checks_the_verifier_is_shown_are_valid' tests/test_verify_producer.py` at `8aefa59`: 1.
- A refactor: what `record` accepts does not change; the sample test reads the example contract.

## Scope

- **In:** `templates/prompts/verify.md`, `plugin/agents/delivery-verifier.md`,
  `plugin/agents/delivery-runner.md`, `ccp/verify.py`, `tests/test_verify_producer.py`.
- The prompt and the two briefs say a check's evidence follows §15.4, `ccp verify record` refuses what
  breaks it, and `contracts/verification.example.json` shows a record; the restated forms and the
  inline samples go.
- `ccp/verify.py`'s module docstring names §15.4 and the functions instead of restating the rules.
- The sample test validates each check of `contracts/verification.example.json` through `record`'s
  checks, and no longer parses prose.
- **Out:** the rule itself (0237), the example's operator sample (0237 changes it).

## dod_checks

- id: `ev-01`
  story: As a plane developer, the evidence rules are no longer copied into prose.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n "operator's live run" -- templates plugin ccp`.
  expect: prints nothing (the sample lives only in `contracts/verification.example.json`).
  dry run (`8aefa59`): prints two lines, `templates/prompts/verify.md` and
    `plugin/agents/delivery-verifier.md`.

- id: `ev-02`
  story: As a verifier, `record` accepts and refuses exactly what it did.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_verify_producer tests.test_verify_as_written 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

- id: `ev-03`
  story: As a plane developer, the example contract's samples are checked and the check bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which one
    check of `contracts/verification.example.json` has `produced_by: "implementer"`.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_verify_producer`.
  expect: at least one failure.
  dry run: n/a — the test reads the example only after this task.

## Implementation notes

## Verification notes
