---
task_id: 0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once
title: ccp tasks prefer and hold refuse any ACTOR but the lead's, the verifier's actor id and the seat-to-actor rule are named once, E27's command covers every seat id in code and tests, and the whole-suite lane roles are one tuple
status: pending
kind: feature
depends_on: ["0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s", "0289-the-runner-s-actor-id-is-named-once-and-tests-read-the-lead-s"]
spec_refs: ["S10", "S14", "S27"]
rule_refs: ["E27", "E12", "E4"]
review_refs: ["ar-20261122T100027Z-dd31#F02", "ar-20261122T100027Z-dd31#F03", "ar-20261122T100027Z-dd31#F12"]
review_point: R26
paths: ["ccp/lifecycle.py", "ccp/cli.py", "ccp/selection.py", "ccp/queue.py", "ccp/report.py", "ccp/suite.py", "ccp/verify.py", "ccp/health.py", "ccp/tasklog.py", "ccp/submit.py", "ccp/config.py", "scripts/observability/lib.py", "scripts/observability/spec_maintainer.py", "plugin/orientation.md", "plugin/agents/delivery-runner.md", "docs/cli/02-delivery.md", "docs/delivery/plane.json", "docs/ENGINEERING.md", "tests/test_lead_state_guard.py", "tests/test_prefer.py", "tests/test_next_passes_over.py", "tests/test_sign_off.py", "tests/architect_fixture.py", "tests/board_drill_fixture.py", "tests/test_architect.py", "tests/test_architect_default_on.py", "tests/test_backstop_retired.py", "tests/test_board_seats.py", "tests/test_contract_writers.py", "tests/test_followups.py", "tests/test_init.py", "tests/test_lead_records.py", "tests/test_mutate.py", "tests/test_notify.py", "tests/test_notify_lead.py", "tests/test_notify_upgrade.py", "tests/test_review_aliases_retired.py", "tests/test_run_abandon.py", "tests/test_spec_maintainer_blocked.py", "tests/test_stale_blockers_retired.py", "tests/test_task_supply.py", "tests/test_team_hosting.py", "tests/test_wait_reasons.py", "tests/toolkit_fixture.py", "tests/upgrade_fixture.py"]
clashes_with: ["0191-the-grace-release-ends", "0270-the-friction-trigger-counts-noted-tasks-and-scales-with-tasks-in-flight", "0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests", "0273-verify-refuses-early-what-record-would-refuse", "0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope", "0278-submit-takes-a-proven-fix-and-the-spec-names-what-ccp-writes", "0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes", "0287-action-parsers-own-their-flags-and-describe-their-actions", "0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily", "0297-a-sign-off-wait-ends-on-the-lead-s-sign-off-and-briefs-name-the-lead-s-actor"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once

## Intent

The lead's preference and holds (§10.4) are recorded only by the lead: `ccp tasks prefer` and
`ccp tasks hold` go through the same guard as the lead's other records, so a runner or worker cannot set
them, and listing them still needs no `ACTOR`. E27 holds for every seat: the verifier's actor id is
written once in the seat table, one function maps a run's seat to its actor, tests read every seat id by
name, and the architect's E27 command fails on a copy of any of the three ids in code or tests. The
lane roles that run the whole suite are named once, beside the other role names. Every other behaviour
is unchanged.

## Context (not checked)

From the triage of architect pass `ar-20261122T100027Z-dd31` (F02, F03, F12; the record is in
`docs/delivery/reviews/`). 0288 (the lead's guard refusing an unset or unknown ACTOR, `tests/helpers.py`'s
`LEAD_ENV` and `as_lead()`) and 0289 (the runner's id as `lib.RUNNER`, the tests' lead id as `lib.LEAD`,
E27's command over both ids) land first; this task builds on both; both are done. Measured at `954bd72` (first measured on `e92f362`): every figure holds except
the architect's wider E27 pattern (91 lines on `e92f362`, 47 now that 0289 has the tests read `lib.LEAD`) and E27's own command, which
0289 extended to `"task-runner"`.

- **prefer and hold.** `"def prefer"` and `"def hold"` in `ccp/lifecycle.py` each set `who = actor(lib.LEAD)`,
  which records any known actor, a runner's included, as `by`: `git grep -n 'who = actor(lib.LEAD)' -- ccp/lifecycle.py` at `954bd72`: 3 lines
  (prefer, hold, and release, which §10.4 gives to "lead or runner" and this task leaves). The shared guard
  `queue.lead_actor` is used only for sign-off, ruling and follow-up: `git grep -n 'lead_actor(' -- ccp` at `954bd72`: 4 lines
  (its definition and those three).
- **Who runs them.** §10.4's heading is "The lead's preference, holds, release and drop", and §10.3 has the
  runner turn a lead's "take X next" back to the lead as `ccp tasks prefer X`; `docs/cli/02-delivery.md` gives both rows
  the seat `lead`. `plugin/orientation.md` tells the lead to run `ccp tasks prefer`; no hook or template runs either:
  `git grep -n 'tasks prefer\|tasks hold' -- plugin/hooks templates` at `954bd72`: 0 lines.
- **The hints.** `git grep -nE 'ccp tasks hold --clear|ccp tasks prefer. a new list' -- ccp` at `954bd72`: 4 lines, each telling a reader to run one
  of them: `ccp/cli.py` (`tasks next`'s passed-over line for a held task), `ccp/lifecycle.py` (the claim's warning on a held task) and
  `ccp/selection.py` (an ignored preference, and a held preferred task). 0288 prefixes its own hints with `ACTOR={lib.LEAD} `.
- **Tests that call them.** `git grep -lE '"(prefer|hold)"' -- tests` at `954bd72`: 3 files (`tests/test_prefer.py`, `tests/test_next_passes_over.py`,
  `tests/test_sign_off.py`); after the guard they run as the lead through 0288's `LEAD_ENV`.
- **The verifier's id.** `git grep -n '"task-verifier"' -- ccp scripts ':(exclude)ccp/board_page.html' ':(exclude,glob)scripts/**/*.sh'` at `954bd72`: 6 lines:
  `ccp/report.py` and `ccp/suite.py` (`"def _actor_for"`), `ccp/verify.py` (the `verify` `recorded` event's actor),
  `scripts/observability/lib.py` (`SEAT_IDS` and `SEAT_DEFAULT_CRON`), `scripts/observability/spec_maintainer.py` (`RAISERS`).
  The shell writers (`heartbeat.sh`, `write-prompt-audit.sh`) embed Python that imports nothing from `lib`, as no
  shell writer does; E27's command excludes them by glob. 0283 (signed) removes `SEAT_DEFAULT_CRON`; whichever
  lands second takes the other's lib.py as its base.
- **Two seat-to-actor functions.** `git grep -n 'def _actor_for' -- ccp` at `954bd72`: 2 lines, `ccp/report.py` and `ccp/suite.py`, both
  `return "task-verifier" if seat == "verifier" else "task-runner"`.
- **Tests' runner and verifier literals.** `git grep -c '"task-runner"' -- tests` at `954bd72`: 38 lines in 22 files; `git grep -c '"task-verifier"' -- tests` at `954bd72`: 5 lines in 3 files
  (the test files in `paths` from `tests/architect_fixture.py` on). No test file other than `.py` holds any of the three ids.
- **E27's command.** At `954bd72` it greps `"design-seat"` and `"task-runner"` in ccp and scripts (0289 added the second).
  The architect's proposed command, run at `954bd72` over ccp, scripts and tests with the shell writers excluded:
  `git grep -nE '"(design-seat|task-runner|task-verifier)"' -- ccp scripts tests ':(exclude)ccp/board_page.html' ':(exclude)scripts/observability/lib.py' ':(exclude,glob)scripts/**/*.sh' | wc -l` at `954bd72`: 47 lines.
- **Whole-suite roles.** `git grep -nE '= \("(full|gate)", "(full|gate)"\)' -- ccp` at `954bd72`: 3 lines: `ccp/health.py` `COLD_ROLES`, `ccp/report.py`
  `AUTO_ROLES` (also read by `ccp/submit.py` as `report.AUTO_ROLES`), `ccp/tasklog.py` `WHOLE_SUITE_ROLES` (in the order
  `("gate", "full")`, which `tasklog`'s judged list follows). `ccp/config.py` holds `SUITE_ROLES = ("full", "gate", "part")`.
- **No SPEC change.** `git grep -n 'tasks prefer\|tasks hold' -- docs/spec` at `954bd72`: 5 lines, all in §10.3 and §10.4, which already
  give both commands to the lead; how a call names its seat is the command's mechanics in `docs/cli/02-delivery.md`
  (as 0288 measured). The actor ids and the role tuples are named in no SPEC sentence this task changes.

### Rulings for the build (the lead's)

- **The guard.** `"def prefer"` sets `who = lead_actor("a preference")` and `"def hold"` `who = lead_actor("a hold")`, after
  the no-argument listing returns, so listing needs no `ACTOR` and `--clear` needs the lead's. `release` keeps `actor(lib.LEAD)`.
- **The hints.** The four hint lines above print the command with `ACTOR={lib.LEAD} ` before `ccp`, built from `lib.LEAD`,
  as 0288 does for its hints (`ACTOR=design-seat ccp tasks hold --clear <id>`, `ACTOR=design-seat ccp tasks prefer`).
- **The docs.** The `ccp tasks prefer` and `ccp tasks hold` rows of `docs/cli/02-delivery.md` add "needs `ACTOR=design-seat` to
  write; refused, exit 2, when `ACTOR` is unset or names any other value; listing needs none". The orientation line 0288 adds
  names `ccp tasks prefer` and `ccp tasks hold` beside the three records, and the existing prefer line reads
  "the lead runs `ACTOR=design-seat ccp tasks prefer <id> [<id>…] --reason "…"`". In `plugin/agents/delivery-runner.md`, the two `ccp tasks prefer` mentions in the **Next** step (the lead's preference that
  `next` honours, and "ask the lead to run `ccp tasks prefer X`") read `ACTOR=design-seat ccp tasks prefer` and
  `ACTOR=design-seat ccp tasks prefer X`; `git grep -n 'ccp tasks prefer' -- plugin/agents/delivery-runner.md` at `954bd72`: 2 lines.
- **The verifier's id.** `scripts/observability/lib.py` gains `VERIFIER = "task-verifier"` beside `RUNNER`; `SEAT_IDS`, the cadence
  table (while it exists), `ccp/verify.py`'s event and `spec_maintainer.py`'s `RAISERS` read it.
- **One seat-to-actor function.** `ccp/queue.py` gains `def seat_actor(seat: str | None) -> str`, returning `lib.VERIFIER` for
  `"verifier"` and `lib.RUNNER` otherwise; `ccp/report.py` and `ccp/suite.py` call it and their `_actor_for` go.
- **Tests.** Each `"task-runner"` and `"task-verifier"` in `tests/` reads `lib.RUNNER` or `lib.VERIFIER`. A test whose subject is a
  stored literal (a contract enum, a legacy ledger row) still reads the constant; if one cannot, stop and ask.
- **E27.** Its command in `docs/delivery/plane.json` becomes
  `! git grep -nE '"(design-seat|task-runner|task-verifier)"' -- ccp scripts tests ':(exclude)ccp/board_page.html' ':(exclude)scripts/observability/lib.py' ':(exclude,glob)scripts/**/*.sh'`.
  Its text and `check:` line in `docs/ENGINEERING.md` become (replacing the rule as 0288 and 0289 leave it):

  > - **E27** A seat's actor id (the lead's, the runner's, the verifier's) is named once, in the seat table, and code and tests
  >   read it by name. A command the SPEC gives to one seat refuses, through one shared guard, every ACTOR that does not name
  >   that seat (unset or unknown included), and a reader counts only that seat's records.
  >   check: command — architect.checks `E27`; pass for the guard (the architect compares the commands the SPEC gives one seat)
- **Whole-suite roles.** `ccp/config.py` gains `WHOLE_SUITE_ROLES = ("gate", "full")` beside `SUITE_ROLES`; `health`'s `COLD_ROLES`,
  `report`'s `AUTO_ROLES` and `tasklog`'s own tuple go, and their readers (`ccp/submit.py` included) import config's. Where
  a reader's result depends on the order, it keeps today's (`tasklog`'s judged list is gate first; health and report
  take each role's lane, which no order changes).

## Scope

- **In:** `ccp/lifecycle.py` (prefer, hold, the claim's hint), `ccp/cli.py` and `ccp/selection.py` (the hints), `ccp/queue.py` (`seat_actor`), `ccp/report.py`, `ccp/suite.py`, `ccp/verify.py`,
  `ccp/health.py`, `ccp/tasklog.py`, `ccp/submit.py`, `ccp/config.py`, `scripts/observability/lib.py`,
  `scripts/observability/spec_maintainer.py`, `plugin/orientation.md`, `plugin/agents/delivery-runner.md` (the two `ccp tasks prefer` mentions), `docs/cli/02-delivery.md`, `docs/delivery/plane.json`
  (E27's command), `docs/ENGINEERING.md` (E27), `tests/test_lead_state_guard.py` (new), the test files in `paths`, and any other
  test file the E27 command names at the build's base (0288's new `tests/test_seat_actor_env.py`, for one).
- No SPEC change (measured in Context).
- **Out:** `ccp tasks release` and `drop` (lead or runner, §10.4); the shell writers; `ccp/board_page.html`;
  `ccp/usage.py`'s actor; what any event other than prefer and hold records.

## dod_checks

- id: `code-01`
  story: As the lead, only a caller whose ACTOR names me sets the runner's preference or a hold; listing them needs no ACTOR.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_lead_state_guard 2>&1 | grep -e refus -e list -e hint -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_lead_state_guard --mutant 'ccp/lifecycle.py:who = lead_actor("a preference")=>who = actor(lib.LEAD)'`.
    3. Run `git grep -n 'ccp tasks prefer' -- plugin/agents/delivery-runner.md | grep -v 'ACTOR=design-seat ccp tasks prefer'`.
  expect: step 1 lists, each `ok`, a test where `ccp tasks prefer <id>` with `ACTOR=task-runner` and with `ACTOR` unset each exits 2 with `only the lead records` and leaves `work.json` unchanged, the same for `ccp tasks hold <id>`, each name holding `refus`, and one where `ccp tasks prefer` and `ccp tasks hold` with no argument and no `ACTOR` exit 0 and print the list, its name holding `list`, and one where `ccp tasks next` passing over a held task prints on stderr `ACTOR=design-seat ccp tasks hold --clear <id>`, its name holding `hint`; then `OK`. Step 2 prints the mutant `killed`. Step 3 prints nothing (exit 1).
  dry run: steps 1 and 2 n/a — the module is new. Step 3 (`954bd72`): printed 2 lines, `plugin/agents/delivery-runner.md` lines 120 and 122.
- id: `code-02`
  story: As a plane developer, the verifier's actor id and the seat-to-actor rule are each written once.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n '"task-verifier"' -- ccp scripts ':(exclude)ccp/board_page.html' ':(exclude,glob)scripts/**/*.sh'`.
    2. Run `git grep -nE 'def (_actor_for|seat_actor)' -- ccp`.
  expect: step 1 prints exactly one line, `VERIFIER = "task-verifier"` in `scripts/observability/lib.py`; step 2 prints exactly one line, `def seat_actor` in `ccp/queue.py`.
  dry run (`954bd72`): step 1 printed 6 lines in 5 files; step 2 printed 2 lines (`_actor_for` in `ccp/report.py` and `ccp/suite.py`).
- id: `cfg-01`
  story: As the architect, E27's command fails on a new copy of any seat's actor id in code or tests.
  setup: A checkout of the PR head, and a mutation worktree of it (`CCP_DEV=1 ./bin/ccp wt create --kind mut --task 0293 --sha HEAD`, its path in the printed `path`; removed afterwards with `ccp wt remove <name>`).
  steps:
    1. In the checkout, run `bash -c "$(python3 -B -c "import json;print([c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E27'][0])")"; echo "exit $?"`.
    2. In the mutation worktree, append the line `X = "task-verifier"` to `tests/helpers.py`, `git add` it, and run the same command there.
  expect: step 1 prints `exit 0`; step 2 prints the planted line and `exit 1`.
  dry run (`954bd72`): the setup's `wt create` printed the worktree's JSON (`"created": true`, its `path`); step 1 printed `exit 0` (the command checks only `"design-seat"` and `"task-runner"` in ccp and scripts); in the worktree, step 2's planted line was found by the PROPOSED pattern (`tests/helpers.py:470:X = "task-verifier"`, exit 1); the wider pattern over the same paths found 47 lines.
- id: `code-03`
  story: As a plane developer, the lane roles that run the whole suite are named once.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nE '= \("(full|gate)", "(full|gate)"\)' -- ccp`.
    2. Run `git grep -nw -e COLD_ROLES -e AUTO_ROLES -- ccp tests`.
    3. Run `python3 -B -m unittest -q tests.test_health_suite tests.test_formal_submit 2>&1 | tail -1`.
  expect: step 1 prints exactly one line, `WHOLE_SUITE_ROLES = ("gate", "full")` in `ccp/config.py`; step 2 prints nothing (exit 1); step 3 prints `OK`.
  dry run (`954bd72`): step 1 printed 3 lines (`ccp/health.py`, `ccp/report.py`, `ccp/tasklog.py`); step 2 printed 8 lines; step 3 printed `OK`.

## Implementation notes

## Verification notes
