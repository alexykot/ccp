---
task_id: 0265-one-gate-lane-and-worker-runs-wait-for-it
title: The plane's gate is one lane, a worker's run waits for a held exclusive lane, and suite run names its lane once
status: pending
kind: feature
depends_on: []
clashes_with: ["0256-suite-run-refuses-a-closed-run-and-config-reads", "0261-a-declared-part-lane-runs-the-affected-modules", "0262-module-docstrings-and-house-rule-checks"]
spec_refs: ["S14", "S16"]
review_refs: ["ar-20261121T132817Z-d5e5#F01", "ar-20261121T132817Z-d5e5#F02", "ar-20261121T132817Z-d5e5#F05"]
rule_refs: ["E12"]
review_point: R20
paths: ["docs/delivery/plane.json", "CLAUDE.md", "tests/CLAUDE.md", "ccp/suite.py", "ccp/cli.py", "docs/spec/02-delivery.md", "tests/test_suite_lane_default.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0265-one-gate-lane-and-worker-runs-wait-for-it

## Intent

The plane's own suite runs under one lane name, so the verifier's gate on a tree a worker's full run
just passed skips the lane queue, as the green-tree rule means it to, and one series holds the lane's
usual time and its waits. A worker whose suite run finds the exclusive lane held waits for it, within
its shell's limit, instead of being refused and rerunning by hand; a run nobody's worker owns is still
refused at once. Every message `ccp suite run` prints names the lane the run really uses, and §16.6
says which lane a run with no `--lane` counts as.

## Context (not checked)

From architect pass `ar-20261121T132817Z-d5e5`, findings F01, F02 and F05 (the record is in
`docs/delivery/reviews/`). Measured at `ce0f4bb`.

- **F01, two names for one lane.** `python3 -B -c "import json;s=json.load(open('docs/delivery/plane.json'))['suite'];print(sorted(s['lanes']), s['exclusive_lanes'])"` at `ce0f4bb`: `['full', 'gate'] ['gate', 'full']`,
  both lanes `scripts/gate.sh`. The green-tree match keys on the lane name (`"def green_run"` in
  `ccp/suite.py`: `key = ((started.get("lane") or default_lane), tree, …)`), so a verify gate never
  matches the passing full run of the same tree. Since 0212, `config.lane_for(cfg, "full")` returns the
  gate lane when `suite.lanes` declares it and not the full role's lane, so dropping `full` changes
  nothing else: the prompts render `{{full_lane}}` through `lane_for`
  (`grep -n '"full_lane"' ccp/prompt.py` at `ce0f4bb`: 1 line). The queue shows the cost (data only the queue holds, read at triage): two
  verify gates in a row ran on a tree a full run had just passed, with no skip.
  `git grep -n -- '--lane full' -- CLAUDE.md docs/ENGINEERING.md tests/CLAUDE.md` at `ce0f4bb`: 3 lines.
  The triage reworded house rule E1's (`docs/ENGINEERING.md`); the CLAUDE.md and tests/CLAUDE.md lines remain.
- **F02, no wait for a worker.** `grep -rn -- '--wait' templates plugin/agents docs/delivery/standing-dod.md`
  at `ce0f4bb`: no match. Every worker learns of `--wait auto` only from the busy refusal, then reruns.
  The queue's `runs/_suites.jsonl`, counted at triage with `python3 -c` over rows with `op` `busy` and `at` from 2026-11-18: 33 busy rows across 29 tasks (data only the queue holds).
  Ruling, the operator's to sign (the triage's question, option b): a run of an exclusive
  lane that is bound to a worker run (§14.2's binding: `--run`, `--task`, or the worker worktree holding
  the current directory; `bound_by` set in `"def _bind"`) and given no `--wait` waits as `--wait auto`
  does. `--wait 0` exits 75 at once, as today; a run bound to no worker run (the lead's, the operator's)
  exits 75 at once, as today. `args.wait` is `None` when the flag is absent, so absent and `0` are told
  apart there. An explicit `--wait SECONDS` or `--wait auto` is unchanged, and so is the catch-up gate's
  own wait in `ccp/lifecycle.py`, which passes its bound explicitly. `lane_busy` stays as §16.6 records
  it: health already reads the busy rows' `waited_s`
  (`grep -c 'waited_s' ccp/health.py` at `ce0f4bb`: 3 lines), and a busy exit now means the auto wait ran out.
- **F05, the lane named twice.** `git grep -c "a.lane or 'full'" -- ccp/suite.py` at `ce0f4bb`: 5 (the
  messages); `git grep -c 'a.lane or lane_for(cfg, "full")' -- ccp/suite.py` at `ce0f4bb`: 3 (the lock
  holder, the auto wait, the busy row). Ruling: `run()` works out the effective lane once, right after the
  arguments are read (`a.lane or lane_for(cfg, "full")`), and every message, the lock holder, the auto
  wait and the busy row use it. The `started` row keeps recording `a.lane` as given (a stored record;
  `green_run`'s `default_lane` already reads a missing lane as the full role's). The module docstring's
  sentence "a run with no lane counts as the `full` role's lane" gains the wait default in the same
  words as §16.6.
- **Lead's rulings** (ruling round 1), verbatim:

  > Ruling 0265-one-gate-lane-and-worker-runs-wait-for-it-r1 (check cfg-01): 0261 added suite.lanes.part after this check was measured. cfg-01 holds when it prints ['gate', 'part'] ['gate']: no full lane, gate the only exclusive lane, and 0261's part lane kept.
  >
  > Ruling 0265-one-gate-lane-and-worker-runs-wait-for-it-r2: Keep as built: an explicit --lane full where plane.json declares no full lane is refused like any undeclared lane (exit 2). Since 0212, prompts render the full role's lane through config.lane_for, which returns gate here, so no rendered prompt names --lane full and in-flight workers are unaffected. SPEC §16.2's exclusive_lanes example is only an example; changing it is § text, left for a later signed task as a follow-up. doc-01's premise count drifting to 1 needs nothing.

## Scope

- **In:**
  - `docs/delivery/plane.json` (`suite.lanes.full` and its `exclusive_lanes` entry removed),
    `CLAUDE.md` and `tests/CLAUDE.md` (the `--lane full` parentheses name the full role's lane, as
    E1 now does).
  - `ccp/suite.py` (`run()`: the effective lane once; the wait default for a bound run; the module
    docstring), `ccp/cli.py` (the `--wait` help names the default).
  - `tests/test_suite_lane_default.py` (new).
- **SPEC, signed before the claim (`sign_off: brief`):** `docs/spec/02-delivery.md` §16.6, its first
  paragraph's first three sentences, replaced. Signing covers the whole passage, including its last
  sentence ("A run whose wait ends with the lane still held exits the same way…"), which describes
  what the code already does after an explicit `--wait`.

    CURRENT (`docs/spec/02-delivery.md` at `ce0f4bb`, §16.6, first paragraph):
    > plane.json `suite.exclusive_lanes` names the `ccp suite run` lanes that run one at a time in a queue (a run with no `--lane` counts as `full`). A run of an exclusive lane takes `QUEUE_ROOT/locks/suite-exclusive.lock` first. Held, `ccp suite run` exits 75 at once, saying who holds it, since when, and the holder's usual duration; the worker does other work and retries.

    PROPOSED:
    > plane.json `suite.exclusive_lanes` names the `ccp suite run` lanes that run one at a time in a queue (a run with no `--lane` counts as the full role's lane, §14.1). A run of an exclusive lane takes `QUEUE_ROOT/locks/suite-exclusive.lock` first. Held, a run given `--wait 0`, or given no `--wait` and bound to no worker run, exits 75 at once, saying who holds it, since when, and the holder's usual duration; a run bound to a worker run (§14.2) and given no `--wait` waits as `--wait auto` does. A run whose wait ends with the lane still held exits the same way, and the worker does other work and retries.
- **Out:** the prompt templates (no `--wait` is rendered: the default covers every worker run); the
  `started` row's `lane` field; a health reader for `lane_busy`; the catch-up gate's wait.

## dod_checks

- id: `cfg-01`
  story: As the plane's verifier, my gate and the worker's full run are one lane, so a passing full run of my tree lets my gate skip the queue.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -c "import json;s=json.load(open('docs/delivery/plane.json'))['suite'];print(sorted(s['lanes']), s['exclusive_lanes'])"`.
  expect: prints exactly `['gate'] ['gate']`.
  dry run (`ce0f4bb`): printed `['full', 'gate'] ['gate', 'full']`.
- id: `doc-01`
  story: As a plane developer, no doc restates the lane by its old name.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n -- '--lane full' -- CLAUDE.md docs/ENGINEERING.md tests/CLAUDE.md`.
  expect: prints nothing (exit 1).
  dry run (`ce0f4bb`): printed 3 lines (`CLAUDE.md:49`, `docs/ENGINEERING.md:10`, `tests/CLAUDE.md:3`); the triage's E1 edit leaves 2.
- id: `code-01`
  story: As a worker in a product that declares only a gate lane, every message names the lane my run uses, and a verify gate after a passing run with no `--lane` on the same tree skips the lock.
  setup: A checkout of the PR head; then a separate copy of it where one busy message in `ccp/suite.py` prints `a.lane or 'full'` again.
  steps:
    1. Run `git grep -c "a.lane or 'full'" -- ccp/suite.py`.
    2. On the head, run `python3 -B -m unittest -v tests.test_suite_lane_default 2>&1 | tail -12`.
    3. In the copy, run `python3 -B -m unittest -q tests.test_suite_lane_default`.
  expect: step 1 prints nothing (exit 1); step 2 exits 0, listing as `ok` a test where a temp product with `suite.lanes` `{"gate": …}` and `exclusive_lanes` `["gate"]`, its lock held, gets a busy message for a run with no `--lane` naming `lane gate` and never `lane full`, and a test where a passing run with no `--lane` on a clean tree lets a following `--lane gate` run on that tree record `lane_skipped: "green_tree"`; step 3 exits non-zero.
  dry run (`ce0f4bb`): step 1 printed `ccp/suite.py:5`; steps 2 and 3 n/a — the module is new.
- id: `code-02`
  story: As a worker, my run of a held exclusive lane waits for it within my shell's limit; a run no worker owns, or one I give `--wait 0`, is refused at once as before.
  setup: A checkout of the PR head; then a separate copy of it where `run()` treats an absent `--wait` as `0` whatever the binding.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_suite_lane_default 2>&1 | grep -i wait`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_suite_lane_default`.
  expect: step 1 prints, each ending `ok`, tests that: a run bound with `--run` and no `--wait`, the lane held by a live holder and a passing run of the lane recorded, prints `--wait auto:` (with the colon, the auto wait's own line) on stderr; the same run unbound exits 75 without that line and with no `waited_s` on its `busy` row; the bound run with `--wait 0` exits 75 the same way. Step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `spec-01`
  story: As the operator, §16.6 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0265`.
  expect: exit 0, the PROPOSED passage found in `docs/spec/02-delivery.md`.
  dry run (simulated: this task file and the passage applied to `docs/spec/02-delivery.md`, committed in a scratch worktree off `ce0f4bb`): `"ok": true`, the passage found.

## Implementation notes

- `ccp/suite.py` `run()` works out the effective lane once, right after the arguments are read
  (`lane = a.lane or lane_for(cfg, "full")`); the five messages, the lock holder, the auto wait, the busy row
  and the two `_exclusive` calls use it. The `started` row still records `a.lane` as given.
- The wait default is a plain function, `suite.lane_wait(given, bound_by)`: `--wait` as given (an explicit `0`
  included), else `auto` when `_bind` set `bound_by` (`run`, `task` or `worktree`), else 0. `run()` feeds it
  the parsed `--wait` (None when absent) and the binding; the rest of the wait loop is unchanged, so a busy row
  carries `waited_s` only when a wait above 0 was taken. The catch-up gate's explicit `--wait` is untouched.
- The module docstring's exclusive-lane sentence now says which lane a run with no lane counts as and the
  wait default, in §16.6's words; `_exclusive`'s docstring names the full role's lane (§14.1). `--wait`'s help
  in `ccp/cli.py` names the default.
- `docs/delivery/plane.json`: `suite.lanes.full` and its `exclusive_lanes` entry removed. The `part` lane that
  task 0261 added after this task was measured stays, so cfg-01's command prints `['gate', 'part'] ['gate']`,
  not the `['gate'] ['gate']` its expect names (raised with the runner as a scope question).
- `CLAUDE.md`: the `--lane full` parenthesis now names the full role's lane, as E1 does. `tests/CLAUDE.md` no
  longer held a `--lane full` line at the base, so it is unchanged.
- `tests/test_parallel_lanes.py`: the cold-gate test's bound run now passes `--wait 0`, since a bound run with
  a passing run of its lane recorded would otherwise wait for the holder; what it checks (a cold-gate task's run
  queues instead of skipping the lock) is unchanged.
- Ruling round 1 (`-r1`, `-r2`, quoted in Context) changes no code: `-r1` accepts cfg-01's
  `['gate', 'part'] ['gate']` with 0261's part lane kept; `-r2` keeps the refusal of an explicit `--lane full`
  where no full lane is declared, and leaves §16.2's `exclusive_lanes` example to a later signed task.

## Verification notes
