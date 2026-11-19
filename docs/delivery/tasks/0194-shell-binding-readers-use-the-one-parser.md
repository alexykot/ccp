---
task_id: 0194-shell-binding-readers-use-the-one-parser
title: The runner's idle hook and run-checkout.sh read the binding through the one binding module
status: pending
kind: refactor
depends_on: ["0175-one-binding-reader"]
spec_refs: ["S8"]
review_refs: ["sh-20261119T170325Z-8142#F07"]
rule_refs: ["E17"]
review_point: R12
paths: ["plugin/hooks/runner-idle.sh", "scripts/run-checkout.sh", "scripts/observability/lib.py", "tests/test_runner_idle_rotation.py", "tests/test_run_checkout_upgrade.py", "tests/test_binding_reader.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0194-shell-binding-readers-use-the-one-parser

## Intent

Task 0175 gave the binding one resolver and one parser, `scripts/observability/lib.py`
`read_binding`, under house rule E17. Two readers fell outside 0175's paths, and its review left them
as a follow-up (MINOR 3). They still parse the binding themselves:
- `plugin/hooks/runner-idle.sh`, with its `block()` function;
- `scripts/run-checkout.sh`, with its `scalar()` sed.

This task routes both through the one module, so E17 holds everywhere. On a binding that `ccp init`
writes, behaviour is unchanged.

## Context (not checked)

- `runner-idle.sh` is a Python heredoc inside a shell hook. It already resolves the binding through
  `ccp where`, and it reads the `runner:` block with its own `block()` function.
- `run-checkout.sh` runs from the run checkout and reads `project_id`, `product_root`,
  `integration_branch` and `queue_root` from each binding with `scalar()`.
- 0175's ruling accepted that, on a hand-edited binding, the one parser differs from the old ones:
  - the whole value is read, not its first word;
  - a comment needs ` #`;
  - the last repeated key wins;
  - only a block's direct children count.

  The same holds here.

## Scope

- **`runner-idle.sh`:** its `block()` function is deleted. The hook reads the `runner:` block through
  `read_binding`, importing `scripts/observability/lib.py` from the plane that `ccp where` names.
- **`run-checkout.sh`:** its `scalar()` function is deleted. It reads each binding's keys through
  `read_binding`, for example through a small entry point in `lib.py` that prints a binding's
  top-level scalars as JSON. That entry point goes in the same module, so there is no second parser.
- **Tests:** the existing tests for both scripts still pass. A new test in
  `tests/test_binding_reader.py` covers the entry point.

## dod_checks

- id: `sb-01`
  story: As a plane developer, no binding parser remains outside the one module.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE '^def block\(|^scalar\(\)' -- plugin/hooks/runner-idle.sh scripts/run-checkout.sh`.
  expect: prints nothing.
  dry run (`9d36e52`): prints `plugin/hooks/runner-idle.sh:63:def block(name):` and
    `scripts/run-checkout.sh:47:scalar() {`, so the expect fails today.
- id: `sb-02`
  story: As a runner, the idle hook and the release still read my binding as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_runner_idle_rotation tests.test_run_checkout_upgrade tests.test_binding_reader`.
  expect: all pass, and `tests.test_binding_reader` has at least one more test than at the base.
  dry run (`9d36e52`): passes today with the base's count (a regression guard, plus the new test).
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, then
       `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
