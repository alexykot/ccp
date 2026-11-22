---
task_id: 0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests
title: ccp mutate takes several tests, refuses a mutant that changes nothing, names the failing tests, and its refusals are tested on plain values
status: pending
kind: feature
depends_on: ["0267-mutate-falls-back-to-the-language-pack"]
spec_refs: ["S20"]
review_refs: ["ar-20261121T223646Z-f0a7#F01", "ar-20261121T223646Z-f0a7#F06", "ar-20261121T132817Z-d5e5#F06"]
review_point: R23
paths: ["ccp/mutate.py", "ccp/cli.py", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "tests/test_mutate.py", "tests/test_mutate_interface.py", "tests/test_mutate_refusals.py", "tests/test_cli_reference.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests

## Intent

A seat that mutation-tests a change makes one `ccp mutate` call where today it makes two or three.
It names every test that should kill the mutants in one call, and a mutant counts as killed when any
of them fails. A substitution that changes nothing is refused before any test runs, as a revert that
changes nothing already is. Each result row names the tests that failed, so the seat knows which
test bit without opening the log. A `--mutant-file` whose old text is not found says that the old
text includes its last line's line break. `ccp mutate`'s refusals are tested on plain values, so
the module costs less in the gate.

## Context (not checked)

Measured at `8020446` unless a line says otherwise. Provenance: architect pass
`ar-20261121T223646Z-f0a7`, F01 (`process-cost`) and F06 (`test-cost`, the trigger of the deferred
`ar-20261121T132817Z-d5e5` F06 in `docs/ROADMAP.md`); the record is in `docs/delivery/reviews/`.
The §20.6 change below is the operator's to sign (the triage's first question).

- **The friction.** `python3 -c` over the queue's `health/notes.jsonl`, notes since the last pass's start (`2026-11-21T17:47Z`) whose text names `mutate`: 15 (data only the queue holds); the architect classed 12 as the four gaps below.
- **One test per call.** `grep -n '"--test", required=True' ccp/cli.py` at `8020446`: 1 line; its help says "one test id". §20.6: "`--test` is one test id, passed whole".
- **No no-op refusal.** `"def _substitution"` in `ccp/mutate.py` checks that the old text is in the
  file once (`_once`) and never compares `old` with `new`; `"def parse_revert"`'s caller refuses a
  revert that changes nothing ("the revert changes nothing").
- **The 0-times refusal.** `"def _once"`: "the old text is in {where} {n} times; a mutant names one
  place". `"def parse_file"`: each text is "exactly the bytes between its marker line and the next
  marker line", so a `--mutant-file`'s old text ends with its last line's line break.
- **No failing test ids.** `"row = {"` in `"def run"` keeps `test`, `mutant`, `kind`, `files`,
  `digest`, `outcome` and the run's exit code, seconds and `timed_out`. The language pack already
  says how a failing test's section starts: `ccp/doclang/python.py` `SUMMARY["section_re"]`
  (`^(?:FAIL|ERROR|UNEXPECTED SUCCESS): `), which `ccp suite run` uses for its summary through
  plane.json `suite.summary.section_re`, else the pack's (`grep -n '"section_re": None' ccp/config.py` at `8020446`: 1 line).
- **The module's cost.** `python3 -c` over the queue's `runs/_suites.jsonl`, the cold rows with `modules` since `2026-11-21T19:15Z` (after 0255): 26 runs, `tests.test_mutate` the second slowest module, median 72.8 s (data only the queue holds). `time python3 -B -m unittest -q tests.test_mutate.Refusals` at `8020446`: 10 tests in 11.3 s on a loaded machine; the whole module 70 tests in 102.8 s. Every `Refusals` test builds a git product (`class Refusals(MutateFixture, unittest.TestCase)`, `MutateFixture(ToolkitFixture)`), though `_once`, `parse`, `parse_file` and `together` raise on plain values.
- **0262 is done.** 0262 rewrote `ccp/mutate.py`'s module docstring and merged (PR #295) after this
  triage was first written, so this task edits its result and no clash is recorded.
- **0267 first.** 0267 (R21, signed) changes `_run`'s command and the did-not-build patterns, and two
  clauses of §20.6 that this task does not quote. This task builds on its code and text, so it
  depends on it.

### Rulings for the build (the lead's)

- **Several tests.** `--test` may repeat (argparse `append`; at least one). Unmutated, each test runs
  in the order given; the first that fails stops the call (exit 1), as one does today, naming it.
  For each mutant, the tests run in order until one exits non-zero; that run decides the outcome
  (`killed`, or `unbuilt` when its output matches the did-not-build patterns), and the remaining
  tests are not run for that mutant. A mutant every test passes is `survived`.
- **The row.** `test` is the id of the test whose run decided the outcome (the one that failed, else
  the last one run). A new `failed` field lists, in output order, the rest of each line of that run's
  output (from the log offset `_test` returns) that a `section_re` pattern matches, the matched
  prefix taken off and stripped, at most 20; `[]` when none matches or the mutant survived. The
  patterns are the ones `ccp suite run` reads (plane.json `suite.summary.section_re`, else the
  language pack's). The `run`/`recorded` event payload is unchanged.
- **The no-op refusal.** A `--mutant` text substitution or a `--mutant-file` whose new text equals
  its old text, byte for byte, is refused (exit 2) at parse time, before any test runs: "`<label>`:
  the new text is the old text, so the mutant changes nothing". A `--together` whose parts are each
  refused this way is refused by the first. A patch mutant is not compared.
- **The not-found hint.** When a `--mutant-file`'s old text is not found and ends with a line
  break, `_once`'s refusal adds that the old text includes its last line's line break and that a
  substitution inside one line goes in `--mutant`. The refusal for any other count is unchanged.
- **The refusal tests.** A new `tests/test_mutate_refusals.py` tests `_once`, `parse`, `parse_file`
  and `together` on plain bytes and a temp directory holding plain files, with no git product and no
  fixture class from `tests/helpers.py`. `Refusals` in `tests/test_mutate.py` keeps at most three
  tests, the wiring of the refusals only a recorded run can reach (a closed run, a worktree of another
  task, a test that fails unmutated); the others move.
- **The briefs** keep `--test <id> …`, which stays true; no template changes.

## Scope

- **In:** `ccp/mutate.py` (`"def run"`, `"def _once"`, `"def _substitution"`, `"def parse_file"`,
  the module docstring's `--test` line), `ccp/cli.py` (`--test` repeats; its help),
  `docs/cli/03-quality.md` (the `ccp mutate` row: `--test ID [--test ID …]`),
  `tests/test_mutate.py` (`Refusals` trimmed), `tests/test_mutate_interface.py` (new),
  `tests/test_mutate_refusals.py` (new), `tests/test_cli_reference.py` (if the row's change needs it).
- **SPEC, signed before the claim (`sign_off: brief`):** `docs/spec/03-quality.md` §20.6, six
  passages replaced, each CURRENT at `8020446`. 0267's two passages (the no-command sentence and the
  `unbuilt_re` clause) are not touched.

    CURRENT (`docs/spec/03-quality.md` at `8020446`, §20.6, the synopsis's first line):
    > `ccp mutate --run <run_id> --test <id> [--mutant <m> …] [--mutant-file <path> …]

    PROPOSED:
    > `ccp mutate --run <run_id> --test <id> [--test <id> …] [--mutant <m> …] [--mutant-file <path> …]

    CURRENT (`docs/spec/03-quality.md` at `8020446`, §20.6, The product's command):
    > `--test` is one test id, passed whole, so it may name a single test method (`<module>.<Class>.<method>` for a unittest command); what runs is the command's.

    PROPOSED:
    > `--test` is one test id, passed whole, so it may name a single test method (`<module>.<Class>.<method>` for a unittest command); what runs is the command's. `--test` may be given more than once: each test id runs as its own command, in the order given.

    CURRENT (`docs/spec/03-quality.md` at `8020446`, §20.6, A mutant):
    > Every mutant is checked before any test runs; one that does not apply refuses the call (exit 2), nothing run.

    PROPOSED:
    > Every mutant is checked before any test runs; one that does not apply, or a substitution whose new text is its old text, refuses the call (exit 2), nothing run.

    CURRENT (`docs/spec/03-quality.md` at `8020446`, §20.6, Killed only when the named test fails):
    > - **Killed only when the named test fails.** The test first runs unmutated; when it fails, the call stops (exit 1), nothing applied or recorded. Then each mutant is applied alone, the test runs, and the mutant is `killed` when it exits non-zero and `survived` when it exits 0,

    PROPOSED:
    > - **Killed only when a named test fails.** Each named test first runs unmutated; when one fails, the call stops (exit 1), nothing applied or recorded. Then each mutant is applied alone and the named tests run in order until one exits non-zero; the mutant is `killed` when one does and `survived` when every one exits 0,

    CURRENT (`docs/spec/03-quality.md` at `8020446`, §20.6, the same bullet's last sentence):
    > Another test the mutant breaks does not count.

    PROPOSED:
    > A test not named that the mutant breaks does not count.

    CURRENT (`docs/spec/03-quality.md` at `8020446`, §20.6, Bound to the calling seat's run):
    > Each mutant adds a row to the run record's `mutation` list: the test id, the mutant's number,

    PROPOSED:
    > Each mutant adds a row to the run record's `mutation` list: the id of the test whose run decided its outcome (the one that failed, else the last), the ids of the failing tests that run's output names (the text after each line's `section_re` match, §14.2), the mutant's number,

  The fourth passage's sentence continues, after its last comma, with 0267's `unbuilt` clause,
  unchanged; "one whose run exits non-zero" then reads as the run that decided the mutant. No other
  SPEC text changes: `git grep -n -- '--test <id>' -- docs/spec` at `8020446` finds only §20.6's
  synopsis, and §13.2's `ccp mutate --run <run_id> …` stays true.
- **Out:** the `run`/`recorded` event's payload; choosing mutants; the prompt templates and agent
  briefs; `mutate.command`, `unbuilt_re` and the timeout (0267's); the rest of `tests/test_mutate.py`.

## dod_checks

- id: `code-01`
  story: As a reviewer, I mutation-test a change against two test modules in one call, and a mutant only the second one catches counts as killed.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_mutate_interface`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_mutate_interface --mutant-file <file>`, the file's mutant making `"def run"` try only the first `--test` id for each mutant.
  expect: step 1 exits 0 and lists, each `ok`, a test where a call with two `--test` ids and a mutant that only the second test fails records one row with `outcome` `killed` and `test` the second id; a test where a mutant both tests pass records `survived` with `test` the second id; and a test where the second test fails unmutated stops the call (exit 1) naming it, nothing recorded. Step 2 prints the mutant `killed`.
  dry run: n/a — the module and the flag are new.
- id: `code-02`
  story: As an implementer, a mutant whose new text is its old text is refused before any test runs, instead of running and "surviving".
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_mutate_refusals`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_mutate_refusals --mutant-file <file>`, the file's mutant making `"def _substitution"` (or the code the PR uses for the comparison) skip the old-equals-new comparison.
  expect: step 1 exits 0 and lists, each `ok`, a test that a `--mutant` `<file>:x=>x` is refused with exit 2 and a message containing `changes nothing`, and one that a `--mutant-file` with identical old and new text is refused the same way. Step 2 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `code-03`
  story: As a verifier, each mutation row names the tests that failed, so I see which test bit without opening the log.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_mutate_interface`.
  expect: exits 0 and lists, `ok`, a test where a killed mutant's row carries `failed` holding the id of the one failing test method of a two-method module (the text after unittest's `FAIL: `), and a survived mutant's row carries `failed` `[]`.
  dry run: n/a — the module is new.
- id: `code-04`
  story: As an implementer, a `--mutant-file` whose old text is not found tells me the old text ends with its last line's line break.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_mutate_refusals`.
  expect: exits 0 and lists, `ok`, a test that a `--mutant-file` whose old text is a part of one line followed by its line break, absent from the file as written, is refused with exit 2 and a message containing `line break`; and that a `--mutant` found 0 times gets no such words.
  dry run: n/a — the module is new.
- id: `test-01`
  story: As a plane developer, the mutate refusals are tested on plain values, and the module that builds a git product keeps only the wiring.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nE 'Fixture|from tests.helpers|import helpers' -- tests/test_mutate_refusals.py`.
    2. Run `awk '/^class Refusals/{f=1;next} /^class /{f=0} f && /def test_/' tests/test_mutate.py | wc -l`.
    3. Run `python3 -B -m unittest -q tests.test_mutate_refusals 2>&1 | grep '^Ran'`.
  expect: step 1 prints nothing (exit 1); step 2 prints a number of at most 3; step 3 prints `Ran <n> tests in <s>s` with `n` at least 7 and `s` under 3.
  dry run (`8020446`): step 1 n/a — the module is new; step 2 printed `10`; step 3 n/a.
- id: `spec-01`
  story: As the operator, §20.6 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0271`.
  expect: exit 0, all six PROPOSED passages found in `docs/spec/03-quality.md`.
  dry run (simulated at `8020446`: this task file committed, then the six passages applied to `docs/spec/03-quality.md`, each CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0271 --base HEAD~2`): `"ok": true`, six passage(s) found, none missing.

## Implementation notes

## Verification notes
