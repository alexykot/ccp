---
task_id: 0098-close-catches-up-a-clean-disjoint-head
title: Close merges a verified head behind the tip when the tip's new commits do not touch the task's files
status: pending
kind: feature
depends_on: []
spec_refs: ["S10", "S15", "S16"]
review_point: R5
paths: ["ccp/lifecycle.py", "ccp/verify.py", "ccp/suite.py", "docs/spec/02-delivery.md", "plugin/agents/delivery-runner.md", "tests/test_tasks_close*.py", "tests/test_behind_tip*.py"]
created: 2026-11-13
updated: 2026-11-13
---

# Task: 0098-close-catches-up-a-clean-disjoint-head

## Intent

With several runners, a verified task closes without chasing the integration tip when the tip moved
only in files the task does not touch: `ccp tasks close` merges the tip into the verified head,
re-runs the gate on the result, and merges, instead of refusing as `behind_tip` and sending the task
through a merge round and a full re-verify (§16.5 rule 4).

## Context (not checked)

- An accepted plane proposal: with two runners each close moves the tip, so the other runner's
  verified task is refused as behind the tip and pays a merge round plus a full gate re-verify (about
  25–40 minutes), sometimes three or four times in a row. On the plane's own backlog this cost several
  hours across a handful of tasks in two days.
- What the re-verify adds when the tip's new commits and the task's own diff touch different files is
  only the gate on the combined tree: review and verify judged the task's diff, which is unchanged.
- Operator ruling, 2026-11-13, in the lead session ("Yes, write it"), on the lead's proposal: when a
  verified task's merge with the tip is clean and the tip's new commits don't touch the task's own
  files, close merges after re-running only the gate. §31: this changes when close may merge, so the
  merge waits on the operator's approval of the final text at its gate.

## Scope

- **In:**
  - `ccp tasks close` at `behind_tip`: when (a) `git merge-tree` of the verified head and
    `origin/<integration>` is clean, and (b) the files the tip's new commits change (the same
    `git log <head>..origin/<integration>` set as today, after the task-log and
    `merge.behind_tip_ignore` exclusions) do not meet the files the task's own diff changes
    (`git diff <merge-base>..<verified head>`), close makes the merge commit in its merge worktree,
    runs the gate lane on it through `ccp suite run` (a recorded run, bound to the task), and on a
    green gate pushes that commit as the task branch's new head and merges it pinned to that head.
    The verification record gains `catch_up: {from: <verified head>, to: <new head>, tip, gate run}`.
    A red gate, a conflicting merge-tree or overlapping files refuse as today (`behind_tip`), naming
    which condition failed, so the runner falls back to a merge round and re-verify.
  - `ccp verify merge-ok` accepts the new head only through that recorded catch-up.
  - The runner brief's close step says close catches up on its own in that case.
  - §16.5 rule 4 states the rule; CURRENT → PROPOSED below. §10.5 close step 1 points to it.
  - Tests: a disjoint clean catch-up merges with a recorded gate run; overlapping files refuse; a
    conflicting merge-tree refuses; a red gate refuses and leaves the branch unchanged.
- **Out:** changing what review or verify judge; serialising closes.

§16.5 rule 4, CURRENT (last sentences): "… with several runners close still checks. The task's
implementer merges `origin/<integration>` into the task branch … and resolves any conflict; the task
is verified again on the new head".
PROPOSED (added before "The task's implementer merges"): "When the tip's new commits change no file
the task's own diff changes and the merge is clean, close merges the tip into the verified head
itself, runs the gate lane on the result as a recorded run, and on a green gate merges that commit,
recording the catch-up in the verification record; review and verify are not repeated, since the
task's own diff is unchanged. Otherwise it refuses as above, naming the condition that failed."

## dod_checks

- id: `check-01`
  story: As a runner, my verified task closes when the other runner's merge touched other files.
  setup: a scratch product with two runners; task A verified at head H; task B merges first,
    changing only files A's diff does not touch.
  steps:
    1. Run `ccp tasks close A --pr <A's PR>`.
  expect: close merges the tip into H, runs the gate as a recorded run, merges the new head, and the
    verification record carries `catch_up` with both heads and the gate run.
  dry run: on the merge base close refuses with `behind_tip`.
- id: `check-02`
  story: As a runner, an overlapping or conflicting tip still sends me back.
  setup: as check-01, but B changes a file A also changes; then a case where merge-tree conflicts;
    then a case where the gate goes red on the merge.
  steps:
    1. Run `ccp tasks close A` in each case.
  expect: each refuses `behind_tip`, naming overlap, conflict or red gate; nothing is merged and A's
    branch is unchanged.
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

## Verification notes

*Append-only.*
