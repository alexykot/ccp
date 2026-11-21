---
task_id: 0228-report-sections-as-one-table
title: The worker report's sections are defined once, and the briefs stop restating the report format
status: pending
kind: refactor
depends_on: []
clashes_with: ["0221-workers-reach-the-pr-host-through-ccp-pr", "0233-briefs-point-at-the-evidence-rules"]
review_refs: ["sh-20261120T235613Z-4fce#F04", "sh-20261120T235613Z-4fce#F07"]
rule_refs: ["E13", "E12", "E4"]
review_point: R15
paths: ["ccp/report.py", "ccp/prompt.py", "templates/prompts/_common.md", "plugin/agents/delivery-implementer.md", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-runner.md", "tests/test_team_hosting.py", "tests/test_report_sections.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0228-report-sections-as-one-table

## Intent

Adding a section to the worker report (ADR-0044's `## Follow-ups` is next) means editing seven places:
the parser, the prompt's report lines, the common template, three worker briefs and the runner's
brief, and tests pin the briefs' copies. After this task the report's sections are one table in
`ccp/report.py` that both the parser and the rendered prompt read, the briefs say only to finish as
the prompt's last part says, and the run record's returned fields derive from the parser's key lists.
Workers are asked for exactly what they are asked for today.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0044 (`sh-20261120T235613Z-4fce`): F04 (the report format restated in seven
  places) and F07 (the run record's report fields listed in `PARSED_KEYS` and again in `submit`'s
  return dict).
- **The copies.** `ccp/report.py` (`FRICTION_RE`, `BEYOND_RE`, `parse`), `ccp/prompt.py`
  `REPORT_LINES`, `templates/prompts/_common.md` (the `## Friction` paragraph), the closing paragraph
  of `plugin/agents/delivery-implementer.md`, `delivery-reviewer.md` and `delivery-verifier.md`, and
  the runner's brief's account of what `ccp report` records.
- **The pinning tests.** `tests/test_team_hosting.py` asserts the briefs name `` `## Friction` section``
  (`grep -n 'Friction' tests/test_team_hosting.py` at `8aefa59`: four lines).
- A refactor: the rendered prompt's report part says the same; the brief-wording assertions are
  replaced by a test on the rendered prompt (the one expectation change this task names).

## Scope

- **In:** `ccp/report.py`, `ccp/prompt.py`, `templates/prompts/_common.md`,
  `plugin/agents/delivery-implementer.md`, `plugin/agents/delivery-reviewer.md`,
  `plugin/agents/delivery-verifier.md`, `plugin/agents/delivery-runner.md`,
  `tests/test_team_hosting.py`, `tests/test_report_sections.py` (new).
- **`report.SECTIONS`**: one entry per report section or line (heading or prefix, the phases that
  carry it, required or not, secret-checked or not, where it is stored). `parse` walks it; the
  secret check of a friction line becomes the table's flag.
- **The prompt's report part** is rendered from `SECTIONS` (`REPORT_LINES` and `_common.md`'s Friction
  paragraph go); its text for each phase is what workers get today.
- **The briefs** end with one line: finish as the prompt's last part says; the runner's brief names
  `ccp report` and §13.4 instead of listing what it records.
- **`submit`'s returned fields** derive from `PARSED_KEYS`, `COMPUTED_KEYS` and a short explicit list.
- **Tests:** `tests/test_report_sections.py` (new) renders each phase's prompt and checks its report
  part names every section `SECTIONS` gives that phase; the brief-wording assertions on `## Friction`
  in `tests/test_team_hosting.py` go.

## dod_checks

- id: `rs-01`
  story: As a plane developer, the report's sections have one source.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_report_sections 2>&1 | tail -10`.
  expect: exit 0, one test per phase listed `ok`.
  dry run: n/a — the module is new.

- id: `rs-02`
  story: As a worker, my report is checked exactly as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_report_fields tests.test_report_correction tests.test_health_conflicts tests.test_team_hosting 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

- id: `rs-03`
  story: As the plane, the briefs no longer restate the report format.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n '## Friction' -- plugin/agents templates/prompts`.
  expect: prints nothing (the heading is given only by the rendered prompt, from `report.SECTIONS`).
  dry run (`8aefa59`): prints lines in `_common.md` and the three worker briefs.

## Implementation notes

## Verification notes
