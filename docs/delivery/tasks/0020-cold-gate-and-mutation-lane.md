---
task_id: 0020-cold-gate-and-mutation-lane
title: A gate run with nothing cached counts as cold; the verify prompt names the mutation lane
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S15"]
adr_refs: []
review_point: R2
paths: ["ccp/verify.py", "templates/prompts/verify.md", "templates/prompts/review.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0020-cold-gate-and-mutation-lane

## Intent

`ccp verify record` treats a recorded gate run with `cached == 0` as cold, so a cold task's approve is not refused for a missing `cold: true`; the review and verify prompts name the lane a mutation run goes through.

## Context (not checked)

- `ran` and `cached` already fill from the gate's `suite_id`; `cold` never did, so every cold task's approve needed a hand edit.
- Operator's ruling (2026-11-10, sm-20261110T094507Z-0f40): "In PR #16, with this ruling in task 0020's Context. (1) section 14.4: replace '`cold` stays the verifier's to give.' with '`cold` is filled as `true` when the cited run has `cached == 0` and the entry leaves it out; an explicit `cold` from the verifier wins.' (2) section 15.3: wherever it says the verifier must set `cold: true` by hand for a cold task, say instead that a cited suite run with `cached == 0` satisfies it, and an explicit value still wins. Keep the rest of the cold rule (when a task needs a cold run) unchanged. (3) The `part_lane` render value in `ccp/prompt.py` is accepted as the narrowest change the prompt wording needs. List it in the PR body as outside the declared paths. Section 31: the passages are made false by the task's own feature (cold inference, from the triage the operator accepted, ADR-0035), so the operator's 2026-11-10 ruling covers them. Quote it and the old text. No merge gate."

## Scope

- **In:** the cold inference, the prompt wording, tests.
- **Out:** the cache rules themselves.

## dod_checks

- id: `cold-01`
  story: As a verifier on a cold task, my approve is accepted from the recorded gate run.
  setup: a temporary queue with a gate suite record with `cached: 0`.
  steps:
    1. Record an approve citing that `suite_id` with no `cold` field.
  expect: accepted; the record shows the run as cold.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): `fill_gate` (ccp/verify.py) marks a `gate.runs` entry `cold: true` when it cites a
  `suite_id` whose recorded run has `cached` 0, the entry's own `cached` is 0 after filling, and the entry
  gives no `cold`; a `cold` the verifier writes (true or false) stays, and an entry citing no suite run is
  not marked. The verify prompt now says `record` marks such a run cold instead of asking for `cold: true`.
  The review and verify prompts name the `part` role's lane (`--lane {{part_lane}}`, from plane.json
  `suite.roles`) on the mutation-run instruction; that needed one render value in ccp/prompt.py, outside
  the task's `paths`. Open: SPEC §14.4 ("`cold` stays the verifier's to give") and §15.3 ("and `cold: true`
  for a cold run") still describe the old rule; the task gave no SPEC edit, so none was written.

- 2026-11-10 (implementer, round 2): per the operator's 2026-11-10 ruling (Context), SPEC §14.4 now says
  `cold` is filled as `true` from a cited run with `cached == 0` when the entry leaves it out, an explicit
  `cold` winning; §15.3 says a cited suite run with `cached == 0` gives `cold: true`, an explicit value still
  winning. No other SPEC, docs/cli or plugin sentence said who sets `cold`. No code change this round.

## Verification notes

*Append-only.*
