---
task_id: 0115-wait-on-a-suite-run
title: A worker waits on a suite run's summary within its command limit, and long plane commands are given the full shell timeout
status: done
kind: feature
depends_on: []
spec_refs: ["S14", "S16"]
review_point: R7
paths: ["ccp/suite.py", "ccp/cli.py", "templates/prompts/_common.md", "docs/spec/02-delivery.md", "tests/test_suite*.py", "tests/test_prompt*.py"]
adopt: "none: the command and the prompt guidance arrive with the release"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0115-wait-on-a-suite-run
## Intent

A worker whose suite run outlasts its command limit, or whose harness moved a run to the
background, waits for that run's summary with a bounded command instead of polling a log file; and
the prompts tell workers to give the gate and `ccp mutate` the full shell timeout.

## Context (not checked)

- From two accepted proposals: one from the plane's own runs (a full-suite run outlasting the shell limit while the exclusive lane was held), one from a product (long plane commands hitting the harness's default command timeout and being moved to the background).
- §16.6 already bounds a wait for a held lane (`--wait SECONDS`). This task adds a wait on a run that has started, by its suite id.
- No rule changes: a new command and prompt guidance describing it (§31.1). The rule that every command runs in the foreground stays; `ccp suite wait` is itself a foreground command.
- Lead's ruling on spec question sm-20261117T093633Z-4e05 (spec commit 083207b), verbatim: "Keep the behaviour and the sentence. Word it as a description under §10.6: a run that §14.4 counts as killed is a failed run, so `ccp suite wait` exits 1 at once (§10.6). In the same fix round, attach the `suite wait` sentence to `ccp suite run` only (MINOR 2). The verifier judges the killed-run sentence as within intent."
- Runner's note with the ruling: reword the SPEC §14.2 sentence to cite §10.6 as above, and in `templates/prompts/_common.md` attach the `ccp suite wait` sentence to `ccp suite run` only (`ccp mutate` records no suite id and cannot be waited on). Review MINOR 1 (exit 3 collides with a run whose own command exits 3): add one clause to the §14.2 bullet or the prompt, such as "a printed summary means the run ended, whatever the code", only if it needs no rule change.

## Scope

- **In:**
  - `ccp suite wait <suite_id> [--timeout SECONDS]` (default 540): returns when the run's `ended` row is written, printing the same summary `ccp suite run` prints and exiting with the run's exit code; still running at the timeout, it prints the run's elapsed time and exits 3 (§10.6: not done yet). An unknown suite id is refused (exit 2).
  - `templates/prompts/_common.md`: give `ccp suite run` and `ccp mutate` the Bash tool's `timeout: 600000`; if the harness moves a run to the background anyway, call `ccp suite wait <suite_id>` until it exits other than 3, never read the log in a loop.
  - SPEC text describing the command in §14 and §16.6, marked `§31.1`.
- **Out:**
  - Running suites in the background on purpose.

## dod_checks

- id: `cmd-01`
  story: As a worker, I get a finished run's summary.
  setup: a scratch queue with a suite run that ended, exit code 1.
  steps:
    1. Run `ccp suite wait <its id>`.
  expect: the summary is printed and the exit code is 1.
  dry run: n/a.
- id: `cmd-02`
  story: As a worker, a run still going returns within my limit.
  setup: a scratch queue with a suite run started and not ended.
  steps:
    1. Run `ccp suite wait <its id> --timeout 2`.
  expect: exits 3 within 5 s, printing the elapsed time.
  dry run: n/a.
- id: `cmd-03`
  story: As a worker, a run that ends while I wait returns at once.
  setup: a scratch suite run whose `ended` row is written 2 s after the wait starts.
  steps:
    1. Run `ccp suite wait <its id> --timeout 30`.
  expect: returns within 10 s with the run's exit code.
  dry run: n/a.
- id: `cmd-04`
  story: As a worker, an unknown id is refused, and the prompt says how to wait.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp suite wait st-nope`.
    2. Render any worker prompt with `ccp prompt`.
  expect: (1) exit 2 naming the id. (2) the prompt names `timeout: 600000` and `ccp suite wait`.
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

- 2026-11-17 (implementer): `ccp suite wait <suite_id> [--timeout SECONDS]` is in `ccp/suite.py` (`wait`,
  `ended_summary`, `main_wait`) and `ccp/cli.py`. It reads `runs/_suites.jsonl` every 0.5 s for the
  id's rows. Once the `ended` row is there, it rebuilds the summary `ccp suite run` printed from the row
  and the log, using the same `render_summary`, and exits with the run's exit code. What the records
  don't keep is not shown: a gate result's failure ids and a staged lane's stages not run. With no log
  (a `--full` run, or a pruned log) it prints the stage line and the result line, and says the log is
  missing. Choices beyond the task, narrowest reading:
  - a run §14.4 counts as `killed` (no `ended` row, and its run stopped or reported, or it started over
    30 min ago) exits 1 at once, so a worker calling "until it exits other than 3" never loops forever
    (asked of the runner);
  - `--timeout` below 0 is refused (exit 2); `--timeout 0` checks once.
  It writes nothing. The prompt guidance is one line in `templates/prompts/_common.md`, so every
  worker prompt carries it. The SPEC text is a §14.2 bullet and one sentence in §16.6 (§31.1: the
  task's own feature), and `docs/cli/02-delivery.md` gains the command's row.
- 2026-11-17 (implementer, ruling round 1): per the lead's ruling, the §14.2 sentence on a killed run now
  reads as a description under §10.6: a run §14.4 counts as `killed` is a failed run, so `ccp suite wait`
  exits 1 at once. The prompt line in `templates/prompts/_common.md` sends only a `ccp suite run` to
  `ccp suite wait` (`ccp mutate` records no suite id); the §14.2 bullet's closing sentence says the
  same. Review MINOR 1: the prompt and the §14.2 bullet now say a printed summary means the run ended,
  whatever the code, so a run whose own command exits 3 is not waited on again; the worker calls again
  only while the command says the run is still running. Wording only: no code or rule change.

## Verification notes
- 2026-11-17 — verifier, PR #121 head `16e507c` (squash `0feb94c`): APPROVE. Passed: cmd-01, cmd-02, cmd-03, cmd-04, suite-01. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0115-wait-on-a-suite-run.json.

