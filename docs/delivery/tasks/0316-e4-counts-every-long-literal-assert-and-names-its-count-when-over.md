---
task_id: 0316-e4-counts-every-long-literal-assert-and-names-its-count-when-over
title: E4's long-literal count reads every assert call with a string argument of 40 or more characters, f-strings and concatenations included, and prints its count and figure when it is over
status: pending
kind: refactor
depends_on: ["0309-the-bare-runner-warning-reads-past-env-and-timeout-options-and-e4-skips-a-test-file-it-cannot-read"]
rule_refs: ["E4"]
review_refs: ["ar-20261123T230912Z-197a#F02", "ar-20261123T230912Z-197a#F07"]
review_point: R32
paths: ["docs/delivery/plane.json", "tests/test_self_hosting.py"]
clashes_with: ["0191-the-grace-release-ends"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0316-e4-counts-every-long-literal-assert-and-names-its-count-when-over

## Intent

E4's ratchet on prose assertions counts what E4 forbids: every assert call whose string argument holds 40
or more characters, whether written as a plain literal, an f-string or a concatenation, in any assert method.
A writer can no longer step past it by switching to an f-string or `assertEqual`. When the count is over its
figure, the check prints one line naming the count and the figure, so a worker sees which part of E4 failed
without taking the command apart.

## Context (not checked)

Findings F02 and F07 of architect pass `ar-20261123T230912Z-197a` (`docs/delivery/reviews/ar-20261123T230912Z-197a.md`),
and E4's amended `check:` line (`docs/ENGINEERING.md`, applied by that triage).

Measured at `bb102371`:

- **The count part today** is `test "$(LC_ALL=C git grep -hE 'assert(Not)?In\("[^"]{40,}' -- 'tests/*.py' | wc -l)" -le 345`,
  one of E4's parts joined by ` && ` in `architect.checks` (`docs/delivery/plane.json`). It counts lines, only
  `assertIn`/`assertNotIn` with a plain double-quoted literal, and prints nothing when it fails, so
  `"def failure"` in `ccp/rules.py` shows only the whole command. `LC_ALL=C git grep -hE 'assert(Not)?In\("[^"]{40,}' -- 'tests/*.py' | wc -l`: 344.
  `LC_ALL=C git grep -hE 'assert(Not)?In\(f"[^"]{40,}' -- 'tests/*.py' | wc -l`: 83 f-string pins it does not count.
- **The AST count.** A probe, a `python3 -B` program walking `ast.parse` of each `git ls-files 'tests/*.py'` file and
  counting each `ast.Call` whose function's name (`Name.id` or `Attribute.attr`) starts with `assert` and one of whose
  arguments, positional or keyword, has a literal text of 40 or more characters, gave 481. Literal text: a `str`
  `Constant`'s value (Python joins an implicit concatenation into one constant), a `JoinedStr`'s `Constant` parts
  joined, and for a `+` of strings, its two sides' texts joined.
- **Ruled.** The count part becomes one `python3 -B -c '…'` program, with no ` && ` inside it and without the words
  `from tests` (0309's extraction in `tests/test_self_hosting.py` finds the import part by them). It counts as the
  probe does, over the files named on its command line, or with none over `git ls-files 'tests/*.py'`; a file it
  cannot read or parse is skipped with the line `E4: skipped <path>: <message>` on stderr, as 0309 rules for the import
  part. Its figure is written once in the program as `figure = <N>`, set to the count at the build's own head. Over the figure it prints
  `E4 long-literal asserts: <count> > <figure>` on stdout and exits 1; otherwise it prints nothing and exits 0. E4's
  other parts are not changed: each grep prints its hits when it fails, and 0309's import part prints `<path>:<line>`.
- **The test.** `test_the_long_literal_count_reads_every_assert_form_and_names_its_figure` in
  `tests/test_self_hosting.py` extracts the part (the one holding `long-literal`) and runs it on a scratch file
  holding one long plain `assertIn`, one long f-string `assertIn`, one long `assertEqual` second argument, one implicit
  concatenation over 40 characters and one short literal (4 counted), with the figure replaced by 3 (exit 1, the line
  names `4 > 3`) and by 4 (exit 0, no output).
- **E19** is not changed: its three parts are `git grep` absences, each printing its own hits when it fails (F07's
  second half is rejected in the review record).
- **No SPEC change.** `git grep -n 'long-literal\|long literal' -- docs/spec` at `bb102371`: no line; E4 is a house
  rule (§20.1).

## Scope

- **In:** `docs/delivery/plane.json` (`architect.checks` `E4`: the count part only); `tests/test_self_hosting.py`
  (the new test).
- **Out:** E4's other parts and their order; `docs/ENGINEERING.md` (amended by the triage); converting tests to fewer
  long literals (0317 does the prompt-text modules); E19.

## dod_checks

- id: `cfg-01`
  story: As the architect, E4's count reads every assert form and holds the head's figure.
  setup: A checkout of the PR head at `<checkout>` (any seat).
  steps:
    1. Run `part=$(python3 -B -c "import json;print([p for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E4' for p in c['cmd'].split(' && ') if 'long-literal' in p][0])"); bash -c "$part"; echo "exit $?"; git grep -c 'assert(Not)?In' -- docs/delivery/plane.json`.
  expect: step 1 prints `exit 0`, then nothing from the last command (exit 1: the grep count part is gone).
  dry run (`bb102371`): the extraction found no part (`IndexError`); the last command printed `docs/delivery/plane.json:1`.
- id: `cfg-02`
  story: As a worker whose change tips E4, the failure names the count and the figure.
  setup: As `cfg-01`. A scratch file `<f>` outside the checkout holding `self.assertEqual(x, "` followed by 50 `a` characters and `")`.
  steps:
    1. In `<checkout>`, run `bash -c "$part $(git ls-files 'tests/*.py' | tr '\n' ' ') <f>"; echo "exit $?"` with `$part` as in `cfg-01`.
  expect: one line `E4 long-literal asserts: <n> > <figure>`, where `<n>` is the figure plus one, then `exit 1`.
  dry run: n/a — the part is new.
- id: `code-01`
  story: As a plane developer, the count's test bites.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_self_hosting`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_self_hosting --revert docs/delivery/plane.json`.
  expect: step 1 exits 0; step 2 prints the mutant `killed`.
  dry run: n/a — `--revert` needs the branch.

## Implementation notes

## Verification notes
