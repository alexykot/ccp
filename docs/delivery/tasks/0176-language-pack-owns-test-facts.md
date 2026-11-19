---
task_id: 0176-language-pack-owns-test-facts
title: The language pack owns its test-output patterns, its affected reader and its test command
status: done
kind: refactor
depends_on: []
spec_refs: ["S14", "S21"]
review_refs: ["sh-20261119T170325Z-8142#F03"]
rule_refs: ["E18"]
review_point: R12
paths: ["ccp/doclang/__init__.py", "ccp/doclang/python.py", "ccp/doclang/CLAUDE.md", "ccp/suite.py", "ccp/config.py", "ccp/mutate.py", "contracts/plane_config.schema.json", "docs/delivery/plane.json", "tests/test_doclang_test_facts.py"]
clashes_with: ["0171-affected-says-run-the-full-lane", "0173-plane-json-block-registry"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0176-language-pack-owns-test-facts

## Intent

What the plane knows about Python's tests (how unittest prints its counts and failures, how a test
module is found and what it imports, the command that runs named modules) lives in the Python language
pack, beside its doc conventions, and core code names no language and no test runner. When ADR-0043
makes the language a required top-level key (0182), only the pack lookup changes. Nothing the plane
does changes.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, finding F03 and preparatory refactor P5; house rule E18 (added in
  this triage).
- The Python test facts at `e9ff0fc`, outside `ccp/doclang`:
  - `ccp/config.py` `SUITE_SUMMARY_DEFAULTS`: `failed_re`, `skipped_re`, `section_re` (unittest's
    `FAILED (…)`, `OK (skipped=…)`, `FAIL:`/`ERROR:`).
  - `ccp/suite.py`: `DEFAULT_COUNT_RE = r"^Ran (\d+) tests? in "`, `TEST_FILE_GLOB = "test*.py"`,
    `def _python_affected`, `AFFECTED_READERS = {"python": _python_affected}`,
    `AFFECTED_COMMANDS = {"python": "python3 -m unittest"}`.
  - `ccp/mutate.py`: the refusal for a missing `mutate.command` suggests `python3 -m unittest {test}`.
  - `git grep -n unittest -- ccp ':(exclude)ccp/doclang' | wc -l` at `e9ff0fc`: 10 lines (code,
    comments and docstrings in `config.py`, `suite.py`, `mutate.py`).
- Today's behaviour, which this task keeps:
  - `suite affected` picks the reader by `package_docs.language`, `python` when the block is absent
    (`def _language` in `ccp/suite.py`); a pack with no reader uses `suite.affected_map` alone or exits 2.
  - The test-output patterns are unittest's for every product, whatever its language, unless the
    product sets `suite.count_re` / `suite.summary`.
- Decided here:
  - `doclang.Pack` gains `count_re`, `summary` (a dict of `failed_re`, `skipped_re`, `section_re`),
    `test_glob`, `affected` (the reader, or None) and `test_command` (or None). The Python pack fills
    them with today's values; `none` leaves them empty.
  - `doclang.for_tests(cfg)` is the one lookup. In this task it keeps today's behaviour: the reader
    and command follow `package_docs.language` (`python` when the block is absent), and the output
    patterns are the Python pack's for every product. Making the patterns follow the language is
    0182's behaviour change.
  - `config.SUITE_SUMMARY_DEFAULTS`' three pattern keys become `None`, meaning "the pack's"; the schema's
    defaults for them become `null` with that description. The loaded values a reader sees are the
    same.
  - Core code and its comments say "the language pack's patterns" where they said unittest.
  - The E18 check is a `docs.checks` entry in this repo's own `docs/delivery/plane.json`, id
    `language-pack`, command `! git grep -n unittest -- ccp ':(exclude)ccp/doclang'`.
- SPEC: §14.1 and §14.7 already say the defaults read Python unittest and the pack reads the tests;
  they stay true (`git grep -n "unittest" -- docs/spec/02-delivery.md` at `e9ff0fc`: 4 lines, all
  describing what the defaults read). No SPEC change.

## Scope

- **In:**
  - `ccp/doclang/__init__.py`, `ccp/doclang/python.py`, `ccp/doclang/CLAUDE.md`: the fields and
    `for_tests`.
  - `ccp/suite.py`: the constants and `_python_affected` move to the pack; `affected`,
    `main_affected` and the summary and count readers ask `doclang.for_tests(cfg)`.
  - `ccp/config.py`: the three summary defaults `None`; comments reworded.
  - `ccp/mutate.py`: the refusal names the pack's command when the product's language has one, else
    says "a command that runs one test".
  - `contracts/plane_config.schema.json`: the three summary defaults `null`.
  - `docs/delivery/plane.json`: the `language-pack` docs check.
  - `tests/test_doclang_test_facts.py` (new): the Python pack's fields; `for_tests` for a product with
    no `package_docs` block, with `python`, with `none`.
- **Out:**
  - Any behaviour change for a `none` product (0182).
  - A second language pack.

## dod_checks

- id: `lang-01`
  story: As a plane developer, core code names no test runner, and a check keeps it so.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n unittest -- ccp ':(exclude)ccp/doclang'`.
    2. Run `git grep -n unittest -- ccp/doclang/python.py`.
    3. Run `./bin/ccp --root . docs check`.
  expect: step 1 prints nothing; step 2 prints at least one line; step 3 exits 0 and runs the `language-pack` check.
  dry run (`e9ff0fc`): step 1 printed 10 lines (`ccp/config.py` 3, `ccp/mutate.py` 1, `ccp/suite.py` 6); step 2 printed nothing; step 3 `docs: clean` with no `language-pack` check.
- id: `lang-02`
  story: As a plane developer, the Python facts sit in the pack.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -c "from ccp import doclang; p = doclang.get('python'); print(p.count_re, p.test_command, p.test_glob, sorted(p.summary))"`.
    2. Run `git grep -nE 'DEFAULT_COUNT_RE|AFFECTED_READERS|AFFECTED_COMMANDS|TEST_FILE_GLOB' -- ccp`.
  expect: step 1 prints `^Ran (\d+) tests? in  python3 -m unittest test*.py ['failed_re', 'section_re', 'skipped_re']`; step 2 prints nothing.
  dry run (`e9ff0fc`): step 1 raised `AttributeError: 'Pack' object has no attribute 'count_re'`; step 2 printed 11 lines in `ccp/suite.py`.
- id: `lang-03`
  story: As a plane developer, the suite reads and affected lists exactly as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_suite tests.test_suite_affected tests.test_suite_stages tests.test_mutate tests.test_doclang_test_facts`.
    2. Run `./bin/ccp --root . suite affected --paths ccp/doclang/python.py`.
  expect: step 1 exits 0; step 2 lists the modules it lists at the base plus any test module that now imports the pack's new fields, with the part-lane line.
  dry run (`e9ff0fc`): step 2 listed 1 module (`tests.test_doc_rules`); step 1's existing modules pass at the base.
- id: `lang-04`
  story: As a plane developer, the summary reader really takes the pack's patterns.
  setup: a separate copy of the PR head with the Python pack's `failed_re` changed to match nothing (`"^NEVER$"`).
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_suite`.
  expect: exits non-zero, a failure in a test that reads a failing unittest summary.
  dry run: n/a — the pack has no `failed_re` at `e9ff0fc`.

## Implementation notes

*Append-only, newest last.*

- 2026-11-19: Built as written, with these choices the task left open:
  - The pack's reader takes the file list from the core: `affected(root, changed, files)` and a sixth field,
    `suite_size(root, files)`, replace `AFFECTED_READERS` and `AFFECTED_SIZERS`. `ccp/suite.py` lists the
    files once (`_tracked_files`), so the pack imports nothing from `ccp.suite` and the git failure still
    exits 2 from the core. `_py_module`, `_py_imports`, `_read` and the test-file walk moved to
    `ccp/doclang/python.py` with the reader.
  - `for_tests(cfg)` returns the language's pack with the Python pack's `count_re` and `summary` put over
    it (`dataclasses.replace`), so a `none` product has no reader, counter or command and today's output
    patterns.
  - The `affected` refusal for a pack with no reader lists the packs that have one.
  - The schema's three summary keys state `"default": null` and keep their type (a `null` given in
    plane.json is still refused, as before).
  - `tests/test_suite_affected.py` reaches the pack's command and counter through `doclang` instead of
    `suite.AFFECTED_COMMANDS` and `suite._python_suite_size`; no expectation changed.

## Verification notes
- 2026-11-19 — verifier, PR #201 head `50c52b0` (squash `118e337`): APPROVE. Passed: lang-01, lang-02, lang-03, lang-04. Gate: `ccp suite run --lane gate` exit 0, `./bin/ccp --root . tasks check` exit 0, `./bin/ccp --root . docs check` exit 0. Record: verification/0176-language-pack-owns-test-facts.json.

