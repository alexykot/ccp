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
- Lead ruling, fix round 1 (verbatim): "(1) edit SPEC §15.6 rule 2 and §16.1 so each points to the
  catch-up exception in §16.5 rule 4, so the SPEC does not contradict itself. In the PR body's §31
  section quote each with its exact CURRENT text (and PROPOSED), alongside the other four sites. (2)
  Also fix the review's MINOR 1 (runner brief step 9 / Several runners rule 4: say close may run the
  gate lane before merging, up to 3 times, so give it the longest timeout and re-run it if
  interrupted) and MINOR 3 (add a test that a task with sign_off: brief and its sign-off recorded
  still catches up and merges). NITs optional; skip them unless trivial. Then merge origin/main if
  behind, and report the new head."

## Scope

- **In:**
  - `ccp tasks close` at `behind_tip` catches up only when all hold:
    (a) `git merge-tree` of the verified head and `origin/<integration>` is clean;
    (b) the files the tip's new commits change (the same `git log <head>..origin/<integration>` set as
    today, after the task-log and `merge.behind_tip_ignore` exclusions) meet neither the files the
    task's own diff changes (`git diff --name-status --no-renames <merge-base>..<head>`, both sides of
    any rename) nor the task's declared `paths`;
    (c) the task declares no `build` sign-off (a catch-up changes the head a build sign-off covers, so
    such a task falls back to the merge round and re-verify; a `brief` sign-off is unaffected, being
    tied to the task file, not the head);
    (d) the task declares non-empty `paths` (with none, the overlap test has nothing to go on);
    (e) the product configures a gate lane (`suite.roles` gate); with none, close refuses and falls
    back, never skipping the run.
  - Then close makes the merge commit in its merge worktree, runs the product's gate lane (the lane
    `suite.roles` gives the `gate` role) on it through `ccp suite run` as a recorded run bound to the
    task, and on a green gate re-checks `behind_tip` against the new head. If the tip moved again it
    repeats the catch-up, at most 3 times in all, then refuses `behind_tip`. Otherwise it pushes the
    commit as the task branch's new head and merges pinned to it.
  - The verification record gains `catch_up: {from, to, tip, gate_run, merge_tree: clean,
    tip_files, task_files}`. `ccp verify merge-ok` accepts the new head only through such a record
    with a green gate run bound to this task.
  - Every other case refuses as today (`behind_tip`), naming the condition that failed (conflict,
    overlap, build sign-off, red gate, tip moved too often, push or merge refused), with the task
    branch unchanged.
  - The `behind_tip` refusal hint, the `ccp prompt merge` text and the runner brief's close step name
    the new path.
  - SPEC, each with its exact CURRENT text and PROPOSED text quoted in the PR body:
    - §16.5 rule 4, added before "The task's implementer merges": "When the merge with the tip is
      clean, the tip's new commits change no file the task's own diff or declared paths change, and
      the task declares no build sign-off, close merges the tip into the verified head itself, runs
      the gate lane on the result as a recorded run, re-checks the tip (at most 3 catch-ups), and on
      a green gate merges that commit, recording the catch-up in the verification record. Review and
      verify are not repeated: the task's own diff is unchanged. A break outside the gate lane's
      coverage is not caught here; the gate lane is what the integration branch is held to.
      Otherwise it refuses as above, naming the condition that failed."
    - §10.5 close step 1: "refuses a head behind the tip" becomes "refuses a head behind the tip
      unless it catches it up (§16.5 rule 4)".
    - §15.5: the merge is pinned to the verified head, or to a head recorded as its catch-up.
    - §15.6 rule 3: a new head needs a new verdict, except a catch-up close made itself (§16.5 rule 4).
- **Out:** changing what review or verify judge; serialising closes.

## dod_checks

- id: `check-01`
  story: As a runner, my verified task closes when the other runner's merge touched other files.
  setup: a scratch product with two runners; task A verified at head H; task B merges first,
    changing only files outside A's diff and declared paths.
  steps:
    1. Run `ccp tasks close A --pr <A's PR>`.
  expect: close merges the tip into H, runs the gate lane as a recorded run, and merges that commit;
    the merged commit is the record's `catch_up.to`, which carries both heads, the tip and the run.
  dry run: on the merge base close refuses with `behind_tip`.
- id: `check-02`
  story: As a runner, an overlapping tip still sends me back.
  setup: as check-01, but B changes a file A's diff changes; a second case where B renames a file A
    changes; a third where B changes a file under A's declared paths that A's diff does not touch.
  steps:
    1. Run `ccp tasks close A` in each case.
  expect: each refuses `behind_tip` naming overlap; nothing is merged; A's branch is unchanged. A
    fourth case, A with empty `paths`, refuses naming the missing declaration.
  dry run: n/a.
- id: `check-03`
  story: As a runner, a conflicting merge or a red gate sends me back.
  setup: as check-01, but B's change makes `git merge-tree` conflict; separately, B's change is
    disjoint but makes the gate lane fail on the merged tree (B removes a helper A's new test imports
    from an untouched module).
  steps:
    1. Run `ccp tasks close A` in each case.
  expect: refuses `behind_tip` naming conflict, then red gate (with the gate run id); nothing merged.
  dry run: n/a.
- id: `check-04`
  story: As a runner, a tip that moves during the catch-up gate does not merge a stale head.
  setup: as check-01, with a third task C merging (disjoint) while A's catch-up gate runs.
  steps:
    1. Run `ccp tasks close A`.
  expect: close re-checks after the gate and catches up again (a second recorded gate run) or, past 3
    catch-ups, refuses `behind_tip`; it never merges a head behind the tip.
  dry run: n/a.
- id: `check-05`
  story: As a lead, a build sign-off is never carried across a catch-up.
  setup: as check-01, with A declaring `sign_off: build` and its sign-off recorded at H.
  steps:
    1. Run `ccp tasks close A`.
  expect: refuses `behind_tip` naming the build sign-off; nothing merged.
  dry run: n/a.
- id: `check-06`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-13 — implementer: `ccp tasks close` at `behind_tip` (several runners) calls `lifecycle._catch_up`.
  Conditions, in the order checked: no `build` sign-off; non-empty frontmatter `paths` (the declared ones,
  not the Scope-derived fallback of §16.3); a `suite.lanes` entry for the gate role's lane (`suite.roles`;
  the role always has a name, so "configures" is read as "the lane exists to run"); a merge worktree
  (`worktrees.dir`); a queue that keeps its records outside git. Then per round: `git merge-tree
  --write-tree` of the head and the tip (a), the merge made with `commit-tree` (parents: head, tip); the
  overlap (b): tip files are `git log -m --no-renames --name-only <head>..<tip>` with the behind_tip
  pathspec, task files `git diff --name-status --no-renames <merge-base>..<head>`, a tip file meets a task
  file exactly or a declared path by `parallel.meets`. The merge is checked out in `merge-<nnnn>` and the
  gate lane runs there as `ccp suite run --task <id> --phase verify --lane <gate> --summary --wait 1800` (a
  child of this `ccp`, `suite.self_argv`); the new suite row for the task and lane is the gate run. A green
  gate re-checks `behind_tip` on the merge; at most `CATCH_UPS = 3` rounds. Then a plain push to the PR's
  head branch (`headRefName`, else `task/<id>`), `verify.record_catch_up` (the record's `schema_version`
  raised to 2), a `verify`/`set` event (`field: catch_up`), and `merge-ok` read until the PR shows the
  push (15 reads, 2 s apart). Any refusal before the push removes the merge worktree and refuses
  `behind_tip` naming the condition; the branch is unchanged.
- `merge-ok` (`verify.catch_up_refusal`) accepts a PR head other than `head_sha` only when `catch_up.from`
  is `head_sha`, `catch_up.to` is the PR head and `gate_run` is a recorded, passed suite run of the gate
  lane bound to the task. `ccp verify record` refuses a verdict carrying `catch_up` (only close writes it).
  `ccp verify check` is unchanged: it still wants `head_sha`. A re-run of close after a merge at the
  caught-up head accepts it as approved. The Verification notes line names the catch-up and its gate run.
- A merge refused after the push leaves the branch at the catch-up, which the record covers: the error
  says so, and a re-run of close merges it (tested). The record contract's key list for version 2 is
  pinned in `tests/test_verify.py`; the example record says version 2.
- 2026-11-13 — implementer, fix round 1 (the lead's ruling in Context): SPEC §15.6 rule 2 ("close also
  refuses such a verified head unless it catches it up (§16.5 rule 4)") and §16.1 ("verified there or
  caught up by close (§16.5 rule 4)") now point to the catch-up, so the SPEC no longer contradicts it.
  The runner brief's step 9 and Several runners rule 4 say close may run the gate lane before merging,
  up to 3 times: give it the longest timeout and run it again if interrupted. New test
  `test_a_brief_sign_off_is_carried_across_a_catch_up` (a `brief` sign-off recorded before the claim;
  the tip disjoint; close catches up and merges). NITs left: none was trivial inside this scope.

## Verification notes

*Append-only.*
