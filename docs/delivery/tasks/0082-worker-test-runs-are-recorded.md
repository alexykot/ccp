---
task_id: 0082-worker-test-runs-are-recorded
title: Workers run tests and mutation checks through recorded commands
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S14"]
review_point: R5
paths: ["plugin/agents/", "templates/prompts/", "ccp/suite.py", "docs/spec/02-delivery.md", "tests/test_plugin.py", "tests/test_suite*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0082-worker-test-runs-are-recorded

## Intent

Every test run a worker relies on, including mutation checks, goes through `ccp suite run` or `ccp mutate`, so it is recorded and can be cited (§13.1, §14.1); the briefs make that the obvious route.

## Context (not checked)

- Reviews across several review points: implementers, reviewers and verifiers ran mutation checks with plain `unittest` and disclosed it; and a bare `ccp suite run --wait` printed a parse error and still ran the command unrecorded (an accepted plane proposal).
- §31.1: SPEC text this task writes describes its own feature; no merge gate.

## Scope

- **In:** the implementer, reviewer and verifier briefs say that a run cited as evidence, a mutation check included, goes through `ccp suite run --lane …` or `ccp mutate`, never a bare test runner, with the command to use; `ccp suite run` refuses (exit 2, naming the problem) an argument list it cannot parse instead of running the command.
- **Out:** blocking bare test runs.

## dod_checks

- id: `check-01`
  story: As a worker, the brief names the recorded route.
  setup: a checkout of the PR head.
  steps:
    1. Read the three worker briefs.
  expect: each says evidence and mutation runs go through `ccp suite run` or `ccp mutate`, with the command.
  dry run: on the merge base they do not.
- id: `check-02`
  story: As a runner, a malformed suite call runs nothing.
  setup: a scratch product.
  steps:
    1. Run `ccp suite run --wait`.
  expect: it exits 2 naming the parse problem, and no command runs.
  dry run: on the merge base it prints an error and runs the command.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-13 (implement): `ccp suite run … -- COMMAND` whose options argparse refuses now runs
  nothing: `ccp/cli.py` re-raises argparse's exit (2 for a parse error, after one `ccp suite:` line
  saying the command did not run; 0 for `--help`) instead of falling back to `suite.unparsed`, which
  is removed. "Cannot parse" is read narrowly as an argparse failure (unknown flag, an option missing
  its value or given one of the wrong type, `--full` with `--summary`, an abbreviated `--root`). A
  `--lane` label or `--phase` value that parses but is invalid still runs the command unrecorded with
  a warning, as SPEC §14.5 already listed it. SPEC §14.2 and §14.5 say so.
- The recorded route for evidence is stated twice, at two levels: a generic bullet in each of the
  three worker definitions (`plugin/agents/delivery-{implementer,reviewer,verifier}.md`, pinned in
  `tests/test_plugin.py`'s `WORKER_RULES`; SPEC §13.1 now counts four generic rules), and the
  rendered command, with the run id and queue root, in `templates/prompts/_common.md`, which the
  implement, fix, review and verify prompts share (SPEC §13.2 item 1). The definitions now name
  `ccp suite run` once, in that bullet: §13.5's "one statement" rule and the two tests that pinned
  "no `ccp suite run` in a definition" (`tests/test_suite.py`, `tests/test_worker_efficiency.py`) now
  allow exactly that bullet and still keep the full §14.1 rule out of the definitions.

## Verification notes

*Append-only.*
