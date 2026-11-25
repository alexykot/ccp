---
task_id: 0349-tests-stop-asserting-a-retired-name-is-absent-and-pin-the-run-clock-and-the-docs-sync-refusal
title: Tests stop asserting that a retired command's name is absent (0342's seven assertions, and the docs-audit command test), keeping the behaviour they also pin; the run clock's shared stamps and its start, and the docs sync's refusal of a project with no binding, are tested; tests/helpers.py's imports are in order
status: pending
kind: feature
depends_on: []
spec_refs: ["S8", "S21"]
rule_refs: ["E4"]
review_refs: ["ar-20261125T184522Z-c248#F06"]
review_point: R38
paths: ["tests/test_init.py", "tests/test_tasklog.py", "tests/test_review_aliases_retired.py", "tests/test_run_clock.py", "tests/test_binding_by_id.py", "tests/helpers.py"]
clashes_with: ["0191-the-grace-release-ends"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0349-tests-stop-asserting-a-retired-name-is-absent-and-pin-the-run-clock-and-the-docs-sync-refusal

## Intent

A maintainer who retires a command deletes its tests and finds no test that pins its name's absence, so the next
retirement does not copy that pattern (house rule E4, amended by this triage). The tests' shared run clock and the
docs sync's refusal of an unbound project are held by tests of their own, and the helpers module reads cleanly.

## Context (not checked)

Finding F06 of architect pass `ar-20261125T184522Z-c248` (`docs/delivery/reviews/ar-20261125T184522Z-c248.md`), and
three follow-ups of 0344 the lead passed to that pass: `tests/test_run_clock.py` does not pin a clock shared across
the names it patches or the `start=` branch; no test covers `scripts/sync-product-docs.sh` refusing a project with
no binding; `tests/helpers.py`'s imports are out of order.

Measured at `05cb00e2`:

- **F06.** `git grep -c 'assertNotIn(.*tasks migrate' -- tests`: `tests/test_init.py:2`, `tests/test_tasklog.py:5`.
  Two tests are named for the absence: `tests.test_init.EarlierTaskFiles.test_the_warning_names_tasks_check_not_a_converter`
  (its positive assertion: the warning names `` `ccp tasks check` ``) and
  `tests.test_tasklog.TaskLogTest.test_no_message_names_a_retired_converter` (its positive assertions: a gone file
  is told the `status: dropped` line, a file with no frontmatter ends with `tasklog.NO_FRONTMATTER`, `tasks list`
  says `no frontmatter`). The older tombstone modules the report names drive a reader over old data (the board and
  health over older records, `set-waiting-on.sh` refusing old reasons, an old queue's markers archived), which E4's
  amended text keeps as behaviour, except
  `tests.test_review_aliases_retired.OlderAliasRecords.test_docs_audit_is_no_longer_a_command`, whose one subject is
  that `ccp docs audit` is not a command.
- **run clock.** `"def run_clock(case, *where: str, start: str | None = None)"` (`tests/helpers.py`) shares one
  generator across every name in `where`; `tests/test_run_clock.py` has one test, which patches the default name
  and gives no `start`.
- **docs sync.** `scripts/sync-product-docs.sh` refuses with `fail(f"no project binding for {project} in
  {lib.bindings_dir()}")` (exit 2) when `lib.binding_for_id` finds none; `git grep -n 'no project binding' -- tests`
  at `05cb00e2`: nothing.
- **imports.** `awk '/^import /{print $2}' tests/helpers.py | sort -c` at `05cb00e2`: `sort: -:5: disorder: itertools`,
  exit 1 (`import itertools` follows `import tempfile`).

**Ruled.**

- **F06.** Delete the seven `assertNotIn` lines naming `tasks migrate` (`tests/test_init.py` two, `tests/test_tasklog.py`
  five, the loop at the end of the second named test included). Rename
  `test_the_warning_names_tasks_check_not_a_converter` to `test_the_warning_names_tasks_check` and
  `test_no_message_names_a_retired_converter` to `test_a_gone_or_bare_file_is_told_its_fix`, their other assertions
  unchanged. Delete `test_docs_audit_is_no_longer_a_command` (and imports only it used). The other tombstone
  modules stay.
- **run clock.** New tests `tests.test_run_clock.RunClock.test_one_clock_runs_across_every_name_it_patches`
  (`run_clock(self, "ccp.runs.iso", "ccp.report.iso")`; alternating calls give stamps a minute apart, in order) and
  `tests.test_run_clock.RunClock.test_start_sets_the_first_stamp` (`start="2026-01-02T03:04:00Z"`: the first two
  stamps are that and `2026-01-02T03:05:00Z`).
- **docs sync.** New test `tests.test_binding_by_id.BindingById.test_sync_refuses_a_project_with_no_binding`: the
  script run for an id with no binding in the test's bindings directory (`PROJECT_YAML` unset) exits 2 and names
  the id on stderr.
- **imports.** `tests/helpers.py`'s plain `import` lines sorted (`itertools` before `json`).
- No other test expectation changes; no code or SPEC changes.

## Scope

- **In:** `tests/test_init.py`; `tests/test_tasklog.py`; `tests/test_review_aliases_retired.py` (the one test);
  `tests/test_run_clock.py`; `tests/test_binding_by_id.py`; `tests/helpers.py` (its imports only).
- **Out:** `tests/test_queue_markers_gone.py`, `tests/test_stale_blockers_retired.py`,
  `tests/test_operator_rename.py` and the rest of `tests/test_review_aliases_retired.py`; `scripts/`; `ccp/`.

## dod_checks

- id: `test-01`
  story: As a maintainer, no test pins the retired converter's name and the behaviour those tests held still passes.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `git grep -n 'assertNotIn(.*tasks migrate' -- tests`.
    2. Run `git grep -n -e 'def test_the_warning_names_tasks_check_not_a_converter' -e 'def test_no_message_names_a_retired_converter' -e 'def test_docs_audit_is_no_longer_a_command' -- tests`.
    3. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_init.EarlierTaskFiles.test_the_warning_names_tasks_check tests.test_tasklog.TaskLogTest.test_a_gone_or_bare_file_is_told_its_fix tests.test_review_aliases_retired`.
  expect: steps 1 and 2 print nothing (git grep's exit 1); step 3 exits 0.
  dry run (`05cb00e2`): step 1 printed 7 lines; step 2 printed 3 lines; step 3 exit 1 (`AttributeError: type object 'EarlierTaskFiles' has no attribute 'test_the_warning_names_tasks_check'`).
- id: `test-02`
  story: As a test writer, the run clock is one clock across the names it patches and starts where I say.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_run_clock.RunClock.test_one_clock_runs_across_every_name_it_patches tests.test_run_clock.RunClock.test_start_sets_the_first_stamp tests.test_run_clock`.
  expect: exit 0.
  dry run (`05cb00e2`): exit 1 (`AttributeError: type object 'RunClock' has no attribute 'test_one_clock_runs_across_every_name_it_patches'`).
- id: `test-03`
  story: As the operator, the docs sync's refusal of a project with no binding is held by a test.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_binding_by_id.BindingById.test_sync_refuses_a_project_with_no_binding tests.test_binding_by_id`.
  expect: exit 0.
  dry run (`05cb00e2`): exit 1 (`AttributeError: type object 'BindingById' has no attribute 'test_sync_refuses_a_project_with_no_binding'`).
- id: `code-01`
  story: As a maintainer, tests/helpers.py's imports are in order.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `awk '/^import /{print $2}' tests/helpers.py | sort -c`.
  expect: exit 0, nothing printed.
  dry run (`05cb00e2`): exit 1 (`sort: -:5: disorder: itertools`).

## Implementation notes

## Verification notes
