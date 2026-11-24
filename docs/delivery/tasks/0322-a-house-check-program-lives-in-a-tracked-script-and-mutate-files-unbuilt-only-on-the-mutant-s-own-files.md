---
task_id: 0322-a-house-check-program-lives-in-a-tracked-script-and-mutate-files-unbuilt-only-on-the-mutant-s-own-files
title: E4's and E24's check programs move out of plane.json into one tracked script that architect.checks calls in one line each; ccp mutate files a mutant unbuilt on a source-location line only when it names a file the mutant touched, and prints one line per mutant on stderr
status: pending
kind: feature
depends_on: []
spec_refs: ["S20"]
rule_refs: ["E4", "E24"]
review_refs: ["ar-20261124T034246Z-e089#F05", "ar-20261124T034246Z-e089#F07"]
review_point: R33
paths: ["scripts/house_checks.py", "scripts/CLAUDE.md", "docs/delivery/plane.json", "tests/test_self_hosting.py", "ccp/mutate.py", "ccp/doclang/python.py", "ccp/cli.py", "tests/test_mutate.py", "tests/test_doclang_test_facts.py", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "contracts/plane_config.schema.json"]
clashes_with: ["0191-the-grace-release-ends", "0311-suite-affected-and-suite-run-affected-run-a-staged-part-lane-as-declared", "0319-the-pack-stops-matching-a-path-the-affected-map-names-by-name-so-a-plane-json-edit-runs-the-tests-that-read-it", "0320-dry-run-lists-a-placeholder-step-as-not-run-and-here-prints-each-step-s-whole-output"]
sign_off: brief
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0322-a-house-check-program-lives-in-a-tracked-script-and-mutate-files-unbuilt-only-on-the-mutant-s-own-files

## Intent

A seat can mutation-test a house-rule check and read the result without help. E4's two check programs and E24's
program live in one tracked Python script, `scripts/house_checks.py`, with a subcommand each, and `architect.checks`
calls each in one line with its figure as an argument; a mutant then targets an ordinary `.py` file, not raw `\n`
escapes inside a JSON string where the same `except` clause occurs twice. `ccp mutate` stops filing a killed mutant
as `unbuilt` because a failing test's message quotes a child program's syntax error in some other file: a
source-location line counts as "did not build" only when it names a file the mutant touched. Each call ends with one
plain line per mutant on stderr (its number, its outcome and the test that decided it), so a seat no longer greps
the JSON for `outcome`.

## Context (not checked)

Findings F05 and F07 of architect pass `ar-20261124T034246Z-e089` (`docs/delivery/reviews/ar-20261124T034246Z-e089.md`),
and the lead's friction notes T95 (a killed mutant filed `unbuilt` in 0309's review) and T97 (`ccp mutate` cannot run
a plane.json check part).

Measured at `9691fd9c` (origin/main after 0317's reconcile):

- **The embedded programs.**
  `python3 -B -c 'import json; c=json.load(open("docs/delivery/plane.json"))["architect"]["checks"]; print(sum("python3 -B -c" in x["cmd"] for x in c), max(len(x["cmd"]) for x in c))'`
  printed `2 2236`: E4 (2236 characters, two `python3 -B -c` programs: the long-literal count with `figure = 448`, and
  the test-module import check) and E24 (513 characters, one program with `long_max = 10; exit_max = 0`). Both E4
  programs hold `except (OSError,SyntaxError,ValueError) as e: print(f"E4: skipped {f}: {e}",file=sys.stderr); continue`.
  With each program replaced by a one-line call, E4's cmd is 445 characters (a probe substituting
  `python3 -B scripts/house_checks.py e4-count --max 448` and `python3 -B scripts/house_checks.py e4-imports`).
- **Who runs them.** `tests/test_self_hosting.py` (`TestModulesImportNoTestModule`, `LongLiteralCount`) cuts the
  programs out of E4's cmd (`e4_part`, `e4_import_check`) and runs them on scratch repos. Friction 0316: a unique mutant
  of plane.json took four tries, and bash `${var/…/…}` failed silently on a mutant's text.
- **The unbuilt misfile.** `"def _says_unbuilt"` in `ccp/mutate.py` matches every pattern against every line of a
  mutant's run. The Python pack's first pattern (`UNBUILT_RE` in `ccp/doclang/python.py`) is
  `^  File "[^<"][^"]*", line \d+$`, the frame a module's syntax error prints. 0309's review log
  (`runs/0309-…/review-mutate.log` in the queue, mutant 2 on `tests.test_self_hosting.TestModulesImportNoTestModule`,
  a mutant of `docs/delivery/plane.json`): the FAIL section's assertion message quotes the child's
  `  File "tests/test_b.py", line 1` and `SyntaxError: invalid syntax` (the test's own fixture), so a killed mutant
  was filed `unbuilt`.
- **The output.** `"def main"`'s toolkit branch in `ccp/cli.py` prints the whole result with
  `json.dumps(body, indent=2, ensure_ascii=False)`; friction 0306 (reviewer and implementer) grepped it for `outcome`.
- **Ruled.**
  - `scripts/house_checks.py` (new, plane development only, listed in `scripts/CLAUDE.md`) has three subcommands:
    `e4-count --max N [FILE …]` (the long-literal count; with no files, the tracked `tests/*.py`; prints
    `E4 long-literal asserts: <count> > <N>` and exits 1 when over), `e4-imports` (the import check, printing
    `<path>:<line>` per hit) and `e24 --long-max N --exit-max N` (printing each over line as now). Each skips and names
    a file it cannot read as now (`E4: skipped <file>: <error>` on stderr), through one shared function. The output
    lines stay as they are.
  - `architect.checks` `E4` keeps its four greps and calls `e4-count --max 448` and `e4-imports`; `E24` becomes
    `python3 -B scripts/house_checks.py e24 --long-max 10 --exit-max 0`. The figures stay in plane.json, where the
    ratchet edits them; each is the value at the build's base.
  - `tests/test_self_hosting.py` runs the script instead of cutting parts out of the cmd, and gains
    `test_the_house_checks_name_their_figure_when_over` (class `LongLiteralCount`), which runs `e4-count --max 0`
    and `e24 --long-max 0 --exit-max 0` on the checkout and asserts exit 1 and each over line.
  - Unbuilt: a pattern with a group named `path` counts a line only when that group's text is a file the mutant
    touched, root-relative, or ends with `/` and that path. The Python pack's first pattern becomes
    `^  File "(?P<path>[^<"][^"]*)", line \d+$`; its other two lines have no group and count as now. The decision is a
    plain function of the output text, the patterns and the mutant's files. Its test is a new class `UnbuiltLines` in
    `tests/test_mutate.py`, `test_a_frame_counts_only_when_it_names_a_file_the_mutant_touched`: 0309's FAIL section
    (above) with files `["docs/delivery/plane.json"]` is not unbuilt and with `["tests/test_b.py"]` is; a frame
    `  File "/w/rev-1/ccp/x.py", line 5` with `["ccp/x.py"]` is; `ImportError: Failed to import test module: tests.test_x`
    is, whatever the files. `tests/test_doclang_test_facts.py`'s pin of the pattern text changes with it.
  - After the JSON, `ccp mutate` prints on stderr one line per mutant, `mutant <n>: <outcome> (<test id>)`, the test
    being the row's `test`. The test is `test_each_mutant_prints_one_line_on_stderr` in `tests/test_mutate.py` (class
    `Outcomes`).

## Scope

- **In:** `scripts/house_checks.py` (new); `scripts/CLAUDE.md` (its line); `docs/delivery/plane.json`
  (`architect.checks` `E4` and `E24` only); `tests/test_self_hosting.py`; `ccp/mutate.py` (the unbuilt decision, the
  stderr lines); `ccp/doclang/python.py` (`UNBUILT_RE`'s first pattern and its comment); `ccp/cli.py` (only if the
  stderr lines are printed there); `tests/test_mutate.py`; `tests/test_doclang_test_facts.py`;
  `docs/spec/03-quality.md` (§20.6, the passages below); `docs/cli/03-quality.md` (the `ccp mutate` row) and
  `contracts/plane_config.schema.json` (`mutate.unbuilt_re`'s description), §31.1: they follow the passages.
- **SPEC, signed before the claim (`sign_off: brief`):** two passages in `docs/spec/03-quality.md`, §20.6.

    CURRENT (`docs/spec/03-quality.md` at `9691fd9c`), §20.6, the bullet "Killed only when a named test fails":
    > - **Killed only when a named test fails.** Each named test first runs unmutated; when one fails, the call stops (exit 1), nothing applied or recorded. Then each mutant is applied alone and the named tests run in order until one exits non-zero; the mutant is `killed` when one does and `survived` when every one exits 0, except that one whose run exits non-zero with an output line matching plane.json `mutate.unbuilt_re` (a regular expression or a list of them; unset, the language pack's did-not-build lines) is `unbuilt`: the code did not build or import, which proves nothing about the test. A test not named that the mutant breaks does not count.

    PROPOSED:
    > - **Killed only when a named test fails.** Each named test first runs unmutated; when one fails, the call stops (exit 1), nothing applied or recorded. Then each mutant is applied alone and the named tests run in order until one exits non-zero; the mutant is `killed` when one does and `survived` when every one exits 0, except that one whose run exits non-zero with an output line matching plane.json `mutate.unbuilt_re` (a regular expression or a list of them; unset, the language pack's did-not-build lines) is `unbuilt`: the code did not build or import, which proves nothing about the test. A pattern with a group named `path` matches a line only when that group's text is a file the mutant touched (its root-relative path, or ending with `/` and that path), so a test whose output quotes another file's syntax error leaves the mutant `killed`; the Python pack's source-location line has such a group. A test not named that the mutant breaks does not count.

    CURRENT (same file and commit), §20.6, the bullet "Bound to the calling seat's run", its last sentence:
    > The call ends with one `run`/`recorded` event (run id and the counts).

    PROPOSED:
    > The call ends with one `run`/`recorded` event (run id and the counts) and prints on stderr one line per mutant, `mutant <n>: <outcome> (<test id>)`, the test that decided it.

  No sentence is retired: the first bullet gains one sentence; the second sentence gains a clause.
- **Out:** E4's four greps and its figure; the other `architect.checks`; the JSON result's shape; `--together`'s rows.

## dod_checks

- id: `code-01`
  story: As a plane developer, no house check embeds a Python program in plane.json.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `python3 -B -c 'import json; c=json.load(open("docs/delivery/plane.json"))["architect"]["checks"]; print(sum("python3 -B -c" in x["cmd"] for x in c), max(len(x["cmd"]) for x in c))'`.
  expect: prints `0` and a number of at most 600.
  dry run (`9691fd9c`): printed `2 2236`.
- id: `cmd-01`
  story: As a seat, the house-check script names its figure when a count is over, and the repo's checks still pass.
  setup: As `code-01`.
  steps:
    1. Run `python3 -B scripts/house_checks.py e4-count --max 0; echo "exit $?"`.
    2. Run `python3 -B scripts/house_checks.py e24 --long-max 0 --exit-max 0; echo "exit $?"`.
    3. Run `CCP_DEV=1 ./bin/ccp docs check --only E4 && CCP_DEV=1 ./bin/ccp docs check --only E24; echo "exit $?"`.
  expect: step 1 prints a line starting `E4 long-literal asserts: ` and ending ` > 0`, then `exit 1`; step 2 prints a line starting `E24 docstrings over 30 lines: ` and ending ` > 0`, then `exit 1`; step 3's last line is `exit 0`.
  dry run (`9691fd9c`): steps 1 and 2 printed `python3: can't open file …/scripts/house_checks.py: [Errno 2] No such file or directory`, `exit 2`; step 3 printed `docs: clean: E4 only`, `docs: clean: E24 only`, `exit 0`.
- id: `code-02`
  story: As a reviewer, a mutant whose test quotes another file's syntax error is killed, and one that breaks the mutated file's syntax is unbuilt.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_mutate.UnbuiltLines.test_a_frame_counts_only_when_it_names_a_file_the_mutant_touched`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_mutate.Unbuilt tests.test_doclang_test_facts`.
  expect: both exit 0.
  dry run: n/a — the test is new.
- id: `code-03`
  story: As a seat, each mutant's outcome is one plain line on stderr.
  setup: As `code-02`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_mutate.Outcomes.test_each_mutant_prints_one_line_on_stderr`.
  expect: exit 0.
  dry run: n/a — the test is new.
- id: `code-04`
  story: As a plane developer, the self-hosting tests run the house checks from the script and fail when it is broken.
  setup: As `code-02`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_self_hosting.LongLiteralCount.test_the_house_checks_name_their_figure_when_over`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_self_hosting`.
    3. Run `git grep -nE 'def (e4_part|e4_import_check)\(' -- tests/test_self_hosting.py`.
  expect: steps 1 and 2 exit 0; step 3 prints nothing (exit 1): no test cuts a program out of plane.json.
  dry run (`9691fd9c`): step 3 printed 2 lines (`def e4_part`, `def e4_import_check`); steps 1 and 2 n/a — the test is new.
- id: `spec-01`
  story: As the operator, §20.6 says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0322`.
  expect: exit 0, both PROPOSED passages found.
  dry run (`9691fd9c`): exit 1, both PROPOSED passages missing; each CURRENT passage is found once in `docs/spec/03-quality.md` (`grep -c 'The call ends with one' docs/spec/03-quality.md`: 1).

## Implementation notes

- `scripts/house_checks.py` holds E4's two programs (`e4-count --max N [FILE …]`, `e4-imports`) and E24's (`e24
  --long-max N --exit-max N`), moved without changing what they count or print; one shared `parsed` reads and parses
  each file and names one it cannot on stderr. `architect.checks` `E4` is 445 characters and `E24` one call; neither
  embeds a program (`code-01` prints `0 445`). At the base, both scripts' figures match the old programs' (E4 446,
  E24 10 over 30 lines).
- E24's program used to stop on a file it could not parse; it now skips and names it as E4's do, with its own rule
  id: `E24: skipped <file>: <error>` (the narrowest reading of "each skips … as now").
- The unbuilt decision is `mutate.says_unbuilt(text, patterns, files)`, a plain function; `_says_unbuilt` reads the
  run's log and passes the mutant's `files`. A pattern whose `path` group did not take part in the match counts as
  naming no touched file.
- The stderr lines come from `mutate.lines(body)`; `ccp/cli.py`'s `_toolkit` takes an optional `after` that prints
  them after the JSON, used by `ccp mutate` alone.
- `tests/test_self_hosting.py` runs the script (`house_check`); besides the ruled
  `test_the_house_checks_name_their_figure_when_over`, `LongLiteralCount` gains
  `test_the_docstring_counts_read_the_tracked_ccp_modules_and_skip_one_they_cannot_parse`, a scratch repo for E24's
  two counts and its skip, which no test covered.
- Fix round 1: `_names_touched` compares the mutant's paths as `_key` spells them. A `--mutant`, `--mutant-file`
  or `--revert` keeps the path as typed, so `./ccp/x.py` never matched the frame's real path and a syntax-breaking
  mutant was filed killed; `UnbuiltLines` now pins `./ccp/x.py` and `ccp//x.py`.

## Verification notes
