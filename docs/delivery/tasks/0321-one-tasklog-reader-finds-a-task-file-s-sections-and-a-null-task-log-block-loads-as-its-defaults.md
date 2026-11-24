---
task_id: 0321-one-tasklog-reader-finds-a-task-file-s-sections-and-a-null-task-log-block-loads-as-its-defaults
title: One public tasklog reader finds a task file's sections, close and the estimator call it and E22 checks it; the Context number scan blanks fences through unfence; a null task_log block loads as its defaults and an absolute or .. task_log.dir is refused at load
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S8", "S20"]
rule_refs: ["E22"]
review_refs: ["ar-20261124T034246Z-e089#F03"]
review_point: R33
paths: ["ccp/tasklog.py", "ccp/estimate.py", "ccp/lifecycle.py", "ccp/parallel.py", "ccp/plan.py", "ccp/config.py", "tests/test_section_readers_fences.py", "tests/test_task_format.py", "tests/test_tasks_migrate.py", "tests/test_plane_config_defaults.py", "docs/ENGINEERING.md", "docs/delivery/plane.json"]
clashes_with: ["0191-the-grace-release-ends"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0321-one-tasklog-reader-finds-a-task-file-s-sections-and-a-null-task-log-block-loads-as-its-defaults

## Intent

A task file's sections are found in one place. `ccp/tasklog.py` offers one public reader of a section's span and
body, outside fenced blocks, with the section's older names and a heading line that ends in a carriage return;
`ccp tasks close` and the estimator call it instead of their own heading searches, and the modules that read a
section through tasklog's private helper call the public one. House rule E22 says so and its check refuses another
heading search, so a later fix to the grammar is one change, not two tasks. The Context number scan blanks fenced
blocks through the same `unfence` helper. A plane.json whose `task_log` is `null` loads as the defaults, as every
other block does, instead of an `AttributeError`; a `task_log.dir` that is absolute or climbs out with `..` is
refused at load, as `task_log.reviews_dir` already is.

## Context (not checked)

Finding F03 of architect pass `ar-20261124T034246Z-e089` (`docs/delivery/reviews/ar-20261124T034246Z-e089.md`), whose
E22 amendment (accepted by that triage) this task lands: E22's text and its check together. It also covers these open
follow-ups (`QUEUE_ROOT=<queue> ccp --root . tasks follow-ups --open`):

- `0313-…/implement#1`, `/review#1`, `/verify#1`: `tasklog.unmeasured_numbers` blanks its Context body with
  `FENCE_RE.sub(_blank, body)`, a second spelling of `unfence`.
- `0315-…/review#1`, `/verify#1`: `"task_log": null` crashes at load in `_toolkit` (`ccp/config.py`).
- `0315-…/implement#1`: `task_log.dir` refuses only a value that is not a non-empty string; an absolute or `..` path
  still loads, while `task_log.reviews_dir` refuses both.

Measured at `9691fd9c` (origin/main after 0317's reconcile):

- **The heading searches.** `git grep -nE 'search\(rf"\^## ' -- ccp scripts` at `9691fd9c`: 3 lines,
  `ccp/tasklog.py` (`"def _section_at"`, which honours `SECTION_ALIASES`), `ccp/estimate.py` (`"def strip_notes"`)
  and `ccp/lifecycle.py` (the notes edit of `ccp tasks close`, which alone accepts a heading line ending in `\r`,
  through `(?=\r?$)`). `git grep -n 'tasklog._section(' -- ccp` at `9691fd9c`: 3 lines, `ccp/estimate.py`,
  `ccp/parallel.py` and `ccp/plan.py`. 0304 fixed fenced headings in tasklog and 0313 had to fix close and the
  estimator.
- **E22's check today** (`architect.checks` `E22` in `docs/delivery/plane.json`):
  `! git grep -n CHECK_RE -- ccp ':(exclude)ccp/tasklog.py'`.
- **The second spelling.** `git grep -c 'FENCE_RE.sub' -- ccp/tasklog.py` at `9691fd9c`: `ccp/tasklog.py:2`, `"def
  unfence"` itself and `"def unmeasured_numbers"`.
- **The null block.** A scratch git product with an empty `docs/delivery/tasks/` and plane.json
  `{"project_id": "p", "language": "python", "suite": {"lanes": {"gate": ["true"]}}, "task_log": null}`:
  `CCP_DEV=1 ./bin/ccp --root <product> tasks index` printed a traceback ending
  `AttributeError: 'NoneType' object has no attribute 'get'`, exit 1, and `tasks check` the same. The same product
  without the `task_log` key printed `wrote docs/delivery/INDEX.yaml`, then `tasks: clean (0 tasks)`, both exit 0.
  `"def _merge"` in `ccp/config.py` returns the defaults for a block given as `null`; `"def _toolkit"` reads
  `raw.get("task_log", {})` five times, which a `null` breaks.
- **The dir.** The same product with `"task_log": {"dir": "/tmp/x"}`, then `{"dir": "../x"}`: `tasks check` named
  `/tmp/x/tasks: missing` (then `../x/tasks: missing`) with the §29.3 constant warning, exit 1. `task_log.reviews_dir`
  is refused at load when it starts with `/` or has a `..` part (`"def _toolkit"`). No bound product's plane.json sets
  `task_log.dir` (read from each binding's product on this machine).
- **Ruled.**
  - `ccp/tasklog.py` gains `section_span(text, name) -> tuple[int, int, int] | None`: the offsets in `text` of the
    heading line's start, the body's start (right after the heading's name and trailing blanks, before any `\r`, as
    close's search gives it now) and the body's end (the next `## ` heading outside a fence, else the end); `None`
    when the heading is absent. A heading matches `^## <name>[ \t]*(?=\r?$)` in `unfence(text)`, for the name or an
    older name in `SECTION_ALIASES`. `section(text, name) -> str | None` returns the body. `_section_at` and `_section`
    go; every caller in `ccp/` and `tests/` calls `section` or `section_span`.
  - `"def strip_notes"` (`ccp/estimate.py`) and close's notes edit (`ccp/lifecycle.py`) call `section_span`.
    `task_hash` is unchanged for every task file: the notes sections have no older names, and `task_hash` already
    turns CRLF into LF before `strip_notes`.
  - `"def unmeasured_numbers"` blanks with `unfence(body)`.
  - The test is `test_every_reader_finds_a_heading_line_ending_in_cr` in `tests/test_section_readers_fences.py`
    (class `SectionReadersFences`): on a CRLF task text, `tasklog.section` finds `dod_checks`, `estimate.strip_notes`
    drops `## Implementation notes`, and the existing close tests still pass.
  - `"def _toolkit"` reads the block once as `raw.get("task_log") or {}`; a `null` block then loads as the defaults.
    A `task_log.dir` that starts with `/` or has a `..` part (`Path(td).parts`) is refused with the message it has
    now, `task_log.dir must be a path relative to the product root; delete the key to take the constant`. The tests
    are `test_a_null_task_log_block_loads_as_the_defaults` and
    `test_an_absolute_or_parent_task_log_dir_is_refused_at_load` in `tests/test_plane_config_defaults.py` (class
    `PlaneConfigDefaults`).
  - **E22** (`docs/ENGINEERING.md`, line-neutral: the doc is at 150 lines, its cap) becomes:

    > - **E22** One parser per durable grammar: one tasklog function finds a task file's sections, one splits its
    >   dod_checks; no other module matches a task file's `## ` heading or `CHECK_RE`, or re-splits a section.
    >   check: command — architect.checks `E22`

    and `architect.checks` `E22`'s cmd becomes
    `! git grep -n CHECK_RE -- ccp ':(exclude)ccp/tasklog.py' && ! git grep -nE 'search\(rf"\^## |tasklog\._section' -- ccp scripts ':(exclude)ccp/tasklog.py'`.
- **No SPEC change.** `git grep -n 'task_log.dir' -- docs/spec` at `9691fd9c`: no line; §8.1 already refuses a
  plane.json that does not validate, and the message is the one 0315 ruled. `git grep -n -i 'CRLF' -- docs/spec` at
  `9691fd9c`: 2 lines, both on the review-point stamp, none on section headings.

## Scope

- **In:** `ccp/tasklog.py` (`section_span`, `section`, `unmeasured_numbers`, every internal caller);
  `ccp/estimate.py` (`strip_notes`, the dod_checks read); `ccp/lifecycle.py` (close's notes edit); `ccp/parallel.py`;
  `ccp/plan.py`; `ccp/config.py` (`_toolkit`); `tests/test_section_readers_fences.py`; `tests/test_task_format.py`
  and `tests/test_tasks_migrate.py` (their `tasklog._section` calls); `tests/test_plane_config_defaults.py`;
  `docs/ENGINEERING.md` (E22, the text above); `docs/delivery/plane.json` (`architect.checks` `E22`).
- No SPEC change (Context, *No SPEC change*).
- **Out:** the dod_check reader (`CHECK_RE`, `checks`); the fence grammar (`FENCE_RE`); other house rules.

## dod_checks

- id: `code-01`
  story: As a plane developer, a task file's sections are found by one tasklog function and E22's check refuses another heading search.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nE 'search\(rf"\^## |tasklog\._section' -- ccp scripts ':(exclude)ccp/tasklog.py'`.
    2. Run `python3 -B -c 'import json; print([x["cmd"] for x in json.load(open("docs/delivery/plane.json"))["architect"]["checks"] if x["id"] == "E22"][0].count("git grep"))'`.
    3. Run `CCP_DEV=1 ./bin/ccp docs check --only E22; echo "exit $?"`.
  expect: step 1 prints nothing (exit 1); step 2 prints `2`; step 3's last line is `exit 0`.
  dry run (`9691fd9c`): step 1 printed 5 lines (`ccp/estimate.py` ×2, `ccp/lifecycle.py`, `ccp/parallel.py`, `ccp/plan.py`); step 2 printed `1`; step 3 printed `docs: clean: E22 only`, `exit 0`.
- id: `code-02`
  story: As a plane developer, every reader finds a heading line that ends in a carriage return, and the section tests still pass.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_section_readers_fences.SectionReadersFences.test_every_reader_finds_a_heading_line_ending_in_cr`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_section_readers_fences tests.test_task_format tests.test_tasks_migrate tests.test_tasks_close`.
  expect: both exit 0.
  dry run: n/a — the test is new.
- id: `code-03`
  story: As a plane developer, the Context number scan blanks fences through unfence, not a second spelling.
  setup: As `code-01`.
  steps:
    1. Run `git grep -c 'FENCE_RE.sub' -- ccp/tasklog.py`.
  expect: prints `ccp/tasklog.py:1` (only `unfence` itself).
  dry run (`9691fd9c`): printed `ccp/tasklog.py:2`.
- id: `cmd-01`
  story: As a product owner, a plane.json whose task_log is null loads as the defaults.
  setup: A checkout of the PR head at `<checkout>` (any seat). A scratch git repo `<product>` outside it (`git init`) holding an empty directory `docs/delivery/tasks/` and `docs/delivery/plane.json` = `{"project_id": "p", "language": "python", "suite": {"lanes": {"gate": ["true"]}}, "task_log": null}`, and a scratch `QUEUE_ROOT`.
  steps:
    1. Run `CCP_DEV=1 <checkout>/bin/ccp --root <product> tasks index; echo "exit $?"`.
    2. Run `CCP_DEV=1 <checkout>/bin/ccp --root <product> tasks check; echo "exit $?"`.
  expect: no line holds `Traceback`; step 1's last line is `exit 0`; step 2 prints `tasks: clean (0 tasks)` and its last line is `exit 0`.
  dry run (`9691fd9c`): each step printed a traceback ending `AttributeError: 'NoneType' object has no attribute 'get'`, then `exit 1`.
- id: `cmd-02`
  story: As a product owner, a task_log.dir outside the product is refused by name at load.
  setup: As `cmd-01`, with `"task_log": {"dir": "/tmp/x"}` in `<product>`'s plane.json, and a second product `<product2>` the same with `"task_log": {"dir": "../x"}`.
  steps:
    1. Run `CCP_DEV=1 <checkout>/bin/ccp --root <product> tasks check; echo "exit $?"`.
    2. Run `CCP_DEV=1 <checkout>/bin/ccp --root <product2> tasks check; echo "exit $?"`.
  expect: each step's output holds `task_log.dir must be a path relative to the product root` and its last line is `exit 2`.
  dry run (`9691fd9c`): step 1 printed `/tmp/x/tasks: missing — the task log lives here` and the §29.3 constant warning, `exit 1`; step 2 the same for `../x`, `exit 1`.

## Implementation notes

## Verification notes
