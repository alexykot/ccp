---
task_id: 0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs
title: The retired watchdog seat and the per-seat cron cadences leave every writer and doc, the watchdog stays a read-only actor, and the observability scripts keep one package doc
status: pending
kind: feature
depends_on: []
spec_refs: ["S18", "S23"]
review_refs: ["ar-20261122T055103Z-11aa#F03", "ar-20261122T055103Z-11aa#F04"]
rule_refs: ["E9", "E10", "E11"]
review_point: R25
paths: ["scripts/observability/lib.py", "scripts/observability/heartbeat.sh", "scripts/observability/emit-event.sh", "scripts/observability/spec_maintainer.py", "scripts/observability/README.md", "scripts/observability/CLAUDE.md", "ccp/queue.py", "contracts/observability_event.schema.json", "contracts/prompt_audit.schema.json", "docs/design/observability.md", "queue/README.md", "docs/spec/04-observability.md", "tests/test_stale_blockers_retired.py", "tests/test_seat_actors.py"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs

## Intent

Nothing the plane writes names the retired watchdog seat or a seat's cron cadence, matching §18.3 (every
seat is event-only, no watchdog). A ledger row written as the watchdog, which a bound product's queue
still holds, is still read (house rule E9). The observability scripts have one package doc,
`scripts/observability/CLAUDE.md`, which `ccp docs check` judges, and no second README carrying retired
cadences, watchdog rules and dated operator records.

## Context (not checked)

From architect pass `ar-20261122T055103Z-11aa`, F03 (`holdover`) and F04 (`doc-history`); the record is
in `docs/delivery/reviews/`. Measured at `76f41dd`.

- **The watchdog in writers and docs.** `git grep -n 'delivery-watchdog' -- ':!docs/delivery/tasks' ':!docs/delivery/reviews'` at `76f41dd`: 17 lines:
  lib.py (`SEAT_IDS` and the cadence comment and table), heartbeat.sh (usage, the seat check, the cron
  default), emit-event.sh (its usage example), spec_maintainer.py (a docstring), the README, the design
  note and the two contracts' `actor` enums; per file, `git grep -c delivery-watchdog -- scripts docs/design contracts` at `76f41dd`.
- **Rows that still hold it.** Read-only, a bound product's ledger still holds watchdog rows, and this
  plane's own ledger holds none. So the actor stays readable (E9).
- **Who accepts an actor.** `lib.ACTORS` (`SEAT_IDS` plus four) is read by `"def validate_event"`
  (every row read or appended), `ccp/queue.py`'s `"def actor"` (the ACTOR a write records), and the actor
  pickers of `spec_maintainer.py` and `architecture_review.py`.
- **cron_expected.** `git grep -n 'cron_expected\|cron-expected\|default_cron\|SEAT_DEFAULT_CRON' -- ':!docs/delivery/tasks' ':!docs/delivery/reviews'` at `76f41dd`: 14 lines,
  all writers or docs (lib's fold and `empty_seat`, `heartbeat.sh`'s option, defaults and two writes,
  the README, and `tests/test_stale_blockers_retired.py`'s fixture rows). `git grep -n cron_expected -- ccp contracts` at `76f41dd`: no lines,
  so nothing reads it. No contract describes `seats/<id>.json`.
- **The seat ids §18.3 names.** "`design-seat`, `task-runner` and `task-verifier` are seat ids". `heartbeat.sh`'s
  seat check accepts `task-runner|task-verifier|delivery-watchdog`; `ccp/queue.py`'s heartbeat call passes
  the seat it is given.
- **The README.** `wc -l scripts/observability/README.md` at `76f41dd`: 140 lines, beside the 9-line
  `CLAUDE.md`; `package_docs.claude_md_dirs` judges `CLAUDE.md` only. Its sections: the runtime layout,
  the scripts table, shell examples, spec questions, the timer formula ("LOCKED"), the single-writer
  rule, auth precedence (with "Watchdog Wake B"), seat liveness (the dated 2026-09-24 cadence), the
  prompt audit, secrets, contracts. `git grep -n 'observability/README' -- ':!docs/delivery/tasks' ':!docs/delivery/reviews'` at `76f41dd`: 2 lines,
  §23.3 (`docs/spec/04-observability.md`, "`scripts/observability/README.md` documents them") and `queue/README.md`.
  §23.3 states the three timer formulas itself, so dropping its pointer loses nothing.
- **A probe at `65065dc`** (a scratch copy: `delivery-watchdog` out of `SEAT_IDS`, the fold's and
  `empty_seat`'s `cron_expected` removed, heartbeat's watchdog default removed, then `scripts/gate.sh`):
  `gate: 204 modules, ran 204, cached 0, 3634 tests … all passed`. No existing test module breaks; the
  new behaviour is proved by `tests/test_seat_actors.py` (new).
- **Other tasks.** 0272 (done, PR #323) named the lead's and the runner's actor ids: lib.py now reads
  `SEAT_IDS = (RUNNER, "task-verifier", "delivery-watchdog", LEAD)` and keys `SEAT_DEFAULT_CRON` by `RUNNER`
  (`git grep -n 'SEAT_IDS =' -- scripts/observability/lib.py` at `76f41dd`: 1 line), and `ccp/queue.py` gained
  `"def lead_actor"`, which reads `actor(lib.LEAD)`; the ruling's `SEAT_IDS` below means those values, the
  constants kept. 0268 (done, PR #321) added a `pr` event to the contract and §23, not the actor or seat
  code. Neither did any of this task's work: every count above is unchanged since `072d9f9`. 0277 (R24,
  pending) changes the wait writers in lib.py. This task changes the watchdog entry and the cadence code:
  different logic, no clash.

### Rulings for the build (the lead's)

- `lib.SEAT_IDS` is `("task-runner", "task-verifier", "design-seat")`. A new `LEGACY_ACTORS = ("delivery-watchdog",)`
  joins `WAIT_READ_ONLY` and `LEGACY_EVENT_TYPES` as values only read: `validate_event` accepts it on a
  row it reads and refuses it on a row `append_event` writes; `ccp/queue.py`'s `actor()` and the actor
  pickers of `spec_maintainer.py` and `architecture_review.py` do not accept it (they fall back as for any
  unknown ACTOR).
- The contracts keep `delivery-watchdog` in their `actor` enums, and each `actor` description says it is
  historical: read in old rows, never written.
- `DEFAULT_CRON`, `EVENT_ONLY`, `SEAT_DEFAULT_CRON`, `default_cron` and the cadence comment leave lib.py;
  `empty_seat` and the fold record no `cron_expected` (an old row's field is ignored).
  `heartbeat.sh` loses `--cron-expected` and its defaults, writes no `cron_expected`, and accepts the seat
  ids of §18.3. Its `--wake-kind` default becomes `manual` (no seat runs on a routine); `cron` stays an
  accepted value, since old rows hold it. `git grep -n wake_kind -- ccp contracts` at `76f41dd`: no lines, so
  no reader depends on `cron`; lib's fold only copies the value, and `ccp/queue.py`'s heartbeat passes `manual`. `emit-event.sh`'s usage example emits as `task-runner`.
- `scripts/observability/README.md` is removed. What in it is current and is neither in the SPEC, in a
  script's `--help`, nor in `scripts/observability/CLAUDE.md` goes into that CLAUDE.md, in at most 6 added
  lines; the implementation notes list each README section and where its content now lives, or that it
  was retired. `queue/README.md`'s pointer names `scripts/observability/CLAUDE.md`, and lib.py's module
  docstring stops citing the README (`git grep -n README -- scripts/observability` at `76f41dd`: lib.py's
  "Timer formula (stable — see README.md):" and "Do not change this formula without a SPEC + README note.",
  besides the README itself); it cites §23.3 instead.
  `docs/design/observability.md`'s actor list and seat-id line drop the watchdog and name the §18.3 seats.

## Scope

- **In:** `scripts/observability/lib.py`, `scripts/observability/heartbeat.sh`,
  `scripts/observability/emit-event.sh`, `scripts/observability/spec_maintainer.py` (the docstring),
  `scripts/observability/README.md` (removed), `scripts/observability/CLAUDE.md`, `ccp/queue.py`,
  `contracts/observability_event.schema.json`, `contracts/prompt_audit.schema.json` (descriptions only),
  `docs/design/observability.md`, `queue/README.md`, `tests/test_stale_blockers_retired.py`,
  and `tests/test_seat_actors.py` (new).
- **SPEC, signed before the claim (`sign_off: brief`):** two passages in `docs/spec/04-observability.md`, each CURRENT at `76f41dd`.

    CURRENT (`docs/spec/04-observability.md` at `76f41dd`), §23.1, the table's seat-heartbeat row:
    > | Seat heartbeats | `observability/seats/<seat_id>.json` | Last wake and action of a scheduled seat (`event` for an event-only seat) |

    PROPOSED:
    > | Seat heartbeats | `observability/seats/<seat_id>.json` | A seat's last wake and action (§18.3) |

    CURRENT (`docs/spec/04-observability.md` at `76f41dd`), §23.3, its first line:
    > Folded from the ledger (the formulas are fixed; `scripts/observability/README.md` documents them):

    PROPOSED:
    > Folded from the ledger (the formulas are fixed):
- **Out:** which seats write heartbeats and when (§18.3, unchanged); the board; the move of `lib.py` (the roadmap's F17).

## dod_checks

- id: `code-01`
  story: As the plane, nothing I write names the retired watchdog or a seat cadence.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n -e delivery-watchdog -e cron_expected -e cron-expected -e default_cron -- ccp scripts plugin templates docs/design queue`.
  expect: prints exactly one line, `scripts/observability/lib.py`'s `LEGACY_ACTORS`.
  dry run (`76f41dd`): printed 25 lines (lib.py, heartbeat.sh, emit-event.sh, spec_maintainer.py, README.md, docs/design/observability.md).
- id: `cmd-01`
  story: As a reader of an old ledger, a watchdog row still folds, and as a writer I cannot record one.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_seat_actors 2>&1 | grep -e watchdog -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_seat_actors --mutant-file <file>`, the file's mutant dropping `LEGACY_ACTORS` from the read-side check in `validate_event`.
  expect: step 1 prints, each `ok`, a test where a ledger holding a `seat`/`heartbeat` row with actor `delivery-watchdog` folds with no error and the seat's `last_wake_at` set; one where `append_event` of a row with that actor is refused naming `invalid actor`; and one where `heartbeat.sh delivery-watchdog --wake-kind manual` exits 2 and `heartbeat.sh design-seat --wake-kind manual` exits 0 writing a seat file with no `cron_expected`; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the test module is new.
- id: `doc-01`
  story: As a reader of the observability scripts, there is one package doc and nothing points at the removed README.
  setup: A checkout of the PR head.
  steps:
    1. Run `test -e scripts/observability/README.md; echo "exists=$?"; git grep -n 'observability/README' -- ':!docs/delivery/tasks' ':!docs/delivery/reviews'; git grep -n README -- scripts/observability`.
    2. Run `CCP_DEV=1 ./bin/ccp docs check 2>&1 | tail -1`.
  expect: step 1 prints only `exists=1`; step 2's last line reports no failure.
  dry run (`76f41dd`): step 1 printed `exists=0`, 2 lines (§23.3 and `queue/README.md`), then lib.py's 2 lines.
- id: `cmd-02`
  story: As the plane's maintainer, the tests that read seats and the ledger still pass.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_stale_blockers_retired tests.test_event_registry tests.test_contract_writers tests.test_operator_rename 2>&1 | tail -1`.
  expect: prints `OK`.
  dry run (`76f41dd`): printed `OK`.
- id: `spec-01`
  story: As the operator, §23.1 and §23.3 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0283`.
  expect: exit 0, both PROPOSED passages found.
  dry run (simulated at `76f41dd`: this task file committed, then the 2 passages applied, each CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0283 --base HEAD~1`): `"ok": true`, 2 passage(s) found, none missing.

## Implementation notes

## Verification notes
