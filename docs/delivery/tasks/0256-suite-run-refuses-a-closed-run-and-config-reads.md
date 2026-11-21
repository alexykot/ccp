---
task_id: 0256-suite-run-refuses-a-closed-run-and-config-reads
title: ccp suite run refuses a closed run as ccp mutate does, the sandbox reads plane.json through config, and suite busy rows lose wait_auto
status: pending
kind: feature
depends_on: ["0243-one-source-for-syntax-events-and-config"]
clashes_with: ["0213-a-green-tree-skips-the-lane-queue", "0238-the-runner-runs-marked-checks-before-verify"]
spec_refs: ["S14", "S20"]
review_refs: ["ar-20261121T020523Z-1d5f#F10", "ar-20261121T020523Z-1d5f#F11", "ar-20261121T020523Z-1d5f#F15"]
rule_refs: ["E16"]
review_point: R17
paths: ["ccp/suite.py", "ccp/sandbox.py", "docs/spec/02-delivery.md", "docs/ENGINEERING.md", "docs/delivery/plane.json", "tests/test_parallel_lanes.py", "tests/test_suite_run_closed.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0256-suite-run-refuses-a-closed-run-and-config-reads

## Intent

A worker that runs `ccp suite run --run` with a stale run id is stopped before its command starts,
told which run of the task is open, as `ccp mutate` already stops it, instead of recording its suite
against a run that has reported. No `ccp` module but `ccp/config.py` reads plane.json, and the E16
check now looks in `ccp/` too. The suite's busy rows stop carrying a field nothing reads.

## Context (not checked)

From architect pass `ar-20261121T020523Z-1d5f`, findings F10, F11 and F15, triaged by the lead on
2026-11-21, with the triage's amendment to house rule E16, which lands here because its widened
check fails until this task is built. Measured at `aaa81b2`. `depends_on` 0243 because it amends E16
and its check first (to `plugin scripts` with `CONFIG_REL`); this task widens that check to `ccp`.

- **F11.** `ccp/mutate.py` refuses a run not in `runs.OPEN` ("mutants are recorded only on an open
  run", exit 2; §20.6: "`--run` names the run, which must be open (not reported or abandoned)").
  `ccp/suite.py` `"def _bind"` (the `if a.run:` branch) loads the run and binds to it whatever its
  state (`git grep -n 'out\["bound_by"\] = "run"' -- ccp/suite.py` at `aaa81b2`: 1 line, with no state
  test before it). Ruling: a `--run` whose record loads and whose `runs.state` is not in `runs.OPEN` is
  refused with exit 2 before the command starts and before any row is written; the message names the
  run's state and, when the task has an open run (the one `--task` alone would bind), that run's id.
  A `--run` that names no run in the queue keeps today's warning and unbound record.
- **F10.** `ccp/sandbox.py` reads plane.json itself for `project_id`:
  `git grep -nE '(plane\.json"|CONFIG_REL)\)\.read_text' -- ccp plugin scripts ':(exclude)ccp/config.py'` at `aaa81b2`: 2 lines (`ccp/sandbox.py`, and `scripts/observability/lib.py`, which 0243 removes).
  Ruling: the sandbox takes `config.load(root).project_id`, returning None when the load raises, as
  it does today when the read fails.
- **F15.** `git grep -n wait_auto -- ccp scripts contracts tests` at `aaa81b2`: 2 lines
  (`ccp/suite.py`, `tests/test_parallel_lanes.py`); `ccp/health.py` reads `waited_s` from busy rows,
  never `wait_auto`. Ruling: the field and its assertion go; no schema names it.
- **E16, the text this task applies** (agreed in the triage record
  `docs/delivery/reviews/ar-20261121T020523Z-1d5f.md`, replacing the text 0243 applies): "Only
  ccp/config.py reads plane.json. A hook, script, shared library or ccp module that needs a setting
  asks `ccp` (JSON out) or takes it from ccp.config's loaded Config; it never opens the file, by literal
  name or by `CONFIG_REL`, and never defaults a key itself. A command that records into plane.json
  edits its text through ccp/jsonedit.py." Check and `architect.checks` `E16`:
  `! git grep -nE '(plane\.json"|CONFIG_REL)\)\.read_text' -- ccp plugin scripts ':(exclude)ccp/config.py'`.

## Scope

- **In:**
  - `ccp/suite.py` (`_bind`'s refusal; the busy row's `wait_auto` removed), `ccp/sandbox.py`.
  - `tests/test_suite_run_closed.py` (new), `tests/test_parallel_lanes.py` (the `wait_auto` assertion).
  - `docs/ENGINEERING.md` (E16 text and check), `docs/delivery/plane.json` (`architect.checks` `E16`).
  - SPEC, signed before the claim (`sign_off: brief`):
  - `docs/spec/02-delivery.md` §14.2, the binding bullet; one sentence added at its end:

    CURRENT (`docs/spec/02-delivery.md` at `aaa81b2`):
    > - The run it belongs to is `--run`, else `--task` (and `--phase`)'s latest open run, else the one running worker run whose worktree holds the current directory; otherwise it is recorded unbound.

    PROPOSED: (a sentence added after it, in the same bullet)
    > A `--run` naming a run that is reported or abandoned is refused (exit 2) before the command starts, with nothing recorded, and the refusal names the task's open run when it has one.
- **Out:** `ccp mutate`'s own refusal (unchanged); health splitting waits by how their bound was set.

## dod_checks

- id: `sf-01`
  story: As a reviewer sent a stale prompt, `ccp suite run --run` on a reported run stops me before the suite runs, and the test bites.
  setup: a checkout of the PR head; then a separate copy of it with the new state test in `ccp/suite.py` `_bind` removed.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_suite_run_closed 2>&1 | tail -8`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_suite_run_closed`.
  expect: step 1 exits 0, with tests listed `ok` for a reported run refused with exit 2 (no `started` row written, the open run's id in the message) and an open run still bound; step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `sf-02`
  story: As a plane developer, no ccp module but config reads plane.json, and the widened E16 check holds.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE '(plane\.json"|CONFIG_REL)\)\.read_text' -- ccp plugin scripts ':(exclude)ccp/config.py'`.
    2. Run `python3 -B -c "import json; c={x['id']: x['cmd'] for x in json.load(open('docs/delivery/plane.json'))['architect']['checks']}; print('-- ccp plugin scripts' in c['E16'])"`.
    3. Run `python3 -B -m unittest -q tests.test_sandbox`.
  expect: step 1 prints nothing; step 2 prints `True`; step 3 exits 0.
  dry run (`aaa81b2`): step 1 printed 2 lines; step 2 printed `False`; step 3 exited 0 (run with `tests.test_parallel_lanes`).
- id: `sf-03`
  story: As a plane developer, suite busy rows carry no field that only a test reads.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n wait_auto -- ccp scripts contracts tests`.
    2. Run `python3 -B -m unittest -q tests.test_parallel_lanes`.
  expect: step 1 prints nothing; step 2 exits 0.
  dry run (`aaa81b2`): step 1 printed 2 lines; step 2 exited 0 (run with `tests.test_sandbox`).
- id: `sf-04`
  story: As the operator, the §14.2 sentence reads as I signed it.
  setup: a checkout of the PR head; the brief sign-off recorded.
  steps:
    1. Run `./bin/ccp verify spec-text 0256`.
  expect: exit 0, the PROPOSED passage found in `docs/spec/02-delivery.md`.
  dry run: n/a — the passage lands with the task.

## Implementation notes

## Verification notes
