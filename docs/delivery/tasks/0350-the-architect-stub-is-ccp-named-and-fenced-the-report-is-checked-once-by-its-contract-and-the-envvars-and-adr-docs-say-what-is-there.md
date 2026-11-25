---
task_id: 0350-the-architect-stub-is-ccp-named-and-fenced-the-report-is-checked-once-by-its-contract-and-the-envvars-and-adr-docs-say-what-is-there
title: The architect's claude override is CCP_ARCHITECT_CLAUDE_BIN, fenced in the tests like the estimator's; ccp architect checks a report's shape only through its contract, as §19.7 item 3 says (§31.1); envvars.py drops for_child and says what envvar does; the architect design note and docs/adr/README.md describe what is there
status: done
kind: feature
depends_on: []
spec_refs: ["S6", "S19"]
rule_refs: ["E12"]
review_refs: ["ar-20261125T184522Z-c248#F07", "ar-20261125T184522Z-c248#F08", "ar-20261125T184522Z-c248#F09", "ar-20261125T184522Z-c248#F10"]
review_point: R38
paths: ["ccp/architect.py", "ccp/envvars.py", "ccp/CLAUDE.md", "ccp/baseline.py", "ccp/lifecycle.py", "ccp/notify.py", "ccp/prhost.py", "ccp/suite.py", "ccp/wt.py", "docs/spec/03-quality.md", "docs/design/architect.md", "docs/adr/README.md", "contracts/architect_report.schema.json", "tests/__init__.py", "tests/architect_fixture.py", "tests/test_architect.py", "tests/test_architect_triage_schema.py"]
clashes_with: ["0191-the-grace-release-ends", "0347-a-cold-suite-run-takes-the-exclusive-lock-mutate-names-the-lines-of-an-ambiguous-mutant-and-spec-text-says-what-it-read"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0350-the-architect-stub-is-ccp-named-and-fenced-the-report-is-checked-once-by-its-contract-and-the-envvars-and-adr-docs-say-what-is-there

## Intent

A test that forgets the architect's stub fails instead of launching a real `claude -p`, and the override is named
like every other plane variable. A malformed architect report is refused once, by its contract, and §19.7 says so.
A maintainer reading `ccp/envvars.py`, `ccp/CLAUDE.md`, the architect design note or the ADR directory's README
reads what is there now, with the `ccp` command names.

## Context (not checked)

Findings F07, F08, F09 and F10 of architect pass `ar-20261125T184522Z-c248`
(`docs/delivery/reviews/ar-20261125T184522Z-c248.md`), and two follow-ups of 0345 the lead passed to that pass:
§19.7 item 3 should say the driver refuses what `contracts/architect_report.schema.json` refuses (a §31.1
description of 0345's feature), and `architect.validate`'s hand checks of action, check, metrics and shape
duplicate the contract (E12), with `tests/test_architect.py`'s pinned message moving; validating the report as
written is accepted.

Measured at `05cb00e2`:

- **F07.** `"argv += [os.environ.get(\"DA_CLAUDE_BIN\") or \"claude\""` (`ccp/architect.py`, `"def _run_one"`); `git grep -n 'DA_CLAUDE_BIN\|DA_STUB_' -- ccp tests docs/design`: 16 lines
  (`ccp/architect.py` 1, `docs/design/architect.md` 2, `tests/architect_fixture.py` 10, `tests/test_architect.py`
  3, its docstring included). `tests/__init__.py` fences `CCP_ESTIMATOR_CLAUDE_BIN` and not the architect's
  variable. `tests/test_review_aliases_retired.py`'s `DA_ID` is a docs-audit review id, not a variable, and stays.
- **validate.** `"def validate(report: Any, rid: str, pid: str, mode: str"` (`ccp/architect.py`) runs
  `ar.validate_report` on the report as written, then checks by hand that `rule_changes` is a list of objects, each
  `action` one of `RULE_ACTIONS` and each `check` non-blank, `metrics` an object, and a shape report's `shape` an
  object of lists. The contract holds each of these (`rule_changes.items.required` with `check` at `minLength: 1`,
  `action`'s enum, `metrics` type object, the `shape` properties, and its `if mode shape then required adr, shape`),
  so a report missing a check gets both `rule_changes[0]: names no check` and `report.rule_changes[0]: missing
  check`. `grep -c -e 'names no check' -e 'metrics is not an object' -e 'shape report carries' ccp/architect.py`: 3.
  `tests.test_architect.RuleChangesAndShape.test_rule_changes_are_validated_and_disposed` pins `rule_changes[0]:
  names no check`.
- **F08.** `"def for_child(variables: dict) -> dict"` returns `dict(variables)`; `git grep -c for_child -- ccp`:
  `ccp/baseline.py:2`, `ccp/envvars.py:2`, `ccp/lifecycle.py:2`, `ccp/notify.py:2`, `ccp/prhost.py:2`,
  `ccp/suite.py:5`, `ccp/wt.py:3` (each module's import and calls). `grep -c 'one place' ccp/envvars.py
  ccp/CLAUDE.md`: 1 and 1, both claiming the naming has one place, which 57 `CCP_*` literals in 15 modules belie.
- **F09.** `grep -c 'cpl ' docs/adr/README.md`: 5, its command list, which `docs/cli/01-model.md` gives as `ccp adr …`
  rows (E25).
- **F10.** `grep -cw Kind docs/design/architect.md`: 1 (the "One review kit" bullet); 0345 replaced `Kind` with
  module constants in `ccp/architecture_review.py` (`EVENT`, `PREFIXES`, `STATE`, `LOCK`, `LENSES`).

**Ruled.**

- **F07.** `ccp/architect.py` reads `envvar("CCP_ARCHITECT_CLAUDE_BIN") or "claude"` (`ccp.envvars`).
  `tests/__init__.py` sets `os.environ["CCP_ARCHITECT_CLAUDE_BIN"] = "/nonexistent/claude-architect-guard"`
  beside the estimator's line. The test stub's variables become `CCP_ARCHITECT_STUB_REPORT`,
  `CCP_ARCHITECT_STUB_LINK` and `CCP_ARCHITECT_STUB_WATCH` (`tests/architect_fixture.py`,
  `tests/test_architect.py`, its docstring included).
- **validate.** `architect.validate` keeps `ar.validate_report` on the report as written and its own comparisons of
  the model's `review_id`, `mode` and `lenses` with the run's (the report as written overwrites them, so the
  contract never sees the model's); the hand checks of `rule_changes`, `metrics` and `shape` go. The hand check's
  refusal of a blank `check` moves to the contract: `contracts/architect_report.schema.json`'s
  `rule_changes.items.properties.check` gains `"pattern": "\\S"` beside its `minLength: 1`, so §19.7 item 3's
  "every `rule_changes` entry names … a check" still refuses a `check` of only spaces. In
  `test_rule_changes_are_validated_and_disposed`, `rule_changes[0]: names no check` becomes `rule_changes[0]:
  missing check`. New test
  `tests.test_architect_triage_schema.ReportContract.test_a_malformed_rule_change_metrics_or_shape_is_refused_once_by_the_contract`:
  a shape report whose rule change has action `x` and no check, whose `metrics` is `3` and whose `shape.hot_spots`
  is `1` gets exactly one error naming `rule_changes[0]` and `check`, one naming `rule_changes[0].action`, one naming
  `metrics` and one naming `shape.hot_spots`; and a report whose one rule change has a `check` of three spaces gets
  exactly one error, naming `rule_changes[0].check`.
- **F08.** `for_child` goes; each caller passes its dict as it is (`{COLD_VAR: "1"}` in place of
  `for_child({COLD_VAR: "1"})`), and the imports drop the name. `ccp/envvars.py`'s docstring becomes "The plane's
  environment variables are named `CCP_*` (ADR-0036 D3). `envvar` reads one, an empty value counting as unset, as
  the shell scripts' `${CCP_X:-default}` does." In `ccp/CLAUDE.md`, "`envvars.py` (the plane's `CCP_*` environment
  variables, read and set in one place)" becomes "`envvars.py` (`envvar`, which reads a `CCP_*` environment
  variable, empty counting as unset)".
- **F09.** `docs/adr/README.md`'s five command bullets become one line: "The commands are `ccp adr …`
  (`docs/cli/01-model.md`), the rules SPEC §6; `adr.strict` is on here."
- **F10.** `docs/design/architect.md`'s first bullet becomes "- **One review kit.** `ccp/architecture_review.py`
  holds the architect's state file, lock, id prefixes, event type and lenses as module constants (`STATE`, `LOCK`,
  `PREFIXES`, `EVENT`, `LENSES`), with the lock, report and triage validation, rendering and triage hand-off; the
  architect (`ccp/architect.py`) is the seat it serves." Its two `DA_CLAUDE_BIN` mentions read
  `CCP_ARCHITECT_CLAUDE_BIN`.
- No other test expectation changes.

## Scope

- **In:** `ccp/architect.py` (the launch line and `validate`); `ccp/envvars.py`; `ccp/CLAUDE.md` (the one entry);
  `ccp/baseline.py`, `ccp/lifecycle.py`, `ccp/notify.py`, `ccp/prhost.py`, `ccp/suite.py`, `ccp/wt.py` (the
  `for_child` calls and imports only); `docs/design/architect.md`; `docs/adr/README.md`; `contracts/architect_report.schema.json` (the `check`
  pattern only); `tests/__init__.py`; `tests/architect_fixture.py`; `tests/test_architect.py`; `tests/test_architect_triage_schema.py`; the SPEC, a
  description of 0345's accepted feature (§31.1), no sign-off:

  CURRENT (`docs/spec/03-quality.md` at `05cb00e2`), §19.7 item 3:
  > 3. **Result.** The architect's final message is one JSON report. The driver refuses it unless the required fields are present, the findings are within the mode's cap,

  PROPOSED:
  > 3. **Result.** The architect's final message is one JSON report. The driver refuses it unless the
  > report as written (the model's object with the fields the plane sets) holds to its contract,
  > `contracts/architect_report.schema.json`, the findings are within the mode's cap,

  Retired: "the required fields are present".
- **Out:** the other `CCP_*` literals (no registry of names); `contracts/`; `tests/test_review_aliases_retired.py`.

## dod_checks

- id: `code-01`
  story: As a maintainer, the architect's claude override is a CCP_* name and the tests fence it.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n 'DA_CLAUDE_BIN\|DA_STUB_' -- ccp tests docs/design`.
    2. Run `grep -c 'CCP_ARCHITECT_CLAUDE_BIN' tests/__init__.py`.
  expect: step 1 prints nothing (git grep's exit 1); step 2 prints `1`.
  dry run (`05cb00e2`): step 1 printed 16 lines; step 2 printed `0` (exit 1).
- id: `code-02`
  story: As the plane, a malformed architect report is refused once, by its contract.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_architect_triage_schema.ReportContract.test_a_malformed_rule_change_metrics_or_shape_is_refused_once_by_the_contract tests.test_architect.RuleChangesAndShape.test_rule_changes_are_validated_and_disposed tests.test_architect_triage_schema`.
  expect: exit 0.
  dry run (`05cb00e2`): exit 1 (`AttributeError: type object 'ReportContract' has no attribute 'test_a_malformed_rule_change_metrics_or_shape_is_refused_once_by_the_contract'`).
- id: `spec-01`
  story: As a reader of §19.7, item 3 says the report is held to its contract.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0350`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`05cb00e2`, with this brief): exit 1, the PROPOSED passage not found.
- id: `code-03`
  story: As a maintainer, envvars.py has no pass-through helper and its docs say what envvar does.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n for_child -- ccp`.
    2. Run `grep -c 'one place' ccp/envvars.py ccp/CLAUDE.md`.
  expect: step 1 prints nothing (git grep's exit 1); step 2 prints `ccp/envvars.py:0` and `ccp/CLAUDE.md:0` (grep's exit 1).
  dry run (`05cb00e2`): step 1 printed 18 lines; step 2 printed `ccp/envvars.py:1` and `ccp/CLAUDE.md:1`.
- id: `doc-01`
  story: As a maintainer, the ADR directory's README points at the ccp commands instead of listing cpl ones.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'cpl ' docs/adr/README.md`.
    2. Run `grep -c 'docs/cli/01-model.md' docs/adr/README.md`.
  expect: step 1 prints `0` (grep's exit 1); step 2 prints `1`.
  dry run (`05cb00e2`): step 1 printed `5`; step 2 printed `0` (exit 1).
- id: `doc-02`
  story: As a maintainer, the architect design note describes the kit without the Kind 0345 removed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -cw Kind docs/design/architect.md`.
  expect: prints `0` (grep's exit 1).
  dry run (`05cb00e2`): printed `1`.

## Implementation notes

- Premises re-measured at `248a2b14` (one commit, 0347, since `05cb00e2`): the 16 `DA_*` lines, the 18 `for_child` lines, the five `cpl ` lines and the one `Kind` hold as the Context states.
- `ccp/architect.py`: the launch line reads `envvar("CCP_ARCHITECT_CLAUDE_BIN") or "claude"`; `validate` keeps `ar.validate_report` and the comparisons of the model's `review_id`, `mode` and `lenses`, and loses the hand checks of `rule_changes`, `metrics` and `shape`. `RULE_ACTIONS`, which only those checks used, is removed with them (the contract's enum holds the actions).
- `contracts/architect_report.schema.json`: `rule_changes.items.properties.check` gains `"pattern": "\\S"`.
- `for_child` is removed from `ccp/envvars.py` and its six callers; `ccp/envvars.py`, `ccp/CLAUDE.md`, `docs/adr/README.md` and `docs/design/architect.md` carry the ruled text; the SPEC §19.7 item 3 carries the PROPOSED passage (§31.1).
- Tests: `tests/__init__.py` fences `CCP_ARCHITECT_CLAUDE_BIN`; the stub's variables are `CCP_ARCHITECT_STUB_*`; the pinned message in `test_rule_changes_are_validated_and_disposed` is `rule_changes[0]: missing check`; the new contract test is in `tests/test_architect_triage_schema.py`.

## Verification notes
- 2026-11-25 — verifier, PR #428 head `71c1469` (squash `18bb4d0`): APPROVE. Passed: code-01, code-02, spec-01, code-03, doc-01, doc-02. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0350-the-architect-stub-is-ccp-named-and-fenced-the-report-is-checked-once-by-its-contract-and-the-envvars-and-adr-docs-say-what-is-there.json.

