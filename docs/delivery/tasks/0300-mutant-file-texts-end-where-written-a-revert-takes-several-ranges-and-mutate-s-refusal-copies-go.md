---
task_id: 0300-mutant-file-texts-end-where-written-a-revert-takes-several-ranges-and-mutate-s-refusal-copies-go
title: A --mutant-file's texts end where their writer stopped, a revert takes several line ranges, mutate's end-to-end copies of its plain-value refusal tests go, and its --test help, suite-pattern read and a test's call are put right
status: done
kind: feature
depends_on: ["0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes"]
spec_refs: ["S20"]
rule_refs: ["E15", "E21"]
review_refs: ["ar-20261122T141424Z-e148#F02", "ar-20261122T141424Z-e148#F04", "ar-20261122T141424Z-e148#F08"]
review_point: R27
paths: ["ccp/mutate.py", "ccp/suite.py", "ccp/cli.py", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "tests/test_mutate.py", "tests/test_mutate_refusals.py", "tests/test_mutant_file_line_break.py", "tests/test_mutant_file_texts.py", "tests/test_doclang_test_facts.py"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-23
---

# Task: 0300-mutant-file-texts-end-where-written-a-revert-takes-several-ranges-and-mutate-s-refusal-copies-go

## Intent

A worker writes a `--mutant-file` the way it reads: each text ends where the writer stopped, so a
substitution inside one line works in a file as it does in `--mutant`, and no refusal has to explain a
hidden line break. Putting back several separate hunks of one file is one revert with several line
ranges, not one range that also reverts the lines between them. `tests.test_mutate`, the slowest
module, keeps only the wiring its plain-value refusal tests cannot reach, and the smaller leftovers of
0271 are closed.

## Context (not checked)

From the triage of architect pass `ar-20261122T141424Z-e148` (F02, a `rule-cost` finding; F04; F08) and
0271's open follow-ups `implement#1` to `#3` (`0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests`).
F02 is the operator's to decide (that record's first question): signing this brief chooses its option (a).
Measured at `3368264`.

- **F02.** §20.6 makes each text "exactly what lies between its marker line and the next", so an old text
  always ends with the line break before `=== new`. 0291 and 0271 only reworded the refusal: `"def _once"`
  in `ccp/mutate.py` works out the text less that line break and still refuses
  (`git grep -n '_without_line_break\|from_file' -- ccp` at `3368264`: 10 lines). Workers' notes of eleven tasks (0234, 0237,
  0261, 0272, 0276, then 0287, 0288, 0291, 0294, 0271, 0273; queue data) describe it; 0273's notes add that a
  line with a trailing comment must be written whole. 0271's `implement#1` asks whether a whole-line old text
  that matches nothing should carry the hint too; with the line break dropped, the hint and that question go.
- **What (a) costs.** A whole-line substitution is written as before (both texts lose their last line break, so
  the line's own break is untouched). Four cases change:
  - an old text that is also the start of another line (`x = 1` in `x = 10`) now counts twice and is refused as
    ambiguous, until the writer makes it unique or keeps its line break with an empty line after it;
  - a text that must end with a line break needs the empty line in the new text too, or the line after it joins
    the new text's last line;
  - a whole-line deletion written as before (an empty new text) is not refused but leaves a blank line where the
    lines were; deleting the line breaks too takes an empty line before `=== new`;
  - a new text at the file's end keeps a last line break only through an empty last line, which editors often
    strip.
- **F04.** `tests/test_mutate.py` runs, on `MutateFixture` (a git product with a worktree, a run and a
  ledger), refusals `tests/test_mutate_refusals.py` already tests on plain files:
  `test_a_part_missing_is_refused_and_nothing_runs`, `test_old_text_absent_a_missing_target_or_no_such_file_is_refused`,
  `test_together_a_patch_and_a_substitution_on_one_file_are_refused`,
  `test_together_a_substitution_whose_old_text_an_earlier_one_removed_is_refused` and
  `test_together_with_one_mutant_is_refused`. `Refusals`' three tests already prove that a refusal runs nothing
  and records no row. The plain tests lack two of the end-to-end variants: a mutant file whose marker comes
  first or whose markers are swapped, and a mutant file naming `missing.py` or `../calc.py` (read at `3368264`).
- **F08.** `RANGE_RE` takes one `N-M`, and `"def _revert_lines"` takes one `first, last`; `--together` lets
  only substitutions share a file, so separate hunks need one range over the lines between them (0270's
  implementer's note).
- **0271's leftovers.** `implement#2`: `tests/test_doclang_test_facts.py` calls `mutate._run(…, "t", …)` with a
  string for the tests. `implement#3`: `ccp/mutate.py` reads `suite._summary_cfg(cfg)["section_re"]` with a
  `noqa: SLF001`. The lead's note: `--test`'s help says the failing run "kills the mutant", though it may be
  `unbuilt`.
- **0285 first.** 0285 (signed) rewrites the same `--test` help in `ccp/cli.py` and touches `ccp/mutate.py`,
  `tests/test_mutate.py` and `tests/test_doclang_test_facts.py`. Its ruled help text ("one test id, passed whole
  to plane.json mutate.command ({test}), or, unset, after the language pack's test command; it may name a single
  method") was written before 0271 made `--test` repeat; this task's help ruling follows it.

### Rulings for the build (the lead's)

- **Mutant-file texts.** `"def parse_file"` takes each text less the one line break it ends with (`\r\n`, `\n` or
  `\r`), none when it ends with none. The not-found refusal is the plain one for every source: `_once`'s
  `from_file` parameter (and `_substitution`'s and the parts' `from_file`) and the line-break and `--mutant`
  hint go; `_without_line_break` may stay as `parse_file`'s stripper.
  `tests/test_mutant_file_line_break.py` is removed, and `test_a_mutant_file_part_of_a_line_names_its_line_break_and_a_mutant_does_not`
  in `tests/test_mutate_refusals.py` goes. A new `tests/test_mutant_file_texts.py` tests on plain files: a
  mid-line old text is found and substituted; a whole-line mutant written as before gives the same file as at
  `3368264`; an empty line before `=== new` keeps the old text's line break; CRLF files behave the same;
  `test_each_text_is_exactly_the_bytes_between_its_markers` (`tests/test_mutate.py`) moves here with the new texts.
  `test_a_relative_path_is_read_from_the_current_directory` (`tests/test_mutate.py`, `MutantFiles`) asserts the old
  text with its last line break, so it breaks too: it expects the text less that break.
- **Several ranges.** `--revert <path>:<n>[-<m>][,<n>[-<m>]…]`: `RANGE_RE` reads comma-separated ranges, in any
  order, overlapping allowed; `_revert_lines` takes the list and puts back each hunk any range hits, by today's
  rule per range. Each range is checked against the file as today, naming the bad one. The digest covers the
  ranges as given. `ccp/cli.py`'s `--revert` metavar becomes `PATH[:N[-M][,N[-M]…]]`, and the docs/cli row's
  synopsis follows. Tests go in `RevertLines` (`tests/test_mutate.py`, plain values).
- **The copies.** The five tests in Context go from `tests/test_mutate.py`; before they go,
  `tests/test_mutate_refusals.py` gains the two variants it lacks.
- **`--test`'s help** reads "a test id, passed whole to plane.json mutate.command ({test}), or, unset, after the
  language pack's test command; it may name a single method; repeat for more: they run in the order given until
  one fails, and that run decides the mutant (killed, or unbuilt)".
- **The suite patterns.** `ccp/suite.py` gains `def section_patterns(cfg)`, the `section_re` list
  `_summary_cfg` resolves; `ccp/mutate.py` calls it, and its `noqa: SLF001` goes.
- **The test's call.** `tests/test_doclang_test_facts.py` passes `["t"]`.

## Scope

- **In:** `ccp/mutate.py`, `ccp/suite.py` (`section_patterns`), `ccp/cli.py` (`--test` help, `--revert`
  metavar), `docs/cli/03-quality.md` (the `ccp mutate` row's `--revert` synopsis), `tests/test_mutant_file_texts.py`
  (new), `tests/test_mutant_file_line_break.py` (removed), `tests/test_mutate.py`, `tests/test_mutate_refusals.py`,
  `tests/test_doclang_test_facts.py`.
- **SPEC, signed before the claim (`sign_off: brief`):** three passages in `docs/spec/03-quality.md`, each CURRENT
  at `3368264`.

    CURRENT (`docs/spec/03-quality.md` at `3368264`), §20.6, **A mutant**:
    > each text exactly what lies between its marker line and the next (or the file's end); a file without the path, either marker or the old text refuses the call (exit 2).

    PROPOSED:
    > each text what lies between its marker line and the next (or the file's end), less the one line break that ends it, so a text ends where its writer stopped and one that must end with a line break is followed by an empty line; a file without the path, either marker or the old text refuses the call (exit 2).

    CURRENT (`docs/spec/03-quality.md` at `3368264`), §20.6, **A revert**:
    > (`--revert <path>[:<n>[-<m>]]`) is a mutant that puts back the merge base's version

    PROPOSED:
    > (`--revert <path>[:<n>[-<m>][,<n>[-<m>]…]]`) is a mutant that puts back the merge base's version

    CURRENT (`docs/spec/03-quality.md` at `3368264`), §20.6, **A revert**:
    > With a line range (1-based, inclusive, lines of the worktree's file) it puts back only the changes from the merge base those lines overlap, and a deletion inside the range or next to it;

    PROPOSED:
    > With line ranges (1-based, inclusive, lines of the worktree's file, separated by commas, in any order) it puts back only the changes from the merge base any of them overlaps, and a deletion inside a range or next to one;
- **Out:** `--mutant`'s grammar; patch mutants; `--together`'s file-sharing rule; the `failed` and `test` row
  fields (0271); the `ccp mutate` stdout keys.

## dod_checks

- id: `spec-01`
  story: As the operator, §20.6 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0300`.
  expect: exit 0, all three PROPOSED passages found.
  dry run (simulated at `d17505a`: this task file committed, then each passage applied, its CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0300 --base HEAD~1`): `"ok": true`, every passage found.
- id: `code-01`
  story: As a worker writing a mutant file, a text ending mid-line is found as I wrote it.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_mutant_file_texts tests.test_mutate_refusals`.
    2. Run `grep -e mid_line -e whole_line -e '^OK' <the log step 1 names>`.
    3. Run `git grep -n 'from_file\|line break before\|includes its last line\|names_its_line_break' -- ccp/mutate.py tests/test_mutate_refusals.py tests/test_mutant_file_texts.py`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_mutant_file_texts --mutant-file <file>`, the file's mutant making `parse_file` keep the old text's last line break.
  expect: step 1 exits 0; step 2 lists, each `ok`, a test whose name holds `mid_line` (a mutant file whose old text ends mid-line is substituted) and one whose name holds `whole_line` (a whole-line mutant gives the same file as before), then `OK`; step 3 prints nothing (exit 1); step 4 prints the mutant `killed`.
  dry run (`3368264`): step 3 printed 12 lines (11 in `ccp/mutate.py`, 1 in `tests/test_mutate_refusals.py`); steps 1, 2 and 4: n/a — the module is new.
- id: `code-02`
  story: As a worker reverting separate hunks of one file, one revert with several ranges puts back just those hunks.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_mutate.RevertLines`.
    2. Run `grep -e ranges -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_mutate.RevertLines --mutant-file <file>`, the file's mutant making `_revert_lines` read only the first range.
  expect: step 1 exits 0; step 2 lists, `ok`, a test whose name holds `ranges` where, on a file with changes at lines 2 and 5, `2,5` puts both back and leaves line 3's other change, `5,2` gives the same, and a range past the file's end is refused naming it; then `OK`. Step 3 prints the mutant `killed`.
  dry run (`3368264`): step 2 printed only `OK` (no test names `ranges` yet).
- id: `test-01`
  story: As a plane developer, the slowest module no longer repeats refusals the plain tests hold.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -c -e 'def test_a_part_missing_is_refused_and_nothing_runs' -e 'def test_old_text_absent_a_missing_target_or_no_such_file_is_refused' -e 'def test_together_a_patch_and_a_substitution_on_one_file_are_refused' -e 'def test_together_a_substitution_whose_old_text_an_earlier_one_removed_is_refused' -e 'def test_together_with_one_mutant_is_refused' -- tests/test_mutate.py`.
    2. Run `git grep -nF -e 'missing.py\n=== old' -- tests/test_mutate_refusals.py`.
    3. Run `git grep -nF -e '../calc.py\n=== old' -- tests/test_mutate_refusals.py`.
    4. Run `git grep -nF -e '"calc.py\n=== new\n' -- tests/test_mutate_refusals.py`.
  expect: step 1 prints nothing (exit 1); steps 2 and 3 each print at least one line; step 4 prints at least two lines (the existing text with no `=== old`, and the swapped markers).
  dry run (`3368264`): step 1 printed `tests/test_mutate.py:5`; steps 2 and 3 printed nothing; step 4 printed 1 line (the text with no `=== old`).
- id: `code-03`
  story: As a worker reading mutate's help, and a plane developer reading its code, each says what happens.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp mutate -h | tr -s ' \n' ' ' | grep -o 'killed, or unbuilt'`.
    2. Run `git grep -n '_summary_cfg' -- ccp/mutate.py; git grep -n '_run(.*"t",' -- tests`.
  expect: step 1 prints `killed, or unbuilt`; step 2 prints nothing.
  dry run (`3368264`): step 1 printed nothing; step 2 printed 2 lines (`ccp/mutate.py`'s `suite._summary_cfg` and `tests/test_doclang_test_facts.py`'s `"t"`).

## Implementation notes

- **Mutant-file texts.** `parse_file` takes each text through `_without_line_break`, which now returns the text
  itself when it ends with no line break (it returned empty, which only the old hint needed). `_once`,
  `_substitution`, the text part's dict and `together` lose `from_file`, and the line-break hint goes: a zero
  count is the plain refusal for every source. The module docstring's two sentences on the texts and the range
  follow §20.6.
- **Several ranges.** `RANGES_RE` is `RANGE_RE` comma-separated; `parse_revert` matches it and hands the ranges
  to `_ranges(spec, rel, rng, n)`, a plain function that reads them in the order given and refuses the first
  bad one, naming it as today (`lines N-M are not a range of <file>'s n lines`). `_revert_lines` takes the list
  and puts back a hunk when any range hits it, by today's rule per range. The digest still hashes `rng` as given,
  so `3,8` and `8,3` give the same content and different digests.
- **code-02's file.** Under `git diff -U0` a change at line 3 is in one hunk with a change at line 2, so no file
  has changes at 2 and 5 and a separate change between them. `RevertLines`' `ranges` test uses changes at lines 2,
  4 and 6 of a seven-line file: `2,6`, `6,2` (and overlapping or repeated ranges) put back 2 and 6 and leave 4,
  `2-6` puts back all three, and a range past the end (`2,8`) or reversed is refused naming it.
  `RevertsAsGitShows` gains one call of `parse_revert` with two ranges (no test run), for the wiring.
- **The copies.** The five end-to-end tests go from `tests/test_mutate.py`; `tests/test_mutate_refusals.py`
  gains a mutant file whose marker comes first, one whose markers are swapped, and
  `test_a_mutant_file_whose_old_text_or_target_is_not_there` (old text absent, `missing.py`, `../calc.py`, an
  absolute path). `test_each_text_is_exactly_the_bytes_between_its_markers` moves to
  `tests/test_mutant_file_texts.py` as `test_each_text_is_what_lies_between_its_markers_less_its_last_line_break`.
- **The rest.** `suite.section_patterns(cfg)` returns `_summary_cfg(cfg)["section_re"]`, and
  `test_doclang_test_facts` asserts it gives the pack's pattern. The `--test` help is the ruled text; the
  `--revert` metavar is `PATH[:N[-M][,N[-M]…]]`.
- **Fix round 1.** `Reverts.test_a_revert_that_changes_nothing_or_names_no_file_is_refused` drops
  `calc.py:5-99` and `calc.py:6-5`: a range past the end or reversed is `_ranges`' branch, held on plain values
  by `RevertLines`' ranges test and wired by `RevertsAsGitShows`' `rep.txt:3,9`. It keeps `calc.py:15`: line 15
  of the 15-line `GUARDED` is in the file and unchanged, so that spec is the ranged changes-nothing refusal, not
  a range refusal. The module docstring and the two §20.6 bullets are re-wrapped (`verify spec-text` still
  finds all three passages), and the `ccp mutate` row in `docs/cli/03-quality.md` says "a file or of line
  ranges".

## Verification notes
- 2026-11-23 — verifier, PR #367 head `975b706` (close's catch-up of the approved `ccf3b03`, gate run st-20261123T225125Z-9a96fa) (squash `ec6c068`): APPROVE. Passed: spec-01, code-01, code-02, test-01, code-03. Gate: `ccp wt exec -- suite run --lane gate` exit 0, `ccp wt exec -- tasks check` exit 0, `ccp wt exec -- docs check` exit 0. Record: verification/0300-mutant-file-texts-end-where-written-a-revert-takes-several-ranges-and-mutate-s-refusal-copies-go.json.

