---
task_id: 0083-worktree-exec-and-base-follow-ups
title: wt exec, base runs and shallow checkouts are complete and clean up after themselves
status: done
kind: feature
depends_on: []
spec_refs: ["S12", "S15"]
review_point: R5
paths: ["ccp/wt.py", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "docs/cli/", "docs/spec/02-delivery.md", "tests/test_wt.py", "tests/test_merge_base*.py"]
created: 2026-11-12
updated: 2026-11-13
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

- 2026-11-13 (implementer): `run_on_base` (`ccp/wt.py`) now wraps everything after the merge base in
  one try/finally: the record save, the command, a SIGTERM (a handler raising in the main thread, the
  caller's handler restored after) and any OSError all end in `remove`; `create` removes a half-made
  `base` worktree and its record itself when its link, setup or save step raises. The command runs in
  its own process group; `--timeout S` (default `env.timeout_seconds`) kills the group, exit 124,
  `timed_out: true`. A SIGTERM to ccp exits 143 with `signal: 15` in the result. A failed fetch in
  `merge_base` is a warning (`warnings` argument; `ccp mutate` passes none and is unchanged).
- Distinct refusal codes: a base run's own refusals and failures exit 125 (`BASE_REFUSED`, as
  timeout(1)'s "the wrapper failed"), print why on stderr and no result JSON; a command or `--timeout`
  on another kind stays exit 2. The existing `test_refusals` expectations for base runs moved from
  2/3 to 125, as Scope asks.
- `--shallow` (rev, ver, mut, mac) is a depth-1 clone (`git init` + `git fetch --depth 1
  file://<main> <full sha>` + detached checkout): a git worktree shares the whole history, so it
  cannot be shallow. Recorded with `shallow: true` (added to `contracts/worktree.schema.json`);
  removal deletes a clone (`.git` a directory) instead of `git worktree remove`; reuse needs the same
  depth (exit 3). check-02's command needs `--kind` and `--task` like any other create.
- The reviewer and verifier briefs say `ccp wt exec --print` shows which `ccp` runs (`$CCP_ROOT`
  wins); the verifier brief also names `--shallow` and the 125/124 codes. SPEC §12.1 describes the
  new behaviour (§31.1, this task's own feature).

## Verification notes

- 2026-11-13 — verifier, PR #91 head `beff06e` (squash `b3ad843`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0083-worktree-exec-and-base-follow-ups.json.
