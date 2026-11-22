---
task_id: 0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s
title: The lead's three records refuse any caller whose ACTOR does not name the lead, the hooks and the test fence drop an inherited ACTOR, sign-offs count only the lead's, and a ruling id is never reused
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S13", "S17", "S23"]
rule_refs: ["E27"]
review_point: R25
paths: ["ccp/queue.py", "ccp/lifecycle.py", "ccp/selection.py", "ccp/followups.py", "ccp/verify.py", "plugin/hooks/run-binding.sh", "plugin/hooks/runner-idle.sh", "plugin/orientation.md", "docs/cli/02-delivery.md", "docs/ENGINEERING.md", "tests/__init__.py", "tests/helpers.py", "tests/test_seat_actor_env.py", "tests/test_lead_records.py", "tests/test_lead_ruling.py", "tests/test_marked_checks_loop.py", "tests/test_marked_checks_record.py", "tests/test_catch_up_decision.py", "tests/test_behind_tip_catch_up.py", "tests/test_followups.py", "tests/test_followups_closed_point.py", "tests/test_next_passes_over.py", "tests/test_prefer.py", "tests/test_review_points.py", "tests/test_session_park.py", "tests/test_sign_off.py", "tests/test_sign_off_beyond_intent.py", "tests/test_task_supply.py", "tests/test_toolkit.py", "tests/test_verify_spec_text.py", "tests/test_wait_reasons.py"]
clashes_with: ["0191-the-grace-release-ends", "0273-verify-refuses-early-what-record-would-refuse", "0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope", "0278-submit-takes-a-proven-fix-and-the-spec-names-what-ccp-writes", "0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log", "0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs", "0287-action-parsers-own-their-flags-and-describe-their-actions", "0289-the-runner-s-actor-id-is-named-once-and-tests-read-the-lead-s", "0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s

## Intent

A runner, worker or hook can no longer record a sign-off, a ruling or a follow-up's outcome as the
lead by leaving `ACTOR` unset or setting a value the plane does not know. Each of the lead's three
records runs only when `ACTOR` names the lead, and refuses every other caller with a message that
says how the lead runs it. The lead's orientation says so too. The plugin's hooks and the test fence
drop an `ACTOR` they inherit. Sign-offs count only when the lead recorded them, as rulings already do.
A new ruling is numbered from every recorded ruling of its task, so no id is reused. Every other
event records the same actor as today.

## Context (not checked)

Measured at `329ff75` unless a line says otherwise.

Follow-ups covered (the lead's worker follow-up log):
`0272-the-lead-s-records-share-one-guard-and-one-actor-id/review#1` (seats set no `ACTOR`),
`…/review#2` (`queue.sign_offs`), `…/implement#1` (ruling numbering), `…/implement#4` (a test helper
that runs `ccp` as the lead), `…` there being `0272-the-lead-s-records-share-one-guard-and-one-actor-id`.

- **Where `ACTOR` is set.** No seat sets it when it starts: `git grep -nw ACTOR -- plugin templates` at `329ff75`: 0 lines. The only line that sets it is a docs example, `export ACTOR=task-runner` in `scripts/observability/README.md`.
- **Where it is read.** `git grep -lw ACTOR -- ccp scripts plugin templates` at `329ff75`: 12 files. In `ccp/`: `"def actor"` and `"def lead_actor"` in `ccp/queue.py`, and `os.environ.get("ACTOR")` in `ccp/cli.py`, `ccp/health.py` and `ccp/prompt.py`; in `scripts/`: the writers (`emit-event.sh`, `set-waiting-on.sh`, `write-prompt-audit.sh`, `heartbeat.sh`'s help), `architecture_review.py`, `spec_maintainer.py` and `spec-maintainer-ask.sh`.
- **Why an unset `ACTOR` records as the lead.** `queue.lead_actor` calls `actor(lib.LEAD)`, which returns
  the default, the lead, when `ACTOR` is unset or names no known actor. So a runner that runs
  `ccp tasks ruling` with no `ACTOR` records the ruling as the lead, and so does `ACTOR=task-lead` (a value
  `test_lead_ruling`, `test_marked_checks_loop` and `test_marked_checks_record` use today).
- **The lead's ruling on how seats name themselves.** Refusing an unset or unknown `ACTOR` closes the hole on its
  own: no worker or runner records as the lead without writing `design-seat`. So worker prompts and the runner's
  spawn prompt do not change, and every other event keeps the actor it records today (`"def actor"`'s default,
  the runner), which leaves the board's runner activity (`seats._last_event(…, "task-runner")`) as it is.
- **The hooks.** `plugin/hooks/run-binding.sh` (`ccp agent start|stop`) and `plugin/hooks/runner-idle.sh` inherit the session process's environment, so an `ACTOR` exported there would reach them; `grep -c 'subprocess.run(\[' plugin/hooks/runner-idle.sh` at `329ff75`: 4 calls (`where`, `tasks rotation-due`, `tasks list`, `tasks next`).
- **The test fence.** `tests/__init__.py` pops `QUEUE_ROOT` and `PROJECT_YAML` ("a seat's exported queue and binding never reach a test") but not `ACTOR`: `python3 -B -c "import os; os.environ['ACTOR']='design-seat'; import tests; print(os.environ.get('ACTOR'))"` at `329ff75` printed `design-seat`. Under the new guard, an `ACTOR` a developer's shell exports would change which tests refuse.
- **Sign-offs.** `"def sign_offs"` in `ccp/queue.py` keeps every `sign_off` `recorded` event of the task,
  whoever recorded it, while `"def rulings"` keeps only the lead's (E27: "a reader counts only that seat's
  records"). No live record changes: every `sign_off` `recorded` event in the bound queues' ledgers has
  actor `design-seat` (0272's measurement at `5fa9ff03`, data only the queues hold).
- **Ruling numbers.** `"def ruling"` in `ccp/lifecycle.py` computes `n = len(rulings(q, tid)) + 1`, from the
  lead's rulings only, so a ruling event another actor wrote would leave its id free for the next lead ruling.
- **The lead's command hints.** `git grep -n '`ccp tasks sign-off \|`ccp tasks follow-up {' -- ccp` at `329ff75`: 5 lines (`ccp/lifecycle.py` 3, `ccp/selection.py` 1, `ccp/followups.py` 1), each printing the command the lead runs; and `git grep -n '(ccp tasks ruling)' -- ccp/verify.py` at `329ff75`: 1 line, in the refusal of a waiver whose ruling is not recorded.
- **Tests that break.** Probed at `ba58161` in a scratch clone with `lead_actor` refusing unless `ACTOR` is the lead and `sign_offs` keeping only the lead's (`GATE_COLD=1 python3 scripts/gate_parallel.py`, 210 modules): 5 modules failed, `tests.test_catch_up_decision` (its fixture writes a `sign_off` event with no actor), `tests.test_lead_records` (two tests hold the old unset-is-the-lead rule), `tests.test_lead_ruling`, `tests.test_marked_checks_loop` and `tests.test_marked_checks_record` (`ACTOR=task-lead`).
- **Tests that set the lead's actor by hand.** `git grep -nE '"ACTOR": (lib\.LEAD|"design-seat"|"task-lead")' -- tests` at `329ff75`: 17 lines in 16 files (the test modules in `paths` after `tests/test_catch_up_decision.py`, plus `test_lead_ruling` and the two marked-checks modules).
- **No SPEC change.** `git grep -inw 'actor' -- docs/spec` at `329ff75`: 5 lines, none on how a `ccp` call names its seat or what an unset `ACTOR` records: §3.6's `by` of a `notify` `sent` (`$ACTOR` when it names a ledger actor, else `design-seat`; 2 lines, `ccp notify`, which this task leaves alone), §23.2's event field `actor` (1 line), and §31.5's `plane-session` triage actor (2 lines). The SPEC already gives the three records to the lead (§3.5, §13.4, §17.5, as 0272 measured); how a call names its seat is the command's mechanics, stated in `docs/cli/02-delivery.md`.
- **E27's text.** `docs/ENGINEERING.md`'s E27 says "A command the SPEC gives to one seat refuses another seat's
  ACTOR through one shared guard"; after this task the guard refuses every `ACTOR` that does not name that seat.
- **Other tasks on these files.** 0191 (R13), 0273, 0282, 0283 and 0287 change other code in `ccp/lifecycle.py`,
  `ccp/queue.py` or `tests/test_session_park.py`; 0275 and 0278 change other rows of `docs/cli/02-delivery.md` (0275 also
  `tests/test_review_points.py`); 0289 and 0290 change some of the same test modules and
  `docs/ENGINEERING.md` or `tests/helpers.py`. Recorded as clashes, since the paths overlap.

### Rulings for the build (the lead's)

- **The guard.** `queue.lead_actor(what)` reads `ACTOR` itself and returns the lead's id only when `ACTOR`
  is exactly the lead's (`lib.LEAD`). Unset, empty, unknown or another seat's id is refused, exit 2, nothing
  read or written: "only the lead records {what} (ACTOR is {value, or `unset`}): the lead runs it as
  ACTOR={lib.LEAD} ccp …; any other seat tells the lead". `queue.actor` is unchanged.
- **The hints.** The six hint lines above print the command with `ACTOR={lib.LEAD} ` before `ccp`
  (verify.py's becomes "(`ACTOR=design-seat ccp tasks ruling`)", built from `lib.LEAD`).
- **The orientation.** `plugin/orientation.md`'s team-lead paragraph gains one line: "The lead's three records
  (`ccp tasks sign-off`, `tasks ruling`, `tasks follow-up`) run as `ACTOR=design-seat ccp …`, per command; never
  export ACTOR in the session."
- **The hooks.** `run-binding.sh` unsets `ACTOR` before it runs `ccp`, and `runner-idle.sh`'s Python drops
  `ACTOR` from its environment before the first of its four `ccp` calls, so each records as `queue.actor`'s
  default, as today, whatever the session exports.
- **The fence.** `tests/__init__.py` pops `ACTOR` with `QUEUE_ROOT` and `PROJECT_YAML`.
- **Sign-offs.** `queue.sign_offs` keeps a `sign_off` `recorded` event only when its `actor` is `lib.LEAD`.
- **Ruling numbers.** `queue.rulings` gains a keyword `lead_only: bool = True`; `lifecycle.ruling` numbers
  from `rulings(q, tid, lead_only=False)`. Every other reader keeps the lead-only list.
- **The lead's environment in tests.** `tests/helpers.py` gains `LEAD_ENV = {"ACTOR": lib.LEAD}` and
  `as_lead()`, which returns `mock.patch.dict(os.environ, LEAD_ENV)`. Every test that sets the lead's actor
  uses one of them; `ACTOR=task-lead` goes. `tests/test_lead_records.py`'s unset-is-the-lead tests become
  unset-is-refused tests. `tests/test_catch_up_decision.py`'s fixture event carries `"actor": lib.LEAD`.
- **E27.** Its second sentence becomes "A command the SPEC gives to one seat refuses, through one shared guard,
  every ACTOR that does not name that seat (unset or unknown included)". Its `check:` line is unchanged.
- **The docs.** The `ccp tasks sign-off`, `ccp tasks ruling` and `ccp tasks follow-up` rows of
  `docs/cli/02-delivery.md` say "needs `ACTOR=design-seat`; refused, exit 2, when `ACTOR` is unset or names
  any other value" in place of "refused, exit 2, when `ACTOR` names another seat".

## Scope

- **In:** `ccp/queue.py` (`lead_actor`, `sign_offs`, `rulings`), `ccp/lifecycle.py` (`ruling`, the hints),
  `ccp/selection.py`, `ccp/followups.py` and `ccp/verify.py` (the hints), `plugin/hooks/run-binding.sh`,
  `plugin/hooks/runner-idle.sh`, `plugin/orientation.md`, `docs/cli/02-delivery.md`, `docs/ENGINEERING.md` (E27's
  text), `tests/__init__.py`, `tests/helpers.py`, `tests/test_seat_actor_env.py` (new), and the test modules in `paths`.
- No SPEC change (measured in Context).
- **Out:** worker prompts, the runner's spawn prompt and brief; the actor of any event other than the three
  records; `"def _actor_for"` in `ccp/report.py` and `ccp/suite.py`; the `"task-runner"` literals and the
  tests' `"design-seat"` literals (task 0289); `ccp notify`'s `by`; who may run the lead's other commands.

## dod_checks

- id: `code-01`
  story: As the lead, only a caller whose ACTOR names me records a sign-off, a ruling or a follow-up's outcome; an unset or unknown ACTOR is refused as another seat's is.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_lead_records 2>&1 | grep -e unset -e unknown -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_lead_records --mutant-file <file>`, the file's mutant making `lead_actor` accept an unset `ACTOR` as the lead again.
  expect: step 1 lists, each `ok`, a test where with `ACTOR` unset each of `tasks sign-off`, `tasks ruling` and `tasks follow-up` exits 2 with `only the lead records` and `ACTOR=design-seat` and adds no event, and one where `ACTOR=task-lead` does the same, their names holding `unset` and `unknown`; then `OK`. Step 2 prints the mutant `killed`.
  dry run (`329ff75`): step 1 printed only `OK` (no test names an unset or unknown ACTOR yet; the refusal tests are new).
- id: `code-02`
  story: As the runner, the plugin's hooks record as they do today even when the session's process exports the lead's ACTOR.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_seat_actor_env 2>&1 | grep -e hook -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_seat_actor_env --mutant-file <file>`, the file's mutant removing the line in `plugin/hooks/run-binding.sh` that unsets `ACTOR`.
  expect: step 1 lists, each `ok`, a test where `run-binding.sh start`, run with `ACTOR=design-seat` and a stub `ccp` on PATH that writes the `ACTOR` it sees to a file, leaves that file reading unset, and the same for each of `runner-idle.sh`'s four `ccp` calls, each name holding `hook`; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `code-03`
  story: As a plane developer, an ACTOR my shell exports never reaches a test.
  setup: A checkout of the PR head; run from its root.
  steps:
    1. Run `python3 -B -c "import os; os.environ['ACTOR']='design-seat'; import tests; print(os.environ.get('ACTOR'))"`.
  expect: prints `None`.
  dry run (`329ff75`): printed `design-seat`.
- id: `code-04`
  story: As the lead, a sign-off another seat recorded does not stand for the operator's.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_lead_records 2>&1 | grep -e sign_off -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_lead_records --mutant-file <file>`, the file's mutant dropping the actor condition from `"def sign_offs"`.
  expect: step 1 lists, `ok`, a test where a ledger holding a `sign_off` `recorded` event (stage `brief`) with actor `task-runner` gives `queue.sign_offs` no `brief` entry, and one where the same event with actor `design-seat` gives it, each name holding `sign_off`; then `OK`. Step 2 prints the mutant `killed`.
  dry run (`329ff75`): step 1 printed only `OK` (the tests are new).
- id: `code-05`
  story: As a verifier citing a ruling, a ruling id names one ruling only, whoever recorded the earlier ones.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_lead_records 2>&1 | grep -e number -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_lead_records --mutant-file <file>`, the file's mutant making `lifecycle.ruling` number from the lead-only list again.
  expect: step 1 lists, `ok`, a test where a ledger holding a `ruling` `recorded` event `<task>-r1` with actor `task-runner` makes the lead's next `ccp tasks ruling` on that task print and record the id `<task>-r2`, its name holding `number`; then `OK`. Step 2 prints the mutant `killed`.
  dry run (`329ff75`): step 1 printed only `OK` (the test is new).
- id: `test-01`
  story: As a plane developer, a test runs `ccp` as the lead through one shared helper.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nE '"ACTOR": (lib\.LEAD|"design-seat"|"task-lead")' -- tests ':(exclude)tests/helpers.py'`.
    2. Run `git grep -nE '^LEAD_ENV = |^def as_lead' -- tests`.
  expect: step 1 prints nothing (exit 1); step 2 prints exactly two lines, both in `tests/helpers.py`.
  dry run (`329ff75`): step 1 printed 17 lines in 16 files; step 2 printed nothing.

## Implementation notes

## Verification notes
