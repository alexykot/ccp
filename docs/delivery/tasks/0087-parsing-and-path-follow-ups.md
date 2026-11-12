---
task_id: 0087-parsing-and-path-follow-ups
title: Path patterns, markings, reasons and report values are parsed exactly
status: pending
kind: bug
depends_on: []
spec_refs: ["S5", "S13", "S15", "S16"]
review_point: R5
paths: ["ccp/config.py", "ccp/verify.py", "ccp/parallel.py", "ccp/report.py", "scripts/observability/team.py", "tests/test_config*.py", "tests/test_verify*.py", "tests/test_parallel*.py", "tests/test_report_fields.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0087-parsing-and-path-follow-ups

## Intent

Small parsing gaps found in reviews stop silently accepting the wrong thing: match-everything path entries, a marking that applies to a neighbour, a repeat-verify reason swallowed by another, and a pasted template value read as a verdict (§5, §13.4, §15, §16).

## Context (not checked)

- Accepted plane proposals from the reviews of the leftovers, path-marking and report-field tasks.
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** path entries in `merge.behind_tip_ignore` and `verify.skip_review.paths` are refused when they match every path in a probe set (so `*/**`, `**/*` and `?*` are caught as well as the listed forms); a `new`/`(removed)` marking window stops at the next backticked token; a repeat-verify reason is deduplicated by its generated prefix, not by a trailing note; a declared report field whose value is a pasted template in any spelling (`a or b`, `a` slash `b`, `a, b`) is refused; `keep_body` stops inserting into `sys.path` on every call.
- **Out:** other config keys.

## dod_checks

- id: `check-01`
  story: As a product, a match-everything glob is refused.
  setup: a scratch `plane.json` with `merge.behind_tip_ignore: ["**/*"]`.
  steps:
    1. Load the config.
  expect: it is refused, naming the entry.
  dry run: on the merge base it loads.
- id: `check-02`
  story: As a task writer, a marking applies only to its own path.
  setup: a pending task whose Scope names `` `a/x.py`, `b/y.py` (removed) ``, neither existing.
  steps:
    1. Run `ccp tasks check`.
  expect: it warns about `a/x.py` only.
  dry run: on the merge base neither is warned about.
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
