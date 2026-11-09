---
task_id: 0045-python-floor-and-import-guard
title: The declared Python floor matches what runs the plane
status: pending
kind: feature
depends_on: []
spec_refs: ["S29"]
review_point: R3
paths: ["pyproject.toml", "README.md", "ccp/", "tests/", "docs/spec/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0045-python-floor-and-import-guard

## Intent

The Python version the plane declares matches the interpreter that runs it. launchd starts the receiver and the board with the system `python3` (3.9 on macOS), while `pyproject.toml` says 3.10 or newer; either the floor drops to 3.9 or the plists use a declared interpreter. The regex guard test is replaced by one that cannot miss a 3.10-only construct.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §29.
- A module using `X | None` without postponed annotations crash-looped the receiver after a release, while the suite (on a newer Python) passed.

## Scope

- **In:** decide and apply one: floor 3.9 everywhere (pyproject, README, §29) or plists run a configured interpreter (`CCP_PYTHON`) checked at install; replace `tests/test_py39_import.py` with an AST check of annotations (any `BitOr` in an annotation without the future import) or a run of `compileall` and an import of every module under the floor interpreter when present.
- **Out:** supporting Pythons below 3.9.

## dod_checks

- id: `check-01`
  story: As a plane developer, a 3.10-only annotation is caught.
  setup: a scratch module with `def f(x: int | str)` and no future import.
  steps:
    1. Run the guard test against it.
  expect: it fails, naming the module and line.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As an operator, the declared floor matches the plists.
  setup: the PR head.
  steps:
    1. Compare `requires-python`, the README and the interpreter the plists run.
  expect: they agree.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
