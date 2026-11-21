---
task_id: 0267-mutate-falls-back-to-the-language-pack
title: ccp mutate takes its per-test command and its did-not-build patterns from the language pack unless plane.json overrides them
status: pending
kind: feature
depends_on: []
clashes_with: ["0262-module-docstrings-and-house-rule-checks"]
spec_refs: ["S20", "S14"]
review_refs: ["ar-20261121T174754Z-7df5#F04"]
rule_refs: ["E18"]
review_point: R21
paths: ["ccp/mutate.py", "ccp/doclang/__init__.py", "ccp/doclang/python.py", "ccp/doclang/CLAUDE.md", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "README.md", "docs/ENGINEERING.md", "tests/test_mutate.py", "tests/test_doclang_test_facts.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0267-mutate-falls-back-to-the-language-pack

## Intent

A mutant that stops the code from building or importing is recorded `unbuilt`, never `killed`, in
any product whose language pack knows what such a failure prints, without the product having to
write the pattern into plane.json. A product whose language pack has a per-test runner can run
`ccp mutate` with no `mutate.command`. plane.json still overrides both, as it overrides the pack's
test-output patterns for `ccp suite`.

## Context (not checked)

From architect pass `ar-20261121T174754Z-7df5`, finding F04, and its proposed amendment to house rule
E18 (the record is in `docs/delivery/reviews/`). Measured at `31357f0`.

- **The gap.** `ccp/config.py` `MUTATE_DEFAULTS`: `"unbuilt_re": None`. `docs/delivery/plane.json`
  `mutate`: `{"command": "python3 -B -m unittest -q {test}"}`, no `unbuilt_re`
  (`python3 -B -c "import json;print(json.load(open('docs/delivery/plane.json'))['mutate'])"` at
  `31357f0`). So a mutant with a syntax error counts as killed here (0218's friction note).
  `ccp/mutate.py` `"def _run"` reads the pack's `test_command` only for its refusal message;
  `ccp/suite.py` already falls back to the pack's `count_re`.
- **What unittest prints** (measured at triage in a scratch package, running `python3 -B -m unittest -q tests.test_m.T.test_a`): a module the test imports with a syntax error
  ends with the line `SyntaxError: invalid syntax`; one that fails to import prints
  `ImportError: Failed to import test module: test_m`.
- **Ruling.**
  - `ccp/doclang/__init__.py` `Pack` gains `unbuilt_re: tuple[str, ...] = ()`, the lines that say
    the code did not build or import. The Python pack's: `^(?:SyntaxError|IndentationError|TabError): `
    and `^ImportError: Failed to import test module: `.
  - `ccp mutate` runs plane.json `mutate.command` when set, else the pack's `test_command` followed
    by ` {test}`; with neither (language `none`) it refuses (exit 2) as today, naming
    `mutate.command`, `{test}` and `sh {test}`.
  - Its did-not-build patterns are plane.json `mutate.unbuilt_re` when set (a pattern or a list),
    else the pack's. `MUTATE_DEFAULTS` keeps `None`, read as "unset".
  - The schema's `mutate.command` and `mutate.unbuilt_re` descriptions, `ccp/config.py`'s comment,
    `docs/cli/03-quality.md`'s `ccp mutate` row, the README's `mutate.command` row and
    `ccp/doclang/CLAUDE.md` say the same.
  - This repo's plane.json keeps its own `mutate.command` (it adds `-B -q`).
  - The two tests named in `mu-03` replace `"def test_no_command"` and the pack-command refusal test.
- **E18** (the triage's question to the operator, signed with this brief): its text gains the
  did-not-build line and the per-test command, and says plane.json may override the pack.
- **Tests this breaks** (measured by `git grep -n` at `31357f0`): `tests/test_mutate.py`
  (`"def test_no_command"` deletes `mutate` in a Python product and expects the refusal;
  `"def test_with_no_pattern_the_same_mutant_is_a_kill"`), `tests/test_doclang_test_facts.py`
  (`"def test_the_mutate_refusal_names_the_packs_command_when_the_language_has_one"`).

## Scope

- **In:**
  - `ccp/doclang/__init__.py`, `ccp/doclang/python.py`, `ccp/doclang/CLAUDE.md` (the pack field).
  - `ccp/mutate.py` (`_run`'s command and `_unbuilt_patterns`), `ccp/config.py` (the comment),
    `contracts/plane_config.schema.json` (the two descriptions).
  - `docs/cli/03-quality.md`, `README.md` (the rows named above).
  - `tests/test_mutate.py`, `tests/test_doclang_test_facts.py`.
- **SPEC, signed before the claim (`sign_off: brief`):** `docs/spec/03-quality.md` §20.6, one
  sentence in The product's command and one clause in Killed only when the named test fails.

    CURRENT (`docs/spec/03-quality.md` at `31357f0`), §20.6, The product's command:
    > With no command `ccp mutate` refuses (exit 2).

    PROPOSED:
    > With no command it runs the language pack's per-test runner (§14.1), its test command followed by the test id; with neither, `ccp mutate` refuses (exit 2).

    CURRENT (`docs/spec/03-quality.md` at `31357f0`), §20.6, Killed only when the named test fails:
    > except that one whose run exits non-zero with an output line matching plane.json `mutate.unbuilt_re` (a regular expression or a list of them; null, the default, matches nothing) is `unbuilt`: the code did not build or import, which proves nothing about the test.

    PROPOSED:
    > except that one whose run exits non-zero with an output line matching plane.json `mutate.unbuilt_re` (a regular expression or a list of them; unset, the language pack's did-not-build lines) is `unbuilt`: the code did not build or import, which proves nothing about the test.
- **House rule E18, on the same sign-off:** its rule text, replaced (its `check:` line unchanged).

    CURRENT (`docs/ENGINEERING.md` at `31357f0`), E18:
    > A language's facts (its doc conventions, test-output patterns, test command and import reading) live in its language pack (ccp/doclang). Core code names no language and no test runner.

    PROPOSED:
    > A language's facts (its doc conventions, test-output patterns including the line that says the code did not build or import, the command that runs named tests or one test, and import reading) live in its language pack (ccp/doclang); plane.json may override them. Core code names no language and no test runner.
- **Out:** this repo's plane.json; packs for other languages; `mutate.timeout_seconds`.

## dod_checks

- id: `mu-01`
  story: As a plane developer, the Python pack says which lines mean the code did not build or import.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -c "from ccp import doclang; print(doclang.get('python').unbuilt_re, doclang.get('none').unbuilt_re)"`.
  expect: prints the two Python patterns named in Context, in that order, then `()`.
  dry run (`31357f0`): `AttributeError: 'Pack' object has no attribute 'unbuilt_re'`.
- id: `mu-02`
  story: As a worker in a Python product with no `mutate.unbuilt_re`, a mutant that breaks the syntax is recorded unbuilt, not killed.
  setup: A checkout of the PR head; then a separate copy of it where the Python pack's `unbuilt_re` is `()`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_mutate tests.test_doclang_test_facts`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_mutate`.
  expect: step 1 exits 0, `tests/test_mutate.py` holding a test that records the mutant `calc.py:def add(a, b):=>def add(a, b)` as `unbuilt` with `mutate.unbuilt_re` unset; step 2 exits non-zero.
  dry run (`31357f0`): step 1 exited 0 (`OK`, 59 s); step 2 n/a until the field exists.
- id: `mu-03`
  story: As a worker in a Python product with no `mutate.command`, ccp mutate runs the pack's runner; in a product whose language has none, it still refuses.
  setup: A checkout of the PR head; then a separate copy of it where `_run` ignores the pack's `test_command`.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_mutate tests.test_doclang_test_facts 2>&1 | grep -E 'test_no_command_runs_the_packs_runner|test_a_language_with_no_runner_is_refused'`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_mutate tests.test_doclang_test_facts`.
  expect: step 1 prints two lines, each ending `ok`: `test_no_command_runs_the_packs_runner` (in `tests/test_mutate.py`: a Python product with no `mutate` key kills a mutant through the pack's runner) and `test_a_language_with_no_runner_is_refused` (in `tests/test_doclang_test_facts.py`: a `none`-language product with no `mutate.command` is refused, exit 2, naming `mutate.command`); step 2 exits non-zero.
  dry run (`31357f0`): step 1 n/a — the tests are this task's; step 2 n/a.
- id: `spec-01`
  story: As the operator, §20.6 and E18 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0267`.
  expect: exit 0, the two §20.6 passages found in `docs/spec/03-quality.md` and the E18 passage in `docs/ENGINEERING.md`.
  dry run (simulated: this task file and the three passages applied, committed in a scratch worktree off `31357f0`, `--base` the commit holding the task file): `"ok": true`, exit 0; the two §20.6 passages found in `docs/spec/03-quality.md`, the E18 passage in `docs/ENGINEERING.md`.

## Implementation notes

## Verification notes
