---
task_id: 0296-the-spec-question-script-loads-the-product-config-once-and-reads-its-task-dir
title: The spec-question script and lib load a product's config through one quiet loader, the task-id check reads the configured task directory (DURABLE_DOCS goes), blocked builds its dependency map once, and the architect driver no longer imports the spec-question script
status: pending
kind: feature
depends_on: []
spec_refs: ["S17", "S19"]
review_point: R26
paths: ["scripts/observability/spec_maintainer.py", "scripts/observability/architecture_review.py", "scripts/observability/lib.py", "scripts/queue/README.md", "tests/test_spec_maintainer_blocked.py", "tests/test_spec_maintainer_task_ids.py", "tests/test_binding_reader.py", "tests/test_init.py"]
clashes_with: ["0191-the-grace-release-ends", "0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs", "0289-the-runner-s-actor-id-is-named-once-and-tests-read-the-lead-s", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0296-the-spec-question-script-loads-the-product-config-once-and-reads-its-task-dir

## Intent

The leftovers of 0282 are closed. A product's plane.json is loaded from a queue root by one function in
lib, which prints no load warnings in the middle of a spec-question command; the spec-question script
uses it for its config, its notices and its task-id check. That check finds a task in the task
directory the product's config names, as `blocked` already does, and the undocumented `DURABLE_DOCS`
override goes. `blocked` reads the task log once per call, not once per open question. The architect
driver takes the lock, project-id and product-root helpers from lib, so it no longer imports the
spec-question script.

## Context (not checked)

From the triage of architect pass `ar-20261122T100027Z-dd31`, which maps the open worker follow-ups of 0282 here (the
record's "Worker follow-ups" table): `0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log/implement#1`,
`…/implement#2`, `…/implement#3`, `…/review#1`, `…/review#2` and `…/fix#1`, `…` being
`0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log`. Measured at `e92f362`.

- **The driver's import (implement#1, review#2).** `scripts/observability/architecture_review.py` imports `spec_maintainer as sm`
  with the comment "(lock, quota parse, Claude JSON parse, binding helpers)", and uses only `sm.lock_is_stale`, `sm.project_id`
  and `sm.product_root`: `git grep -n 'sm\.' -- scripts/observability/architecture_review.py` at `e92f362`: 4 lines. `lock_is_stale` lives in lib
  (`"def lock_is_stale"`) and `spec_maintainer.py` re-exports it ("re-exported: architecture_review.py's lock reads it");
  `project_id` and `product_root` are defined in `spec_maintainer.py` from lib's `binding_str` and `binding_data`.
  `scripts/observability/team.py` also calls `sm.product_root` and `sm.project_id` and is left as it is.
- **Three config loads (implement#2, fix#1).** `git grep -n 'ccp_config.load\|cfg.load(' -- scripts/observability/spec_maintainer.py scripts/observability/lib.py` at `e92f362`: 3 lines:
  `spec_maintainer.product_config`, `notify_operator`'s inline load (which turns a load error into a warning naming it), and
  lib's private `_product_config`, the only one that silences the load's warnings. `team.py`'s six loads are out of scope.
- **The task-id check (implement#3).** `"def check_task_ids"` finds the task directory through lib's `resolve_durable_docs_dir`,
  which reads `DURABLE_DOCS` before the binding's product root; `blocked` (0282) reads the task log through the loaded config.
  `git grep -n 'DURABLE_DOCS\|resolve_durable_docs_dir' -- ccp scripts tests` at `e92f362`: 16 lines (in `scripts/observability/lib.py`,
  `scripts/observability/spec_maintainer.py`, `scripts/queue/README.md`, `tests/test_binding_reader.py`, `tests/test_init.py` and
  `tests/test_spec_maintainer_blocked.py`). `check_task_ids` is its only caller in `ccp` and `scripts`. No hook, template or binding sets
  the variable: `git grep -n DURABLE_DOCS -- plugin templates` at `e92f362`: no line.
- **blocked (review#1).** `"def cmd_blocked"` calls `descendants` once per open question, and each call loads plane.json and the
  whole task log and globs the queue's `tasks/*.json`.
- **No SPEC change.** `git grep -n 'DURABLE_DOCS\|resolve_durable_docs_dir\|product_config' -- docs/spec` at `e92f362`: no line. §17.7 already names
  the task log's descendants; how the script finds the task directory is not a SPEC rule.
- **Other tasks.** 0283 (signed) and 0289 change other lines of `spec_maintainer.py`, `lib.py` and `architecture_review.py`;
  0293 changes `lib.py`'s seat ids and `spec_maintainer.py`'s `RAISERS`. Recorded as clashes.

### Rulings for the build (the lead's)

- **One loader.** lib's `_product_config(product_root)` stays the one place that calls `ccp.config.load` here. lib gains
  `def product_config(root: Path, *, strict: bool = False)`: the binding's product root for the queue `root`, then
  `_product_config`'s quiet load; None with no product root or no plane.json; with `strict=True` a plane.json that exists but
  fails to load raises the load's error (still quiet) instead of returning None. `spec_maintainer.product_config` goes and its
  callers use lib's; `notify_operator` uses it with `strict=True`, keeping its warning text.
- **The task directory.** `check_task_ids` takes the directory from the loaded config (`cfg.tasks_dir`), with no check when
  there is no config, as `blocked` does. `resolve_durable_docs_dir` and `DURABLE_DOCS` go, with `scripts/queue/README.md`'s row,
  `tests/test_binding_reader.py`'s tests of that function, `tests/test_init.py`'s assertion (it reads the loaded config's
  `tasks_dir` instead) and `tests/test_spec_maintainer_blocked.py`'s filter of the variable.
- **blocked.** `descendants` takes the dependency map as an argument (`def descendants(deps, seeds)`), built once per call by a
  new `def dependency_map(root)` from the queue's tasks and the task log; `cmd_blocked` builds it once.
- **The driver.** `project_id` and `product_root` move to lib; `spec_maintainer.py` imports them from there (so `sm.project_id`
  and `sm.product_root` still resolve for `team.py`) and drops its `lock_is_stale` re-export. `architecture_review.py` imports
  `lock_is_stale`, `project_id` and `product_root` from lib and no longer imports `spec_maintainer`.

## Scope

- **In:** `scripts/observability/spec_maintainer.py`, `scripts/observability/architecture_review.py`, `scripts/observability/lib.py`,
  `scripts/queue/README.md`, `tests/test_spec_maintainer_blocked.py`, `tests/test_spec_maintainer_task_ids.py` (new),
  `tests/test_binding_reader.py`, `tests/test_init.py`.
- No SPEC change (measured in Context).
- **Out:** `scripts/observability/team.py`'s loads and `sm.` calls; moving lib or the driver into `ccp` (the roadmap's F17).

## dod_checks

- id: `code-01`
  story: As a plane developer, the architect driver takes its helpers from lib, not from the spec-question script.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'import spec_maintainer\|sm\.\|re-exported' -- scripts/observability/architecture_review.py scripts/observability/spec_maintainer.py`.
  expect: prints nothing (exit 1).
  dry run (`e92f362`): printed 6 lines.
- id: `code-02`
  story: As a lead running a spec-question command, a product's plane.json is loaded by one quiet loader.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `git grep -n 'ccp_config.load\|cfg.load(' -- scripts/observability/spec_maintainer.py scripts/observability/lib.py`.
    2. Run `python3 -B -m unittest -v tests.test_spec_maintainer_task_ids 2>&1 | grep -e warning -e '^OK'`.
  expect: step 1 prints exactly one line, in `scripts/observability/lib.py`'s `_product_config`; step 2 lists, `ok`, a test where `check_task_ids` on a product whose plane.json carries a key that makes `ccp.config.load` warn writes nothing to stderr, its name holding `warning`, then `OK`.
  dry run (`e92f362`): step 1 printed 3 lines; step 2: n/a — the module is new.
- id: `code-03`
  story: As a runner raising a spec question, a blocked task id is checked against the task directory the product's config names, whatever DURABLE_DOCS says.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `git grep -n 'DURABLE_DOCS\|resolve_durable_docs_dir' -- ccp scripts tests`.
    2. Run `python3 -B -m unittest -v tests.test_spec_maintainer_task_ids 2>&1 | grep -e task_dir -e '^OK'`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_spec_maintainer_task_ids --mutant-file <file>`, the file's mutant making `check_task_ids` look in `<product root>/docs/delivery/tasks` whatever the config says.
  expect: step 1 prints nothing (exit 1); step 2 lists, each `ok`, a test where a product whose plane.json sets `task_log.dir` to another directory has a task id found there accepted and an unknown id refused (exit 2, `no such task`, naming that directory), with `DURABLE_DOCS` set to an unrelated path, its name holding `task_dir`, then `OK`; step 3 prints the mutant `killed`.
  dry run (`e92f362`): step 1 printed 16 lines in 6 files; steps 2 and 3: n/a — the module is new.
- id: `code-04`
  story: As a runner asking what is blocked, blocked reads the task log once however many questions are open.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_spec_maintainer_blocked 2>&1 | grep -e once -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_spec_maintainer_blocked --mutant-file <file>`, the file's mutant making `cmd_blocked` build the dependency map inside its loop over questions.
  expect: step 1 lists, `ok`, a test where with three open questions `blocked` calls `tasklog.load` exactly once and prints the same `blocked` and `by_question` as before, its name holding `once`, then `OK`; step 2 prints the mutant `killed`.
  dry run (`e92f362`): step 1 printed only `OK` (no test names `once` yet).

## Implementation notes

## Verification notes
