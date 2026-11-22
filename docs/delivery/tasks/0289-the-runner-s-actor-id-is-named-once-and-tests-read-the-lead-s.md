---
task_id: 0289-the-runner-s-actor-id-is-named-once-and-tests-read-the-lead-s
title: The runner's actor id is named once in the seat table, E27's command checks it as it checks the lead's, and tests read the lead's id through lib.LEAD
status: pending
kind: refactor
depends_on: ["0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s"]
rule_refs: ["E27", "E4"]
review_point: R25
paths: ["ccp/cli.py", "ccp/prompt.py", "ccp/queue.py", "ccp/seats.py", "scripts/observability/architecture_review.py", "scripts/observability/spec_maintainer.py", "docs/delivery/plane.json", "docs/ENGINEERING.md", "tests/helpers.py", "tests/test_allowance_lapse.py", "tests/test_board_seats.py", "tests/test_lead_ruling.py", "tests/test_next_passes_over.py", "tests/test_prefer.py", "tests/test_review_points.py", "tests/test_session_park.py", "tests/test_task_supply.py", "tests/test_team_hosting.py", "tests/test_toolkit.py", "tests/test_usage.py", "tests/test_usage_advice.py", "tests/test_wait_reasons.py"]
clashes_with: ["0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests", "0273-verify-refuses-early-what-record-would-refuse", "0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope", "0278-submit-takes-a-proven-fix-and-the-spec-names-what-ccp-writes", "0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log", "0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes", "0287-action-parsers-own-their-flags-and-describe-their-actions", "0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0289-the-runner-s-actor-id-is-named-once-and-tests-read-the-lead-s

## Intent

E27 holds for the runner as it does for the lead: the runner's actor id is written once, in the seat
table, every module reads it from there, and the architect's E27 command fails on a new copy of
either id. Tests name the lead's id through `lib.LEAD` rather than spelling it (E4). Behaviour does
not change.

## Context (not checked)

Measured at `329ff75` unless a line says otherwise.

Follow-ups covered (the lead's worker follow-up log):
`0272-the-lead-s-records-share-one-guard-and-one-actor-id/implement#2` (the runner's literals and E27's
command), `0272-the-lead-s-records-share-one-guard-and-one-actor-id/implement#3` (the tests' literals).

- **The runner's literal.** `git grep -n '"task-runner"' -- ccp scripts ':(exclude)ccp/board_page.html'` at `329ff75`: 13 lines. 0288 removes the two in `"def _actor_for"` (`ccp/report.py`, `ccp/suite.py`), and the definition `RUNNER = "task-runner"` in `scripts/observability/lib.py` stays, leaving 10: `ccp/cli.py` 1 and `ccp/prompt.py` 1 (`os.environ.get("ACTOR") or "task-runner"`), `ccp/queue.py` 2 (`"def actor"`'s and `"def heartbeat"`'s defaults), `ccp/seats.py` 2 (`_last_event(events, "task-runner")`), `scripts/observability/architecture_review.py` 1, `scripts/observability/spec_maintainer.py` 2 (`RAISERS` and the actor fallback in `"def process"`), and `scripts/observability/write-prompt-audit.sh` 1.
- **The shell writer stays.** `write-prompt-audit.sh` is a shell script whose embedded Python reads
  `ACTOR_IN`, which the script defaults with `${ACTOR:-task-runner}`; it imports nothing from `lib`, as no
  shell writer does. E27's command excludes it, as it excludes `lib.py` and `ccp/board_page.html`.
- **Imports.** `ccp/` reads `lib` as `from ccp.queue import lib` or through `queue.lib`;
  `architecture_review.py` and `spec_maintainer.py` already import names `from lib import (…)`. `RAISERS`
  also names `"task-verifier"`, which 0288 adds to the seat table as `lib.VERIFIER`.
- **E27's command today.** `python3 -c "import json;print([c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E27'])"` at `329ff75`:
  `! git grep -n '"design-seat"' -- ccp scripts ':(exclude)ccp/board_page.html' ':(exclude)scripts/observability/lib.py'`,
  the lead's id only. `docs/ENGINEERING.md`'s E27 `check:` line quotes the same command.
- **The tests' literal.** `git grep -n '"design-seat"' -- tests` at `329ff75`: 36 lines in 14 files (the test files in `paths`; `tests/helpers.py` 1). 0288 replaces the ones that set `ACTOR` to the lead; the rest are fixture events and expected actors.
- **Behaviour unchanged.** Each replacement names the same string through the constant, so no test
  expectation changes (refactor DoD); the gate holds it.
- **Other tasks on these files.** 0271, 0273, 0275, 0278, 0282, 0283, 0285, 0287 and 0290 change other code in
  these files (0283 retires the watchdog's seat id beside these). Recorded as clashes, since the paths overlap.

### Rulings for the build (the lead's)

- Each of the nine `ccp/` and `scripts/observability/*.py` literals above reads `lib.RUNNER` (or `RUNNER`
  imported from `lib`); `RAISERS` becomes `(RUNNER, VERIFIER)`.
- E27's command in `docs/delivery/plane.json` becomes
  `! git grep -nE '"(design-seat|task-runner)"' -- ccp scripts ':(exclude)ccp/board_page.html' ':(exclude)scripts/observability/lib.py' ':(exclude)scripts/observability/write-prompt-audit.sh'`,
  and E27's `check:` line in `docs/ENGINEERING.md` quotes it. E27's rule text is unchanged: it already names
  the runner's id.
- Each `"design-seat"` in `tests/` reads `lib.LEAD` (or, for an environment, 0288's `LEAD_ENV`).

## Scope

- **In:** `ccp/cli.py`, `ccp/prompt.py`, `ccp/queue.py`, `ccp/seats.py`,
  `scripts/observability/architecture_review.py`, `scripts/observability/spec_maintainer.py` (the literals),
  `docs/delivery/plane.json` (E27's command), `docs/ENGINEERING.md` (E27's `check:` line), and the test modules in `paths`.
- **Out:** `scripts/observability/write-prompt-audit.sh`; `ccp/board_page.html`; any change to what an actor
  records.

## dod_checks

- id: `code-01`
  story: As a plane developer, the runner's actor id is written once, as the lead's is.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n '"task-runner"' -- ccp scripts ':(exclude)ccp/board_page.html'`.
  expect: prints exactly two lines, one in `scripts/observability/lib.py` and one in `scripts/observability/write-prompt-audit.sh`.
  dry run (`329ff75`): printed 13 lines in 10 files.
- id: `cfg-01`
  story: As the architect, E27's command fails on a new copy of the runner's id or the lead's.
  setup: A checkout of the PR head, and a scratch copy of it (`git worktree add --detach <scratch> HEAD`, removed afterwards).
  steps:
    1. In the checkout, run `bash -c "$(python3 -B -c "import json;print([c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E27'][0])")"; echo "exit $?"`.
    2. In the scratch copy, append the line `X = "task-runner"` to `ccp/seats.py`, `git add` it, and run the same command there.
  expect: step 1 prints `exit 0`; step 2 prints the planted line and `exit 1`.
  dry run (`329ff75`): step 1 printed `exit 0` (the command checks only the lead's id); step 2 printed `exit 0`, the planted runner literal not caught.
- id: `test-01`
  story: As a plane developer, tests name the lead's actor id through the code (E4).
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n '"design-seat"' -- tests`.
  expect: prints nothing (exit 1).
  dry run (`329ff75`): printed 36 lines in 14 files.

## Implementation notes

## Verification notes
