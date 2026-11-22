---
task_id: 0272-the-lead-s-records-share-one-guard-and-one-actor-id
title: The lead's three records refuse another seat through one guard, a ruling counts only when the lead recorded it, and the lead's actor id is named once
status: pending
kind: feature
depends_on: ["0253-one-wait-reason-table"]
spec_refs: ["S3", "S13", "S17"]
review_refs: ["ar-20261121T223646Z-f0a7#F03"]
rule_refs: ["E12", "E27"]
review_point: R23
paths: ["scripts/observability/lib.py", "scripts/observability/team.py", "ccp/followups.py", "ccp/lifecycle.py", "ccp/queue.py", "ccp/cli.py", "ccp/notify.py", "ccp/reviewpoints.py", "ccp/seats.py", "ccp/usage.py", "docs/delivery/plane.json", "docs/ENGINEERING.md", "docs/cli/02-delivery.md", "tests/test_lead_records.py", "tests/test_sign_off.py", "tests/test_sign_off_beyond_intent.py", "tests/test_verify_spec_text.py", "tests/test_behind_tip_catch_up.py", "tests/test_followups.py", "tests/test_followups_closed_point.py", "tests/test_notify_lead.py", "tests/test_orientation_follow_ups.py", "tests/test_report_follow_ups.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0272-the-lead-s-records-share-one-guard-and-one-actor-id

## Intent

The SPEC gives the lead three records: sign-offs (§3.5), rulings (§17.5) and follow-up outcomes
(§13.4). After this task each of the three commands refuses a caller whose `ACTOR` names another
seat, through one shared guard, as `ccp tasks follow-up` alone does today. A ruling in the ledger
counts, wherever a verdict or `--waived` cites it, only when the lead recorded it, so the record
that can now waive an operator-machine check is held at least as tightly as a follow-up's outcome.
The lead's actor id is written once, in the seat table, and every other module reads it from there.

## Context (not checked)

Measured at `8020446` unless a line says otherwise. Provenance: architect pass
`ar-20261121T223646Z-f0a7`, F03 (`incoherence`), and house rule E27, which the triage added to
`docs/ENGINEERING.md`; the record is in `docs/delivery/reviews/`.

- **One guard of three.** `"def decide"` in `ccp/followups.py`: `if by != LEAD: raise QueueError("only the lead records a follow-up's outcome …", 2)`, with `by` from `queue.actor(followups.LEAD)` in `ccp/cli.py` (`grep -n 'queue.actor(followups.LEAD)' ccp/cli.py` at `8020446`: 1 line). `"def sign_off"` and `"def ruling"` in `ccp/lifecycle.py` emit with `actor("design-seat")` and check no caller.
- **`actor()`** in `ccp/queue.py` returns `ACTOR` when it is a known actor (`lib.ACTORS`), else the
  default; so a caller with no `ACTOR` records as the lead, and so does one with an unknown value.
- **Rulings are counted whoever recorded them.** `"def rulings"` in `ccp/queue.py` keeps every `ruling` `recorded` event of the task. Since 0237/0238 a ruling id waives a check marked `runs_on: operator-machine` (`grep -n 'CHECK=RULING' ccp/cli.py` at `8020446`: 1 line, `--waived`).
- **No migration.** `python3 -c` over every bound product's queue ledger (`observability/events.jsonl`), the `ruling` and `sign_off` `recorded` events by actor: every one is `design-seat` (data only the queues hold), so counting only the lead's rulings drops none (E9).
- **The literal.** `git grep -n '"design-seat"' -- ccp scripts ':(exclude)ccp/board_page.html'` at `8020446`: 28 lines in 8 files (usage.py 13, lifecycle.py 5, seats.py 4, lib.py 2, followups.py, notify.py, reviewpoints.py, team.py 1 each). Two more constants hold it: `followups.LEAD` and team.py's `LEAD, RUNNER = "design-seat", "task-runner"`; `lib.SEAT_IDS` is the seat table. `ccp/board_page.html` (2 lines) is the board's JavaScript and stays (E27's command excludes it).
- **Tests that break.** With a lead-only guard on sign-off and ruling and the ruling reader filtered,
  probed at `8020446` in a scratch copy (`python3 -B -m unittest -q <module>` per module): `tests.test_sign_off` (26 failures: its fixture sets `ACTOR` `task-runner`), `tests.test_sign_off_beyond_intent`, `tests.test_verify_spec_text` and `tests.test_behind_tip_catch_up` fail; `test_lead_ruling`, `test_marked_checks_loop`, `test_marked_checks_record`, `test_board_drill`, `test_estimate`, `test_full_lane_prompt`, `test_health_signoff`, `test_models_block`, `test_prompt_note_env`, `test_resolution_review`, `test_tasks_close`, `test_verify`, `test_verify_as_written`, `test_tasklog_spec_signoff`, `test_notify_lead`, `test_prompt_rounds`, `test_prompt_tools`, `test_review_skip` and `test_review_skip_clean` pass. The modules that import `followups.LEAD` (`git grep -ln 'followups.LEAD' -- tests` at `8020446`) change with the constant's home.
- **No SPEC change.** The SPEC already gives each record to the lead: `git grep -n 'tasks sign-off\|tasks ruling\|The lead alone records' -- docs/spec` at `8020446`: 3 lines (§3.5 "The lead records each sign-off", §13.4 "The lead alone records each one's outcome", §17.5 "A ruling the lead gives a runner … is recorded with `ccp tasks ruling`"), and §15.4 accepts as a ruling "lead ruling ids (`<task_id>-r<n>`, §17.5)", so a ruling another seat recorded is no lead ruling id. The guard enforces those sentences and adds none.
- **0253 first.** 0253 (R17, done since) edited `ccp/lifecycle.py`, `ccp/usage.py` and
  `scripts/observability/lib.py`; this task replaces literals in the code it left.

### Rulings for the build (the lead's)

- **The name.** `scripts/observability/lib.py` defines `LEAD = "design-seat"` and `RUNNER = "task-runner"` beside `SEAT_IDS`, which is built from them; `SEAT_DEFAULT_CRON` keys on them. `followups.LEAD` and team.py's own `LEAD, RUNNER` are removed; every reader uses `lib.LEAD` (team.py its sibling `lib`). `usage.py`'s seat labels compare with `lib.LEAD`.
- **The guard.** One function, `queue.lead_actor(what)`, returns the lead's id when `ACTOR` is unset or
  names the lead, and refuses (exit 2, nothing written) when `ACTOR` names another known actor:
  "only the lead records {what} (ACTOR is {actor}): tell the lead". `ccp tasks sign-off`,
  `ccp tasks ruling` and `ccp tasks follow-up` call it before any read or write and emit with what it
  returns; `followups.decide` keeps no check of its own. Other lead commands are unchanged.
- **The reader.** `queue.rulings` keeps a `ruling` `recorded` event only when its `actor` is the
  lead. A ruling recorded by another actor is not a ruling (§15.4): a verdict or `--waived` citing it
  is refused as for an unknown id.
- **E27's command** joins `architect.checks` in `docs/delivery/plane.json` once it passes:
  `{"id": "E27", "cmd": "! git grep -n '\"design-seat\"' -- ccp scripts ':(exclude)ccp/board_page.html' ':(exclude)scripts/observability/lib.py'"}`, and E27's `check:` line in `docs/ENGINEERING.md` becomes "command — architect.checks `E27`: <the
  command>; pass for the guard (the architect compares the lead's commands)", so `ccp docs check`
  finds the entry the rule names.

## Scope

- **In:** `scripts/observability/lib.py`, `scripts/observability/team.py`, `ccp/followups.py`,
  `ccp/lifecycle.py` (`"def sign_off"`, `"def ruling"` and the other `actor("design-seat")` calls),
  `ccp/queue.py` (`"def lead_actor"` (new), `"def rulings"`), `ccp/cli.py` (the follow-up call),
  `ccp/notify.py`, `ccp/reviewpoints.py`, `ccp/seats.py`, `ccp/usage.py`, `docs/delivery/plane.json`,
  `docs/ENGINEERING.md` (E27's `check:` line), `docs/cli/02-delivery.md` (the `ccp tasks sign-off` and
  `ccp tasks ruling` rows gain "refused, exit 2, when `ACTOR` names another seat", as the
  `ccp tasks follow-up` row already says), `tests/test_lead_records.py` (new), and the test
  modules named in Context.
- No SPEC change (measured in Context).
- **Out:** `ccp/board_page.html`; who may run the lead's other commands; the actor of any other event;
  the `ACTOR` an agent brief or hook sets.

## dod_checks

- id: `code-01`
  story: As the lead, only I record a sign-off, a ruling or a follow-up's outcome; a runner's or verifier's ACTOR is refused through the same guard.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_lead_records`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_lead_records --mutant-file <file>`, the file's mutant removing the guard call from `"def ruling"`.
  expect: step 1 exits 0 and lists, each `ok`, tests that with `ACTOR` `task-runner` each of `tasks sign-off`, `tasks ruling` and `tasks follow-up` exits 2 with `only the lead records` and adds no event; with `ACTOR` unset and with `ACTOR` `design-seat` each records. Step 2 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `code-02`
  story: As a verifier, a ruling another seat recorded does not waive a check.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_lead_records`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_lead_records --mutant-file <file>`, the file's mutant dropping the actor condition from `"def rulings"`.
  expect: step 1 lists, `ok`, a test where a ledger holding a `ruling` `recorded` event with actor `task-runner` gives `queue.rulings` no row for it and `ccp prompt verify --waived <check>=<that id>` exits non-zero naming the id. Step 2 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `code-03`
  story: As a plane developer, the lead's actor id is written once, in the seat table.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n '"design-seat"' -- ccp scripts ':(exclude)ccp/board_page.html'`.
    2. Run `git grep -nE '^(LEAD|LEAD, RUNNER) =' -- ccp scripts`.
  expect: step 1 prints exactly one line, in `scripts/observability/lib.py`; step 2 prints exactly one line, in `scripts/observability/lib.py`.
  dry run (`8020446`): step 1 printed 28 lines in 8 files; step 2 printed 2 lines (`ccp/followups.py:19`, `scripts/observability/team.py:32`).
- id: `cfg-01`
  story: As the architect, E27's command runs in every pass.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -c "import json;print([c['id'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E27'])"`.
  expect: prints `['E27']`.
  dry run (`8020446`): printed `[]`.

## Implementation notes

- Premises re-measured at `5fa9ff03`: the literal grep printed 28 lines in 8 files, the `LEAD` grep 2 lines,
  `queue.actor(followups.LEAD)` and `CHECK=RULING` 1 line each in `ccp/cli.py`, the SPEC grep 3 lines; every
  `ruling` and `sign_off` `recorded` event in both bound queues' ledgers has actor `design-seat`.
- `scripts/observability/lib.py` holds `LEAD` and `RUNNER`, on two lines; `SEAT_IDS` and `SEAT_DEFAULT_CRON`
  are built from them. team.py imports both from `lib`; every other module reads `lib.LEAD` (notify.py through
  its lazy `queue` import).
- `queue.lead_actor(what)` reads `ACTOR` as `queue.actor(lib.LEAD)` does, so an `ACTOR` that names no known
  actor still records as the lead, as before; only another known actor is refused. `lifecycle.sign_off` and
  `lifecycle.ruling` call it first, before `root()` and any read; `ccp tasks follow-up` calls it in cli.py
  before `queue.root()`, and `followups.decide` no longer checks its caller.
- `lifecycle.ruling` still numbers a ruling from `queue.rulings`, now the lead's only: a ruling another actor
  recorded takes no number, so a later lead ruling may reuse its id. No ledger holds one (measured above),
  and the guard writes none from now on.
- Only the `"design-seat"` literals moved; the other `"task-runner"` literals in `ccp/` are untouched (the
  task's checks and E27's command name only the lead's).
- Test modules that recorded a sign-off as the fixture's `task-runner` now record it as the lead
  (`lib.LEAD`); the follow-up modules and `test_notify_lead` read `lib.LEAD` in place of the old constant or
  the literal.

## Verification notes
