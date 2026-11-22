---
task_id: 0292-the-review-prompt-asks-for-a-cold-run-where-review-takes-no-cache-hits
title: Where the product takes no cache hits for review, the review prompt asks for the reviewer's run of the touched modules with --cold
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S15"]
review_point: R26
paths: ["templates/prompts/review.md", "docs/spec/02-delivery.md", "tests/test_worker_efficiency.py"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0292-the-review-prompt-asks-for-a-cold-run-where-review-takes-no-cache-hits

## Intent

In a product that does not let review take cache hits (`verify.accept_cache.review` off, the default),
the reviewer's run of the modules the PR touches is a real run: the review prompt gives that run with
`--cold`, so a cache entry the implementer's run wrote never stands for it, and no reviewer has to notice
the cache hits and add a cold run by hand. A product with `review: true` keeps today's prompt.

## Context (not checked)

From the triage of architect pass `ar-20261122T100027Z-dd31` (F01; the record is in `docs/delivery/reviews/`).
The operator chooses between this and setting `verify.accept_cache.review: true` here (question 1 of that
record); signing this brief chooses this. Measured at `e92f362`.

- **The template.** `templates/prompts/review.md`, the line that starts "Run the tests the PR touches", gives
  the run "through `{{ccp}} suite run` with `--lane {{part_lane}}`", followed only by a `{{#review_cache}}`
  section; there is no `{{^review_cache}}` text: `grep -c 'review_cache' templates/prompts/review.md` at `e92f362`: 2 (the
  section's open and close).
- **Why every hit is the implementer's.** The gate's cache is per repository, shared by every worktree and
  clone (`scripts/gate_parallel.py`'s docstring, "every worktree and clone of the repo shares it"), and a run
  is cold only with `CCP_SUITE_COLD` (`ccp suite run --cold`, §14.2). The reviewer's run at the implementer's
  head therefore finds the implementer's entries.
- **The friction.** Reviewers of seven tasks in the window (0265, 0266, 0267, 0268, 0276, 0280, 0281) noted all
  cache hits and added a `--cold` run; the notes are in the queue's friction log (data only the queue holds).
- **ADR-0014 D5.** "A product may let the verifier accept its cache hits, with reviewers checking them."
  With `review` off, the reviewer's run is that check, so it must not come from the cache.
- **This product.** `docs/delivery/plane.json` `verify.accept_cache` is `{"max_age_days": 7}` (no `review`), so
  after this task its reviewers get the cold run.
- **The render variable.** `ccp/prompt.py` already sets `review_cache` from `verify.cache_rule(cfg)`'s `review`;
  no code change is needed.
- **Tests that change.** `tests/test_worker_efficiency.py`'s `test_review_without_the_reviewer_setting_is_unchanged`
  asserts the review brief without `review_cache` holds no "cache" and equals the one with the verifier's rule
  alone; the second half still holds, the first gains the `--cold` expectation.
- **SPEC.** §15.3's closing sentence says "without the setting each prompt is unchanged": the PROPOSED text
  below replaces it.

### Rulings for the build (the lead's)

- In `templates/prompts/review.md`, `--lane {{part_lane}}` becomes `--lane {{part_lane}}{{^review_cache}} --cold{{/review_cache}}`.
  Nothing else in the template changes; mutation runs (`ccp mutate`) are untouched.
- `tests/test_worker_efficiency.py` gains a test, its name holding `cold`, that renders `review` without
  `review_cache` and finds `--lane <part lane> --cold`, and with `review_cache=True` finds no `--cold`.

## Scope

- **In:** `templates/prompts/review.md`, `tests/test_worker_efficiency.py`, and the SPEC passage below.
- **SPEC, signed before the claim (`sign_off: brief`):** one passage in `docs/spec/02-delivery.md`, CURRENT at `e92f362`.

    CURRENT (`docs/spec/02-delivery.md` at `e92f362`), §15.3, its closing sentence:
    > `ccp prompt verify` renders the exception only for such a product, and `ccp prompt review` the reviewer's only with `review: true`; without the setting each prompt is unchanged.

    PROPOSED:
    > `ccp prompt verify` renders the exception only for such a product, and `ccp prompt review` the reviewer's only with `review: true`; without the setting the verify prompt is unchanged, and the review prompt gives the reviewer's run of the modules the PR touches with `--cold` (§14.2), so a cache entry another run wrote never stands for it.
- **Out:** `verify.accept_cache` in this repo's plane.json; the verifier's gate (warm under §15.3); mutation runs.

## dod_checks

- id: `spec-01`
  story: As the operator, §15.3 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0292`.
  expect: exit 0, the PROPOSED passage found.
  dry run (simulated at `e92f362`: this task file committed, then the passage applied, its CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0292 --base HEAD~1`): `"ok": true`, the passage found.
- id: `code-01`
  story: As a reviewer in a product that takes no cache hits for review, my prompt gives my affected-module run cold.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_worker_efficiency 2>&1 | grep -e cold -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_worker_efficiency --mutant 'templates/prompts/review.md:{{^review_cache}} --cold{{/review_cache}}=>'`.
  expect: step 1 lists, `ok`, a test whose name holds `cold` (the review brief without `review_cache` holds `--lane <part lane> --cold`, and with it no `--cold`), then `OK`. Step 2 prints the mutant `killed`.
  dry run (`e92f362`): step 1 printed only `OK` (no test names `cold` yet).

## Implementation notes

## Verification notes
