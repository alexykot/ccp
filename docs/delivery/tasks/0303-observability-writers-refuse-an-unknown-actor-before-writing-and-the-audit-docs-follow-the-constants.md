---
task_id: 0303-observability-writers-refuse-an-unknown-actor-before-writing-and-the-audit-docs-follow-the-constants
title: The prompt-audit writer refuses an actor the ledger would refuse, heartbeat.sh validates before it writes the seat file, validate_event loses its unused reading keyword while a test holds the schemas' actor enums, and the audit docs describe keep_body and audit_keep_days as constants
status: pending
kind: feature
depends_on: []
spec_refs: ["S23", "S29"]
rule_refs: ["E9"]
review_point: R26
paths: ["scripts/observability/lib.py", "scripts/observability/heartbeat.sh", "scripts/observability/write-prompt-audit.sh", "scripts/observability/emit-event.sh", "scripts/observability/prune-prompts.sh", "ccp/prompt.py", "docs/design/observability.md", "tests/test_seat_actors.py", "tests/test_event_registry.py", "tests/test_prompt_audit.py"]
clashes_with: ["0191-the-grace-release-ends", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once", "0296-the-spec-question-script-loads-the-product-config-once-and-reads-its-task-dir"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0303-observability-writers-refuse-an-unknown-actor-before-writing-and-the-audit-docs-follow-the-constants

## Intent

The observability writers leave nothing behind for an actor the ledger refuses. `write-prompt-audit.sh`
refuses an `ACTOR` or `--actor` that is not one of the actors the plane writes as (so the retired
watchdog can no longer write an audit), and `ccp prompt` passes the actor it records as, so a session
with a stray `ACTOR` still gets its audit. `heartbeat.sh` checks the event before it writes the seat
file, so a refused actor leaves no seat file. `validate_event` loses the `reading` keyword no reader
calls, and a test holds both contracts' `actor` enums to the actors written plus the legacy ones, as it
holds the event types. `emit-event.sh`'s usage drops its seat-heartbeat example. And the design doc and
`prune-prompts.sh` describe `prompts.keep_body` and `prompts.audit_keep_days` as what they are, constants
a product may still set, matching SPEC §23.8.

## Context (not checked)

Covers these follow-ups of 0283 (`ccp --root . tasks follow-ups --open`), all `0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs/…`:

- `implement#1`, `review#1`, `fix#1`, `verify#1`: no ledger reader calls `validate_event(..., reading=True)`.
- `review#2`, `fix#2`, `verify#2`: `write-prompt-audit.sh` writes an unchecked actor.
- `implement#2`: `heartbeat.sh` writes the seat file before the event append.
- `implement#3`: SPEC §23.8 and `docs/design/observability.md` disagree on `prompts.audit_keep_days`.
- The lead's note on 0283's implementation note: `emit-event.sh`'s example emits as `task-verifier` only because E27's
  command refuses a `"task-runner"` literal outside `lib.py`.

Measured at `7a2993b` (origin/main).

- **`reading` has no caller.** `git grep -nw reading -- scripts/observability/lib.py tests/test_seat_actors.py` at `7a2993b`: 4 lines,
  the signature, docstring and check in `"def validate_event"` and the one test call; `git grep -n 'validate_event' -- ccp scripts` at `7a2993b`:
  `append_event`, `ccp/queue.py`'s `emit` and `ccp/lifecycle.py`'s pre-check, all writers. The board fold and `ccp doctor` read
  rows without validating them.
- **What a validating reader would refuse.** Read-only, on 2026-11-22, each live ledger counted (the rows failing, then all rows):
  - this plane's own: `python3 -B -c 'import json,sys;sys.path.insert(0,"scripts/observability");import lib;print(sum(1 for l in open(sys.argv[1]) if l.strip() and lib.validate_event(json.loads(l), reading=True)))' <ledger>` at `7a2993b`: 1153 of 17262 rows;
  - a bound product's, the same `python3 -B -c` command at `7a2993b`: 1600 of 42678 rows.
  - The causes, from the same loop printing each error (`lib.validate_event(ev, reading=True)` per row at `7a2993b`): `payload missing unbuilt` (rows from before that payload key was required) on all failing rows but 2, which hold a type no longer registered.
  - The product's watchdog rows (`python3 -B -c '…print(sum(1 for l in open(sys.argv[1]) if l.strip() and json.loads(l).get("actor") in lib.LEGACY_ACTORS))' <ledger>` at `7a2993b`: 91 rows) pass with `reading=True` and fail without it, but no reader needs that: the fold reads every row as it is.

  A reader that validated would refuse a large share of history for reasons that have nothing to do with actors, so none should. The keyword goes; `LEGACY_ACTORS` stays, as
  `LEGACY_EVENT_TYPES` does, the value list a test holds the contracts to (E9).
- **The contracts' actor enums.** Both `contracts/observability_event.schema.json` and `contracts/prompt_audit.schema.json` list
  `task-runner`, `task-verifier`, `delivery-watchdog`, `design-seat`, `adapter`, `operator`, `system`, `plane-session`, which is
  `lib.ACTORS + lib.LEGACY_ACTORS` as a set; `tests/test_event_registry.py` holds the type and op enums to `lib`, not the actor enum
  (`git grep -n actor -- tests/test_event_registry.py` at `7a2993b`: no line).
- **The audit's actor.** `write-prompt-audit.sh` writes `os.environ.get("ACTOR_IN") or "task-runner"`, unchecked. A probe at `7a2993b`
  in a scratch queue: `echo hi | QUEUE_ROOT=<scratch> ACTOR=delivery-watchdog bash scripts/observability/write-prompt-audit.sh --task-id t1 --phase estimate --prompt-file - --project-id demo`
  exited 0 and wrote `"actor": "delivery-watchdog"`. Its callers: `ccp/architect.py` (`ar.actor_of`, which falls back to a known
  actor), `ccp/estimator.py` (`"system"` by default), `scripts/observability/team.py` (`LEAD`, three calls) and `ccp/prompt.py`'s
  `"def audit"`, which passes no `--actor`, so the audit takes the session's `ACTOR` as it is (`git grep -n 'write-prompt-audit' -- ccp scripts` at `7a2993b`).
- **The heartbeat's order.** A probe at `7a2993b`: `QUEUE_ROOT=<scratch> PROJECT_ID=demo bash scripts/observability/heartbeat.sh task-runner --actor delivery-watchdog`
  exited 1 (`invalid event: invalid actor 'delivery-watchdog'`) and left `observability/seats/task-runner.json`.
- **The emit example.** `git grep -n 'task-verifier' -- scripts/observability/emit-event.sh` at `7a2993b`: 2 lines, the second usage example
  (a `seat`/`heartbeat` event). `heartbeat.sh` is the seat-heartbeat writer, and E27's command (in `docs/delivery/plane.json`) refuses
  a `"task-runner"` literal in `scripts` outside `lib.py`, which is why 0283 wrote `task-verifier` there. The example is dropped, not reworded.
- **§23.8 and the code agree; the design doc does not.** SPEC §23.8: "The full prompt text (`prompt_body`) is not kept" and "Every
  prompt audit is kept: `ccp prompt` prunes none." Since 0192, `prompts.keep_body` and `prompts.audit_keep_days` are constants
  (ADR-0043 D9): `ccp/config.py`'s `_CONSTANT_KEYS` lists both, at `False` and `None`; a value a product still sets applies, and
  `ccp upgrade status` lists it (SPEC §8.1, §29.3). `"def prune_audits"` in `ccp/prompt.py` returns 0 when `audit_keep_days` is null,
  so by default nothing is pruned, as §23.8 says (`tests/test_prompt_audit.py`'s `test_without_a_retention_age_every_audit_is_kept`).
  0189 wrote §23.8 that way on purpose (the SPEC states behaviour, not a knob's default). What disagrees is non-normative text that
  still presents both keys as settings to choose:
  `git grep -n -e 'Set .audit_keep_days' -e 'has .ccp prompt. remove' -e 'is opt-in (.prompts.keep_body' -- docs/design/observability.md` at `7a2993b`: 3 lines;
  `git grep -n 'Retention by age is plane.json' -- scripts/observability/prune-prompts.sh` at `7a2993b`: 2 lines (its header and usage);
  `ccp/prompt.py`'s module docstring ("audits older than `prompts.audit_keep_days` are pruned"). So the docs change, not the SPEC or the code.
- **No SPEC change.** `git grep -n 'reading=\|LEGACY_ACTORS\|validate_event\|audit_keep_days\|keep_body' -- docs/spec` at `7a2993b`: no line.
  §23.2 already names the actors ("Actors are seat ids …, `operator` and `system`"); a writer refusing any other follows it.
- **Breaking modules.** A scratch worktree at `7a2993b` with every change below and 0302's applied ran `GATE_COLD=1 scripts/gate.sh`: 222 modules, 3837 tests, all passed once `tests/test_seat_actors.py` dropped its one `reading=True` call. No other module breaks.
- **Other tasks.** 0293 (pending) adds `VERIFIER` to `lib.py` and widens E27's command to exclude `scripts/**/*.sh` by glob; this
  task leaves E27's command alone and reads `RUNNER` and `ACTORS` from `lib`, so its shell scripts hold no new seat literal either
  way. 0296 (pending) changes `spec_maintainer.py`'s config loading, 0285 (signed) changes `ccp/prompt.py`'s lane text, 0191 (pending)
  config keys: different logic, recorded as clashes since paths meet.

### Rulings for the build (the lead's)

- **`validate_event`.** Its `reading` keyword and the docstring sentence about it go; the actor check reads `ACTORS` only.
  `LEGACY_ACTORS` and its comment stay. `tests/test_seat_actors.py`'s
  `test_a_ledger_holding_a_watchdog_row_folds_with_the_seats_last_wake` drops its `validate_event(..., reading=True)` assertion and keeps
  the fold's; the module docstring's "still validates and folds" reads "still folds".
- **The actor enums.** `tests/test_event_registry.py` gains
  `test_each_schemas_actors_are_the_writer_actors_and_the_legacy_ones`: for both contracts, the `actor` enum has no duplicate and
  its set equals `{*lib.ACTORS, *lib.LEGACY_ACTORS}`, and `set(lib.ACTORS) & set(lib.LEGACY_ACTORS)` is empty. Its module docstring
  adds the actor enums.
- **The audit's actor.** `write-prompt-audit.sh`'s Python imports `ACTORS` and `RUNNER` from `lib`, takes
  `actor = os.environ.get("ACTOR_IN") or RUNNER` before it reads the prompt, and on an actor not in `ACTORS` calls
  `die(f"invalid actor {actor!r}")` (exit 1, as `append_event` exits), writing nothing; the audit's `"actor"` is that value.
  `ccp/prompt.py`'s `"def audit"` passes `"--actor", actor()` (`ccp.queue`'s, which falls back to the runner for an unknown `ACTOR`).
  `tests/test_prompt_audit.py` gains, in `Writer`, `test_an_actor_the_ledger_refuses_writes_no_audit` (`ACTOR=delivery-watchdog` in the
  env, then `--actor nobody`: each exits non-zero with `invalid actor` on stderr and no file under the queue; `--actor` `lib.LEAD`
  writes one naming it), and in `PromptAudit`, `test_a_stray_actor_in_the_env_audits_as_the_runner` (`ACTOR=nobody` patched into
  `os.environ` around `render`: the audit's `actor` is `lib.RUNNER`). Tests read the ids from `lib`, never as literals (E27).
- **The heartbeat.** `heartbeat.sh` builds the event, calls `validate_event` on it, and on any error dies with
  `"invalid event: " + "; ".join(errors)` (as `append_event` does) before `write_json` writes the seat file; then it writes the seat
  file and appends as today. `tests/test_seat_actors.py` gains `test_a_refused_actor_leaves_no_seat_file`
  (`heartbeat.sh task-runner --actor delivery-watchdog`: exit 1, no `seats/task-runner.json`, no ledger).
- **The emit example.** The second example of `emit-event.sh`'s usage (the two lines from `emit-event.sh --type seat`) goes.
- **The audit docs.** In `docs/design/observability.md`, the paragraph from "`prompt_body` is opt-in" to "`prune-prompts.sh` prunes on
  demand." becomes:

  > `prompts.keep_body` and `prompts.audit_keep_days` are constants (ADR-0043 D9): an audit holds the hash and the length, never
  > the body, and an `argv` entry that is the prompt itself reads `<prompt>`; every audit is kept (SPEC §23.8). A product that
  > still sets either key gets its value until it deletes the key, and `ccp upgrade status` lists it (SPEC §29.3):
  > `keep_body: true` keeps the body, and `audit_keep_days: N` has `ccp prompt` remove audits older than N days, by the stamp in
  > the file name, each time it writes one; the rendered prompt and env files beside them are not audits and stay. Health's
  > prompt sizes (§27.1) read `prompt_chars`, or the body's length in an audit from before it. `prune-prompts.sh` prunes on demand.

  and the sentence "Set `audit_keep_days` above the longest life of a task, from its first launch to its close, so no audit of a task
  still measured is pruned." becomes "A product that still sets `audit_keep_days` keeps it above the longest life of a task, from its
  first launch to its close, so no audit of a task still measured is pruned."
  `prune-prompts.sh`'s header comment and usage paragraph read "Every prompt audit is kept (SPEC §23.8); this script prunes on demand.
  A product that still sets the constant plane.json prompts.audit_keep_days (SPEC §29.3) has `ccp prompt` prune by age too.", and its
  "nothing selected" line reads `prune-prompts: nothing selected (every audit is kept unless pruned here: SPEC §23.8).`
  `ccp/prompt.py`'s module docstring reads "(the full text only under a still-set `prompts.keep_body`; audits older than a still-set
  `prompts.audit_keep_days` are pruned, §29.3)".

## Scope

- **In:** `scripts/observability/lib.py` (`validate_event`), `scripts/observability/heartbeat.sh`,
  `scripts/observability/write-prompt-audit.sh`, `scripts/observability/emit-event.sh` (its usage),
  `scripts/observability/prune-prompts.sh` (its comment, usage and one message), `ccp/prompt.py` (`"def audit"` and the module
  docstring), `docs/design/observability.md`, `tests/test_seat_actors.py`, `tests/test_event_registry.py`, `tests/test_prompt_audit.py`.
- No SPEC change (Context's grep): §23.8 already matches the code.
- **Out:** the contracts (their enums and descriptions stay); E27's command and `docs/ENGINEERING.md` (0293); `ccp/config.py`;
  the board fold and `ccp doctor` (they keep reading rows unvalidated); the `prompt_body` line of the design doc's audit example.

## dod_checks

- id: `code-01`
  story: As a plane developer, validate_event has only a writer's reading, and the contracts' actor enums are held to lib's actors.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `git grep -nw reading -- scripts/observability/lib.py tests/test_seat_actors.py`.
    2. Run `python3 -B -m unittest -v tests.test_event_registry tests.test_seat_actors 2>&1 | grep -e actors_are -e watchdog_row_folds -e '^OK'`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_event_registry --mutant 'contracts/observability_event.schema.json:"delivery-watchdog",=>'`.
  expect: step 1 prints nothing (exit 1); step 2 lists `test_each_schemas_actors_are_the_writer_actors_and_the_legacy_ones` `ok` and `test_a_ledger_holding_a_watchdog_row_folds_with_the_seats_last_wake` `ok`, then `OK`; step 3 prints the mutant `killed`.
  dry run (`7a2993b`): step 1 printed 4 lines (Context); `python3 -B -m unittest -v tests.test_event_registry 2>&1 | grep -c actors_are` printed `0`.
- id: `cmd-01`
  story: As the plane, no prompt audit names an actor the ledger would refuse, and ccp prompt still audits under a stray ACTOR.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prompt_audit 2>&1 | grep -e ledger_refuses -e stray_actor -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_prompt_audit --revert scripts/observability/write-prompt-audit.sh --revert ccp/prompt.py`.
  expect: step 1 lists `test_an_actor_the_ledger_refuses_writes_no_audit` `ok` and `test_a_stray_actor_in_the_env_audits_as_the_runner` `ok`, then `OK`; step 2 prints both mutants `killed`.
  dry run (`7a2993b`): the write-prompt-audit probe of Context exited 0 and wrote `"actor": "delivery-watchdog"`.
- id: `cmd-02`
  story: As a seat, a heartbeat the ledger refuses leaves no seat file.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_seat_actors 2>&1 | grep -e leaves_no_seat_file -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_seat_actors --revert scripts/observability/heartbeat.sh`.
  expect: step 1 lists `test_a_refused_actor_leaves_no_seat_file` `ok`, then `OK`; step 2 prints the mutant `killed`.
  dry run (`7a2993b`): the heartbeat probe of Context exited 1 and left `observability/seats/task-runner.json`.
- id: `doc-01`
  story: As a reader, the emit usage shows no seat example and the audit docs describe the two keys as constants, as §23.8 does.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n 'task-verifier' -- scripts/observability/emit-event.sh; git grep -n -e 'Set .audit_keep_days' -e 'has .ccp prompt. remove' -e 'is opt-in (.prompts.keep_body' -- docs/design/observability.md; git grep -n 'Retention by age is plane.json' -- scripts/observability/prune-prompts.sh`.
    2. Run `tr '\n' ' ' < docs/design/observability.md | tr -s ' ' | grep -c 'are constants (ADR-0043 D9)'`.
    3. Run `CCP_DEV=1 ./bin/ccp docs check 2>&1 | tail -1`.
  expect: step 1 prints nothing; step 2 prints `1`; step 3's last line reports no failure.
  dry run (`7a2993b`): step 1 printed 7 lines (2 in `emit-event.sh`, 3 in the design doc, 2 in `prune-prompts.sh`); step 2 printed `0`.

## Implementation notes

## Verification notes
