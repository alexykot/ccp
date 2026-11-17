---
task_id: 0127-throwaway-adopted-product
title: ccp sandbox makes a throwaway adopted product, fenced from real queues, for end-to-end checks
status: pending
kind: feature
depends_on: []
spec_refs: ["S4", "S8"]
review_point: R8
paths: ["ccp/sandbox.py", "ccp/cli.py", "docs/spec/05-operations.md", "tests/test_sandbox.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0127-throwaway-adopted-product
## Intent

An implementer or verifier exercises init, adoption, close and upgrade paths end to end on a real,
adopted product made by one command and removed by another, never touching a real product's queue
or binding.

## Context (not checked)

- Seats hand-build these fixtures today (a temp repo, a plane.json, a binding, a queue) and get the
  binding resolution wrong, which risks a real queue.
- `ccp/sandbox.py` (new) is the module.
- §31.1: the SPEC paragraph only describes the command.

## Scope

- **In:**
  - `ccp sandbox create [DIR] [-- <ccp init options>]` (new): under `DIR` (default a new temporary
    directory) makes a git repository with one commit, runs `ccp init` there with the options given,
    writing the binding and the queue inside `DIR` (never the installation's bindings directory),
    commits what init wrote, writes a marker file, and prints JSON: `root`, `binding`, `queue_root`,
    and `env`, the `PROJECT_YAML` and `QUEUE_ROOT` lines that point `ccp` at it.
  - `ccp sandbox remove DIR` (new): removes a directory holding the marker; any other directory is
    refused (exit 2).
  - Under the test fence (`tests/__init__.py`), `create` works only below the fence's temporary root.
  - §31.1: `docs/spec/05-operations.md`, one paragraph describing both commands.
- **Out:**
  - A remote, a hosting service or a telemetry receiver for the sandbox.

## dod_checks

- id: `cmd-01`
  story: As a verifier, I get an adopted product in one command.
  setup: a scratch directory `S` that does not exist.
  steps:
    1. Run `ccp sandbox create S`.
    2. With the printed `env` lines exported, run `ccp tasks check` and `ccp upgrade status` in the printed `root`.
  expect: step 1 exits 0 and prints the four keys, each path under `S`; step 2's commands exit 0.
  dry run: n/a.
- id: `cmd-02`
  story: As the installation, my bindings are untouched.
  setup: the run of cmd-01.
  steps:
    1. List the installation's bindings directory before and after cmd-01.
  expect: the two listings are equal.
  dry run: n/a.
- id: `cmd-03`
  story: As an operator, remove deletes only a sandbox.
  setup: the sandbox `S` of cmd-01 and a scratch directory `T` without the marker.
  steps:
    1. Run `ccp sandbox remove T`, then `ccp sandbox remove S`.
  expect: the first exits 2 and `T` remains; the second exits 0 and `S` is gone.
  dry run: n/a.
- id: `cmd-04`
  story: As a task, init options pass through.
  setup: a scratch directory `U` that does not exist.
  steps:
    1. Run `ccp sandbox create U -- --gate "python3 -m unittest"`.
  expect: the sandbox's plane.json names that command as its gate lane.
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

## Verification notes
