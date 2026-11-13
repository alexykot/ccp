---
task_id: 0087-parsing-and-path-follow-ups
title: Path patterns, markings, reasons and report values are parsed exactly
status: done
kind: bug
depends_on: []
spec_refs: ["S5", "S13", "S15", "S16"]
review_point: R5
paths: ["ccp/config.py", "ccp/verify.py", "ccp/parallel.py", "ccp/report.py", "scripts/observability/team.py", "tests/test_config*.py", "tests/test_verify*.py", "tests/test_parallel*.py", "tests/test_report_fields.py"]
created: 2026-11-12
updated: 2026-11-13
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

- 2026-11-13 (implementer): `ccp/config.py` `_every_path` refuses an entry of `merge.behind_tip_ignore`
  or `verify.skip_review.paths` that normalises to the root or that covers every path in
  `EVERY_PATH_PROBES`, as git's default pathspec matching does (`_pathspec_hits`: the path or a directory
  above it, or `fnmatch` where `*` and `?` match `/`; `[^…]` read as `[!…]`). Git's default pathspec
  has no zero-directory `**/`, so `**/*` and `*/**` leave top-level files out (checked against git
  2.56): the probes all sit below a directory, so those two are refused as the task asks, and `*/*` with
  them. `ccp/parallel.py` `missing_paths`: the 25-character marking window stops at the next backtick.
  `ccp/verify.py` `fill_reason`: a finding counts as giving the note only when it is the note or starts
  with the generated `REPEAT_PREFIX` and ends `: <note>`; `tests/test_review_gate.py`, which pinned the
  old swallowing, is updated and gains the inverse case. `ccp/report.py`: a declared value followed by
  `/`, `,` or `or` and then another of the field's declared values is the template respelled and
  refused; a reason after them is not (`|` stays refused whatever follows). `scripts/observability/
  team.py` `keep_body` puts the plane root on `sys.path` only when it is not there (the other helpers in
  that file are unchanged). No SPEC edit: the task gives no SPEC text.

## Verification notes

- 2026-11-13 — verifier, PR #93 head `1aefa45` (squash `dd0e29a`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0087-parsing-and-path-follow-ups.json.
