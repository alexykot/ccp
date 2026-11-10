---
task_id: 0049-no-usage-command-no-session-check
title: A product without a usage command gets no session-limit check on parallel claims
status: done
kind: feature
depends_on: []
spec_refs: ["S16", "S25"]
review_point: R3
paths: ["ccp/parallel.py", "ccp/usage.py", "docs/spec/02-delivery.md", "tests/test_parallel*.py"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0049-no-usage-command-no-session-check

## Intent

A product that sets no `telemetry.allowance_cmd` can run more than one runner (§16): rule 5 of §16.3
passes, because the plane reads no usage for it, instead of refusing every second claim as "usage
unknown".

## Context (not checked)

- §16.3 rule 5 refuses a claim beside others when no usage reading exists. A product with no usage
  command, for example on a plan with no session limit, therefore never gets a second runner.
- The fix belongs in `ccp/parallel.py` or `ccp/usage.py`; `claim` only forwards the sample. If `ccp/lifecycle.py` must change, say so in the report: it is not in this task's paths.
- Operator ruling, 2026-11-10, approving this § change: §16.3 rule 5 gains the sentence "A product
  without `telemetry.allowance_cmd` reads no usage: the rule passes." Quote it in the PR's §31 section.

## Scope

- **In:** `ccp tasks claim` and `ccp tasks next` skip rule 5 when `telemetry.allowance_cmd` is unset;
  with it set, rule 5 is unchanged; §16.3 rule 5 gains the sentence above.
- **Out:** the weekly checkpoint (§25), which already does nothing without a usage command.

## dod_checks

- id: `check-01`
  story: As a lead without a usage command, a second runner gets a task.
  setup: a scratch product with `parallel.max_in_flight: 2`, no `telemetry.allowance_cmd`, and two ready
    tasks whose paths do not meet; one already claimed.
  steps:
    1. Run `ccp tasks claim` for the second task.
  expect: it is claimed.
  dry run: on the merge base it refuses with exit 7, "the 5-hour usage is unknown … (rule 5)".
- id: `check-02`
  story: As a lead with a usage command, rule 5 still holds.
  setup: as check-01 with `telemetry.allowance_cmd` set to a command printing a reading without
    `five_hour` but with `seven_day`, then one printing nothing.
  steps:
    1. Claim the second task under each.
  expect: the first claims (no session limit); the second refuses (rule 5), as today.
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

- 2026-11-10 (implementer): `parallel.join_refusal` judges rule 5 only when `parallel.reads_usage(cfg)`
  (a non-empty `telemetry.allowance_cmd`), so `ccp tasks claim` and `ccp tasks next` (both go through
  it) pass rule 5 for a product with no usage command, whatever `board/allowance.jsonl` holds. With a
  command set, rule 5 is unchanged: a weekly-only reading passes, an empty or failed one refuses.
  `ccp/lifecycle.py` is untouched. §16.3 rule 5 gains the operator-approved sentence.
- 2026-11-10 (implementer, fix round 1): §16.3 rule 5's "A sample with neither (no `allowance_cmd`,
  a failed read) refuses" becomes "A sample with neither (a failed read) refuses": the task's change
  made "no `allowance_cmd`" false, so this is a §31.1 correction under the task's acceptance.

## Verification notes

- 2026-11-10 — verifier, PR #36 head `2a3079d` (squash `11e12af`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0049-no-usage-command-no-session-check.json.
