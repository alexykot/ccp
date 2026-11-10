---
task_id: 0058-r1-r2-leftovers
title: R1 and R2 leftovers
status: pending
kind: refactor
depends_on: []
spec_refs: ["S14", "S15", "S23"]
review_point: R4
paths: ["scripts/observability/lib.py", "scripts/observability/team.py", "scripts/observability/README.md", "ccp/verify.py", "ccp/config.py", "tests/test_doc_rules.py", "plugin/skills/"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0058-r1-r2-leftovers

## Intent

The small defects reviewers left open in R1 and R2 are fixed, so the plane's own tools and docs say and do what they mean (§14, §15, §23).

## Context (not checked)

- R1: dead helpers in `scripts/observability/lib.py` after the snapshot retirement; `team.py` ignores `prompts.keep_body`; pruned prompt audits drop launch stamps that health reads (document that `audit_keep_days` must exceed the longest task life, or guard it); vacuous `ccp board build` halves of the snapshot compatibility tests; `scripts/observability/README.md` still says `status.sh` exits 1 on stale seats; skills name product-doc headings 'Architecture review' and 'Docs audit'.
- R2: repeat-verify reasons dedupe by substring, so a short note can be dropped; two `assertLess(took, 2)` timing bounds in `tests/test_doc_rules.py` can flake under load; `merge.behind_tip_ignore` accepts `.` (and a glob such as `*` in `verify.skip_review` matches everything), silently disabling the check; `--allow-unreviewed-fix` is dropped with no recorded override when the review gate proves the skip; `git merge-tree --write-tree` needs git 2.38 or later (state or check it); missing edge tests for the skip proof.

## Scope

- **In:** each item above, fixed or stated; `merge.behind_tip_ignore` and `verify.skip_review` refuse entries that match every path, consistently.
- **Out:** new behaviour.

## dod_checks

- id: `check-01`
  story: As a lead, an ignore list that disables the check is refused.
  setup: a scratch plane.json with `merge.behind_tip_ignore: ["."]`.
  steps:
    1. Run `ccp tasks check` (config load).
  expect: it refuses the entry, naming it.
  dry run: on the merge base it loads.
- id: `check-02`
  story: As a runner, a short repeat-verify reason is kept.
  setup: two reasons where one is a substring of the other.
  steps:
    1. Record both.
  expect: both are kept.
  dry run: on the merge base the shorter is dropped.
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
