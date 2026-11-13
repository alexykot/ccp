---
task_id: 0085-release-a-claimed-task-with-no-open-run
title: The lead can release a claimed task with no open worker run, keeping its branch
status: pending
kind: feature
depends_on: []
spec_refs: ["S10"]
review_point: R5
paths: ["ccp/lifecycle.py", "ccp/cli.py", "docs/spec/02-delivery.md", "tests/test_tasks_release*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0085-release-a-claimed-task-with-no-open-run

## Intent

When a claimed task's checks or scope turn out wrong, the lead can release it while no worker run is open, keeping its branch and PR, amend it unleased and have it re-claimed under the same id (§10.5), instead of dropping it and superseding it with a new id.

## Context (not checked)

- Accepted plane proposal from a superseded task: §10.5 routes such a change through releasing or superseding, but `ccp tasks release` refuses any task with a run behind it, so the only route was a new task id and branch.
- §31: this task adds or changes a § rule beyond describing its own feature, so its merge waits on the operator's approval of the final text at its merge gate (§31.1).

## Scope

- **In:** `ccp tasks release <id> --keep-branch --reason R` releases a claimed task whose worker runs are all closed: the lease clears, the queue status returns to `pending`, the branch and PR stay, and a later claim resumes on them; a task with an open run is still refused; §10.5 states it (CURRENT: release undoes only a leased task with no run; PROPOSED: "or, with `--keep-branch`, a claimed task whose runs are all closed, keeping its branch and PR").
- **Out:** releasing a task with an open run.

## dod_checks

- id: `check-01`
  story: As a lead, I release an in-flight task with no open run.
  setup: a scratch product with a claimed task whose implement run is closed and a pushed branch.
  steps:
    1. Run `ccp tasks release <id> --keep-branch --reason fix-check`.
    2. Run `ccp tasks claim <id>`.
  expect: the release succeeds and the branch remains; the re-claim resumes on that branch.
  dry run: on the merge base the release is refused.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-13 (implementer): `ccp tasks release <id> --keep-branch --reason R` (`ccp/lifecycle.py`
  `release`, `_releasable_keeping_branch`; flag in `ccp/cli.py`) releases a claimed task whose runs
  are all closed (no run `pending`, `running` or `stopped`, §11.1): every claimed phase from `leased`
  to `verifying`, `blocked`, or `pending` (a release that stopped after its phase move), with or
  without a PR. It refuses (exit 3) an open run, naming it; a task `merging`; and one merged by close.
  The release itself is the existing one (wait, phase, lease cleared and recorded, out of
  `work.json`), and its result adds `kept_branch`. The branch, its PR and the worktree are untouched;
  the later claim is a fresh claim (status `leased`, the task file's checks re-read) in the kept
  worktree on the kept branch. Without the flag nothing changes but the refusal for a task with work
  behind it, which now names `--keep-branch`. Choices the task left open: `merging` is refused (a
  merge may be under way); prompt audits from before run records do not count under the flag (they
  are not runs); the task's time restarts at the re-claim, as §10.4 already says for every release.
  SPEC: §10.4's Release bullet and §10.5's paragraph on changing a claimed task state it, with the
  PROPOSED text; the CLI table in `docs/cli/02-delivery.md` names the flag.

## Verification notes

*Append-only.*
