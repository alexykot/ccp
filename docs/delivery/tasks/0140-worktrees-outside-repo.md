---
task_id: 0140-worktrees-outside-repo
title: worktrees.dir may be an absolute path or lead outside the main checkout, such as a sibling directory
status: done
kind: feature
depends_on: []
spec_refs: ["S12"]
review_point: R9
sign_off: brief
paths: ["ccp/config.py", "ccp/wt.py", "ccp/prompt.py", "contracts/plane_config.schema.json", "docs/spec/02-delivery.md", "tests/test_wt.py", "tests/test_wt_outside.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-18
---

# Task: 0140-worktrees-outside-repo
## Intent

A product can keep the plane's worktrees outside its repository, as an absolute directory or a
sibling of the main checkout (`../<name>`), so tools that walk the repository tree from its root never
descend into whole nested checkouts, and a product that already keeps its worktrees as siblings keeps
that layout.

## Context (not checked)

- Today plane.json `worktrees.dir` must be relative to the main checkout with no `..`: `_worktree_blocks`
  in `ccp/config.py` (`"worktrees.dir must be a path relative to the main checkout, or null"`) refuses an
  absolute value or one with a `..` part. So every plane worktree lives inside the product repository,
  and every root-level tree walker (`find .`, doc generators, linters without ignore files) needs its own
  prune.
- The binding's `runner.worktree` is already absolute (`contracts/project.schema.json`).
- Where the directory is used: `wt.base_dir` (`"def base_dir"` in `ccp/wt.py`) joins it to the main
  checkout, as does `worktree_for` in `ccp/prompt.py`. A `pathlib` join already yields the absolute path
  for an absolute value; a `../x` value yields an unresolved `<main>/../x`.
- A directory outside the repository may be shared, by mistake or by design, with another checkout
  holding `impl-<nnnn>` or `merge-<nnnn>` directories of its own. Today `wt.listing`, `wt.remove_task`'s
  pre-record fallback and `wt.gc`'s merge-worktree sweep act on any directory under `worktrees.dir` whose
  name matches, with no record. Outside the main checkout that could remove another product's worktree,
  so this task limits those fallbacks there (Scope).
- The SPEC rule is §12.1's "(relative to the main checkout)": a rule change, so this task carries its
  text for signing.
- Out of scope, noted for the lead: a session started in a worktree outside the repository is outside
  the product's `.claude/` permission scope only if the harness resolves it from the cwd; workers
  already run with their worktree as cwd, so nothing changes for them.

## Scope

- **In:**
  - `ccp/config.py` `_worktree_blocks`: `worktrees.dir` (and the legacy `adapter.worktree_dir`) may be
    absolute, or relative with `..` parts. Still refused: an empty string, and a value that resolves to
    the main checkout itself. The refusal says "a path relative to the main checkout (`..` allowed) or
    an absolute path, or null".
  - `ccp/wt.py` `base_dir` and `ccp/prompt.py` `worktree_for` return the resolved directory
    (`(<main checkout> / dir).resolve()`), so every caller (`merge_path`, `_free_name`, `listing`,
    `remove`, `remove_task`, `gc`, close's merge worktree) gets one absolute path.
  - Under a `worktrees.dir` that resolves outside the main checkout, a directory with no worktree record
    is listed by `ccp wt list`, removed by `remove_task`'s fallback, or swept by `gc` only when
    `git worktree list --porcelain` run in the main checkout names it; any other is left alone.
    Inside the main checkout the fallbacks are unchanged.
  - `contracts/plane_config.schema.json`: the `worktrees.dir` and `adapter.worktree_dir` descriptions
    say the same as the SPEC text below.
  - `docs/spec/02-delivery.md` §12.1. CURRENT (at `921507e`): "worktree under plane.json `worktrees.dir` (relative to the main checkout), named" PROPOSED:
    > worktree under plane.json `worktrees.dir` (a path relative to the main checkout, which may lead outside it with `..`, such as a sibling directory, or an absolute path; not the main checkout itself), named
    Put the PROPOSED passage on lines of its own, unwrapped, with the line holding its first word part
    of the diff, so `ccp verify spec-text` finds it.
  - `tests/test_wt.py`: `test_bad_blocks_are_refused` no longer lists `{"worktrees": {"dir": "/abs"}}`
    as bad (the change breaks it); `tests/test_wt_outside.py` (new) holds this task's tests.
- **Out:**
  - Moving an existing product's worktrees, or changing `ccp init`'s default `.plane-runtime`.
  - The binding's `runner.worktree`.

## dod_checks

- id: `cfg-01`
  story: As a product writer, I can name an absolute or sibling worktrees directory.
  setup: a scratch product (`tests/helpers.py`) and, in turn, plane.json `worktrees.dir` set to `../<repo>-wt`, to an absolute directory outside the repository, to `""` and to `.`.
  steps:
    1. Load the config (`config.load`) for each value.
  expect: the first two load, and `wt.base_dir` returns the resolved absolute directory for each; `""` and `.` are refused with a `ConfigError` naming `worktrees.dir`.
  dry run: n/a.
- id: `wt-01`
  story: As an implementer, my task worktree is made in the sibling directory.
  setup: a scratch product with an origin and `worktrees.dir: "../<repo>-wt"`, and a pending task.
  steps:
    1. Run `ccp wt create --kind impl --task <task>`.
    2. Run `ccp wt list --task <task>` and `git worktree list` in the main checkout.
  expect: the worktree is `<parent of the main checkout>/<repo>-wt/impl-<nnnn>`, recorded with that absolute path; no directory named `impl-<nnnn>` exists inside the main checkout.
  dry run: n/a.
- id: `close-01`
  story: As a runner, close works with worktrees outside the repository.
  setup: the scratch product of wt-01 with its task verified and a PR merged in the test fixture's fake hosting.
  steps:
    1. Run `ccp tasks close <task> --pr <n>`.
  expect: exit 0; the reconcile is made in `<repo>-wt/merge-<nnnn>` outside the main checkout, and the task's `impl` worktree and `merge-<nnnn>` are gone afterwards.
  dry run: n/a.
- id: `wt-02`
  story: As another checkout sharing the directory, my worktrees are not taken for this product's.
  setup: a scratch product with an absolute `worktrees.dir` `D`; in `D`, a directory `impl-0001` and a directory `merge-0001` that are not worktrees of this product's repository (plain directories, or worktrees of a second scratch repository); task `0001-…` done in the queue.
  steps:
    1. Run `ccp wt list`, then `ccp wt gc`, then `ccp tasks close`'s worktree cleanup for task 0001 (`wt.remove_task`).
  expect: `ccp wt list` lists neither directory; both directories still exist after gc and the cleanup.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Run `ccp verify spec-text 0140-worktrees-outside-repo`, and compare the §12.1 edit with the PROPOSED text above.
  expect: exit 0, the edit matches word for word, and no other § rule changes.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-18 (implementer): `_worktree_blocks` now takes the product root. A value with no `..` that is
  not absolute is refused as the main checkout when it normalises to `.`; an absolute or `..` value is
  resolved against the main checkout (`wt.main_of`, which asks git, so only for those values) and
  refused when it is that checkout. The main-checkout refusal appends ", not the main checkout itself"
  to the Scope's message. The legacy `adapter.worktree_dir` type refusal uses the same message.
  `wt.base_dir` and `prompt.worktree_for` resolve. The outside rule is `wt._git_named`/`_ours`: `None`
  (any directory) when the resolved dir is the main checkout's descendant, else the resolved paths
  `git worktree list --porcelain` names; applied in `listing`, `remove_task`'s fallback (pre-record
  names and the merge worktree) and `gc`'s merge sweep. `ccp wt remove NAME` of an unrecorded
  directory and `create`'s adoption of an existing one are unchanged (not in Scope). SPEC text for the
  outside rule was not carried by the task: proposed as `pp-20261118T073953Z-eec0`.

## Verification notes
- 2026-11-18 — verifier, PR #158 head `fdbc008` (squash `4ef5438`): APPROVE. Passed: cfg-01, wt-01, close-01, wt-02, check-01, suite-01. Gate: `ccp suite run --run 0140-worktrees-outside-repo/verify --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0140-worktrees-outside-repo.json.

