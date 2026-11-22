---
task_id: 0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s
title: Every seat that records names its ACTOR, the lead's three records refuse a caller that does not name the lead, sign-offs count only the lead's, and a ruling id is never reused
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S13", "S17", "S23"]
rule_refs: ["E27"]
review_point: R25
paths: ["ccp/queue.py", "ccp/lifecycle.py", "ccp/selection.py", "ccp/followups.py", "ccp/prompt.py", "ccp/report.py", "ccp/suite.py", "scripts/observability/lib.py", "scripts/observability/team.py", "plugin/hooks/run-binding.sh", "plugin/hooks/runner-idle.sh", "plugin/agents/delivery-runner.md", "templates/prompts/_common.md", "templates/prompts/implement.md", "templates/prompts/review.md", "templates/prompts/verify.md", "docs/cli/02-delivery.md", "tests/helpers.py", "tests/test_seat_actor_env.py", "tests/test_lead_records.py", "tests/test_lead_ruling.py", "tests/test_marked_checks_loop.py", "tests/test_marked_checks_record.py", "tests/test_catch_up_decision.py", "tests/test_behind_tip_catch_up.py", "tests/test_followups.py", "tests/test_followups_closed_point.py", "tests/test_next_passes_over.py", "tests/test_prefer.py", "tests/test_review_points.py", "tests/test_session_park.py", "tests/test_sign_off.py", "tests/test_sign_off_beyond_intent.py", "tests/test_task_supply.py", "tests/test_toolkit.py", "tests/test_verify_spec_text.py", "tests/test_wait_reasons.py"]
clashes_with: ["0273-verify-refuses-early-what-record-would-refuse", "0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope", "0278-submit-takes-a-proven-fix-and-the-spec-names-what-ccp-writes", "0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log", "0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes", "0287-action-parsers-own-their-flags-and-describe-their-actions", "0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s

## Intent

A runner, worker or hook can no longer record a sign-off, a ruling or a follow-up's outcome as the
lead by leaving `ACTOR` unset. Each of the lead's three records needs `ACTOR` to name the lead, and
refuses any other caller with a message that says how the lead runs it. Every seat that records sets
its own actor: the runner's spawn prompt names it, every worker prompt's `ccp` commands carry it, and
the plugin's hooks run `ccp` as the runner. Sign-offs count only when the lead recorded them, as
rulings already do. A new ruling is numbered from every recorded ruling of the task, so no id is
reused.

## Context (not checked)

Measured at `329ff75` unless a line says otherwise.

Follow-ups covered (the lead's worker follow-up log):
`0272-the-lead-s-records-share-one-guard-and-one-actor-id/review#1` (seats set no `ACTOR`),
`…/review#2` (`queue.sign_offs`), `…/implement#1` (ruling numbering), `…/implement#4` (a test helper
that runs `ccp` as the lead), `…` there being `0272-the-lead-s-records-share-one-guard-and-one-actor-id`.

- **Where `ACTOR` is set.** Nowhere a seat starts: `git grep -nw ACTOR -- plugin templates` at `329ff75`: 0 lines.
  The only line that sets it is a docs example, `export ACTOR=task-runner` in `scripts/observability/README.md`.
- **Where it is read.** `git grep -lw ACTOR -- ccp scripts plugin templates` at `329ff75`: 12 files. In
  `ccp/`: `"def actor"` and `"def lead_actor"` in `ccp/queue.py`, and `os.environ.get("ACTOR")` in `ccp/cli.py`,
  `ccp/health.py` and `ccp/prompt.py`; in `scripts/`: the writers (`emit-event.sh`, `set-waiting-on.sh`,
  `write-prompt-audit.sh`, `heartbeat.sh`'s help), `architecture_review.py`, `spec_maintainer.py` and
  `spec-maintainer-ask.sh`.
- **Why an unset `ACTOR` records as the lead.** `queue.lead_actor` calls `actor(lib.LEAD)`, which returns
  the default, the lead, when `ACTOR` is unset or names no known actor. So a runner that runs
  `ccp tasks ruling` with no `ACTOR` records the ruling as the lead, and so does `ACTOR=task-lead` (a value
  `test_lead_ruling`, `test_marked_checks_loop` and `test_marked_checks_record` use today). Every other
  event's default is the runner (`"def actor"`'s default is `"task-runner"`), so the hooks already record as
  the runner when they inherit no `ACTOR`.
- **How the seats start.** The runner is spawned with the prompt `"def spawn_prompt"` in `scripts/observability/team.py` builds, and its brief (`plugin/agents/delivery-runner.md`) says each `ccp` command runs "with `QUEUE_ROOT=<queue root>` and `--root` your runner worktree". A worker's commands are the rendered prompt's: `git grep -c 'QUEUE_ROOT={{queue_root}} {{ccp}}' -- templates` at `329ff75`: 17 lines (`_common.md` 5, `implement.md` 1, `review.md` 4, `verify.md` 7). The hooks `plugin/hooks/run-binding.sh` (`ccp agent start|stop`) and `plugin/hooks/runner-idle.sh` (three `subprocess.run([ccp, …])` calls: `grep -c 'subprocess.run(\[ccp' plugin/hooks/runner-idle.sh` at `329ff75`: 3) inherit the session's environment, so an `ACTOR` the session's process holds reaches them.
- **The seat's actor.** `ccp/report.py` and `ccp/suite.py` each define `"def _actor_for"`: the verifier
  records as `task-verifier`, every other worker as the runner. `runs.SEAT` maps a phase to its seat.
- **Sign-offs.** `"def sign_offs"` in `ccp/queue.py` keeps every `sign_off` `recorded` event of the task,
  whoever recorded it, while `"def rulings"` keeps only the lead's (E27: "a reader counts only that seat's
  records"). No live record changes: every `sign_off` `recorded` event in the bound queues' ledgers has
  actor `design-seat` (0272's measurement at `5fa9ff03`, data only the queues hold), and the guard has written
  none by another actor since.
- **Ruling numbers.** `"def ruling"` in `ccp/lifecycle.py` computes `n = len(rulings(q, tid)) + 1`, from the
  lead's rulings only, so a ruling event another actor wrote would leave its id free for the next lead ruling.
- **The lead's command hints.** `git grep -n '`ccp tasks sign-off \|`ccp tasks follow-up {' -- ccp` at `329ff75`: 5 lines (`ccp/lifecycle.py` 3, `ccp/selection.py` 1, `ccp/followups.py` 1), each printing the command the lead runs.
- **Tests that break.** Probed at `ba58161` in a scratch clone, with `lead_actor` refusing unless `ACTOR` is the lead, `sign_offs` keeping only the lead's, the 17 template lines carrying `ACTOR={{actor}}` and the spawn prompt's actor line (`GATE_COLD=1 python3 scripts/gate_parallel.py`, 210 modules): 5 modules failed, `tests.test_catch_up_decision` (its fixture writes a `sign_off` event with no actor), `tests.test_lead_records` (two tests hold the old unset-is-the-lead rule), `tests.test_lead_ruling`, `tests.test_marked_checks_loop` and `tests.test_marked_checks_record` (`ACTOR=task-lead`). No prompt or spawn-prompt test failed.
- **Tests that set the lead's actor by hand.** `git grep -nE '"ACTOR": (lib\.LEAD|"design-seat"|"task-lead")' -- tests` at `329ff75`: 17 lines in 16 files (the test modules in `paths` after `tests/test_catch_up_decision.py`, plus `test_lead_ruling` and the two marked-checks modules).
- **No SPEC change.** `git grep -n 'ACTOR' -- docs/spec` at `329ff75`: 1 line, §3.6's "`by` records the seat a
  `sent` was run as (`$ACTOR` when it names a ledger actor, else `design-seat`)", which concerns `ccp notify`
  and this task leaves alone. The SPEC already gives the three records to the lead (§3.5, §13.4, §17.5, as 0272
  measured); how a `ccp` call names its seat is the command's mechanics, stated in `docs/cli/02-delivery.md`.
  §23.7 names who writes the ledger and no actor variable.
- **Other tasks on these files.** 0273, 0275, 0278 and 0285 change other `ccp/prompt.py` values and template
  lines; 0282 and 0283 change `ccp/queue.py`, `team.py` and `lib.py` elsewhere (0283 retires the watchdog's
  seat id); 0287 changes `tests/test_session_park.py`. Recorded as clashes, since the paths overlap.

### Rulings for the build (the lead's)

- **The guard.** `queue.lead_actor(what)` reads `ACTOR` itself and returns the lead's id only when `ACTOR`
  is exactly the lead's (`lib.LEAD`). Unset, empty, unknown or another seat's id is refused, exit 2, nothing
  read or written: "only the lead records {what} (ACTOR is {value, or `unset`}): the lead runs it with
  ACTOR={lib.LEAD}; any other seat tells the lead". `queue.actor` is unchanged.
- **The hints.** The five hint lines above print the command with `ACTOR={lib.LEAD} ` before `ccp`.
- **The seat's actor, once.** `scripts/observability/lib.py` gains `VERIFIER = "task-verifier"` beside `RUNNER`
  (`SEAT_IDS` built from it) and `seat_actor(seat)`: `VERIFIER` for the seat `verifier`, else `RUNNER`.
  `report.py` and `suite.py` drop `_actor_for` and call it.
- **Worker prompts.** `ccp prompt`'s values gain `actor`, `lib.seat_actor(runs.SEAT[phase])`. Each of the 17
  template lines becomes `QUEUE_ROOT={{queue_root}} ACTOR={{actor}} {{ccp}} …`. No other template line changes.
- **The runner.** `"def spawn_prompt"` adds, after the queue root line, `f"Actor: {RUNNER}: run every ccp
  command with ACTOR={RUNNER}."`. `delivery-runner.md`'s "run with `QUEUE_ROOT=<queue root>` and `--root` your
  runner worktree" becomes "run with `QUEUE_ROOT=<queue root>`, `ACTOR=` the actor your spawn prompt names, and
  `--root` your runner worktree", and its later "runs with `QUEUE_ROOT` set and `--root` your runner worktree"
  becomes "runs with `QUEUE_ROOT` and `ACTOR` set and `--root` your runner worktree".
- **The hooks.** `run-binding.sh` unsets `ACTOR` before it runs `ccp`, and `runner-idle.sh`'s Python drops
  `ACTOR` from its environment before its first `ccp` call, so each records as `queue.actor`'s default, the
  runner, and names no actor id of its own.
- **Sign-offs.** `queue.sign_offs` keeps a `sign_off` `recorded` event only when its `actor` is `lib.LEAD`.
- **Ruling numbers.** `queue.rulings` gains a keyword `lead_only: bool = True`; `lifecycle.ruling` numbers
  from `rulings(q, tid, lead_only=False)`. Every other reader keeps the lead-only list.
- **The lead's environment in tests.** `tests/helpers.py` gains `LEAD_ENV = {"ACTOR": lib.LEAD}` and
  `as_lead()`, which returns `mock.patch.dict(os.environ, LEAD_ENV)`. Every test that sets the lead's actor
  uses one of them; `ACTOR=task-lead` goes. `tests/test_lead_records.py`'s unset-is-the-lead tests become
  unset-is-refused tests. `tests/test_catch_up_decision.py`'s fixture event carries `"actor": lib.LEAD`.
- **The docs.** The `ccp tasks sign-off`, `ccp tasks ruling` and `ccp tasks follow-up` rows of
  `docs/cli/02-delivery.md` say "needs `ACTOR=design-seat`; refused, exit 2, when `ACTOR` is unset or names
  another seat" in place of "refused, exit 2, when `ACTOR` names another seat".

## Scope

- **In:** `ccp/queue.py` (`lead_actor`, `sign_offs`, `rulings`), `ccp/lifecycle.py` (`ruling`, the hints),
  `ccp/selection.py` and `ccp/followups.py` (the hints), `ccp/prompt.py` (the `actor` value), `ccp/report.py`
  and `ccp/suite.py` (`_actor_for` removed), `scripts/observability/lib.py` (`VERIFIER`, `seat_actor`),
  `scripts/observability/team.py` (`spawn_prompt`), `plugin/hooks/run-binding.sh`, `plugin/hooks/runner-idle.sh`,
  `plugin/agents/delivery-runner.md`, `templates/prompts/_common.md`, `templates/prompts/implement.md`,
  `templates/prompts/review.md`, `templates/prompts/verify.md`, `docs/cli/02-delivery.md`, `tests/helpers.py`,
  `tests/test_seat_actor_env.py` (new), and the test modules in `paths`.
- No SPEC change (measured in Context).
- **Out:** the `"task-runner"` literals and the tests' `"design-seat"` literals (task 0289); `ccp notify`'s
  `by`; the actor of any event other than the three records; who may run the lead's other commands.

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
  story: As a worker or the runner, the commands my brief gives me carry my seat's actor.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `git grep -c 'QUEUE_ROOT={{queue_root}} {{ccp}}' -- templates`.
    2. Run `git grep -c 'QUEUE_ROOT={{queue_root}} ACTOR={{actor}} {{ccp}}' -- templates`.
    3. Run `python3 -B -m unittest -v tests.test_seat_actor_env 2>&1 | tail -1`.
  expect: step 1 prints nothing (exit 1); step 2 prints `templates/prompts/_common.md:5`, `templates/prompts/implement.md:1`, `templates/prompts/review.md:4`, `templates/prompts/verify.md:7`; step 3 prints `OK`, the module holding a test that a rendered implement prompt holds `ACTOR=task-runner` and no `ACTOR=task-verifier`, one that a rendered verify prompt holds `ACTOR=task-verifier`, and one that `team.spawn_prompt`'s text holds `ACTOR=task-runner`.
  dry run (`329ff75`): step 1 printed the four files with 5, 1, 4 and 7; step 2 printed nothing; step 3 n/a — the module is new.
- id: `code-03`
  story: As the runner, the plugin's hooks record as me even when the session's process holds the lead's ACTOR.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_seat_actor_env 2>&1 | grep -e hook -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_seat_actor_env --mutant-file <file>`, the file's mutant removing the line in `plugin/hooks/run-binding.sh` that unsets `ACTOR`.
  expect: step 1 lists, each `ok`, a test where `run-binding.sh start`, run with `ACTOR=design-seat` and a stub `ccp` on PATH that writes the `ACTOR` it sees to a file, leaves that file reading unset, and the same for `runner-idle.sh`'s `ccp` calls, each name holding `hook`; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `code-04`
  story: As the lead, a sign-off another seat recorded does not stand for the operator's.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_lead_records 2>&1 | grep -e sign_off -e sign-off -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_lead_records --mutant-file <file>`, the file's mutant dropping the actor condition from `"def sign_offs"`.
  expect: step 1 lists, `ok`, a test where a ledger holding a `sign_off` `recorded` event (stage `brief`) with actor `task-runner` gives `queue.sign_offs` no `brief` entry, and one where the same event with actor `design-seat` gives it, each name holding `sign_off`; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the tests are new.
- id: `code-05`
  story: As a verifier citing a ruling, a ruling id names one ruling only, whoever recorded the earlier ones.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_lead_records 2>&1 | grep -e number -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_lead_records --mutant-file <file>`, the file's mutant making `lifecycle.ruling` number from the lead-only list again.
  expect: step 1 lists, `ok`, a test where a ledger holding a `ruling` `recorded` event `<task>-r1` with actor `task-runner` makes the lead's next `ccp tasks ruling` on that task print and record the id `<task>-r2`, its name holding `number`; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the test is new.
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
