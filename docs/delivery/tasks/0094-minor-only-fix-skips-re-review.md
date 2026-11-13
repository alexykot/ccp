---
task_id: 0094-minor-only-fix-skips-re-review
title: A fix round that answers only minor findings of a clean review goes to verify without a new review
status: done
kind: feature
depends_on: []
spec_refs: ["S8", "S15"]
review_point: R5
paths: ["ccp/prompt.py", "ccp/verify.py", "ccp/config.py", "templates/prompts/", "docs/spec/02-delivery.md", "contracts/plane_config.schema.json", "tests/test_review_skip*.py", "tests/test_prompt*.py"]
created: 2026-11-12
updated: 2026-11-13
---

# Task: 0094-minor-only-fix-skips-re-review

## Intent

When the latest review found nothing above MINOR, the fix round that answers it goes straight to
verify, and the verifier confirms the fix touches only those findings, so a minor-only fix does not
cost a full review cycle (§15.2).

## Context (not checked)

- Accepted plane proposal. A managed product's delivery data showed most fix rounds followed a clean
  review with only MINOR findings, each costing a full re-review and re-verify.
- Operator approval, 2026-11-12, in the lead session, approving the proposed changes for this task and its companion
  (0094, 0095). This is the acceptance (§31.1): § text that states only what this task describes needs no
  further gate; a rule beyond it still waits for the operator.
- Lead's ruling, 2026-11-12 (spec question sm-20261112T232937Z-8195, spec commit fd1ecbb): yes,
  `review_skip` records the findings as severity counts (`{MINOR, NIT}`) with the review run, its
  reviewed head and the review report's path. The plane stores no finding text. The verify prompt tells
  the verifier to read the report and check the fix diff against each MINOR and NIT finding there, and to
  send the task back to review if the diff goes beyond them. Read check-01's "both findings" as "both
  findings, by their counts and the report that holds them"; the expectation is unchanged. The
  `plugin/agents/delivery-runner.md` step-7 edit and the §15.2 and §8.1 text are accepted under §31.1
  (they describe the feature the operator approved). The PR body names the extra path
  `plugin/agents/delivery-runner.md` and the schema.

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

- 2026-11-12 (implementer): `verify.skip_review_after_clean` (boolean, default false) in `ccp/config.py`
  and the schema. `verify.skip_after_clean` decides the skip; `ccp prompt verify` tries it after
  `verify.skip_review` (unchanged) and records `review_skip: {reason: "minor-only", review_run, findings}`.
  `findings` is the review's recorded MINOR and NIT counts (`{"MINOR": n, "NIT": n}`), not finding text:
  run records carry numbers and ids only (E5), and the plane parses no report prose (E6); the verify
  prompt lists the counts and the review's report path, and asks the verifier to check the fix diff
  (reviewed head to verified head) against each of those findings. Narrowest rules where the task was
  open: the review must count at least one MINOR or NIT; the verified head must be the one the latest
  fix (merge, ruling) round reported; a verify run since the review that recorded `reject` sends the
  task back to review, so a reject is not followed by another skip. `ccp verify record` accepts the
  approve at the skipped verify run's head. §15.2 gains the rule (and its lead bullet now names two
  exceptions), §8.1 lists the knob, and the runner brief (step 7) names it.
- 2026-11-12 (implementer, ruling round 1): per the lead's ruling, `review_skip` now also records
  `reviewed` (the head the clean review judged) and `report` (its report's path), so the record holds
  everything the verifier needs without the prompt rereading the review run; the verify prompt reads them
  from the record and tells the verifier to read that report and check the fix diff against each MINOR and
  NIT finding there. §15.2 names the two fields and that the plane stores no finding text.

## Verification notes

- 2026-11-13 — verifier, PR #86 head `e3a226b` (squash `1927f49`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0094-minor-only-fix-skips-re-review.json.
