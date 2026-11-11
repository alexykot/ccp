---
task_id: 0066-run-a-check-on-the-merge-base
title: A verifier can run a check against the merge base's code
status: done
kind: feature
depends_on: []
spec_refs: ["S12", "S15"]
review_point: R4
paths: ["ccp/wt.py", "docs/spec/02-delivery.md", "docs/cli/", "plugin/agents/delivery-verifier.md", "tests/test_wt.py", "tests/test_merge_base*.py"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0066-run-a-check-on-the-merge-base

## Intent

Every task's dod_checks carry a "dry run: on the merge base" line. A verifier can check it with one command that runs a given command against the task's merge base, in a worktree of its own, and reports its exit code and output, instead of improvising with `git stash` or a hand-made worktree.

## Context (not checked)

- Verifiers improvise today (a stash, a second worktree), which risks running against the wrong tree or leaving changes behind.

## Scope

- **In:** a `ccp wt` kind or flag (the simplest that fits §12) that checks out the merge base of the task's PR head and the integration branch, runs a command there and removes the worktree; the verifier brief names it for dry runs; §12 and §15 describe it (§31.1: the task's own feature).
- **Out:** running the full gate on the merge base.

## dod_checks

- id: `check-01`
  story: As a verifier, I can confirm a check fails on the merge base.
  setup: a scratch product with a task branch that adds a test the merge base lacks the code for.
  steps:
    1. Run the new command with that test against the task's merge base.
  expect: the test fails there, the command reports it, and no worktree is left behind.
  dry run: n/a — the command does not exist yet.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 (implementer): a new kind, `ccp wt create --kind base --task ID --sha <PR head> -- COMMAND`
  (`ccp/wt.py` `run_on_base`, `merge_base`; the CLI passes everything after `--` through, as for
  `wt exec`). It fetches, makes `base-<nnnn>[-<n>]` detached at `git merge-base <head>
  origin/<integration>`, recorded (with `head`) and set up like any worktree, runs COMMAND (argv, no
  shell) with its output passed through, removes the worktree in a `finally`, prints `{name, head,
  merge_base, integration, exit, seconds, removed, warnings}` and exits with COMMAND's code (127 not
  found, 126 cannot run, 128 + N on signal N). Refusals: a command on any other kind, or none on
  `base` (2); no `--sha` (2); a head with no merge base (3); a `--name` already in use (3: a base
  worktree is never adopted, since it is removed afterwards). The command brings the head's test in
  itself (`git checkout <head> -- <path>`); no flag copies paths from the head. The worktree contract
  and the plane.json schema's kind list name `base`. SPEC §12.1 and §15.1, `docs/cli/02-delivery.md`
  and the verifier brief describe it. Tests: `tests/test_merge_base.py`.

## Verification notes

- 2026-11-11 — verifier, PR #59 head `dd9ba37` (squash `04ac815`): APPROVE. Passed: check-02. Not run by the verifier: check-01. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0066-run-a-check-on-the-merge-base.json.
