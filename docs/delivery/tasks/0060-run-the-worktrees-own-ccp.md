---
task_id: 0060-run-the-worktrees-own-ccp
title: Workers can run a worktree's own ccp; §5.2 lists covers
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S12"]
review_point: R4
paths: ["ccp/wt.py", "docs/spec/01-model.md", "docs/cli/", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "tests/test_wt.py"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0060-run-the-worktrees-own-ccp

## Intent

A reviewer or verifier can run the `ccp` of the worktree under review (`ccp wt exec -- <args>`, or a printed path), so a change that adds a subcommand can be tried as `ccp`, and §5.2 lists the `covers` frontmatter field the outside-changes task added (§5.2, §12).

## Context (not checked)

- `ccp` on PATH is the run checkout, which predates the change under review, so new subcommands cannot be run as `ccp`.
- The outside-changes task added `covers` to task frontmatter but could not edit §5.2, which was outside its paths.
- §31: this task's SPEC text describes its own feature. If the operator's standing ruling for such text (given for R3, 2026-11-10) is not extended to R4, the merge waits on their approval.

## Scope

- **In:** a `ccp wt` subcommand that runs (or prints) the worktree's `bin/ccp` with the given arguments; the reviewer and verifier briefs mention it; §5.2 gains the `covers` row.
- **Out:** putting worktree binaries on PATH.

## dod_checks

- id: `check-01`
  story: As a verifier, I can run the change's own ccp.
  setup: a worktree whose `bin/ccp` has a subcommand the installed `ccp` lacks.
  steps:
    1. Run the new `ccp wt` command with that subcommand.
  expect: the subcommand runs.
  dry run: on the merge base there is no such `ccp wt` command.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 — implementer: `ccp wt exec [NAME] [--print] [-- ARGS]` (`ccp/wt.py` `own_ccp`,
  `exec_ccp`; `ccp/cli.py` `cmd_wt_exec`). It runs `<worktree>/bin/ccp` with ARGS verbatim (split at
  `--` in `main()`, as `suite run` does), through the running Python, in the caller's directory and
  environment, and exits with its code (128 + N for signal N). NAME is a recorded worktree (needs
  `QUEUE_ROOT`); without it, the checkout `ccp` resolved (`--root`, `$CCP_ROOT`, the cwd's git
  toplevel). It runs before plane.json loads, so a change the installed ccp cannot load can still be
  tried. `--print` prints the path. Refusals: a NAME that is not a worktree name (arguments not
  after `--`) or `--print` with arguments exit 2; an unrecorded NAME or no `bin/ccp` exit 3. SPEC
  §12.1 gains a bullet for it and §5.2 the `covers` row; `docs/cli/02-delivery.md` a row; the
  reviewer and verifier briefs mention it. Outside the declared paths: `ccp/cli.py` (the wiring) and
  `docs/spec/02-delivery.md` (§12.1). Tests: `tests/test_wt.py` `ExecOwnCcp`.

## Verification notes

*Append-only.*
