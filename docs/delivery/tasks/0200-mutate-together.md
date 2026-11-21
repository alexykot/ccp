---
task_id: 0200-mutate-together
title: ccp mutate --together applies the given mutants as one, so a mutant can move lines
status: done
kind: feature
depends_on: []
clashes_with: ["0198-architect-runs-in-its-own-worktree"]
spec_refs: ["S20"]
review_point: R14
paths: ["ccp/mutate.py", "ccp/cli.py", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "tests/test_mutate.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-21
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

- `mutate.together(parts, texts)` is the decision on plain values: the fewer-than-two refusal, the
  file-sharing refusal (any part other than a substitution sharing a file), the in-order check of
  substitutions on one file and the row's `parts`, `files` (union, order of first touch) and `digest`.
  `_run` parses the substitutions without the per-file count check under `--together` (`parse` and
  `parse_file` take `count`), so a later part may find an old text an earlier one wrote; a lone
  substitution on its file is then checked against the unmutated file by `together`, as before.
- The fewer-than-two refusal comes after the run, worktree and per-part checks, still before
  anything runs (no unmutated run, no log).
- `_apply` applies a `together` mutant's parts in order under the one snapshot `_run` already takes
  of `m["files"]`; a part that does not apply raises exit 2 and the existing `finally` restores the
  tree. The row gains `parts` only for a `together` mutant.
- Beyond the six Scope tests: a later part editing what an earlier one wrote, a part that does not
  apply (exit 2, tree restored), and `together` on plain parts.
- The move test alone does not catch "`--together` applies only its first part" (deleting the step
  already fails its test); the two-file test does (mt-02 asks for one of the two).
- Fix round 1 (review MINOR-1): `together` and `_run`'s `texts` key files by `_key(rel)`
  (`os.path.normpath`, POSIX separators), so `./calc.py` and `calc.py` are one file for the in-order
  check and the file-sharing refusal; the row's `files` holds that one spelling. A single mutant's
  `files` and every part's digest keep the path as given. Test:
  `test_together_two_spellings_of_one_file_are_one_file`.

## Verification notes
- 2026-11-21 — verifier, PR #239 head `c055e83` (squash `da1607f`): APPROVE. Passed: mt-01, mt-02, mt-03, mt-04, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0200-mutate-together.json.

