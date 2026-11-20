---
task_id: 0199-suite-wait-auto
title: ccp suite run --wait auto derives the wait from the shell limit and the lane's usual cold time
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S16"]
review_point: R14
paths: ["ccp/suite.py", "ccp/cli.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_parallel_lanes.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0199-suite-wait-auto

## Intent

When an exclusive lane is held, a worker either retries later or passes `--wait SECONDS`. To pick
the seconds, it has to work out its shell's limit less how long its own run will take, and it often
guesses wrong. The plane already knows both figures. After this task, `--wait auto` waits as long as
the shell limit allows once the lane's usual cold run is set aside, with a margin, and says what it
derived.

## Context (not checked)

Measured at `58cf1d0`.

- Provenance: an accepted plane proposal (triage item T7a).
- `ccp/cli.py` declares `--wait` as `type=int` (`git grep -n '"--wait", type=int' ccp/cli.py` at
  `58cf1d0`: one line), so `ccp --root . suite run --wait auto -- true` exits 2 with "invalid int
  value: 'auto'".
- `ccp/suite.py` `run` reads `wait = max(0, int(getattr(a, "wait", None) or 0))` and polls the lane
  lock until that many seconds have passed (`git grep -n 'int(getattr(a, "wait"' ccp/suite.py` at
  `58cf1d0`: one line).
- The shell limit is `config.gate_limits(cfg)[0]`, plane.json `gate.shell_limit_seconds` (§14.6);
  its default is in `GATE_DEFAULTS` (`git grep -n 'shell_limit_seconds": 600' ccp/config.py` at `58cf1d0`).
- `suite.usual_seconds(q, lane, default)` is the median of the lane's last ten passing runs. Each
  `ended` row also records `cold` (`run_cold`, §14.2), so a cold median can be taken from the same
  rows.
- `tests/test_parallel_lanes.py` holds the exclusive-lane tests and passes at the base
  (`python3 -B -m unittest -q tests.test_parallel_lanes` at `58cf1d0`: 8 tests).
- The SPEC sentence below describes only this task's own option (§31.1).

## Scope

- **In:** `ccp/suite.py`, `ccp/cli.py`, `docs/spec/02-delivery.md`, `docs/cli/02-delivery.md`,
  `tests/test_parallel_lanes.py`.
- **`--wait` takes `auto`.** The argument's type accepts a whole number of seconds, as today, or the
  word `auto`. Anything else is refused by the parser (exit 2), with "--wait takes seconds or auto".
- **What `auto` waits.** `suite.auto_wait(cfg, q, lane)` returns `(seconds, why)`:
  - `cold` is the median of the lane's last ten passing runs recorded `cold: true`, else, with none,
    `usual_seconds` for the lane (passing runs of any kind), else None;
  - `seconds = max(0, limit - cold - WAIT_AUTO_MARGIN_S)`, where `limit` is
    `config.gate_limits(cfg)[0]` and `WAIT_AUTO_MARGIN_S = 30`, a module constant;
  - with `cold` None, `seconds` is 0 and `why` says the lane has no passing run recorded.
- `auto` is resolved once, when the lane turns out to be held. The stderr line becomes
  `waiting up to <n> s (--wait auto: limit <L> s, the lane's usual cold run <C> s, margin 30 s)`,
  or `--wait auto: the lane has no passing run recorded, so it waits 0 s` before the busy exit.
- The busy row's `waited_s` and the run's `wait_s` are recorded as today. The row also gets
  `wait_auto: true` when `auto` was given.
- `docs/cli/02-delivery.md`'s `ccp suite run` row says `--wait SECONDS|auto`.
- **SPEC §16.6 (§31.1).** CURRENT (`docs/spec/02-delivery.md` at `58cf1d0`): "`--wait SECONDS` waits
  up to that bound instead (the wait plus the run stay under the worker shell's 600 s limit),
  recorded as `wait_s` apart from the run's time." PROPOSED: "`--wait SECONDS` waits up to that bound
  instead (the wait plus the run stay under the worker shell's 600 s limit), recorded as `wait_s`
  apart from the run's time. `--wait auto` takes the bound from that limit (§14.6) less the lane's
  usual cold run (the median of its last ten passing cold runs, else of its last ten passing runs)
  and a 30 s margin, never below 0; with no passing run of the lane recorded it waits 0 s and says so."
- **Tests** in `tests/test_parallel_lanes.py`:
  - with cold runs of 100, 120 and 140 s recorded and the default limit, `auto_wait` gives 450;
  - with no cold run but passing runs, it uses their median;
  - with no passing run, it gives 0 and the busy exit (75) comes at once, its message naming the
    reason;
  - a held lane released during an `auto` wait lets the run start, recording `wait_s`;
  - `--wait soon` exits 2.
- **Out:** the lock itself, the 600 s figure, and `ccp suite wait`.

## dod_checks

- id: `wa-01`
  story: As a worker, `--wait auto` is accepted where it was refused.
  setup: a checkout of the PR head; a temp product whose plane.json names `suite.exclusive_lanes:
    ["gate"]` and a gate lane `["true"]`, with QUEUE_ROOT a temp queue and the lane free.
  steps:
    1. Run `ccp --root <temp> suite run --lane gate --wait auto; echo rc=$?`.
  expect: `rc=0`, with no "invalid int value" in the output.
  dry run (`58cf1d0`): on this repo, `ccp --root . suite run --wait auto -- true` exits 2, printing
    "argument --wait: invalid int value: 'auto'"; the setup above with `--wait 5` passes, exit 0.

- id: `wa-02`
  story: As a worker, the wait is derived from the limit and the lane's cold time, and the tests bite.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `WAIT_AUTO_MARGIN_S` is 0.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_parallel_lanes 2>&1 | tail -20`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_parallel_lanes`.
  expect: step 1 exits 0 and lists the five Scope tests as `ok`; step 2 has at least one failure (the
    450 s case).
  dry run (`58cf1d0`): step 1 runs 8 tests, OK; the new tests do not exist yet.

- id: `wa-03`
  story: As the SPEC reader, §16.6 describes `--wait auto`.
  setup: a checkout of the PR head.
  steps:
    1. Run `tr -s '[:space:]' ' ' < docs/spec/02-delivery.md | grep -c '.--wait auto. takes the bound from that limit (§14.6) less the lane.s usual cold run'`.
    2. Run `grep -c 'wait SECONDS|auto' docs/cli/02-delivery.md`.
  expect: each step prints 1.
  dry run (`58cf1d0`): 0 and 0.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `ccp/suite.py`: `usual_seconds` now delegates to `_lane_seconds(q, lane, default, cold_only)`, so the passing-run median and the cold median share one reader. `auto_wait(cfg, q, lane)` and `WAIT_AUTO_MARGIN_S = 30` are new; `run` resolves `auto` once, right after the first failed `take_lane`, prints the stderr line and then polls like `--wait SECONDS`.
- Open points, narrowest reading taken: `wait_auto: true` goes on the busy row only (the task says "the row", after the busy row's `waited_s`); a started row records `wait_s` as today. `auto` with a known cold time but a limit it leaves under the margin gives 0 and prints `waiting up to 0 s (--wait auto: ...)` before the busy exit. `seconds` is truncated to a whole number. The busy message's hint now reads "`--wait SECONDS` or `--wait auto`".
- `ccp/cli.py`: `_wait_arg` is the parser type (int or `auto`; anything else is `ArgumentTypeError("--wait takes seconds or auto")`, exit 2).

## Verification notes
