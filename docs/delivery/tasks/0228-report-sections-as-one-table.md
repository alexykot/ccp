---
task_id: 0228-report-sections-as-one-table
title: The worker report's sections are defined once, and the briefs stop restating the report format
status: pending
kind: refactor
depends_on: []
clashes_with: ["0203-follow-up-fixes", "0221-workers-reach-the-pr-host-through-ccp-pr", "0233-briefs-point-at-the-evidence-rules", "0238-the-runner-runs-marked-checks-before-verify"]
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
- **Clashes.** R14's 0203 changes report parsing in `ccp/report.py` (`resolution_lines`), which
  `parse` walks; 0221, 0233 and 0238 edit the briefs or the prompt templates this task trims.
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
  paragraph go); its text for each phase is what workers get today, in the same places: the rendered
  prompt of every phase is byte for byte today's once run ids, times and temp paths are normalised.
- **The briefs** end with one line: finish as the prompt's last part says; the runner's brief names
  `ccp report` and §13.4 instead of listing what it records.
- **`submit`'s returned fields** derive from `PARSED_KEYS`, `COMPUTED_KEYS` and a short explicit list.
- **Tests:** `tests/test_report_sections.py` (new) renders each phase's prompt and checks its report
  part names every section `SECTIONS` gives that phase; the brief-wording assertions on `## Friction`
  in `tests/test_team_hosting.py` go. Run as `python3 -m tests.test_report_sections --dump <dir> --ccp
  <checkout>/bin/ccp`, the module renders each phase's prompt (implement, fix, merge, ruling, review,
  verify, and verify `--mode resolution`) for one fixture task with that checkout's `ccp`, into
  `<dir>/<phase>.txt`, normalised (run ids, times and temp paths replaced by fixed tokens).

## dod_checks

- id: `rs-01`
  story: As a plane developer, the report's sections have one source.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_report_sections 2>&1 | tail -10`.
  expect: exit 0, one test per phase listed `ok`.
  dry run: n/a — the module is new.

- id: `rs-04`
  story: As a worker, the prompt I am handed reads exactly as before.
  setup: a checkout of the PR head; a checkout of `origin/main` at `<base>` (`git worktree add --detach
    <base> origin/main`).
  steps:
    1. Run `python3 -m tests.test_report_sections --dump <tmp>/a --ccp <base>/bin/ccp`.
    2. Run `python3 -m tests.test_report_sections --dump <tmp>/b --ccp ./bin/ccp`.
    3. Run `diff -r <tmp>/a <tmp>/b; echo rc=$?`.
  expect: steps 1 and 2 exit 0 and write seven files each; step 3 prints only `rc=0`.
  dry run: n/a — the dump helper is new.

- id: `rs-05`
  story: As a plane developer, the section test bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `report.SECTIONS` no longer gives the verify phase its `Friction` entry.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_report_sections`.
  expect: at least one failure, naming the verify phase.
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

- `report.SECTIONS` (a tuple of `Section`: key, name, label, phases, required, secret, keys, stored, reader,
  missing text, prompt line, mode) is read by `report.parse` (via `sections_for`), by `prompt.report_lines`
  (which renders each phase's report part, `runner` filled in) and by `submit` (the secret check; the returned
  fields). `prompt.REPORT_LINES` and `RESOLUTION_LINES` are gone, and so are `_common.md`'s `Prompt:`, `Suite:`
  and `## Friction` lines: the template ends in `{{report_lines}}`.
- `PARSED_KEYS` is derived from the table's `stored` fields (less `outcome` and `friction_count`, set apart in
  `SET_APART`); `submit` returns the record's fields in `RETURNED_KEYS` (set-apart and parsed fields, and
  `suite_runs_recorded`, `suite_s_recorded`, `corrections`). The reply's fields are as before.
- **`COMPUTED_KEYS` is not in the reply.** The task says the returned fields derive from `PARSED_KEYS`,
  `COMPUTED_KEYS` and an explicit list, but the reply today carries neither `integration_merges` nor
  `before_review`; adding them would change `ccp report`'s output in a refactor, so they stay out.
- The seventh dumped prompt is the resolution review (`ccp prompt review --mode resolution`): the task says
  "verify `--mode resolution`", but `--mode` is for `review` only (`prompt.resolution_gate`).
- The dump (`python3 -m tests.test_report_sections --dump <dir> --ccp <checkout>/bin/ccp`) writes
  `implement`, `fix`, `merge`, `ruling`, `review`, `verify` and `resolution` `.txt`. The fixture declares one
  verdict (`report.required_fields`) so the implementer rounds' declared line is dumped too. Times, hashes
  (including the prompt token) and the two paths are replaced by tokens; git dates are pinned.
- `test_report_sections` asserts the prompt names each section the table gives the phase and, from its own
  literal, `Outcome:`, `Prompt:`, `Suite:` and `## Friction` for every phase, so a table that loses one fails.
- `tests/test_team_hosting.py`: the `## Friction` brief assertions go; the runner-brief assertion on the
  recorded lines now checks the brief names `ccp report` and SPEC §13.4. `tests/test_sign_off_beyond_intent.py`
  reads the review prompt's lines through `prompt.report_lines`, as `REPORT_LINES` is gone.
- The briefs end in `Finish as the last part of your prompt says.`; the runner's brief names `ccp report` and
  §13.4 and no longer lists what it records.
- A `Section` for `Affected checks:` has no reader of its own: `resolution_lines` reads it with `Resolution:`
  (one function, which R14's 0203 changes).

## Verification notes
