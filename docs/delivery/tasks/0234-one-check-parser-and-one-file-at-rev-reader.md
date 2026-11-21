---
task_id: 0234-one-check-parser-and-one-file-at-rev-reader
title: One dod_check parser and one task-file-at-rev reader in tasklog, used by every current site
status: pending
kind: refactor
depends_on: ["0244-tasks-check-runs-dry-runs"]
review_refs: ["sh-20261121T000350Z-5ef1#F04", "sh-20261121T000350Z-5ef1#F05"]
rule_refs: ["E12", "E22"]
review_point: R15
paths: ["ccp/tasklog.py", "ccp/dryrun.py", "ccp/estimate.py", "ccp/adr.py", "ccp/lifecycle.py", "ccp/verify.py", "docs/delivery/plane.json", "docs/ENGINEERING.md", "tests/test_tasklog_checks.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0234-one-check-parser-and-one-file-at-rev-reader

## Intent

ADR-0045 reads a check's `runs_on` in `tasks check`, both prompts, `verify record`, `merge-ok` at a
head and the runner, and reads the task file at a head. Today the dod_checks section is split into
blocks by two hand loops and read for ids in two more places, and a file at a commit is read five
ways, one of which falls back to the checkout's copy. After this task `tasklog.checks(text)` is the
one parser (each check's id, block and fields) and `tasklog.text_at(cfg, rev, rel)` the one reader
(None when absent, no fallback); every current site uses them. Nothing changes for a product.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0045 (`sh-20261121T000350Z-5ef1`): F04 and F05; house rule E22.
- **The parsers.** `git grep -n 'CHECK_RE' -- ccp` at `8aefa59`: five lines (the pattern, two
  `finditer` loops in `_check_dry_runs` and `_check_refactor_gate`, and two `findall` id readers in
  `tasklog` and `ccp/estimate.py`).
- **The readers.** `def _at` in `ccp/adr.py` (with `in_force_at`'s fallback to the checkout),
  `ccp/lifecycle.py`'s `origin/<integration>` read and `_says_dropped`, `tasklog.statuses_at`, and
  `ccp/verify.py`'s `git show {head}:{f}` (`git grep -nE '"show", f"' -- ccp` at `8aefa59`: nine
  lines, among them the index and migration reads this task leaves alone).
- **R16's 0244** adds `ccp/dryrun.py` (`ccp tasks dry-run`), which splits a task's dod_checks into
  blocks to run their steps: a further copy of the grammar once it lands. This task depends on it and
  routes `ccp/dryrun.py` through `tasklog.checks` too, so 0224's `runs_on` is read in one place.
- A refactor: `adr.in_force_at` keeps its fallback where it has one today, made explicit at its call;
  every other behaviour is unchanged.

## Scope

- **In:** `ccp/tasklog.py`, `ccp/dryrun.py`, `ccp/estimate.py`, `ccp/adr.py`, `ccp/lifecycle.py`, `ccp/verify.py`,
  `docs/delivery/plane.json`, `docs/ENGINEERING.md`, `tests/test_tasklog_checks.py` (new).
- `architect.checks` gains `{"id": "E22", "cmd": …}` with house rule E22's command, and E22's `check:`
  line becomes `command`.
- **`tasklog.checks(text) -> list[Check]`** (`id`, `block`, and a dict of the block's `key:` lines);
  `_check_dry_runs`, `_check_refactor_gate`, `meta["_checks"]`, `estimate`'s count and `ccp/dryrun.py`'s
  block split use it, and `CHECK_RE` (or any other check-block pattern) is used nowhere else.
- **`tasklog.text_at(cfg, rev, rel) -> str | None`**; `adr._at`, the two lifecycle reads and
  `verify`'s read use it.
- **Tests** in `tests/test_tasklog_checks.py` (new): `checks` on a task with three checks, with a
  comment after an id, with no section; `text_at` on a present file, a missing file and a bad rev.

## dod_checks

- id: `cg-01`
  story: As a plane developer, the parser and the reader are tested on their own.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_tasklog_checks 2>&1 | tail -10`.
  expect: exit 0, the Scope's six tests listed `ok`.
  dry run: n/a — the module is new.

- id: `cg-02`
  story: As the plane, the check grammar is read in one place.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'CHECK_RE' -- ccp | wc -l`.
  expect: prints 2, both in `ccp/tasklog.py` (the pattern and its one use in `checks`).
  dry run (`8aefa59`): prints 5 (before 0244, whose `ccp/dryrun.py` may add its own split).

- id: `cg-04`
  story: As a plane developer, the reader's no-fallback rule is tested.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `text_at` returns the checkout's copy when the file is missing at the rev.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_tasklog_checks`.
  expect: at least one failure (the missing-file test).
  dry run: n/a — the module is new.

- id: `cg-03`
  story: As a task writer, the task check, the estimates and ADR reads behave as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_tasklog tests.test_estimate tests.test_adr tests.test_verify tests.test_tasks_dry_run 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

## Implementation notes

## Verification notes
