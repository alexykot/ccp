---
task_id: 0223-a-follow-up-is-tracked-not-left-in-notes
title: A worker report states its follow-ups, and the run keeps them for the lead to decide
status: pending
kind: feature
depends_on: ["0228-report-sections-as-one-table", "0230-the-lead-decides-each-follow-up"]
clashes_with: ["0219-integration-merges-leave-out-the-tip", "0233-briefs-point-at-the-evidence-rules"]
spec_refs: ["S11", "S13"]
adr_refs: ["0044 D1"]
review_point: R15
paths: ["ccp/report.py", "ccp/followups.py", "templates/prompts/implement.md", "plugin/agents/delivery-implementer.md", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-runner.md", "docs/spec/02-delivery.md", "docs/adr/0044-a-follow-up-is-tracked-not-left-in.md", "tests/test_report_follow_ups.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0223-a-follow-up-is-tracked-not-left-in-notes

## Intent

A worker that finds work it must not do (a deferred finding, a test gap out of scope, a step for a
later task) has nowhere to put it but a sentence in the task's notes or its report's prose, which
nobody reads once the task closes. After this task every worker report may list such work under
`## Follow-ups`; `ccp report` stores each line on the run with an id the lead decides it by
(`ccp tasks follow-up`, 0230); and the briefs send out-of-scope work, rule text included, there and
nowhere else.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0044 D1, accepted by the operator on 2026-11-20. D2 and D4's list are 0230, D3 is 0231,
  D4's orientation line is 0232.
- **Shaped** by `sh-20261120T235613Z-4fce`:
  - F04 and F07: the section is one more row of 0228's `report.SECTIONS`, and the correction
    carry-over is one function, unit-tested on plain values.
  - F03: the implementer's brief and the implement prompt send rule text the task does not carry to
    `ccp plane propose`, a route ADR-0044 rejects for workers (its Option 3); this task sends it to a
    `## Follow-ups` line (`grep -n 'follow-up proposal' plugin/agents/delivery-implementer.md` at
    `8aefa59`: one line; the prompt says the same). Whether a tool need also moves from Friction to
    Follow-ups is the operator's question; this brief leaves Friction as it is.
  - F05: §11.1 is already wrong about the run record: it lists a phase `pr` the code does not have
    (`ccp/runs.py` `PHASES`), gives the report path without its `-report` suffix (`runs.report_path`),
    and cites `contracts/run.schema.json`, which does not exist (`ls contracts/run.schema.json` at
    `8aefa59`: no such file). The PROPOSED text corrects all three, dropping the citation: §11.1's list
    and the code's key lists are the record's field list.
  - F02 (house rule E5, records hold numbers and ids only) is the operator's: storing the follow-up's
    text on the run needs E5 amended to allow a worker's short statement lines, secret-checked and
    never sent to telemetry. This brief is written on that recommended answer; if the operator keeps
    E5, the text moves to a store beside `health/notes.jsonl` and the brief is revised and signed
    again.
- **Corrections** (§13.4) replace a run's parsed fields; follow-ups keep an outcome for an identical
  line.
- No R14 task edits these passages; 0219 edits the §11.1 sentence after the record list (adjacent
  lines, hence the clash).

## Scope

- **In:** `ccp/report.py`, `ccp/followups.py`, `templates/prompts/implement.md`,
  `plugin/agents/delivery-implementer.md`, `plugin/agents/delivery-reviewer.md`,
  `plugin/agents/delivery-verifier.md`, `plugin/agents/delivery-runner.md`,
  `docs/spec/02-delivery.md`, `docs/adr/0044-a-follow-up-is-tracked-not-left-in.md`,
  `tests/test_report_follow_ups.py` (new).
- **The section.** `report.SECTIONS` gains `## Follow-ups` for every phase: `- ` lines or the single
  line `none`, missing reads as `none`, secret-checked. `ccp report` refuses (exit 1, nothing written)
  a line that is neither, or one that looks like a secret. The run record gains `follow_ups:
  [{"id": "<run_id>#<n>", "text", "outcome": null}]`, `n` from 1.
- **A correction** replaces the list and renumbers it; `followups.carry(old, new)` keeps an outcome
  for a line whose text is identical, and `ccp report` names each outcome it drops on stderr.
- **The routes.** The implementer's brief and the implement prompt send rule text the task does not
  carry to a `## Follow-ups` line; the reviewer's and verifier's briefs say out-of-scope work goes
  there, never only in notes; the runner's brief tells the lead when a report carries follow-ups.
- ADR-0044 D1 recorded `built`.
- **Tests** in `tests/test_report_follow_ups.py` (new): two follow-ups stored with ids; a malformed and
  a secret-like line refused; `carry` keeping an identical line's outcome and dropping the other's.

### SPEC changes (signed in the brief, §31)

**a. §13.1, the worker's follow-up rule.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> never edit a task's checks and never create a task: a follow-up a worker finds goes to the lead.

PROPOSED:
> never edit a task's checks and never create a task: a follow-up a worker finds goes to the lead,
> as a line of its report's `## Follow-ups` (§13.4), never only in notes or prose.

**b. §13.4, the report lines.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> - `## Friction` as `- ` (or `* `) lines, or `none`;

PROPOSED:
> - `## Friction` as `- ` (or `* `) lines, or `none`;
> - `## Follow-ups`, in any worker report, as `- ` lines, or `none` (missing reads as `none`): a line
>   that is neither, or one that looks like a secret, is refused (exit 1, nothing written). The run
>   keeps them as `follow_ups`, each with the id `<run_id>#<n>`; a corrected report renumbers them,
>   an outcome carrying over only to a line whose text is identical, and `ccp report` names each one
>   it drops. The lead alone records each one's outcome, with `ccp tasks follow-up <run_id>#<n>
>   --task <id> | --proposal <id> | --drop "<reason>"`, and `ccp tasks follow-ups [--open]` lists them;

**c. §13.4, the report's path.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> A worker submits its report with `ccp report <run_id> FILE`, which checks its shape, stores it at the
> run's report path (`progress/<task_id>/<phase>[-<n>].md`), closes the run, and records the suite

PROPOSED:
> A worker submits its report with `ccp report <run_id> FILE`, which checks its shape, stores it at the
> run's report path (`progress/<task_id>/<phase>[-<n>]-report.md`), closes the run, and records the suite

**d. §11.1, the run's id.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> - **Id:** `<task_id>/<phase>[-<n>]`, phase `implement`, `pr`, `review`, `fix`, `verify`, `merge` or `ruling`,
>   the same name as its report file `progress/<task_id>/<phase>[-<n>].md`. Runs outside a task:

PROPOSED:
> - **Id:** `<task_id>/<phase>[-<n>]`, phase `implement`, `fix`, `merge`, `ruling`, `review` or `verify`,
>   the same name as its report file `progress/<task_id>/<phase>[-<n>]-report.md`. Runs outside a task:

**e. §11.1, the record's contract.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> - **Record:** `QUEUE_ROOT/runs/<task_id>/<phase>[-<n>].json` (`contracts/run.schema.json`):

PROPOSED:
> - **Record:** `QUEUE_ROOT/runs/<task_id>/<phase>[-<n>].json`, with these fields:

**f. §11.1, the record's fields.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
>   `observed_efforts`, `integration_merges` and `before_review` (a done implement, fix, merge or ruling
>   round with a head).

PROPOSED:
>   `observed_efforts`, `integration_merges` and `before_review` (a done implement, fix, merge or ruling
>   round with a head), and `follow_ups` (the report's lines, each with its id and the lead's
>   `outcome`, §13.4).

- **Out:** the commands (0230), the review-point check (0231), the orientation line (0232), a
  `contracts/run.schema.json`, follow-ups the lead or the architect finds, and §15.8's code-only merge.

## dod_checks

- id: `fu-01`
  story: As a lead, every follow-up a worker states is stored with an id I can decide it by.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_report_follow_ups 2>&1 | tail -15`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `fu-02`
  story: As a plane developer, the correction carry-over is tested and the test bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `followups.carry` keeps every old outcome.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_report_follow_ups`.
  expect: at least one failure (the dropped outcome).
  dry run: n/a — the module is new.

- id: `fu-03`
  story: As a worker, reports without the section are checked as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_report_fields tests.test_report_correction 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

- id: `fu-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0223 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`8aefa59`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
