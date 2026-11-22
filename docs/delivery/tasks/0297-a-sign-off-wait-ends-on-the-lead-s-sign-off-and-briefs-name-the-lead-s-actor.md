---
task_id: 0297-a-sign-off-wait-ends-on-the-lead-s-sign-off-and-briefs-name-the-lead-s-actor
title: ccp health ends a sign-off wait only on the lead's build sign-off, the runner's brief and the writing-tasks skill show the lead's records with the lead's ACTOR, and tests build the lead's id into longer strings from lib.LEAD
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S17", "S27"]
rule_refs: ["E27", "E4"]
review_point: R26
paths: ["ccp/health.py", "plugin/agents/delivery-runner.md", "plugin/skills/writing-tasks/SKILL.md", "templates/prompts/implement.md", "tests/test_health_signoff.py", "tests/test_prefer.py", "tests/test_stale_context_audience.py", "tests/test_usage.py", "tests/test_usage_advice.py"]
clashes_with: ["0191-the-grace-release-ends", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0297-a-sign-off-wait-ends-on-the-lead-s-sign-off-and-briefs-name-the-lead-s-actor

## Intent

A sign-off is the lead's record (§3.5), and every reader counts only the lead's: `ccp health`'s
sign-off wait (§27.1) ends on a `build` sign-off the lead recorded, as `ccp tasks close` already
judges one, so a `sign_off` event another actor wrote neither shortens nor ends a task's wait. The
runner's brief and the writing-tasks skill show the lead's sign-off and ruling commands as the lead
must run them, with `ACTOR=design-seat`. Tests that spell the lead's id inside a longer string build
it from `lib.LEAD`, so the id is written once (E27). Every other behaviour is unchanged.

## Context (not checked)

The open follow-ups of 0288 and 0289 (`ccp --root . tasks follow-ups --open`), all covered here:

- `0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s/review#1` and `/fix#1`: `ccp/health.py`
  `sign_off_wait` ends a wait on any actor's `build` sign-off.
- `0288-…/implement#2`, `/review#2`, `/fix#2` and `/verify#1`: `plugin/agents/delivery-runner.md` and
  `plugin/skills/writing-tasks/SKILL.md` show `ccp tasks sign-off` and `ccp tasks ruling` without `ACTOR=design-seat`.
- `0289-the-runner-s-actor-id-is-named-once-and-tests-read-the-lead-s/review#1` and `/verify#1`: tests spell the
  lead's id inside longer strings.

The other 0288 follow-ups (`tests/CLAUDE.md` naming `LEAD_ENV` and `as_lead()`) go to 0295, which rewrites that doc.

Measured at `7d83efd` (origin/main).

- **The reader.** In `"def sign_off_wait"` (`ccp/health.py`), the line
  `if kind == ("sign_off", "recorded") and p.get("stage") == "build":` takes the event whoever recorded it
  (no `actor` test in the function: `sed -n '/def sign_off_wait/,/^def /p' ccp/health.py | grep -c actor` at `7d83efd`: 0).
  `"def sign_offs"` in `ccp/queue.py`, which `ccp tasks close` reads, already keeps only `ev.get("actor") == lib.LEAD`.
  `ccp/health.py` loads the shared library as `from lib import looks_like_secret  # noqa: E402`.
  `git grep -n 'sign_off_wait' -- ccp scripts` at `7d83efd`: 5 lines, all in `ccp/health.py` (the module docstring, the function, two in `collect` and the text).
- **The tests that break.** `tests/test_health_signoff.py`'s `ev()` builds events with no `actor`:
  `grep -c '"sign_off", "recorded"' tests/test_health_signoff.py` at `7d83efd`: 13 lines, each a sign-off the lead must now have recorded.
  No other test module feeds `health` a `sign_off` event: `git grep -l 'sign_off' -- tests | xargs grep -l 'health'` at `7d83efd`: 2 files,
  `tests/test_health_signoff.py` and `tests/test_health.py`, whose only match is a test name (`test_long_sign_off_waits_do_not_trip_drift`, built on
  `waiting_on` events). The module imports no `lib` yet; `tests/test_prefer.py` takes it as `from ccp.queue import lib`.
- **The briefs.** `git grep -nE 'ccp tasks (sign-off|ruling)' -- plugin/agents plugin/skills | grep -v 'ACTOR=design-seat ccp tasks'` at `7d83efd`: 3 lines:
  `plugin/agents/delivery-runner.md` ("once the lead has recorded it with `ccp tasks sign-off <task_id> --stage build`" and
  "`ccp tasks ruling <task_id> --words "…"` (SPEC §17.5)") and `plugin/skills/writing-tasks/SKILL.md` (the `sign_off` row:
  "The lead records each with `ccp tasks sign-off`"). `plugin/orientation.md` already says the lead's three records run as
  `ACTOR=design-seat ccp …`. No test pins these sentences: `grep -n 'sign-off\|ruling' tests/test_plugin.py tests/test_rotation_model.py` at `7d83efd`: no line.
  `delivery-runner.md`'s two `ccp tasks prefer` lines are 0293's (its guard makes them need the lead's ACTOR), not this task's.
- **The tests' longer strings.** `git grep -n 'design-seat' -- tests | grep -v '"design-seat"'` at `7d83efd`: 5 lines:
  `tests/test_prefer.py` three (`"the lead's preference (2 of 3, design-seat, "`, `"why:       the lead's preference (design-seat, "`,
  `"next: 0004-fourth, 0002-second (design-seat, the demo)"`), `tests/test_usage_advice.py` one (`"design-seat: median context"`),
  `tests/test_usage.py` one (the assertion message `"only design-seat rows are compared with the expected lead"`). Each module
  already reads `lib.LEAD` elsewhere (`grep -c 'lib.LEAD' tests/test_prefer.py tests/test_usage_advice.py tests/test_usage.py` at `7d83efd`: 5, 4 and 3).
- **No SPEC change.** §3.5 already gives sign-offs to the lead ("The lead records each sign-off with `ccp tasks sign-off`",
  `docs/spec/01-model.md`), and §27.1's "Sign-off wait" (`docs/spec/04-observability.md`) says the wait runs "to the `build`
  sign-off": `git grep -n 'Sign-off wait' -- docs/spec` at `7d83efd`: 1 line. A record another actor wrote is no sign-off,
  so the reader now matches the text. E27 (as 0288 left it) already says "a reader counts only that seat's records".

### Rulings for the build (the lead's)

- `ccp/health.py`: the import becomes `from lib import LEAD, looks_like_secret  # noqa: E402`, and the sign-off branch reads
  `if kind == ("sign_off", "recorded") and p.get("stage") == "build" and e.get("actor") == LEAD:`. The merge-gate branch
  is unchanged. `"def sign_off_wait"`'s docstring says "the first `build` sign-off the lead recorded".
- `tests/test_health_signoff.py`: `ev()` gives every event `"actor": lib.LEAD`, and a new test,
  `test_a_build_sign_off_another_actor_recorded_ends_no_wait`, records for one task an approve, then a `build` sign-off by
  `lib.RUNNER`, then the lead's `build` sign-off later: the wait runs to the lead's, and a task whose only `build`
  sign-off is the runner's is in no point.
- `plugin/agents/delivery-runner.md`: the two lines read `ACTOR=design-seat ccp tasks sign-off <task_id> --stage build` and
  `ACTOR=design-seat ccp tasks ruling <task_id> --words "…"`. `plugin/skills/writing-tasks/SKILL.md`'s `sign_off` row reads
  "The lead records each with `ACTOR=design-seat ccp tasks sign-off`".
- The five test strings are f-strings with `{lib.LEAD}` in place of the id; their wording is otherwise unchanged.

## Scope

- **In:** `ccp/health.py` (`sign_off_wait` and its import), `plugin/agents/delivery-runner.md` (the sign-off and ruling lines),
  `plugin/skills/writing-tasks/SKILL.md` (the `sign_off` row), `tests/test_health_signoff.py`, `tests/test_prefer.py`,
  `tests/test_usage.py`, `tests/test_usage_advice.py`, `templates/prompts/implement.md` (the `{{#stale_context}}` block),
  `tests/test_stale_context_audience.py`.
- **Ruling (lead, 2026-11-22, 0275 follow-ups review#1/verify#1):** the `{{#stale_context}}` block of
  `templates/prompts/implement.md` keeps `{{stale_context}}` and drops the sentence after it ("Re-run the Context's
  measurements at your base before you build; …"), which repeats the two lines above it on re-running measured premises
  (E13). `tests/test_stale_context_audience.py`'s `RERUN` assertions then pin the stale-context text itself, not the
  dropped sentence. No SPEC text carries it: `git grep -n "Re-run the Context" -- docs/spec` at `7d83efd`: no line.
- No SPEC change (measured in Context).
- **Out:** the merge-gate end of a wait; `ccp tasks prefer` and `hold` and their docs (0293); `tests/CLAUDE.md` (0295);
  E27's command.

## dod_checks

- id: `code-01`
  story: As the operator reading `ccp health`, a task's sign-off wait ends only when the lead records the build sign-off.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `python3 -B -m unittest -v tests.test_health_signoff 2>&1 | grep -e another_actor -e '^OK' -e FAIL`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_health_signoff --mutant 'ccp/health.py: and e.get("actor") == LEAD=>'`.
  expect: step 1 lists `test_a_build_sign_off_another_actor_recorded_ends_no_wait` `ok`, then `OK`, and no `FAIL`; step 2 prints the mutant `killed`.
  dry run: n/a — the test is new; at `7d83efd`, `python3 -B -m unittest -q tests.test_health_signoff` printed `OK`.
- id: `doc-01`
  story: As the runner, the brief and the writing-tasks skill show the lead's sign-off and ruling as the lead runs them.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nE 'ccp tasks (sign-off|ruling)' -- plugin/agents plugin/skills`.
    2. Run `git grep -nE 'ccp tasks (sign-off|ruling)' -- plugin/agents plugin/skills | grep -v 'ACTOR=design-seat ccp tasks'`.
    3. Run `grep -c "Re-run the Context's measurements" templates/prompts/implement.md; python3 -B -m unittest -q tests.test_stale_context_audience 2>&1 | tail -1`.
  expect: step 1 prints exactly 3 lines (2 in `plugin/agents/delivery-runner.md`, 1 in `plugin/skills/writing-tasks/SKILL.md`); step 2 prints nothing (exit 1); step 3 prints `0` then `OK`.
  dry run (`7d83efd`): step 1 printed the 3 lines; step 2 printed the same 3 lines; step 3 printed `1` then `OK`.
- id: `code-02`
  story: As a plane developer, no test spells the lead's id inside a longer string.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n 'design-seat' -- tests | grep -v '"design-seat"'`.
    2. Run `python3 -B -m unittest -q tests.test_prefer tests.test_usage tests.test_usage_advice 2>&1 | tail -1`.
  expect: step 1 prints nothing (exit 1); step 2 prints `OK`.
  dry run (`7d83efd`): step 1 printed 5 lines (`tests/test_prefer.py` 3, `tests/test_usage_advice.py` 1, `tests/test_usage.py` 1); step 2 printed `OK`.

## Implementation notes

## Verification notes
