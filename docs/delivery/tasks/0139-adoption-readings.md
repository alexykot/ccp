---
task_id: 0139-adoption-readings
title: ccp health reads from the product's adoption onwards, and tasks check's unmeasured-number warning skips stated limits and protocol codes
status: pending
kind: feature
depends_on: []
spec_refs: ["S4", "S5", "S23", "S27"]
review_point: R9
paths: ["ccp/init.py", "ccp/health.py", "ccp/tasklog.py", "scripts/observability/lib.py", "contracts/observability_event.schema.json", "docs/spec/01-model.md", "docs/spec/04-observability.md", "plugin/skills/writing-tasks/SKILL.md", "tests/test_health.py", "tests/test_init.py", "tests/test_tasklog.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0139-adoption-readings
## Intent

The first readings a lead takes after adopting, or re-adopting, a product are about that adoption: `ccp
health` does not present an older queue's figures as current, and `ccp tasks check` does not ask a
brief to measure a rule's own limit or a protocol code.

## Context (not checked)

- **Health after re-adoption.** A re-adopted product keeps its binding and so its old queue (§8.3).
  `ccp health` reads the whole queue and every task merge on the product's history (`"def collect"` in
  `ccp/health.py`, whose only window is `--since`), so tasks done, phase times and cost shares from
  before the adoption read as current. Nothing records when a product was adopted: `ccp init` writes
  the binding and makes the queue directory, and emits no event (`git grep -n 'emit' -- ccp/init.py` at
  `921507e` finds none).
- Ruling: `ccp init` records the adoption as a ledger event, `plane`/`adopted`, which needs no new
  queue file. It records one when it writes the binding, and when the queue it keeps has no such event
  yet (a queue from before this task, the re-adoption case); a rerun on an adopted product records
  nothing, so the mark does not creep forward.
- **The unmeasured-number warning** (`"def unmeasured_numbers"` in `ccp/tasklog.py`; SPEC §5.5's Context
  row) fires on any number on a Context line with no backticked command. Probe at `921507e`, `python3 -c` matching
  `CONTEXT_NUMBER_RE` over three sample lines (a timeout stated "at most" some seconds, an HTTP status,
  an exit code, the lines of check-01): each line yields its number. None of these is a measurement: the
  first is the rule's own limit, the others protocol constants. §5.5 asks for the command beside "a
  count, size, site list or already/never claim"; the regex already leaves out other numbers that are
  not measurements (dates, ids, versions, PR numbers), so leaving these out too needs no SPEC change
  (`git grep -n 'states a number' -- docs/spec/` at `921507e`: the one §5.5 row, which names no form).
  No opt-out marker: a marker would let a real count through.
- `ccp upgrade status` (the third reading the proposals named) is in task 0145, which carries the rule
  change it needs.
- §31.1: the SPEC text below only describes this task's own feature.

## Scope

- **In:**
  - `ccp/init.py`: emits `plane`/`adopted` (actor `operator`, payload `plane`: the plane checkout's
    HEAD, `binding`: `written` or `kept`) when it writes the binding, or when the queue's ledger holds no
    `plane`/`adopted` event.
  - `scripts/observability/lib.py`, `contracts/observability_event.schema.json`: the op `adopted`, its
    required payload keys `plane` and `binding`.
  - `ccp/health.py`: with no `--since`, the window starts at the latest `plane`/`adopted` event, for the
    task merges and for every queue-derived figure; the report (text and `--json`) gives `adopted_at`
    and `before_adoption`, the count of task merges it left out, and the text form says
    "since adoption <at>; N earlier task(s) left out (--since to include them)". `--since` given wins.
    A queue with no such event reads as today.
  - `ccp/tasklog.py`: the warning skips a number right after `at most`, `at least`, `up to`, `no more
    than`, `no less than`, `within` or `under` (any case), and one right after `status`, `status code`,
    `HTTP`, `exit`, `exits` or `exit code`. Every other number on the line is read as today.
  - §31.1: `docs/spec/01-model.md` §4.5, one sentence that init records the adoption event and when;
    `docs/spec/04-observability.md` §27.1, one sentence on health's default window; the `adopted` op in
    the events table where `plane`'s ops are listed. `plugin/skills/writing-tasks/SKILL.md`: the warning's
    line names the two skipped forms.
- **Out:**
  - Moving or deleting the old queue's data (task 0135 archives leftovers; these are owned files).
  - `ccp usage` and the board's windows.

## dod_checks

- id: `health-01`
  story: As a lead who re-adopted a product, health shows only this adoption.
  setup: a fenced scratch product with two task merges, one committed before and one after a `plane`/`adopted` event in its queue's ledger.
  steps:
    1. Run `ccp health --json`.
    2. Run `ccp health --json --since <a date before both merges>`.
  expect: step 1 lists only the later task, with `adopted_at` the event's time and `before_adoption` 1; step 2 lists both.
  dry run: n/a — the event is added by this task.
- id: `init-01`
  story: As an operator, adoption is recorded once.
  setup: a scratch directory `S` that does not exist.
  steps:
    1. Run `ccp sandbox create S`, then, in `S/product`, `CCP_BINDINGS_DIR=S/bindings ccp init` again.
    2. Count the `plane`/`adopted` rows in the sandbox queue's `observability/events.jsonl`.
  expect: one row, its payload `binding: written`.
  dry run: n/a.
- id: `init-02`
  story: As an operator re-adopting on an old queue, the adoption is recorded.
  setup: the sandbox of init-01 with its `adopted` row removed from the ledger.
  steps:
    1. In `S/product`, run `CCP_BINDINGS_DIR=S/bindings ccp init`.
  expect: one `plane`/`adopted` row, its payload `binding: kept`.
  dry run: n/a.
- id: `check-01`
  story: As a task writer, a stated limit or a protocol code is not a measurement.
  setup: a scratch task log with a pending task whose Context has three lines: "a timeout of at most 2 s", "the hook returns HTTP status 400 and exits 2", "there are 14 call sites".
  steps:
    1. Run `ccp tasks check`.
  expect: exit 0; exactly one unmeasured-number warning, on the third line, naming `14`.
  dry run (`921507e`): three warnings, one per line.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-18 (implementer): `ccp init` records `plane`/`adopted` (actor `operator`; payload `plane`, the
  plane checkout's HEAD, empty when it is not a git checkout, and `binding`) after it loads the product's
  config, when the binding was written (a first adoption or `--force`) or the ledger has no such event.
  `health.adopted_at(q)` is the one reader of the event, used by init and health. `ccp health` alone
  applies the window (`collect(..., from_adoption=True)`); the board, architect, estimate and forecast
  callers of `collect` read the whole history as before. Windowed: the task merges (and so the rows,
  trend, small tasks and sign-off wait), the suite series, gate and module time (the judged runs; the
  cache's start is still read from every run), the rotation counts and the friction notes, each at or
  after the event's second. Not windowed: `usage_advice` (`ccp usage`'s advice, Out) and the rotation
  slots due now. `adopted_at` is in the report whenever the queue has the event; `before_adoption` is 0
  when `--since` is given, and the text line prints only when the adoption window applies. With
  `--since`, health reads as before (only the merges windowed). The unmeasured-number warning blanks
  the number right after the listed words, separated by spaces or tabs only, before reading the line.

## Verification notes
