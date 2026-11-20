---
task_id: 0200-mutate-together
title: ccp mutate --together applies the given mutants as one, so a mutant can move lines
status: pending
kind: feature
depends_on: []
spec_refs: ["S20"]
review_point: R14
paths: ["ccp/mutate.py", "ccp/cli.py", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "tests/test_mutate.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0200-mutate-together

## Intent

`ccp mutate` applies each mutant alone. Some faults are not one edit: a fix that changes a call and
its guard together, or a step moved from one place in a function to another. Today a seat can only
express those as a patch file, written by hand. After this task, `--together` applies every mutant
given as one mutant. A move is then two substitutions, one deleting the lines and one putting them
back elsewhere, judged as a single mutant.

## Context (not checked)

Measured at `58cf1d0`.

- The module docstring says "Each mutant is applied alone" (`git grep -n 'Each mutant is applied
  alone' ccp/mutate.py` at `58cf1d0`: one line), and `_run` loops over `parsed`, taking a snapshot,
  applying, testing and restoring one mutant at a time.
- Every mutant is checked against the unmutated tree before anything runs (`parse`,
  `parse_file`, `parse_revert`). A substitution's `old` must occur exactly once in its file.
- `ccp --root . mutate --run x --test y --together` exits 2 with "unrecognized arguments:
  --together" at `58cf1d0`.
- A seat that had to show a test catches a moved step found no single mutant for it. It is one of
  the follow-ups recorded when the R12 tasks closed.
- `tests/test_mutate.py` passes 60 tests at the base (`python3 -B -m unittest -q tests.test_mutate`
  at `58cf1d0`).
- The SPEC text below describes only this task's own option (§31.1).

## Scope

- **In:** `ccp/mutate.py`, `ccp/cli.py`, `docs/spec/03-quality.md`, `docs/cli/03-quality.md`,
  `tests/test_mutate.py`.
- **`--together`** (a flag) makes the call's mutants one mutant, numbered 1. Its parts are the
  `--mutant`s, then the `--mutant-file`s, then the `--revert`s, each in the order given, as today.
  It needs at least two parts; with fewer it is refused (exit 2), nothing run.
- **Checking the parts.** Before anything runs:
  - parts touching different files are each checked against the unmutated tree, as today;
  - two or more substitutions (`--mutant` `<file>:<old>=><new>` or `--mutant-file`) on the same file
    are checked in order on an in-memory copy of it. Each `old` must occur exactly once in the text
    the earlier parts leave;
  - any other pair of parts touching the same file (a patch or a revert with anything else) is
    refused (exit 2), naming the file.
- **Running.** One snapshot covers the union of the parts' files. All parts are applied in order,
  the compiled entries of every touched file are dropped, the test runs once, and every file is
  restored and checked, as for a single mutant. A part that fails to apply restores the tree and
  refuses (exit 2).
- **The row.** One `mutation` row, with `kind: together`, `parts` (each part's kind, in order),
  `files` (the union, in order of first touch) and `digest` (the first 12 hex digits of the sha256
  of the parts' digests joined by `\0`). Never any part's text, as today.
- The module docstring and the `--together` help describe it, including the move: "a move is two
  substitutions, one that deletes the lines and one that puts them back elsewhere".
- **`docs/cli/03-quality.md`:** the `ccp mutate` row shows `[--together]` and says the mutants are
  then applied as one.
- **SPEC §20.6 (§31.1).** The synopsis gains `[--together]`. After the `--revert` bullet, a new
  bullet: "**Together.** `--together` applies every mutant given as one mutant, numbered 1, its row's
  `kind` `together` with its parts' kinds in `parts`. Substitutions on one file apply in order, each
  `old` found exactly once in what the earlier ones leave, so a move is two substitutions, one that
  deletes the lines and one that puts them back elsewhere. Any other two parts on one file refuse
  the call (exit 2), as does a call with fewer than two." In the "Bound to the calling seat's run"
  bullet, CURRENT (at `58cf1d0`): "`kind` (`text`, `patch` or `revert`)". PROPOSED: "`kind` (`text`,
  `patch`, `revert` or `together`)".
- **Tests** in `tests/test_mutate.py`, each with `together` in its name:
  - two substitutions in two files, each surviving alone, are killed together (the test needs both);
  - a move: two `--mutant-file`s on one file, the first deleting a line and the second inserting it
    further down, applied together, are killed by a test of that order, and the file is restored
    byte for byte;
  - the row holds `kind: together`, `parts`, the union of files and a 12-character digest;
  - a patch and a substitution on the same file are refused (exit 2), nothing run;
  - a second substitution whose `old` the first one removed is refused (exit 2);
  - `--together` with one mutant is refused (exit 2).
- **Out:** mutation operators (the plane ships none), and the unmutated run and the restore logic,
  which are unchanged.

## dod_checks

- id: `mt-01`
  story: As a seat, I can judge a test by a fault that needs two edits, or a moved step.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_mutate 2>&1 | grep -i together`.
  expect: the six Scope tests are listed, each `ok`.
  dry run (`58cf1d0`): prints nothing; the module runs 60 tests, OK.

- id: `mt-02`
  story: As a plane developer, the together tests bite.
  setup: a copy of the PR head (`git worktree add --detach <tmp> HEAD`) in which `--together` applies
    only its first part.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_mutate`.
  expect: at least one failure, among the two-file test and the move test.
  dry run: n/a — the tests are new.

- id: `mt-03`
  story: As a seat, the CLI takes the flag.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp --root . mutate --help`.
  expect: the help lists `--together` and says the mutants are applied as one.
  dry run (`58cf1d0`): `ccp --root . mutate --run x --test y --together` exits 2, "unrecognized
    arguments: --together".

- id: `mt-04`
  story: As the SPEC reader, §20.6 describes `--together`.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n 'together' docs/spec/03-quality.md docs/cli/03-quality.md`.
  expect: the synopsis, the new **Together.** bullet and the `kind` list of §20.6 exactly as PROPOSED,
    and the CLI row.
  dry run (`58cf1d0`): prints nothing.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
