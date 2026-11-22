---
task_id: 0268-the-local-pr-record-keeps-the-plane-s-state-words-and-writes-ledger-events
title: The local PR record stores the plane's own state words, and each write of it records a pr ledger event
status: pending
kind: feature
depends_on: []
clashes_with: ["0266-github-knowledge-stays-in-the-pr-host-module", "0263-writers-are-checked-against-their-contracts"]
spec_refs: ["S23", "S4"]
adr_refs: ["0040 D3"]
review_refs: ["ar-20261121T174754Z-7df5#F07"]
rule_refs: ["E7", "E12"]
review_point: R21
paths: ["ccp/prhost.py", "contracts/pr_record.schema.json", "contracts/observability_event.schema.json", "scripts/observability/lib.py", "docs/spec/04-observability.md", "tests/test_prhost_events.py", "tests/test_prhost_local.py", "tests/test_prhost_cli.py", "tests/test_behind_tip_catch_up.py", "tests/test_tasks_close.py", "tests/test_toolkit.py", "tests/test_event_registry.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0268-the-local-pr-record-keeps-the-plane-s-state-words-and-writes-ledger-events

## Intent

The local PR record, a format the plane writes and reads itself, stores a PR's state in the plane's
own words (`open`, `merged`, `closed`), so the PR-host module keeps one table of state words and
translates only GitHub's. Opening a local PR, replacing its body and its merge each append one `pr`
event to the ledger, as every other queue change does, so the ledger shows a local PR's life as it
shows a task's.

## Context (not checked)

From architect pass `ar-20261121T174754Z-7df5`, finding F07 (the record is in
`docs/delivery/reviews/`), and a follow-up of 0222 from the lead's log (its review's MINOR 3: the
local adapter's record writes record no ledger event; 0222's verification note says the ledger has no
`pr` event type). Measured at `afb8ce6` (the figures below match `31357f0`, where the dry runs ran).

- **F07, a second state vocabulary.** `contracts/pr_record.schema.json`:
  `"state": {"enum": ["OPEN", "MERGED", "CLOSED"]}`.
  `git grep -c -E '"(OPEN|MERGED|CLOSED)"' -- ccp/prhost.py` at `31357f0`: 7 lines (`_GITHUB_STATES` and six uses in `Local`), plus `_LOCAL_STATES`, a table
  that only uppercases `STATES`. Ruling: the record stores `STATES`' words; `_LOCAL_STATES` goes;
  `Local` compares with `STATES`' words. `_GITHUB_STATES` stays: it translates `gh`'s output.
- **Stored data, and why there is no migration.** A local record lives in `QUEUE_ROOT/prs/<n>.json`.
  At triage no queue on the operator's machine held a `prs/` directory
  (`ls "$QUEUE_ROOT/prs" | wc -l` run for each bound product's queue: 0 each), and this repo runs the GitHub adapter. So the reader
  accepts the new words only (E9: no live record holds the old ones), and a record in the old words is
  refused as a record with no PR state, naming its file, as `"def _load"` refuses one today.
- **The follow-up, ledger events.** House rule E7: every queue write goes through `ccp` and records
  its own event. `Local`'s writes (`"def open"`, `"def edit"`, `"def merge"`'s `merge_commit`, and
  `"def _read"`'s refresh that finds the squash on the base) call `_save` and emit nothing
  (`grep -c 'emit' ccp/prhost.py` at `31357f0`: 0). Ruling: one event through `queue.emit` per
  opening, body edit and merge: type `pr`, op `opened` (`"def open"`), `edited` (`"def edit"`) or
  `merged`, payload `pr` (the number) and `head`, plus `merge_commit` for `merged`. `merged` is
  emitted only by the write that first sets the record's state to `merged`, so once per PR.
  `"def merge"` sets the state itself: its write after the push records `merge_commit`, the state
  `merged` and `merged_at` (the squash commit's time) together, and emits `merged`. The refresh in
  `"def _read"` emits `merged` only when it is the write that first sets the state (a merge made by
  `merge.command`); a refresh that only moves the record's `head` emits nothing; `task_id` the branch's task id when the branch is
  `task/<id>`, else empty. The GitHub adapter writes nothing to the queue and emits nothing.
  `scripts/observability/lib.py` gains the type in `TOOLKIT_EVENT_TYPES`, the ops `edited` and
  `merged` in `EVENT_OPS`, and `REQUIRED_PAYLOAD` entries for the three ops; the schema follows
  (`tests/test_event_registry.py` holds them together).
- **Tests this breaks**, each line counted by `git grep -c -E '"(OPEN|MERGED|CLOSED)"' -- <module>` at `31357f0`:
  - `git grep -c -E '"(OPEN|MERGED|CLOSED)"' -- tests/test_behind_tip_catch_up.py`: 5;
  - `git grep -c -E '"(OPEN|MERGED|CLOSED)"' -- tests/test_prhost_local.py`: 7;
  - `git grep -c -E '"(OPEN|MERGED|CLOSED)"' -- tests/test_prhost_cli.py`: 2;
  - `git grep -c -E '"(OPEN|MERGED|CLOSED)"' -- tests/test_toolkit.py`: 2 (the fixture's `pr_record()`);
  - `git grep -c -E '"(OPEN|MERGED|CLOSED)"' -- tests/test_tasks_close.py`: 1.
  Each that reads a local record changes to the new words. `tests/test_prhost.py`'s uppercase words are
  `gh`'s and stay.
- **Clashes:** 0266 changes `ccp/prhost.py` too; 0263 checks writers against their contracts,
  `pr_record.schema.json` among them.

## Scope

- **In:**
  - `ccp/prhost.py` (`Local`: the state words, `_LOCAL_STATES` removed, the events).
  - `contracts/pr_record.schema.json` (the state enum), `contracts/observability_event.schema.json`
    and `scripts/observability/lib.py` (the type, the ops, the required payloads).
  - `tests/test_prhost_events.py` (new), and the test modules named in Context.
- **SPEC, signed before the claim (`sign_off: brief`):** `docs/spec/04-observability.md` §23.2,
  the event table: a row added after the `verify` row.

    CURRENT (`docs/spec/04-observability.md` at `31357f0`), §23.2, the event table's `verify` row:
    > | `verify` | `recorded` | `run_id`, `verdict`, `head_sha` |

    PROPOSED:
    > | `verify` | `recorded` | `run_id`, `verdict`, `head_sha` |
    > | `pr` | `opened`, `edited`, `merged` | `pr` (the number), `head`; `merged` adds `merge_commit`. Only the local PR host writes them (§4.5), one per opening, body edit and merge: `ccp pr open`, `ccp pr edit`, and the write that first records the PR as merged, by close or on finding the merge on the base |
- **Out:** events for the GitHub adapter; health or board readers of the new events; the record's
  other fields.

## dod_checks

- id: `data-01`
  story: As a plane developer, the PR-host module keeps one table of state words and translates only GitHub's.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n -E '"(OPEN|MERGED|CLOSED)"' -- ccp/prhost.py contracts/pr_record.schema.json`.
    2. Run `git grep -c '_LOCAL_STATES' -- ccp/prhost.py`.
  expect: step 1 prints exactly one line, `ccp/prhost.py`'s `_GITHUB_STATES` mapping; step 2 prints nothing (exit 1).
  dry run (`31357f0`): step 1 printed 8 lines (7 in `ccp/prhost.py`, 1 in the schema); step 2 printed `ccp/prhost.py:3`.
- id: `data-02`
  story: As an operator on the local adapter, records written in the new words read back, and one in the old words is refused by name rather than misread.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prhost_local 2>&1 | grep -i 'old\|word'`.
    2. Run `python3 -B -m unittest -q tests.test_prhost_local tests.test_prhost_cli tests.test_behind_tip_catch_up tests.test_tasks_close tests.test_toolkit`.
  expect: step 1 prints at least one line ending `ok`, a test that writes `prs/1.json` with `"state": "OPEN"` and gets an error from `ccp pr view 1` naming `1.json`, exit non-zero; step 2 exits 0.
  dry run (`31357f0`): step 1 printed nothing; step 2 n/a (the five modules ran in the gate at `31357f0`).
- id: `ev-01`
  story: As an operator, each opening, body edit and merge of a local PR appears in the ledger as one pr event, and the GitHub adapter writes none.
  setup: A checkout of the PR head; then a separate copy of it where `Local.open` emits nothing.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_prhost_events 2>&1 | tail -8`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_prhost_events`.
  expect: step 1 exits 0, listing as `ok` tests that, on a fenced product with the local adapter, `ccp pr open`, `ccp pr edit` and `ccp tasks close` each append exactly one `pr` event (ops `opened`, `edited`, `merged`, the last with `merge_commit`), a `ccp pr view` that only moves an open PR's head appends none, a second `ccp pr view` of the merged PR appends none, a PR merged by `merge.command` gets its one `merged` event from the `ccp pr view` that finds the squash on the base, and under the GitHub adapter `ccp pr open` appends none; step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `ev-02`
  story: As a plane developer, the ledger's registry and its schema hold the new type and ops.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -c "from ccp.queue import lib; print('pr' in lib.EVENT_TYPES, [o for o in ('edited', 'merged') if o in lib.EVENT_OPS])"`.
    2. Run `python3 -B -m unittest -q tests.test_event_registry`.
  expect: step 1 prints `True ['edited', 'merged']`; step 2 exits 0.
  dry run (`31357f0`): step 1 printed `False []`; step 2 exited 0.
- id: `spec-01`
  story: As the operator, §23.2 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0268`.
  expect: exit 0, the PROPOSED passage found in `docs/spec/04-observability.md`.
  dry run (simulated: this task file and the row applied, committed in a scratch worktree off `31357f0`, `--base` the commit holding the task file): `"ok": true`, exit 0; the passage found in `docs/spec/04-observability.md`.

## Implementation notes

- `ccp/prhost.py` `Local`: the record stores and compares `STATES`' words; `_LOCAL_STATES` is gone and
  `_GITHUB_STATES` is the one uppercase table. `_load` refuses a record whose state is not one of `STATES`
  (an old uppercase record included) as one that names no PR state, naming its file.
- Events go through `queue.emit` from one helper, `Local._emit`: `task_id` is the branch's id when the branch is
  `task/<id>`, else empty; the actor is the caller's (`ACTOR`). `open` emits `opened` and `edit` emits `edited`
  inside the record's lock, right after the write. `merge`'s write after the push sets `state`, `merge_commit`
  and `merged_at` (the squash commit's committer time, read in the merge worktree) together and emits `merged`
  with `head` the merged tip; if a concurrent read already recorded the merge under the lock, it writes and
  emits nothing (the narrowest reading of "only the write that first sets the state"). `_read` emits `merged`
  only when its refresh moved the state to `merged`; a head-only refresh emits nothing.
- `merge` now leaves the record `merged`, so close's `confirm` read finds nothing to change and writes no second
  event; `tests/test_prhost_local.py`'s merge test expects that state and the merge time (the behaviour change
  the task's Context names).
- ADR-0040 D3 was already `built` on the base; `ccp adr decide 40 D3 built` changed nothing.

## Verification notes
