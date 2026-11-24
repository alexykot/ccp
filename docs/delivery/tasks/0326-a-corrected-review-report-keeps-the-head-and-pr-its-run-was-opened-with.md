---
task_id: 0326-a-corrected-review-report-keeps-the-head-and-pr-its-run-was-opened-with
title: A corrected report keeps the head and PR its run was opened with when its phase's report gives no such line, so a verify after a clean review, a correction and a clean catch-up merge round passes
status: done
kind: feature
depends_on: []
spec_refs: ["S13", "S15"]
review_point: R34
paths: ["ccp/report.py", "tests/test_report_correction.py", "tests/test_prompt_rounds.py"]
clashes_with: ["0191-the-grace-release-ends", "0329-tests-edit-plane-json-through-one-helper-name-the-plane-root-once-and-take-git-from-its-own-module"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0326-a-corrected-review-report-keeps-the-head-and-pr-its-run-was-opened-with

## Intent

A runner whose reviewer reported, and whose own `ccp report` then corrected that review (a worker runs `ccp report`
itself, so the runner's call is a correction), still has a review run that names the head and PR it judged. After a
clean catch-up merge round, `ccp prompt verify` and `ccp verify record` pass the integration-merge rule (§15.2) as
they do for an uncorrected review, instead of refusing and sending the task to a second full review of an unchanged
change or to the lead for `--allow-unreviewed-fix`.

## Context (not checked)

An accepted plane proposal (the lead, 2026-11-24: "The review run should record the head and PR it was opened for,
so the integration-merge rule passes verify"), with a second proposal of the same day merged into it and an earlier
one (accepted 2026-11-21: "a re-report of an already-reported run must keep pr/head"). It cost two extra review rounds on 24 Nov.

Measured at `cd3a6bf5`:

- **Where the head goes.** `ccp prompt review --pr N --head SHA` opens the run with `pr` and `head`
  (`"extra={"pr": a.pr or None, "head": a.head or None"` in `ccp/prompt.py`). A first `ccp report` keeps them: it
  updates only the keys the report gives. A correction drops them: `"for k in PARSED_KEYS:"` in `"def submit"`
  (`ccp/report.py`) pops every parsed key but a verify's `verdict` and `head`, and
  `python3 -B -c 'from ccp import report as r; print(r.PARSED_KEYS[:2], [s.phases for s in r.SECTIONS if s.keys[:1] in (("head",), ("pr",))])'`
  printed `('head', 'pr') [('implement', 'fix', 'merge', 'ruling', 'verify'), ('implement', 'fix', 'merge', 'ruling')]`:
  a review's report has no `Head:` or `PR:` line, so a corrected review run keeps neither.
- **The effect.** `"def unreviewed_fix"` (`ccp/runs.py`) reads the judged head from the last done review run;
  `merged_only` needs it, so a merge round after a corrected review is refused as unreviewed.
- **Seen in the plane's own queue** (`runs/<task>/review*.json`, read 24 Nov): 0311's `review.json` (one correction)
  and both of 0321's review runs (one correction each) hold `head: null` and `pr: null`; 0311's `review-2.json` (no
  correction) holds its head and PR 392.
- **Ruled.** A correction drops only the keys the run's phase (and mode) report can give: the union of
  `Section.stored` over `sections_for(phase, mode)`, within `PARSED_KEYS`, besides a verify's `verdict` and `head` as
  now. A key the phase's report never gives (a review's `head` and `pr`) keeps the value the run was opened with. An
  implement, fix, merge or ruling correction still replaces `head` and `pr` with the corrected report's.
- **No SPEC change.** §13.4 says "the run's report fields become the corrected report's"; a review report has no
  `Head:` or `PR:` field (§13.4's list: "`PR:` and `Head:` for implement, fix, merge and ruling"), so the opened values
  are not report fields. `git grep -n 'report fields' -- docs/spec` at `cd3a6bf5`: 1 line, that sentence.

## Scope

- **In:** `ccp/report.py` (`submit`'s correction branch); `tests/test_report_correction.py`;
  `tests/test_prompt_rounds.py`.
- No SPEC change (Context, *No SPEC change*).
- **Out:** making `--head` required on `ccp prompt review`; rewriting live run records that already lost their head;
  how a first report stores its keys.

## dod_checks

- id: `code-01`
  story: As a runner, a review run I correct keeps the head and PR it was opened with, and an implement correction still replaces them.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_report_correction.Correction.test_a_corrected_review_keeps_the_head_and_pr_it_was_opened_with tests.test_report_correction`.
  expect: exit 0.
  dry run (`cd3a6bf5`): exit 1 (the named test does not exist yet: `AttributeError: type object 'Correction' has no attribute 'test_a_corrected_review_keeps_the_head_and_pr_it_was_opened_with'`).
- id: `code-02`
  story: As a runner, a verify after a clean review, its correction and a merge round that left the change alone passes the integration-merge rule.
  setup: As `code-01`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_prompt_rounds.Rounds.test_a_merge_round_after_a_corrected_review_needs_no_new_review tests.test_prompt_rounds`.
  expect: exit 0.
  dry run (`cd3a6bf5`): exit 1 (the named test does not exist yet: `AttributeError: type object 'Rounds' has no attribute 'test_a_merge_round_after_a_corrected_review_needs_no_new_review'`).

## Implementation notes

- `ccp/report.py`: `phase_keys(phase, mode)` gives the `PARSED_KEYS` within the union of `Section.stored` over
  `sections_for(phase, mode)`; `submit`'s correction branch pops only those (a verify's `verdict` and `head` still
  kept). A review correction now keeps the `head` and `pr` the run was opened with; implement, fix, merge and ruling
  corrections still replace them. A verify correction now also keeps the `pr` it was opened with (a verify report
  has no `PR:` line), which follows from the ruled union.
- Re-measured at `7bd2fc42`: the `PARSED_KEYS`/phases command prints the same; `report fields` is still the one
  §13.4 line; 1706f4b1 touched only `tests/test_prompt_rounds.py`'s imports.
- Tests: `Correction.test_a_corrected_review_keeps_the_head_and_pr_it_was_opened_with`, `PhaseKeys` (plain values),
  `Rounds.test_a_merge_round_after_a_corrected_review_needs_no_new_review` (`ccp prompt verify` and
  `ccp verify record` after a clean review, its correction and a merge round that left the change alone).
- Fix round 1 (review MINOR-1, NIT-1): `Resolution.test_a_correction_with_no_resolution_line_drops_the_earlier_one`
  corrects a contained resolution review to `Outcome: blocked` and checks the run keeps no `resolution` or
  `affected_checks`, so `submit` must pass the run's mode to `phase_keys`. The Correction test's `unreviewed_fix`
  assertion now asks about another head and expects the refusal to name the kept head, which passes only when the
  correction kept it.

## Verification notes
- 2026-11-24 — verifier, PR #399 head `6985702` (squash `59e53ce`): APPROVE. Passed: code-01, code-02. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0326-a-corrected-review-report-keeps-the-head-and-pr-its-run-was-opened-with.json.

