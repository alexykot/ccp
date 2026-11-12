---
task_id: 0094-minor-only-fix-skips-re-review
title: A fix round that answers only minor findings of a clean review goes to verify without a new review
status: pending
kind: feature
depends_on: []
spec_refs: ["S15"]
review_point: R5
paths: ["ccp/prompt.py", "ccp/verify.py", "ccp/config.py", "templates/prompts/", "docs/spec/02-delivery.md", "contracts/plane_config.schema.json", "tests/test_review_skip*.py", "tests/test_prompt*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0094-minor-only-fix-skips-re-review

## Intent

When the latest review found nothing above MINOR, the fix round that answers it goes straight to
verify, and the verifier confirms the fix touches only those findings, so a minor-only fix does not
cost a full review cycle (§15.2).

## Context (not checked)

- Accepted plane proposal. A managed product's delivery data showed most fix rounds followed a clean
  review with only MINOR findings, each costing a full re-review and re-verify.
- Operator approval, 2026-11-12, in the lead session: "I approve proposed changes for 15c4 and
  9f18." This is the acceptance (§31.1): § text that states only what this task describes needs no
  further gate; a rule beyond it still waits for the operator.

## Scope

- **In:**
  - plane.json `verify.skip_review_after_clean` (boolean, default false).
  - With it on, when the latest review run's verdict is clean with no BLOCKER or MAJOR finding,
    `ccp prompt verify` accepts a fix head newer than that review without a new review, and records
    `review_skip` on the run: `{reason: "minor-only", review_run, findings}`.
  - The verify prompt lists those findings and asks the verifier to confirm the fix diff addresses
    them and changes nothing beyond them; a diff beyond them is a REJECT that sends the task back to
    review.
  - §15.2 states the knob and its effect; §8.1 lists it; the schema gains it.
- **Out:** skipping review after a BLOCKER or MAJOR; `verify.skip_review`'s path and prover skip.

## dod_checks

- id: `check-01`
  story: As a runner, a minor-only fix goes straight to verify.
  setup: a scratch product with `verify.skip_review_after_clean: true`; a task whose latest review is
    clean with two MINOR findings; a fix round after it.
  steps:
    1. Run `ccp prompt verify <task>`.
  expect: the prompt is issued without a new review; the run records `review_skip` with reason
    `minor-only`, the review run and both findings; the prompt lists both findings.
  dry run: on the merge base it refuses (a fix newer than the last review needs a review).
- id: `check-02`
  story: As a runner, a MAJOR still needs a review, and the knob is off by default.
  setup: as check-01 with a MAJOR among the findings; then with the knob unset.
  steps:
    1. Run `ccp prompt verify <task>` under each.
  expect: both refuse, as today.
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

## Verification notes

*Append-only.*
