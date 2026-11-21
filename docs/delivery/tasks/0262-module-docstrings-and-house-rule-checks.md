---
task_id: 0262-module-docstrings-and-house-rule-checks
title: Module docstrings carry no usage tables or restated rules, house-rule checks hold no bare test run, and E4's check holds the long-literal count
status: pending
kind: refactor
depends_on: ["0255-test-fixtures-shared-helpers-and-one-repo-build"]
clashes_with: ["0213-a-green-tree-skips-the-lane-queue", "0214-an-exclusive-path-keeps-apart-only-its-own-tasks", "0240-plane-workers-run-the-head", "0256-suite-run-refuses-a-closed-run-and-config-reads"]
review_refs: ["ar-20261121T111633Z-4e26#F05", "ar-20261121T111633Z-4e26#F07", "ar-20261121T111633Z-4e26#F08"]
rule_refs: ["E4", "E24", "E25"]
review_point: R19
paths: ["ccp/board.py", "ccp/calibrate.py", "ccp/drill.py", "ccp/estimate.py", "ccp/estimator.py", "ccp/forecast.py", "ccp/health.py", "ccp/init.py", "ccp/mutate.py", "ccp/otel.py", "ccp/plane.py", "ccp/reviewpoints.py", "ccp/suite.py", "ccp/upgrade.py", "ccp/verify.py", "tests/test_cli_reference.py", "tests/test_verify_cache.py", "docs/delivery/plane.json", "docs/ENGINEERING.md", "docs/cli/*.md", "ccp/CLAUDE.md"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0262-module-docstrings-and-house-rule-checks

## Intent

A flag or rule changes in one place. Module docstrings in `ccp/` name their § and purpose and hold
no hand-written call syntax or restated SPEC rules, and the test that holds `docs/cli` to the parser
checks every module, so a stale usage line cannot come back. The house-rule checks the pre-gate
renders hold no bare test-runner command (the gate already runs those test modules), and house rule
E4 gets a command check that stops the count of long prose-pinning assertions from growing.

## Context (not checked)

Measured at `1aa5e3f`.

- From architect pass `ar-20261121T111633Z-4e26`, F05, F07 and F08, with its amendments to house
  rules E25 and E4 (the record is in `docs/delivery/reviews/`). The triage applied the E12
  amendment (E12's `architect.checks` entry is gone) and the E25 and E4 rule texts; the two rules'
  `check:` lines, E25's entry and E4's count are this task's.
- **Usage lines.** `git grep -nP '^ {2}ccp [a-z]' -- 'ccp/*.py'` at `1aa5e3f`: 42 lines in 13
  modules (`board`, `calibrate`, `drill`, `estimate`, `estimator`, `forecast`, `mutate`, `otel`,
  `plane`, `reviewpoints`, `suite`, `upgrade`, `verify`), all in module docstrings. `ccp/suite.py`'s
  usage line for `suite run` lacks `--wait`, which the parser has.
- **The test.** `"def test_the_cli_docstring_carries_no_usage_table"` in `tests/test_cli_reference.py`
  checks `cli.__doc__` only.
- **Long docstrings.** `python3 -B -c "import ast,sys; [print(f, len((ast.get_docstring(ast.parse(open(f).read()), clean=False) or '').splitlines())) for f in sys.argv[1:]]" ccp/suite.py ccp/verify.py ccp/health.py ccp/init.py ccp/forecast.py ccp/mutate.py` at `1aa5e3f`: 104, 97, 77, 72, 68 and 49 lines.
  They restate their § at length; `ccp/mutate.py`'s
  `--together` paragraph is also in `docs/spec/03-quality.md` and `docs/cli/03-quality.md`.
- **The pre-gate.** `architect.checks` `E25` is `python3 -B -m unittest -q tests.test_cli_reference`,
  a bare test run that the pre-gate renders to workers against `_common.md`'s "Never a bare test
  runner"; the gate runs that module anyway (E1).
- **Long literals.** `git grep -hE 'assert(Not)?In\("[^"]{40,}' -- 'tests/*.py' | wc -l` at `1aa5e3f`: 342.
  `tests/test_verify_cache.py`'s `ORIGINAL` pins a whole sentence of
  `templates/prompts/verify.md`.
- **Why after 0255.** 0255 adds `architect.checks` `E4` (the borrowed-helper grep); this task folds
  the count into that one entry, since a command rule has one check id.
- **Rulings for the build** (the lead's):
  - Every usage line goes from the docstrings the `git grep -nP` above lists; a docstring keeps its § and the module's purpose.
    The six long docstrings above end at most 40 lines each, keeping what the SPEC and `docs/cli` do
    not say about the code (none expected; anything moved goes to `docs/cli` or the package doc, not
    dropped).
  - `tests/test_cli_reference.py`'s docstring test reads every `ccp/*.py` module's docstring (and
    `ccp/doclang/*.py`'s) and fails on a line matching `^\s*ccp [a-z]`.
  - plane.json `architect.checks` loses its `E25` entry. `E4`'s `cmd` becomes 0255's grep, then
    `&& test "$(git grep -hE 'assert(Not)?In\(\"[^\"]{40,}' -- 'tests/*.py' | wc -l)" -le <N>`, with
    `<N>` the count at this task's head (at most 342).
  - `ORIGINAL` in `tests/test_verify_cache.py` is replaced by the token it guards (the setting's
    section is absent or present), not the sentence.
  - `docs/ENGINEERING.md` takes these `check:` lines (house rules, no SPEC; the rule texts are
    already in):
    - **E25**: `check: pass, plus the gate — tests.test_cli_reference checks the docs against
      the parser and every ccp module's docstring for usage lines; the gate runs it (E1); no
      architect.checks entry`.
    - **E4**: `check: command — architect.checks E4: the borrowed-helper grep, and the count of assertIn and
      assertNotIn lines on a long string literal in tests/*.py held at or below
      the figure in the command (lowered as tasks remove them)`.
- A refactor: behaviour is unchanged; the only test expectations that change are the docstring test
  (widened) and `ORIGINAL`'s.

## Scope

- **In:** the 13 modules' docstrings and those of `ccp/health.py` and `ccp/init.py`;
  `tests/test_cli_reference.py`, `tests/test_verify_cache.py`, `docs/delivery/plane.json`
  (`architect.checks`), `docs/ENGINEERING.md` (E4's and E25's `check:` lines), `docs/cli/*.md`
  and `ccp/CLAUDE.md` (only for anything a docstring held that they lack).
- **Out:** code outside docstrings, other
  long-literal assertions (ar-20261120T234012Z-27eb#F10, deferred).

## dod_checks

- id: `dc-01`
  story: As a plane developer, no module docstring in ccp/ carries call syntax.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nP '^ {2}ccp [a-z]' -- 'ccp/*.py' | wc -l`.
    2. Run `git grep -nP '^ {2}ccp [a-z]' 1aa5e3f -- ccp/suite.py | wc -l`.
  expect: step 1 prints `0`; step 2 prints `4` (the pattern finds the known usage lines at `1aa5e3f`).
  dry run (`1aa5e3f`): step 1 printed `42`; step 2 printed `4`.
- id: `dc-02`
  story: As a plane developer, the docstring test catches a usage line planted in any module.
  setup: A checkout of the PR head; then a separate copy of it with the line `  ccp graph show ID` added to `ccp/graph.py`'s module docstring.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_cli_reference`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_cli_reference`.
  expect: step 1 exits 0; step 2 exits non-zero, its output naming `ccp/graph.py`.
  dry run (`1aa5e3f`): step 1 exited 0; step 2 n/a (the widened test lands with the task).
- id: `dc-03`
  story: As a plane developer, the longest module docstrings no longer restate their §.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -c "import ast,sys; [print(f, len((ast.get_docstring(ast.parse(open(f).read()), clean=False) or '').splitlines())) for f in sys.argv[1:]]" ccp/suite.py ccp/verify.py ccp/health.py ccp/init.py ccp/forecast.py ccp/mutate.py`.
  expect: six lines, each number 40 or less.
  dry run (`1aa5e3f`): printed 104, 97, 77, 72, 68, 49.
- id: `dc-04`
  story: As an implementer, the pre-gate's house-rule checks hold no bare test-runner command.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -c "import json; print([c['id'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if '-m unittest' in c['cmd']])"`.
    2. Run `CCP_DEV=1 ./bin/ccp docs check 2>&1 | head -1`.
  expect: step 1 prints `[]`; step 2 prints `docs: clean`.
  dry run (triage branch, after the E12 entry was dropped): step 1 printed `['E25']`; step 2 printed `docs: clean`.
- id: `dc-05`
  story: As a reviewer, E4's command check fails a branch that adds a long prose assertion.
  setup: A checkout of the PR head; then a separate copy of it with one line `self.assertIn("a sentence of well over forty characters pinned in a test", "")` added to `tests/test_graph.py`.
  steps:
    1. On the head and in the copy, run `sh -c "$(python3 -B -c "import json; print({c['id']: c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks']}['E4'])")"; echo "exit $?"`.
    2. On the head, run `grep -c 'ORIGINAL' tests/test_verify_cache.py`.
  expect: step 1 ends `exit 0` on the head and a non-zero exit in the copy; step 2 prints `0`.
  dry run (`1aa5e3f`): step 1 n/a (no `E4` entry until 0255); step 2 printed `3`.

## Implementation notes

## Verification notes
