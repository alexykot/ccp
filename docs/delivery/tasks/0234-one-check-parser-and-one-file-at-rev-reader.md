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

- Base `200ca69` already carried 0244's `tasklog.check_blocks` and `check_steps`; `git grep -n 'CHECK_RE' -- ccp`
  there printed 4 lines (the pattern, `check_blocks`' use, and the two `findall` readers in `tasklog.load`
  and `ccp/estimate.py`), not the 5 the Context measured before 0244. `check_blocks` is replaced by
  `tasklog.checks`; `with_dry_runs`, `_check_dry_runs`, `_check_refactor_gate`, `meta["_checks"]`,
  `estimate.features` and `ccp/dryrun.plan` read it. `CHECK_RE` now occurs twice, both in `ccp/tasklog.py`.
- `Check` carries `id`, `block` (the body after the `- id:` line), `fields` and the block's `start`/`end` in
  the text (`with_dry_runs` edits by position). `fields` is the first line of each `key: value` at the indent of
  the block's first key, a key lowercase words (`dry run (`sha`):` is the key `dry run`); a deeper line (a step,
  a wrapped value) is no key and a value is its own line only. That is the narrowest reading of "the block's
  `key:` lines"; 0224's `runs_on` will read `fields["runs_on"]`.
- `text_at` reads `git show <rev>:./<rel>` (cwd-relative, as lifecycle's and `statuses_at`'s reads did; `adr._at`
  and verify's used the toplevel-relative form, the same at a checkout root), "" for the index, None for a
  missing file or a bad rev, decoded with `errors="replace"`. `adr.in_force_at` keeps its fall back to the
  checkout's task (`cited(task)`), now commented at the call. `tasklog.statuses_at` stays a batch
  `cat-file --batch` read (one process for many files); the Scope names four readers, not it.
- Fix round 1: `text_at` decodes the raw bytes, so a CRLF task file kept its `\r\n`, where `queue.git()`
  (`text=True`) had turned it into `\n`; `lifecycle.drop` and `_says_dropped` then read no status from such a
  file. Both callers now normalise `\r\n` to `\n` before `tasklog.frontmatter` (as `adr.in_force_at` does);
  `text_at` itself stays byte-faithful, so ADR bodies read at the head are unchanged. CRLF tests are in `tests/test_lease_edits.py` (`_says_dropped`) and
  `tests/test_tasks_drop.py`. `Check` is `frozen=True, eq=False` (its `fields` dict makes it unhashable by
  value); `text_at`'s docstring names what it reads (it is not "the one reader" of E22).
- Fix round 2: universal newlines (`text=True`) turned a lone `\r` into `\n` as well as `\r\n`, so both
  lifecycle callers now normalise `.replace("\r\n", "\n").replace("\r", "\n")`; `tests/test_tasks_drop.py` has a
  lone-CR case beside the CRLF one. `checks`' docstring names only the ids the estimates read through it
  (`estimate.features` still counts `story:` lines with its own regex).
- Named difference, for the verifier's and lead's judgement (not accepted by anyone yet): `text_at` resolves `rel` against `cfg.root` (`git show <rev>:./<rel>`), where
  `drop`, `adr._at` and `verify._hunks` used the toplevel-relative form. They differ only when `cfg.root` is below
  the git toplevel (`--root`, `$CCP_ROOT`): `drop` then finds the task file instead of refusing, and
  `in_force_at` reads the head's task instead of falling back to the checkout's, and reads the ADR bodies at
  the head too: `by_num`'s paths come from `ls-tree` in the root-relative form, so at the base every ADR read at
  the head failed there (`body` None, `meta` `{}`) and the in-force gate never refused anything; now the reads
  succeed and an approve it used to pass can be refused. `verify._hunks` shows no change.
  A decoding difference too: a file that is not valid UTF-8 is decoded with replacement characters, where the
  old read raised `UnicodeDecodeError`.
- E22 is a command check: `architect.checks` `E22`, and the rule's `check:` line says `command`.
- Fix round 3 (test only, no production change): `tests/test_lease_edits.py` pins `_says_dropped`'s lone-CR
  normalisation with a drop commit written with `\r` line ends, beside the CRLF one (a shared helper takes the line end).

## Verification notes
