---
task_id: 0335-absence-checks-allow-indented-forms-the-repo-s-task-rules-point-at-e21-and-init-counts-only-files-git-keeps
title: The writing-tasks skill tells an absence check on a code form to allow leading whitespace; this repo's task rules point at house rules E2 and E21 instead of the test helpers; ccp init counts only the files git keeps when it decides whether the task log needs its .gitkeep
status: pending
kind: feature
depends_on: []
spec_refs: ["S4"]
review_refs: ["ar-20261124T234643Z-3c95#F05", "ar-20261124T234643Z-3c95#F08"]
review_point: R35
paths: ["plugin/skills/writing-tasks/SKILL.md", "docs/delivery/WRITING-tasks.md", "ccp/init.py", "tests/test_init.py", "docs/spec/01-model.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver"]
sign_off: brief
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0335-absence-checks-allow-indented-forms-the-repo-s-task-rules-point-at-e21-and-init-counts-only-files-git-keeps

## Intent

A task writer's absence check on a code form also finds the form indented (a function-local import, a class-level
alias), so a reviewer's wider search no longer costs a fix round. This repo's own task-writing rules send a check's
scratch product to `ccp sandbox create`, by pointing at house rules E2 and E21, not at test helpers a check's shell
step cannot reach. And an operator adopting a product whose task log holds only a file git drops (a `.DS_Store` an
ignore rule covers) still gets the `.gitkeep` that keeps the task log in a clone.

## Context (not checked)

Findings F05 and F08 of architect pass `ar-20261124T234643Z-3c95` (`docs/delivery/reviews/ar-20261124T234643Z-3c95.md`),
and the follow-up of 0327 that the lead passed to this pass (`0327-…/review#1`, `/fix#1`, `/verify#1`: a task log
holding only an untracked hidden file counts as a file, so init writes no `.gitkeep`). E4's PLANE_ROOT alias grep, the
other half of F05, was widened to `^\s*` in the triage itself (`docs/delivery/plane.json`).

Measured at `1a575497`:

- **F05.** `grep -cF '^\s*' plugin/skills/writing-tasks/SKILL.md`: 0; the absence-check bullet ("An absence check
  first shows its pattern finding a known positive …") says nothing of indentation.
- **F08.** `grep -c 'tests/helpers.py' docs/delivery/WRITING-tasks.md`: 1, the bullet "A check runs in the fenced
  suite", which also restates E2's fence.
- **0327 follow-up.** `"if not any(p.is_file() for p in tasks_dir.iterdir())"` (`ccp/init.py`) counts every file in
  the task log, a file git ignores included.
- **Ruled.**
  - The skill's absence-check bullet gains, after "Use `git grep -nwP`; …": "A pattern for a code form allows leading
    whitespace (`^\s*`), unless the brief rules out nested forms."
  - `docs/delivery/WRITING-tasks.md`'s bullet "A check runs in the fenced suite." becomes "- **A check is fenced and
    builds its scratch product as the house rules say** (E2, E21)."; its last bullet stays.
  - `ccp/init.py`: inside a git work tree, a file in the task log counts only when `git ls-files --cached --others
    --exclude-standard -- docs/delivery/tasks` lists it; outside one, every file counts, as now. New test
    `tests.test_init.Adopt.test_a_task_log_holding_only_an_ignored_file_gets_a_gitkeep` (the product's `.gitignore`
    names `.DS_Store`, and the task log holds only one: init writes and lists `.gitkeep`).
- No other test expectation changes.

## Scope

- **In:** `plugin/skills/writing-tasks/SKILL.md` (the absence-check bullet); `docs/delivery/WRITING-tasks.md`;
  `ccp/init.py`; `tests/test_init.py`; the SPEC, signed:

  CURRENT (`docs/spec/01-model.md` at `1a575497`), §4.5, the task log bullet:
  > - an empty `docs/delivery/tasks/.gitkeep` when the task log directory holds no file, so a clone of the product has its task log;

  PROPOSED:
  > - an empty `docs/delivery/tasks/.gitkeep` when the task log directory holds no file git would keep (one it tracks, or an untracked one no ignore rule drops), so a clone of the product has its task log;

  Retired: "holds no file" (a file git drops does not reach a clone).
- **Out:** `templates/docs-delivery/WRITING-tasks.md`; `plane.json`'s `E4` (done in the triage); the other bullets of
  the skill.

## dod_checks

- id: `doc-01`
  story: As a task writer, the skill tells me an absence check on a code form allows leading whitespace.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -cF '^\s*' plugin/skills/writing-tasks/SKILL.md`.
  expect: prints `1`.
  dry run (`1a575497`): printed `0`, exit 1.
- id: `doc-02`
  story: As this repo's task writer, the repo's rules point a check's scratch product at the house rules, not at test helpers.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'tests/helpers.py' docs/delivery/WRITING-tasks.md`.
  expect: prints `0`.
  dry run (`1a575497`): printed `1`.
- id: `code-01`
  story: As an operator, init writes the task log's .gitkeep when the log holds only a file git ignores.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_init.Adopt.test_a_task_log_holding_only_an_ignored_file_gets_a_gitkeep tests.test_init`.
  expect: exit 0.
  dry run (`1a575497`): exit 1 (`AttributeError: type object 'Adopt' has no attribute 'test_a_task_log_holding_only_an_ignored_file_gets_a_gitkeep'`).
- id: `spec-01`
  story: As the operator, §4.5 says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0335`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`1a575497`, with this brief): exit 1, the PROPOSED passage missing (`not found in the SPEC`).

## Implementation notes

## Verification notes
