---
task_id: 0167-close-catches-up-by-patch-id
title: Under parallel.schedule clashes, close catches a verified head up when its own patch is unchanged, and carries a build sign-off by the same test
status: done
kind: feature
depends_on: ["0162-git-merge-helper", "0163-catch-up-decision-as-a-function", "0164-clashes-with-and-schedule"]
spec_refs: ["S16", "S3"]
adr_refs: ["0042 D4"]
review_point: R11
paths: ["ccp/lifecycle.py", "ccp/gitmerge.py", "tests/test_catch_up_decision.py", "tests/test_gitmerge.py", "tests/test_behind_tip_catch_up.py", "contracts/verification.schema.json", "docs/spec/02-delivery.md", "plugin/agents/delivery-runner.md", "templates/prompts/merge.md"]
adopt: "none"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0167-close-catches-up-by-patch-id
## Intent

On a product that runs under `parallel.schedule: clashes`, a verified task whose head is behind the
integration tip is caught up by `ccp tasks close` itself whenever the merge leaves the task's own
patch unchanged, even when the tip changed a file the task changes and even when the task declares
no paths, so two tasks that share a hub file no longer cost a merge round and a second verify. A build
sign-off is carried across that catch-up by the same patch test. Under `parallel.schedule: paths` (the
default) close behaves exactly as today. The runner's brief and the merge-round prompt point at
SPEC §16.5 rule 4 instead of restating it, so the rule lives in the SPEC and the code alone.

## Context (not checked)

- ADR-0042 D4 (accepted 2026-11-19). The operator's ruling on the shape finding F04, 2026-11-19, in
  the lead session, quoted exactly: "patch id alone". Under `parallel.schedule: clashes` the patch-id
  test (the task's own patch unchanged) is close's whole file condition for a catch-up: the
  declared-path overlap refusal and the "no declared paths" refusal both fall away under `clashes`,
  and both stay under `paths`. The rule's other conditions stay in both modes: a clean merge
  or a union of append-only `parallel.shared` conflicts, a gate lane, a merge worktree, records kept as
  files, a green gate run on the merge, at most 3 catch-ups, a build sign-off recorded for the verified
  head.
- Today (at `b9e58ce`), `_catch_up` in `ccp/lifecycle.py` refuses `"no declared paths: ..."` when
  `meta["paths"]` is empty, and `"overlap: ..."` when a tip file is one the task's diff changes or meets
  a declared path (`parallel.meets`) and is not `parallel.covered` by `shared`; with a build sign-off
  due it refuses `"build sign-off: ..."` when any tip file is one the task's own diff changes, a
  shared path included. The tests holding that,
  `python3 -m unittest tests.test_behind_tip_catch_up -k test_a_tip_changing_a_file_the_task_changes_refuses_naming_overlap -k test_a_task_with_no_declared_paths_refuses_naming_it -k test_a_build_sign_off_is_not_carried_over_a_change_to_a_shared_file_the_task_changes` at `b9e58ce`: 3 tests, OK.
  They stay as they are: they run under the default `paths`.
- This builds on three tasks:
  - 0162-git-merge-helper (the git merge helper module, `ccp/gitmerge.py`): its own-patch-id helper, `gitmerge.own_patch_id`,
    with no fetch inside. Close has already fetched.
  - 0163-catch-up-decision-as-a-function (close's catch-up decision as a pure function, `catch_up_blocked` in `ccp/lifecycle.py`, unit-tested in
    `tests/test_catch_up_decision.py`). The new branches are unit-tested there, on plain values (shape F03). Only a few
    end-to-end tests go into `tests/test_behind_tip_catch_up.py`, the suite's slowest module.
  - 0164-clashes-with-and-schedule (`parallel.schedule`, read through `parallel.settings`).
- **The patch test.** "The task's own patch" is the `git patch-id --stable` of its diff from its merge
  base with the tip:
  - before the merge: `<merge-base(head, tip)>..<head>`;
  - after it: `<tip>..<merge>`, since the tip is the merge's merge base with the tip.
  Unchanged means the two ids are equal.
- **Context lines count.** A patch id includes the diff's context lines. So a tip edit within 3 lines
  of a task hunk changes the id and close refuses. A tip edit further away keeps it. Measured in a
  scratch repo, on a 20-line file, with `git diff <base> task | git patch-id --stable`: the task changed line 10, the tip line 12, and the id changed across the merge; a later tip change to line 1 kept the merged id. §15.2 already states the same of the integration-merge rule ("integration changes inside
  the PR's own hunks or their context lines change the patch id").
- **Two choices this brief rules, which the signed text states:**
  1. *Close's condition leaves `parallel.shared` paths out of both patches.* Close still resolves an
     append-only conflict in a shared path itself (ADR-0042 D4). After such a union, the task's
     appended lines have the tip's lines as context, so a whole-diff patch id would always differ, and
     no union catch-up could happen under `clashes`. A task whose whole diff is in shared paths has an
     empty patch on both sides, which counts as unchanged.
  2. *The sign-off carry's test takes the whole diff, shared paths included.* This mirrors today's
     carry rule, "a `parallel.shared` path included". A union or edit near the signed text then stops
     the carry, and the task goes back to a merge round and a fresh sign-off.
- **F06.** Close's condition is restated in prose in:
  - `plugin/agents/delivery-runner.md`, Several runners rule 4: "touch none of the task's own or
    declared files, no build sign-off is due";
  - `templates/prompts/merge.md`, line 1: "touch none of the task's files and merge cleanly";
  - the `ccp/lifecycle.py` module docstring.
  Under `clashes` each copy is wrong. `git grep -n -e "touch none of the task" -e "no build sign-off is due" -- plugin/agents templates/prompts` at `b9e58ce` prints 3 lines: `delivery-runner.md:226`, `delivery-runner.md:227` and `merge.md:1`.
- **No test pins those texts.** `git grep -n "touch none" -- tests` at `b9e58ce` prints nothing.
- **What merge-ok checks.** `verify.catch_up_refusal` (merge-ok) checks only the catch-up's from, to
  and gate run, not which files the tip touched, so it needs no change. The verification schema's
  `catch_up.tip_files` and `sign_off_carried` descriptions say the tip touched no file of the task.
  That becomes false under `clashes`, so they are corrected (§31.1). The record's shape and
  `RECORD_VERSION` do not change.

## Scope

- **In:**
  - `ccp/gitmerge.py` `own_patch_id` gains two keyword-only arguments; with neither, it behaves as 0162
    built it, so `runs._same_patch` is unchanged:
    - `exclude: list[str] = ()`, files left out of the diff (literal pathspecs);
    - `empty: str | None = None`, what it returns for an empty diff.
    It stays standard library only, and the caller works out which files `parallel.shared` covers.
  - `catch_up_blocked` (`ccp/lifecycle.py`) gains `schedule` (default `"paths"`), and two inputs used
    only under `clashes`: `patch_same` and `whole_patch_same` (booleans, or None when a patch could
    not be read). Under `clashes`:
    - its file condition is `patch_same` alone: true allows. False refuses `patch changed: the merge
      changes the task's own patch (parallel.schedule clashes)`. None refuses `patch unread: the task's
      own patch could not be read`.
    - It never refuses `overlap` or `no declared paths`.
    - With a build sign-off due, it allows only when `whole_patch_same` is also true. Otherwise it
      refuses `build sign-off: the merge changes the task's whole own patch, which the build sign-off
      covers (SPEC §16.5 rule 4)`.
    Under `paths` every branch, text and order is as today.
  - `ccp/lifecycle.py` `_catch_up`, under `clashes` only:
    - before the merge it raises no "no declared paths";
    - in the loop, it computes four ids with `gitmerge.own_patch_id(..., empty="")`: `head` against
      the tip, and the merge against the tip, each once whole and once with `exclude` set to the files
      of that diff that `parallel.covered` puts under `parallel.shared`;
    - it passes `patch_same` (the two shared-excluded ids equal) and `whole_patch_same` (the two whole
      ids equal) to `catch_up_blocked`, each None when either id is None.
    Under `paths` it computes no patch id. The module docstring's restatement of the condition becomes
    a pointer to §16.5 rule 4 and `catch_up_blocked`. No `ccp` module other than `ccp/gitmerge.py`
    names the git subcommands E14 lists.
  - `contracts/verification.schema.json`, two descriptions only:
    - `catch_up.tip_files`: "none the task's own diff or declared paths change (under
      `parallel.schedule: paths`); under `clashes`, any files, the task's own patch unchanged";
    - `catch_up.sign_off_carried`: the carry reason adds "or, under `parallel.schedule: clashes`, the
      task's whole own patch was unchanged".
  - `docs/spec/02-delivery.md` §16.5 rule 4, two passages. Each PROPOSED replaces its CURRENT text in
    place, on one unwrapped line:
    1. CURRENT (at `b9e58ce`): "file the task's own diff or declared paths change other than a `parallel.shared` path," PROPOSED:
       > file the task's own diff or declared paths change other than a `parallel.shared` path (under `parallel.schedule: paths`, the default), or, under `parallel.schedule: clashes`, the task's own patch is unchanged by the merge, whatever files the tip changed and whether or not the task declares paths (the same `git patch-id --stable` of its diff from its merge base with the tip, before the merge and after it, `parallel.shared` paths left out of both),
    2. CURRENT (at `b9e58ce`): "with the tip's new commits changing no file the task's own diff changes, a `parallel.shared` path included," PROPOSED:
       > with, under `paths`, the tip's new commits changing no file the task's own diff changes, a `parallel.shared` path included, or, under `clashes`, the task's whole own patch, `parallel.shared` paths included, unchanged by the merge,
  - `plugin/agents/delivery-runner.md`, Several runners rule 4 (F06): the conditions in "caught up by
    `ccp tasks close` itself when the merge is clean, ... and the product has a gate lane" become
    "when SPEC §16.5 rule 4 allows (close's refusal names the condition that failed)". The rest of the
    paragraph stays.
  - `templates/prompts/merge.md` (F06): the parenthesis becomes "(`ccp tasks close` catches a verified
    head up itself when SPEC §16.5 rule 4 allows; this round is for the cases it refuses, and its
    refusal names the condition that failed.)".
  - `tests/test_catch_up_decision.py`: the unit cases of cu-01 and so-01.
  - `tests/test_gitmerge.py`: `own_patch_id` with `exclude` leaves a file out (two heads differing only
    in that file give equal ids); with `empty=""` an empty diff gives `""`; with neither, the results
    are as before.
  - `tests/test_behind_tip_catch_up.py`: the end-to-end cases of cu-02 and cu-03, as methods of
    `CatchUp`. A helper switches the fixture product to `parallel.schedule: clashes`: it rewrites the
    product's plane.json and pushes it, as `setUp` pushes the product's files. A subclass would run
    every inherited test a second time in the suite's slowest module.
  - ADR-0042 D4 (shared with task 0168): the first of 0167 and 0168 to close marks D4 built (`ccp adr decide 42 D4 built`), since `adr.strict` refuses an approve citing a decision not built at the head (ruling sm-20261119T113130Z-8831); the second marks nothing.
- **Out:**
  - Conflicted catch-ups and the resolution review (task 0168).
  - The behind-tip check itself (`_close_behind_tip`, `merge.behind_tip_ignore`), which is unchanged.
  - `ccp prompt verify`'s behind-tip refusal.
  - Any change under `parallel.schedule: paths`.
  - A new verification-record field or a `RECORD_VERSION` bump.

## dod_checks

- id: `cu-01`
  story: As a plane developer, close's decision under clashes is the patch test alone, and under paths it is unchanged.
  setup: the unit test module `tests/test_catch_up_decision.py` at the PR head, calling `catch_up_blocked` on plain values.
  steps:
    1. Call it with schedule `clashes`, a tip file the task's diff also changes, a declared path the tip changes, `patch_same=True` and no sign-off due.
    2. Call it with schedule `clashes`, no declared paths, `patch_same=True`.
    3. Call it with schedule `clashes` and `patch_same=False`, then with `patch_same=None`.
    4. Call it with schedule `paths` and the inputs of steps 1 and 2.
  expect: step 1 and step 2 allow; step 3 refuses with reasons starting `patch changed` and `patch unread`; step 4 refuses `overlap` for step 1's inputs and `no declared paths` for step 2's, as at the base.
  dry run: n/a — the schedule argument does not exist at `b9e58ce`; under paths, the 3 end-to-end tests named in Context pass there.
- id: `cu-02`
  story: As a runner on a clashes product, close catches up a head whose tip edit is far from the task's hunks and refuses one that is near.
  setup: the fenced `CatchUp` product of `tests/test_behind_tip_catch_up.py` with `parallel.schedule: clashes`; the task's approved head changes line 1 of `shared.txt` (a declared path).
  steps:
    1. Push a tip commit changing `line 10` of `shared.txt`, then run `ccp tasks close 0002 --pr <n>`.
    2. In a fresh product of the same setup, push a tip commit changing `line 3` of `shared.txt`, then run the same close.
  expect: step 1 exits 0, merges the catch-up head, and the verification record carries `catch_up` with a recorded gate run; step 2 exits 1, stderr names `behind_tip` and `patch changed`, no gate run is recorded and `task/0002` is unchanged.
  dry run (`b9e58ce`): step 1's tip under the default `paths` refuses `overlap` naming `shared.txt` (the test named in Context). In a scratch repo with the fixture's 10-line file and the task's line-1 change, `git merge-tree --write-tree` exits 0 for both tips, and `git patch-id --stable` gives the same id across the merge for the line-10 tip and a different one for the line-3 tip.
- id: `cu-03`
  story: As a runner on a clashes product, a task with no declared paths is still caught up.
  setup: the fenced `CatchUp` product with `parallel.schedule: clashes`; the task approved with no `paths` (`approved(paths=False)`); a tip commit adding `other/b.txt`.
  steps:
    1. Run `ccp tasks close 0002 --pr <n>`.
  expect: exit 0; the merge is the catch-up head. Under the default `paths` the same setup still refuses naming `no declared paths`: `test_a_task_with_no_declared_paths_refuses_naming_it` passes unchanged.
  dry run (`b9e58ce`): under `paths` it refuses `no declared paths` (that test, OK).
- id: `so-01`
  story: As the operator, a build sign-off is carried only when the task's whole patch is unchanged.
  setup: the unit test module `tests/test_catch_up_decision.py` at the PR head, calling `catch_up_blocked` with schedule `clashes` and a build sign-off due.
  steps:
    1. Call it with `patch_same=True` and `whole_patch_same=True`.
    2. Call it with `patch_same=True` and `whole_patch_same=False` (a union in a shared path the task changes).
  expect: step 1 allows (close then records `sign_off_carried`); step 2 refuses with a reason starting `build sign-off`.
  dry run: n/a — the schedule argument does not exist at `b9e58ce`.
- id: `brief-01`
  story: As a plane maintainer, close's catch-up condition is written once, in the SPEC and the code.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -e "touch none of the task" -e "no build sign-off is due" -- plugin/agents templates/prompts`.
    2. Run `git grep -n "16.5 rule 4" -- plugin/agents/delivery-runner.md templates/prompts/merge.md`.
  expect: step 1 prints nothing; step 2 prints at least one line from each of the two files.
  dry run (`b9e58ce`): step 1 prints 3 lines (`delivery-runner.md:226`, `:227`, `merge.md:1`); step 2 prints lines from both files.
- id: `suite-01`
  story: As a plane developer, the SPEC carries the signed words and nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0167-close-catches-up-by-patch-id --base origin/main`.
    2. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: step 1 exits 0 with both passages found in `docs/spec/02-delivery.md`; step 2's commands all pass and the branch list is empty.
  dry run: n/a — the passages are not in the SPEC at `b9e58ce`.

## Implementation notes

*Append-only, newest last.*

- Premise re-run at b2c2845: the three named end-to-end tests pass (3 tests, OK); the `git grep` for the runner
  brief and merge prompt texts printed the 3 lines the task states; `git grep -n "touch none" -- tests` printed nothing.
- `own_patch_id` takes `exclude` as a `Sequence[str]` (the task says `list[str]`; a tuple default is the
  narrower typing). Excludes are `:(exclude,literal)<path>` pathspecs after `-- .`.
- Close runs git for the patch ids through a small runner in `lifecycle._own_patches` (`subprocess.run` with
  `input=`, 60 s timeout, `GIT_TERMINAL_PROMPT=0`, the same as `runs.same_change`), since `queue.git` takes no
  stdin. A timeout there reads as an unread patch (`patch unread` refuses).
- Under `clashes` the `task_files` of the merge are read once more (`_task_files(cfg, merged, tip)`) to find the
  shared files to leave out of the after-merge patch; the before-merge ones reuse the loop's `task_files`.
- A sign-off due with an unread whole patch refuses `build sign-off` (the whole patch is not known unchanged).
- ADR-0042 D4 marked built by this task (first of 0167 and 0168 to close).

## Verification notes
- 2026-11-19 — verifier, PR #187 head `ee0f6b8` (squash `aeebec0`): APPROVE. Passed: cu-01, cu-02, cu-03, so-01, brief-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0167-close-catches-up-by-patch-id.json.

