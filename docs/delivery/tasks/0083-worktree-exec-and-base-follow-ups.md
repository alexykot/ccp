---
task_id: 0083-worktree-exec-and-base-follow-ups
title: wt exec, base runs and shallow checkouts are complete and clean up after themselves
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S15"]
review_point: R5
paths: ["ccp/wt.py", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "docs/cli/", "docs/spec/02-delivery.md", "tests/test_wt.py", "tests/test_merge_base*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0083-worktree-exec-and-base-follow-ups

## Intent

A seat checking work in a worktree knows which `ccp` runs, a merge-base run never leaves a worktree behind or runs against a stale base, and a verifier can prove a test passes without git history (§12.1, §15.1).

## Context (not checked)

- Accepted plane proposals from the reviews of the worktree-exec and merge-base tasks, and one asking for shallow checkouts (three seats built one by hand).
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** tests for `ccp wt exec`'s two refusal branches; the reviewer and verifier briefs say `ccp wt exec --print` shows which `ccp` runs; `run_on_base` removes its worktree and record if anything after creation fails, has a timeout (`--timeout`, default the env hook timeout), cleans up on SIGTERM, warns when the merge-base fetch fails, and prints its own refusals with exit codes distinct from the command's; `ccp wt create --shallow --sha <sha>` makes a depth-1 checkout at that sha.
- **Out:** other worktree kinds.

## dod_checks

- id: `check-01`
  story: As a verifier, a failed base run leaves nothing.
  setup: a scratch product where saving the base record fails after the worktree is made.
  steps:
    1. Run `ccp wt create --kind base … -- true`.
  expect: it fails, and neither the worktree nor its record remains.
  dry run: on the merge base the worktree and record remain.
- id: `check-02`
  story: As a verifier, I get a shallow checkout.
  setup: a scratch product with three commits.
  steps:
    1. Run `ccp wt create --shallow --sha <head>`.
  expect: the worktree is at that sha with a history of depth 1.
  dry run: on the merge base the option does not exist.
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
