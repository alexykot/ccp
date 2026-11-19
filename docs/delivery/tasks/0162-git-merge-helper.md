---
task_id: 0162-git-merge-helper
title: One git merge helper module for the merge probe, a head's own patch id and the remerge diff
status: done
kind: refactor
depends_on: []
spec_refs: ["S13", "S15", "S16"]
review_refs: ["sh-20261119T072530Z-663f#F02"]
review_point: R11
paths: ["ccp/gitmerge.py", "ccp/lifecycle.py", "ccp/verify.py", "ccp/runs.py", "ccp/CLAUDE.md", "docs/delivery/plane.json", "tests/test_gitmerge.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0162-git-merge-helper

## Intent

The plane has one reading of "does merging these two commits conflict, and in which files" and one
reading of "a head's own change, by patch id", in one module, so the review refusal, close's
catch-up by patch id, the resolution review and health's conflict count that ADR-0042 adds all build
on the same probe. `ccp docs check` holds the rule (house rule E14) from now on. Nothing the plane
does changes.

## Context (not checked)

- Shape report `sh-20261119T072530Z-663f`, finding F02; this is its task T1. Tasks that depend on it:
  close's catch-up decision as a function, the review catch-up and refusal, and the resolution review.
- House rule E14 (docs/ENGINEERING.md): git merge analysis (merge-tree, patch-id, remerge-diff) goes
  through one helper module; its check is the `git grep` in `gm-01`. This task adds that check to
  `docs.checks`.
- Today, `git grep -n -e merge-tree -e patch-id -e remerge-diff -- ccp` at `b9e58ce`: 12 lines, in three modules:
  - `ccp/lifecycle.py` `_catch_up_commit`: `git merge-tree --write-tree -z --no-messages head tip`, parsed with
    `STAGE_RE` into each conflicted file's stages (mode, blob) for `_union`; two refusal texts name
    `git merge-tree`; `_union`'s docstring says "merge-tree stages".
  - `ccp/verify.py` `_judge_fix` (the review skip): `git merge-tree --write-tree --no-messages reviewed base`,
    without `-z`, reading only the tree and the exit code; an exit that is neither success nor conflict is refused as
    "`git merge-tree --write-tree` failed (exit N); it needs git 2.38 or later". `skip_review`'s docstring
    names `git merge-tree` twice.
  - `ccp/runs.py` `_same_patch` (the integration-merge rule, via `same_change`): fetches origin inside
    itself, then for each head `merge-base` with `origin/<integ>`, `diff --binary`, `patch-id --stable`.
- No remerge-diff exists today: the helper's `remerge_diff` has no caller in this task. The resolution
  review task is its first caller; it is in this module now so that task adds no git analysis of its own.
- Tests that pin the current behaviour and must keep passing unchanged:
  - `tests/test_review_skip.py` `test_a_git_that_cannot_write_the_merge_tree_is_named` patches
    `ccp.queue.git` and matches calls whose first two arguments are `("merge-tree", "--write-tree")`.
    The helper therefore runs git through `ccp.queue.git`, looked up when it is called, and puts
    `merge-tree --write-tree` first, any `-z` after.
  - `tests/test_prompt_rounds.py` patches `ccp.runs.same_change`, so that name and signature stay.
  - Refusal texts are asserted by substring in `tests/test_behind_tip_catch_up.py` ("conflict",
    "conflicts in") and `tests/test_review_skip.py` (the old-git text and "does not merge cleanly").
    Every user-facing text stays byte for byte; a text that names a git subcommand is built in the
    helper, so the E14 search finds it there only.
- Measured (dry runs below): the mutation of each probe's conflict reading fails named tests in
  `test_behind_tip_catch_up`, `test_review_skip` and `test_review_gate`. Their cost:
  - `python3 -B -m unittest -q tests.test_behind_tip_catch_up` at `b9e58ce`: 38 tests in 102 s;
  - `python3 -B -m unittest -q` of the other seven `gm-02` modules at `b9e58ce`: 135 tests in 129 s.
- No SPEC change: `git grep -n -e merge-tree -e patch-id -e "merge probe" -- docs/spec` at `b9e58ce` finds nothing to move.

## Scope

- **In:**
  - `ccp/gitmerge.py` (new), standard library only, its docstring citing §15.2 (the review skip),
    §16.5 rule 4 (close's catch-up) and §13 (the integration-merge rule):
    - `probe(root, ours, theirs)`: runs `git merge-tree --write-tree -z --no-messages` through
      `ccp.queue.git` and returns the tree, the conflicted files with their stages (stage number to
      mode and blob, `STAGE_RE` moved here), the exit code, and whether git could not run the merge at
      all (an exit other than 0 or 1, or no tree).
    - `own_patch_id(root, sha, base_ref, run)`: the patch id (`patch-id --stable`) of the diff from
      `sha`'s merge base with `base_ref` to `sha`, or None when it cannot be read or the diff is empty;
      it never fetches. `run` is the caller's git runner, so `runs` keeps its environment and timeout.
    - `remerge_diff(root, merge)`: the `git show --remerge-diff` text of a merge commit (how its
      recorded resolution differs from git's automatic merge); empty for a clean merge.
    - The refusal texts that name a git subcommand (the two in `_catch_up_commit`, the git 2.38 text in
      `_judge_fix`) are made here, unchanged.
  - `ccp/lifecycle.py` `_catch_up_commit` and `ccp/verify.py` `_judge_fix` call `probe`; `ccp/runs.py`
    `_same_patch` keeps its fetch and calls `own_patch_id` for each head. Docstrings in these three
    modules that name the subcommands point at the helper instead.
  - `ccp/CLAUDE.md`: the file map lists `gitmerge.py` under the runtime queue, worded without the three
    subcommand names (the E14 search reads `ccp/`).
  - `docs/delivery/plane.json`: a `docs.checks` entry `{"id": "merge-helper", "cmd": "! git grep -n -e merge-tree -e patch-id -e remerge-diff -- ccp ':(exclude)ccp/gitmerge.py'"}` (house rule E14), after `leak-check`.
  - `tests/test_gitmerge.py` (new), on a temp repository: `probe` of a clean merge gives a tree and no
    conflicted files; of a conflicting one, the file with stages 1, 2 and 3; a git that exits 129 is
    reported as unable to merge; `own_patch_id` of two heads carrying the same change on different bases
    is equal and its runner sees no `fetch`; `remerge_diff` of a hand-resolved conflict is non-empty and
    of a clean merge empty.
  - No existing test changes.
- **Out:**
  - Any new caller (review refusal, close by patch id, health's count): the dependent tasks.
  - The fetch policy of `same_change`, `skip_review` or close.
  - README's git 2.38 prerequisite line (outside `ccp/`, still true).

## dod_checks

- id: `gm-01`
  story: As a plane developer, `ccp docs check` holds house rule E14, and the helper is the only place git merge analysis lives.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp docs check`.
    2. Run `git grep -n -e merge-tree -e patch-id -e remerge-diff -- ccp`.
  expect: step 1 exits 0 and `docs/delivery/plane.json` has the `merge-helper` entry in `docs.checks`; step 2 lists lines in `ccp/gitmerge.py` only.
  dry run (`b9e58ce`): the entry's command `sh -c '! git grep -n -e merge-tree -e patch-id -e remerge-diff -- ccp ":(exclude)ccp/gitmerge.py"'` exited 1, printing 12 lines (`ccp/lifecycle.py` 1620, 1625, 1630, 1632, 1653, 1694; `ccp/runs.py` 381; `ccp/verify.py` 666, 678, 733, 735; and none in the helper, which does not exist), so the check fails at the base.
- id: `gm-02`
  story: As a plane developer, close's catch-up, the review skip and the integration-merge rule behave as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_behind_tip_catch_up tests.test_review_skip tests.test_review_skip_clean tests.test_review_skip_provers tests.test_review_gate tests.test_prompt_rounds tests.test_sign_off_beyond_intent tests.test_parallel_merging`.
    2. Run `git diff --name-only origin/main...HEAD -- tests/`.
  expect: step 1 exits 0; step 2 lists only `tests/test_gitmerge.py`.
  dry run (`b9e58ce`): step 1's modules passed (38 tests in the catch-up module; 135 in the other seven together); step 2 n/a.
- id: `gm-03`
  story: As a plane developer, those tests bite on the helper.
  setup: three separate copies of the PR head (not the branch's worktree): in the first, `probe` reports no conflicted files and exit 0 whatever git returns; in the second, `own_patch_id` returns the same value for every head; in the third, `probe` reports every merge as one git could not run.
  steps:
    1. In the first copy, run `python3 -B -m unittest -q tests.test_behind_tip_catch_up.CatchUp.test_a_changed_line_in_a_shared_file_still_refuses_naming_it tests.test_review_skip.SkipReview.test_a_reviewed_change_that_conflicts_with_the_new_base_is_reviewed`.
    2. In the second, run `python3 -B -m unittest -q tests.test_review_gate.MergeIn.test_a_merge_in_with_the_same_change_needs_no_new_review`.
    3. In the third, run `python3 -B -m unittest -q tests.test_behind_tip_catch_up.CatchUp.test_a_disjoint_tip_is_caught_up_gated_and_merged`.
  expect: each run exits non-zero with a failure or error in each named test.
  dry run (`b9e58ce`): the same mutations made at their current sites (`_catch_up_commit`'s `if r.returncode == 1:` → `if False:`, `_judge_fix`'s exit test dropped, `_same_patch` returning True) failed `test_a_changed_line_in_a_shared_file_still_refuses_naming_it`, `test_lines_both_sides_append_to_a_shared_file_merge_tip_first`, `test_a_reviewed_change_that_conflicts_with_the_new_base_is_reviewed` and `test_a_merge_in_with_the_same_change_needs_no_new_review`; step 3 n/a (the helper does not exist yet).
- id: `gm-04`
  story: As the author of a later task, the helper does what its callers will rely on.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_gitmerge`.
  expect: exit 0, with a test for each case in Scope: a clean probe, a conflicted probe with its stages, a git exit 129, equal patch ids across bases with no `fetch` run, a non-empty remerge diff of a hand resolution and an empty one of a clean merge.
  dry run: n/a (new module).
- id: `suite-01`
  story: As a plane developer, the plane's own checks still pass.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp tasks check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: both checks exit 0 and the branch list is empty.
  dry run (`b9e58ce`): both exit 0 for the committed task log.

## Implementation notes

*Append-only, newest last.*

- `gitmerge.probe` returns a frozen `Probe` (tree, conflicts, returncode, failed, detail). The three refusal
  texts that name a subcommand are `gitmerge.cannot_merge_text`, `conflict_text` and `old_git_text`, byte for
  byte as before. `_judge_fix` keeps testing `returncode not in (0, 1)` for the git 2.38 text (so a clean
  exit with no tree still reads "does not merge cleanly", as before); `failed` serves close.
- `own_patch_id(root, sha, base_ref, run)` calls `run(root, *git_args, data=None)`: the runner takes the
  directory as its first argument so `root` is used. `runs.same_change`'s inner `g` therefore takes `cwd` first,
  and `_same_patch(g, root, a, b, integ)` gained `root` (no test references it). It still stops at the first head
  with no patch id, as before.
- `remerge_diff` runs `git show --remerge-diff --format=` (so a clean merge gives ""), and raises `QueueError`
  when git fails rather than returning "", so a later caller cannot read a failure as a clean merge.
- `STAGE_RE` moved from `lifecycle` to `gitmerge`; nothing else used it.

## Verification notes
- 2026-11-19 — verifier, PR #181 head `b0a7a64` (squash `12c83b5`): APPROVE. Passed: gm-01, gm-02, gm-03, gm-04, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0162-git-merge-helper.json.

