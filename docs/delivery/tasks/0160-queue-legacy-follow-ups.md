---
task_id: 0160-queue-legacy-follow-ups
title: The queue docs name only what the plane writes, an unused reader goes, a queue archive is in the ledger, and a Finder .DS_Store is no leftover
status: pending
kind: feature
depends_on: []
spec_refs: ["S31", "S24"]
review_point: R10
paths: ["scripts/queue/README.md", "scripts/observability/README.md", "scripts/observability/lib.py", "contracts/observability_event.schema.json", "ccp/plane.py", "ccp/queue.py", "docs/spec/05-operations.md", "docs/spec/04-observability.md", "docs/design/architect.md", "docs/design/plugin.md", "tests/test_plugin.py", "tests/test_plane_check.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0160-queue-legacy-follow-ups
## Intent

After task 0135's queue check, the plane's own docs and code agree with what that check enforces:
- the queue layouts name no entry the plane no longer writes;
- a reader nothing calls is gone;
- an archive is in the ledger beside every other queue change;
- a macOS Finder `.DS_Store` is neither reported nor moved.

## Context (not checked)

- Four lines at `85d388b`: `git grep -n "results/\|artifacts/\|running\.json" -- scripts/queue/README.md scripts/observability/README.md`.
  `scripts/queue/README.md` names `results/<task_id>.json`,
  `artifacts/<task_id>/` and `running.json`, and `scripts/observability/README.md` names
  `running.json`. No code writes them, and `ccp plane check` lists each as a leftover.
- `git grep -n load_durable_statuses -- . ':!docs/delivery/tasks'` at `85d388b`: its definition in
  `scripts/observability/lib.py`, one test (`tests/test_plugin.py`
  `test_readers_use_the_task_files`) and two docs (`docs/design/architect.md`, `docs/design/plugin.md`).
  No code calls it. `parse_index_statuses` is called only from it
  (`git grep -n parse_index_statuses` at `85d388b`). `resolve_durable_docs_dir` has other callers
  (`scripts/observability/spec_maintainer.py`, `tests/test_init.py`) and stays.
- `archive` in `ccp/plane.py` moves entries and writes no event: `"def archive"` holds no `emit`.
  Every other `ccp plane` write emits a `plane` event (`proposed`, `again`, `triaged`, `built`).
- `leftover_entries` in `ccp/queue.py` lists every top-level entry not in `QUEUE_OWNED`, except
  `*.tmp` and the auth-check script. So the `.DS_Store` that macOS Finder drops in any folder it opens
  is listed, and `--archive` moves it.
- §31.1: the §31.3 and §24 sentences below describe this task's own changes.

## Scope

- **In:**
  - `scripts/queue/README.md`, `scripts/observability/README.md`: the layouts drop the `results` and
    `artifacts` directories and `running.json`.
  - `scripts/observability/lib.py`: `load_durable_statuses` and `parse_index_statuses` removed.
    `tests/test_plugin.py` `test_readers_use_the_task_files` is removed with them, since it tests only
    the removed reader. `docs/design/architect.md` and `docs/design/plugin.md` stop naming it: the
    architect's done count is the task log's, read by `ccp/architect.py`.
  - `ccp/plane.py` `check --archive`: when anything moved or failed to move, one event
    `plane`/`archived` with `{day, archived: <count>, not_moved: <count>}`, numbers only, no paths.
    `scripts/observability/lib.py` (`EVENT_OPS` and the required payload fields) and
    `contracts/observability_event.schema.json` (the op enum) admit it. §31.1:
    `docs/spec/04-observability.md` §24's event table gets the row, and `docs/spec/05-operations.md`
    §31.3 says in one clause that the archive is recorded.
  - `ccp/queue.py`: `.DS_Store` is not a leftover, at the queue root or in the queue's `scripts` directory.
    §31.1: §31.3's list of what is not listed names it.
  - `tests/test_plane_check.py`: the tests for this task.
- **Out:**
  - Removing a `.DS_Store` from the queue.
  - Suite time (the same proposal's last point), which is the gate cache's task.

## dod_checks

- id: `doc-01`
  story: As a reader of the queue docs, they name only what the plane writes.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n "results/\|artifacts/\|running\.json" -- scripts/queue/README.md scripts/observability/README.md`.
  expect: no line (exit 1).
  dry run (`85d388b`): 4 lines.
- id: `code-01`
  story: As a plane developer, a reader nothing calls is gone.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nw -e load_durable_statuses -e parse_index_statuses -- ':!docs/delivery/tasks'`.
  expect: no line (exit 1).
  dry run (`85d388b`): 6 lines (the two definitions, the one call, the test, the two design docs).
- id: `arch-01`
  story: As an operator, a queue archive is in the ledger.
  setup: a scratch queue (`tests/test_plane_check.py`'s fixture) with two root leftovers, `old.txt` and `results/`.
  steps:
    1. Run `ccp plane check --archive`.
    2. Read the last line of `observability/events.jsonl`.
  expect: step 1 exits 0; the event is `plane`/`archived` with `archived` 2, `not_moved` 0 and `day` the UTC date, and its payload holds no path.
  dry run: n/a.
- id: `arch-02`
  story: As an operator, a clean queue's check writes nothing.
  setup: a clean scratch queue.
  steps:
    1. Run `ccp plane check --archive`.
  expect: exit 0; `observability/events.jsonl` has no new line.
  dry run: n/a.
- id: `ds-01`
  story: As a macOS operator, Finder's metadata file is not a leftover.
  setup: a clean scratch queue with an empty `.DS_Store` at its root and one in `scripts/`.
  steps:
    1. Run `ccp plane check`, then `ccp plane check --archive`.
  expect: both exit 0 with `root` and `scripts` empty; both `.DS_Store` files are still in place and `_legacy/` does not exist.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
