---
task_id: 0100-prompt-templates-name-the-tools
title: Worker prompts name ccp mutate --revert and ccp suite affected, and worker_env takes kind and seat from the worktree
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S14", "S15"]
review_point: R6
paths: ["templates/prompts/", "ccp/prompt.py", "ccp/mutate.py", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-implementer.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "tests/test_mutate.py", "tests/test_prompt*.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0100-prompt-templates-name-the-tools

## Intent

The worker prompts describe the tools as they now are:
- The verifier runs `ccp mutate --revert` from its own worktree, not from a separate mutation
  worktree it makes by hand.
- The implementer can run `ccp mutate` from its own worktree.
- Every prompt that runs a pre-gate names `ccp suite affected` for the tests a change touches.

`ccp mutate --revert` reverts the same hunks `git diff` shows. `{{kind}}` and `{{seat}}` in
`worker_env` come from the worktree record the worker runs in.

## Context (not checked)

- Four accepted plane proposals (operator, 2026-11-16: all approved), the follow-ups of four earlier
  tasks.
- `templates/prompts/verify.md` and SPEC §15 (02-delivery, the verifier's mutation step) still tell
  the verifier to make a `mut` worktree. They don't mention `ccp mutate --revert`, or that it runs from
  the seat's own `ver`/`rev` worktree.
- `ccp mutate` refuses to run from an implementer's worktree, and the implement prompt does not say to
  make a `mut` worktree either.
- `_revert_lines` (`ccp/mutate.py`) computes its hunks with `difflib`. On repeated lines these can
  differ from `git diff`'s. No test reverts a whole file that the change deleted.
- The implement, fix, ruling and merge templates still say "the product's dependent-modules command"
  where `ccp suite affected` now exists.
- `{{kind}}` and `{{seat}}` in `worker_env` come from the phase and the default seat, not from the
  worktree record. So `mut` and `base` seats only reach the stage templates.

## Scope

- **In:**
  - The verify template and the verifier agent: mutation runs as `ccp mutate --revert …` from the
    verifier's own worktree. The SPEC §15 sentence that describes the verifier's mutation step says
    the same. That passage is now false, so correcting it is §31.1 text.
  - `ccp mutate` runs from an implementer's (`impl`) worktree as well. The implement template says it
    may.
  - `_revert_lines` takes its hunks from `git diff -U0` of the two blobs, not from `difflib`. A test
    has repeated lines where the two differed, and another reverts a whole file the change deleted.
  - The implement, fix, ruling and merge templates name `ccp suite affected` in place of "the
    product's dependent-modules command (if its rules name one)".
  - `worker_env`'s `{{kind}}` and `{{seat}}` come from the worker's worktree record, when one is bound,
    and fall back to today's values otherwise. The prompt tests gain fix, merge and ruling rows for
    these fields.
- **Out:**
  - Any change to what a mutation proves or how the verifier judges it.

## dod_checks

- id: `check-01`
  story: As a verifier, the prompt tells me the command I actually run.
  setup: a checkout of the PR head and a throwaway product with a task.
  steps:
    1. Render `ccp prompt verify` and `ccp prompt implement` for the task.
    2. Grep the templates for "dependent-modules command" and for "mut worktree".
  expect: (1) the verify prompt names `ccp mutate --revert` run from the verifier's own worktree, and
    the implement prompt names `ccp mutate` run from the implementer's worktree. (2) Neither string
    remains in the implement, fix, ruling, merge or verify templates, and those prompts name
    `ccp suite affected`.
  dry run: n/a.
- id: `check-02`
  story: As an implementer, `ccp mutate` runs in my worktree.
  setup: a throwaway product with an `impl` worktree holding a change.
  steps:
    1. Run `ccp mutate --revert <file>:<line>` from the worktree.
  expect: it runs (no refusal for the worktree kind), and the mutated file equals the base version of
    that hunk.
  dry run: n/a.
- id: `check-03`
  story: As a verifier, a revert matches what git shows.
  setup: a change to a file with repeated identical lines, where `difflib` and `git diff` place a hunk
    differently, and a change that deletes a whole file.
  steps:
    1. Revert each hunk `git diff -U0` shows, one at a time, with `ccp mutate --revert`.
    2. Revert the deleted file whole.
  expect: (1) each revert changes exactly the lines of that git hunk. (2) The file comes back as it
    was at the base.
  dry run: n/a.
- id: `check-04`
  story: As a stage template, I see the worktree's kind and seat.
  setup: a throwaway product with a bound `mut` worktree.
  steps:
    1. Render a worker prompt whose `worker_env` uses `{{kind}}` and `{{seat}}`, run from that worktree.
  expect: they show `mut` and that worktree's seat. Without a bound worktree they show today's values.
  dry run: n/a.
- id: `check-05`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-16 (implementer): `ccp mutate` accepts a recorded `impl` worktree of the run's task
  (`WORKTREE_KINDS`); its refusal now points at the seat's own worktree first. `_revert_lines` takes
  its hunks from `git diff --no-index -U0` of the two versions (`_hunks`, run in the worktree so its
  diff settings apply, `--no-ext-diff --no-textconv --text`) and counts lines as git does (newline
  only, `_lines`). `worker_env`'s `{{kind}}` and `{{seat}}` come from `wt.recorded_at` of the path
  the run is bound to (`--worktree` for the change rounds, the seat's own `rev`/`ver` path for review
  and verify), else the phase's kind and its default seat as before.
- Templates: the implement, fix, merge and ruling pre-gates name `ccp suite affected` (`--since
  origin/<integration>` for implement, `--since <head>` for the rounds); the verify bullet runs
  `ccp mutate --revert` from the verifier's own worktree, with the hand-made break through the part
  lane kept for a product with no `mutate.command`; `_common.md` names the worker's own worktree and
  no longer a mutation copy; the implement template says the implementer may run `ccp mutate` from
  its own worktree.
- SPEC: the verifier's mutation step is in §13.2 item 1 (not §15, which has no such sentence); it,
  §13.5's fail-fast line, §20.6 (the `impl` kind; reverts follow `git diff -U0`'s hunks) and
  01-model §8.1's `kind`/`seat` field note (outside the task's `paths`, but false after the change)
  are corrected as §31.1 text. `docs/cli/03-quality.md` and `ccp mutate --help` name the `impl` kind.

## Verification notes
