---
task_id: 0125-worktree-round-in-names
title: A worktree's round reaches worker_env and lane stages, so a second review round gets its own scratch resources
status: done
kind: feature
depends_on: ["0124-suite-and-mutate-tools"]
spec_refs: ["S8", "S12", "S14"]
review_point: R8
paths: ["ccp/wt.py", "ccp/prompt.py", "ccp/suite.py", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "tests/test_wt.py", "tests/test_prompt_env.py"]
adopt: "use {{round}} in prompts.worker_env templates that name a per-worktree resource, so a second round does not reuse the first's"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0125-worktree-round-in-names
## Intent

A product that names a scratch resource (a database, a port range) per worktree from
`prompts.worker_env` gets a distinct name for a task's second review or verify round, so that
round's setup neither replaces the first round's resource nor refuses because it exists.

## Context (not checked)

- A second review round's worktree is `rev-<nnnn>-2` (a default name taken moves to the next `-<n>`,
  §12.1), but `worker_env` templates get only `{{nnnn}}`, `{{kind}}` and `{{seat}}` besides paths, so
  a product's template built from those gives the second round the first round's name (a product's report,
  2026-11-17).
- §31.1: the placeholder and variable are this task's own feature; the SPEC lines below only
  describe them.
- Depends on 0124 so that `ccp prompt env` shows the new placeholder.

## Scope

- **In:**
  - `ccp/wt.py`: a worktree record carries `round`: 1 for the default name, `<n>` for a name ending
    `-<n>`; a record without it reads as 1.
  - `ccp/prompt.py`: `prompts.worker_env` templates get `{{round}}`.
  - `ccp/suite.py`: a lane's stages in a recorded worktree get `CCP_WT_ROUND` with the other
    `CCP_WT_<FIELD>` variables.
  - §31.1: `docs/spec/02-delivery.md` §12.1, the bullet on kind and seat: name `{{round}}` and
    `CCP_WT_ROUND` beside `{{kind}}`, `{{seat}}`, `CCP_WT_KIND` and `CCP_WT_SEAT`;
    `docs/spec/01-model.md` §8.1's `worker_env` example adds `{{round}}` to its placeholder list.
- **Out:**
  - Renaming any worktree or changing the `-<n>` rule.

## dod_checks

- id: `wt-01`
  story: As a product, my second review round gets its own scratch name.
  setup: a scratch product whose `prompts.worker_env` sets `DB_NAME` to `t{{nnnn}}_{{kind}}_{{round}}`; a task with worktrees `rev-0001` and `rev-0001-2` made by `ccp wt create`.
  steps:
    1. Run `ccp prompt env <path of rev-0001>` and `ccp prompt env <path of rev-0001-2>`.
  expect: the first prints `DB_NAME=t0001_rev_1`, the second `DB_NAME=t0001_rev_2`.
  dry run: n/a — `ccp prompt env` is built by 0124.
- id: `wt-02`
  story: As a gate, my stages know the round.
  setup: the product of wt-01 with a lane whose stage prints `$CCP_WT_ROUND`.
  steps:
    1. Run that lane with `ccp suite run` inside `rev-0001-2`.
  expect: the log shows `2`.
  dry run: n/a.
- id: `wt-03`
  story: As an existing worktree, my record still loads.
  setup: a recorded worktree whose record file has no `round` key.
  steps:
    1. Run `ccp wt list --json`.
  expect: exit 0; the worktree lists with `round` 1.
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

- 2026-11-17 (implementer): `ccp wt create` records `round` (`wt.round_of`: `<n>` for a name ending
  `-<n>`, else 1), also when a taken default name moves on; `wt.load` and `wt.records` read a record
  without a valid `round` as 1, so `ccp wt list`, `ccp prompt env` and every reader see 1.
  `prompts.worker_env` gets `{{round}}` (`config.WORKER_ENV_FIELDS`): from the bound worktree's record,
  else from the worker's worktree's name. `CCP_WT_ROUND` is added in `wt.env_fields`, so a lane's stages
  and close's catch-up gate get it with the other `CCP_WT_<FIELD>` variables; an env hook's environment
  gets it too, but `{round}` is not a hook template field (§12.2 unchanged). `contracts/worktree.schema.json`
  gains the optional `round`. wt-03's step names `ccp wt list --json`, a flag `ccp wt list` does not take
  (it always prints JSON); no flag was added.

## Verification notes
- 2026-11-17 — verifier, PR #141 head `e3d0458` (squash `1d3ba8a`): APPROVE. Passed: wt-01, wt-02, wt-03, suite-01. Gate: `ccp suite run --lane gate -- scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0125-worktree-round-in-names.json.

