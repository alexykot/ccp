---
task_id: 0341-an-exclusive-lane-may-declare-a-cache-probe-that-lets-a-fully-cached-run-skip-the-lock
title: An exclusive lane may declare a cache probe in plane.json suite.cache_probe, and a run the probe says the product's test cache answers whole skips the lane's lock, recorded as such
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S16"]
review_point: R36
paths: ["ccp/suite.py", "ccp/config.py", "contracts/plane_config.schema.json", "tests/test_suite_cache_probe.py", "docs/spec/02-delivery.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver", "0337-five-constants-become-plane-json-settings-again", "0338-a-feature-task-may-cite-adr-refs-in-place-of-spec-refs", "0339-a-suite-run-s-liveness-is-judged-by-its-process-and-a-killed-run-s-processes-are-ended", "0340-a-pending-run-whose-agent-never-started-expires-and-no-longer-blocks-its-agent-type"]
adopt: "plane.json suite.cache_probe, for a product whose test cache can tell that a run is answered whole"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0341-an-exclusive-lane-may-declare-a-cache-probe-that-lets-a-fully-cached-run-skip-the-lock

## Intent

A product whose exclusive lane is mostly answered by its own content-keyed test cache stops making its workers queue
for the lock on runs that execute nothing. It names, per lane, a probe command in plane.json `suite.cache_probe`;
before such a run takes the lock, `ccp suite run` asks the probe, and when the probe says every module of the run is a
cache hit the run starts at once without the lock, recorded `lane_skipped: "cache_probe"`. A probe that says no,
fails or hangs leaves the run taking the lock as today.

## Context (not checked)

An accepted plane proposal, narrowed by the lead, generic as stated here. Under several runners a product's exclusive
lane serialises every uncached-looking run, and most of them run nothing: the product's test cache answers them.
Plane task 0213 already lets a run skip the lock when its clean tree matches a recorded passing run of the lane (the
green-tree skip, §16.6); the remaining case is a run the cache would answer at another tree, which the plane cannot
see without being told. The lead accepted on 2026-11-24: a lane may declare a probe command that reports whether
every module is a cache hit; when it says so the run skips the lock, recorded as the green-tree skip is.

Measured at `554fe3a`:

- `"def _green_from"` in `ccp/suite.py` is the one lock-skip rule; the run then records
  `started.update(lane_skipped=GREEN_TREE, green_from=green)` and prints
  `lane {lane}: a passing run of this tree is recorded (...): running without the lock`. A run bound to a task whose
  gate is cold (`verify.cold_gate`) never skips.
- `python3 -c 'import json; print(list(json.load(open("contracts/plane_config.schema.json"))["properties"]["suite"]["properties"]))'`
  prints `['exclusive_lanes', 'lanes', 'count_re', 'roles', 'affected_map', 'affected_exclude', 'log_keep_days', 'summary']`;
  an unknown `suite.cache_probe` loads with the warning `unknown key(s) suite.cache_probe ignored`.
- In a scratch product whose exclusive `gate` lane is held by a background run, a second `ccp suite run --lane gate
  --wait 0` exits 75 (busy), with or without a `suite.cache_probe` (cmd-01's dry run).

**Ruled.**

- **The key.** plane.json `suite.cache_probe`: an object mapping a lane name to a probe command, an argv (a non-empty
  list of non-blank strings); default `{}`. Any other shape is refused when plane.json is read, with
  `suite.cache_probe must map a lane name to a command, a list of strings (§16.6)` and exit 2. A probe for a lane not
  in `suite.exclusive_lanes` is accepted and never run. The schema gains the property with `"default": {}` and a
  description citing §16.6.
- **When it runs.** In `ccp suite run`, for a recorded run of an exclusive lane that the green-tree rule does not
  already let skip and that is not bound to a cold-gate task, when the lane has a probe: only when the first
  `take_lane` finds the lock held (a free lane is taken at once and no probe runs), once, before any wait, and
  whatever the wait given (`--wait 0` included: a probe that says yes means no wait at all). Its seconds count
  against the wait that follows: the run then waits at most the bound (`--wait SECONDS`, or `--wait auto`'s bound)
  less the probe's time, never below 0, and when it then takes the lock its `wait_s` includes the probe's time. It runs in the run's own directory, stdin from `/dev/null`, its output discarded, in its own
  process group, killed whole after `CACHE_PROBE_TIMEOUT_S = 60` seconds (a constant in `ccp/suite.py`), with the
  argv the run would run appended (none for a lane declared with stages) and `CCP_SUITE_LANE` set to the lane.
- **What it decides.** Exit 0: the run does not take the lock; it records `lane_skipped: "cache_probe"` (no
  `green_from`) and prints `ccp suite: lane <lane>: its cache probe says every module is a cache hit: running without
  the lock` on stderr. Any other exit: the lock, silently. A timeout or a probe that cannot start: the lock, with one
  warning naming why. The run itself, its record and its summary are otherwise unchanged; a run the probe let through
  that turns out uncached is still a recorded run, judged like any other.
- **Tests.** `tests/test_suite_cache_probe.py` (new), class `CacheProbe(unittest.TestCase)`:
  `test_a_probe_that_exits_zero_skips_the_lock`, `test_a_probe_that_fails_or_times_out_takes_the_lock`,
  `test_the_probe_gets_the_runs_command_arguments`, `test_a_cold_gate_task_takes_the_lock_whatever_the_probe_says`
  `test_the_key_must_map_a_lane_to_a_command`, `test_a_free_lane_runs_no_probe` and
  `test_the_probes_time_counts_against_the_wait`. No other test expectation changes.

## Scope

- **In:** `ccp/suite.py` (the probe and the skip), `ccp/config.py` (the default and the validation),
  `contracts/plane_config.schema.json` (`suite.cache_probe`), `tests/test_suite_cache_probe.py` (new); the SPEC,
  describing this task's own feature (§31.1, the accepted proposal; a knob with a neutral default): one passage added
  to §16.6, its `--wait 0` sentence corrected, and the §14.4 field clause the new skip makes false corrected. No other § sentence changes.

  CURRENT (`docs/spec/02-delivery.md` at `3539c23`), §16.6, the sentence the new passage follows, unchanged (the new sentences go right after it and retire none):
  > since the product's test cache answers most of it; a run bound to a task whose gate is cold (§15.3)
  > takes the lock as any other.

  PROPOSED:
  > A lane may declare a cache probe, plane.json `suite.cache_probe` (`{"<lane>": [<argv>]}`, default none). When a run of that lane finds the lock held, `ccp` runs the probe once, before any wait, in the run's directory, with the command the run would run appended as arguments (none for a lane declared with stages), for at most 60 s; its time counts against the run's wait (`--wait SECONDS` or `--wait auto`'s bound, and `wait_s`). Exit 0 says the product's test cache answers every module of the run: the run does not take the lock and is recorded `lane_skipped: "cache_probe"`. Any other exit, a timeout, or a probe that cannot start leaves the run taking the lock as before, and a run bound to a task whose gate is cold takes the lock whatever the probe says.
  CURRENT (`docs/spec/02-delivery.md` at `3539c23`), §16.6, the sentence:
  > Held, a run given `--wait 0`, or given no `--wait` and
  > bound to no worker run, exits 75 at once, saying who holds it, since when, and the holder's usual
  > duration;

  PROPOSED:
  > Held, a run given `--wait 0`, or given no `--wait` and bound to no worker run, exits 75 at once (after its cache probe, when the lane declares one), saying who holds it, since when, and the holder's usual duration;

  CURRENT (`docs/spec/02-delivery.md` at `3539c23`), §14.4, the clause:
  > and a run that skipped an exclusive
  > lane's lock adds `lane_skipped` and `green_from`.

  PROPOSED:
  > and a run that skipped an exclusive lane's lock adds `lane_skipped`, and `green_from` for a green-tree skip.
- **Out:** a probe for a lane that is not exclusive; a probe on a free lane; caching the probe's answer; any change to the green-tree skip,
  to `--wait`, or to what the verifier runs (§15.3); `README.md` and `docs/cli/` (call syntax unchanged).

## dod_checks

- id: `cmd-01`
  story: As a product's worker, a run my cache probe says is fully cached runs at once beside a held lane, and one it does not vouch for still waits its turn.
  setup: A checkout of the PR head (any seat); the step builds its scratch product with an exclusive `gate` lane, holds the lane with a background run, and runs from the product's root.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["estimate"] = {"auto": False}; c["language"] = "none"; c["suite"] = {"lanes": {"gate": ["true"]}, "exclusive_lanes": ["gate"], "cache_probe": {"gate": ["false"]}}; json.dump(c, open(p, "w"))' "$P" && C="$PWD/bin/ccp" && cd "$P" && export QUEUE_ROOT="$D/queue" && unset PROJECT_YAML && (CCP_DEV=1 "$C" --root "$P" suite run --lane gate -- sleep 20 </dev/null >/dev/null 2>&1 &) && for i in $(seq 150); do test -s "$D/queue/locks/suite-exclusive.json" && break; sleep 0.1; done && CCP_DEV=1 "$C" --root "$P" suite run --lane gate --wait 0 </dev/null >/dev/null 2>&1; echo "exit $?"; python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["suite"]["cache_probe"] = {"gate": ["true"]}; json.dump(c, open(p, "w"))' "$P" && CCP_DEV=1 "$C" --root "$P" suite run --lane gate --wait 0 </dev/null >/dev/null 2>&1; echo "exit $?"; python3 -c 'import json, sys; print([r.get("lane_skipped") for r in map(json.loads, open(sys.argv[1] + "/queue/runs/_suites.jsonl")) if r.get("op") == "started"])' "$D"; pkill -f "$P suite run"`.
  expect: exactly three lines: `exit 75` (the probe said no: busy, as today), `exit 0`, and `[None, 'cache_probe']` (the background holder's row, then the run the probe let through; the busy run writes no `started` row).
  dry run (`3539c23`): printed `exit 75`, `exit 75`, `[None]` (the key ignored with a warning).
- id: `cmd-02`
  story: As a product's lead, a malformed cache probe is refused when plane.json is read, not silently ignored.
  setup: A checkout of the PR head (any seat); the step builds its scratch product.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["estimate"] = {"auto": False}; c["language"] = "none"; c["suite"] = {"lanes": {"gate": ["true"]}, "exclusive_lanes": ["gate"], "cache_probe": {"gate": "true"}}; json.dump(c, open(p, "w"))' "$P" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" docs check > "$D/out" 2>&1; echo "exit $?"; grep -c 'suite.cache_probe must map a lane name to a command' "$D/out"`.
  expect: exactly two lines: `exit 2`, then `1`.
  dry run (`3539c23`): printed `exit 1`, then `0` (the key unknown, which `ccp docs check` fails on).
- id: `code-01`
  story: As a plane developer, the tests hold the probe's skip, its fallbacks, its arguments, the cold-gate rule, the key's shape, no probe on a free lane and the probe's time in the wait.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_suite_cache_probe.CacheProbe.test_a_probe_that_exits_zero_skips_the_lock tests.test_suite_cache_probe.CacheProbe.test_a_probe_that_fails_or_times_out_takes_the_lock tests.test_suite_cache_probe.CacheProbe.test_the_probe_gets_the_runs_command_arguments tests.test_suite_cache_probe.CacheProbe.test_a_cold_gate_task_takes_the_lock_whatever_the_probe_says tests.test_suite_cache_probe.CacheProbe.test_the_key_must_map_a_lane_to_a_command tests.test_suite_cache_probe.CacheProbe.test_a_free_lane_runs_no_probe tests.test_suite_cache_probe.CacheProbe.test_the_probes_time_counts_against_the_wait`.
  expect: exit 0.
  dry run (`3539c23`): exit 1, the run FAILED (`tests.test_suite_cache_probe` does not exist yet).
- id: `doc-01`
  story: As a product's lead adopting the plane, the contract names the key.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `python3 -c 'import json; print(json.load(open("contracts/plane_config.schema.json"))["properties"]["suite"]["properties"]["cache_probe"]["default"])'`.
  expect: prints `{}`.
  dry run (`3539c23`): exit 1 (`KeyError: 'cache_probe'`).
- id: `spec-01`
  story: As the operator, §16.6 describes the cache probe and what it decides.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0341`.
  expect: exit 0, all three PROPOSED passages found.
  dry run (`554fe3a`, with this brief): exit 1, all three passages `not found in the SPEC`.

## Implementation notes

- `ccp/suite.py`: `cache_probe_argv` (the lane's probe with the run's argv appended, none for a staged lane),
  `run_cache_probe` (the process: run's directory, stdin from /dev/null, output discarded, its own session, killed
  whole after `CACHE_PROBE_TIMEOUT_S`, `CCP_SUITE_LANE` set) and `CACHE_PROBE`, the `lane_skipped` value. In `run`,
  the probe runs right after the first `take_lane` finds the lock held, before the `--wait auto` bound is resolved and
  before the wait loop; the wait's clock (`t_wait`) starts before the first `take_lane`, so the probe's seconds count
  against the bound and land in `wait_s` (or the busy row's `waited_s`) without a separate subtraction. A yes sets
  `lane_skipped: "cache_probe"` and runs as the lock-failure path does (`lane_fd = -1`): no `wait_s`, no busy row.
- The cold-gate test the green-tree skip used is now `_cold_task`, shared by both skips (unchanged behaviour: a task
  that cannot be read keeps the lock).
- The probe's environment, which the brief leaves open, is the run's own (the caller's, the worktree's fields and
  `CCP_SUITE_COLD` under `--cold`), plus `CCP_SUITE_LANE`; never `CCP_SUITE_ID` or `CCP_SUITE_RESULT`.
- `ccp/config.py`: `suite.cache_probe` defaults to `{}`; a key that is no lane name (`SUITE_LANE_RE`) is refused with
  the other shapes.
- Fix round 1 (review MINOR 1): a probe no longer outlives `ccp`. It runs in its own process group in `ccp`'s
  session (`_group(0)`, not a new session, so a watchdog can join the group), with the watchdog (`WATCHDOG`) the run's
  own command gets: when `ccp` dies (SIGTERM, SIGKILL, a harness killing its group) the watchdog ends the probe's
  group. An exception out of the wait (SIGINT) kills the group before it propagates. The watchdog's start and release
  are now `_start_watchdog` and `_release_watchdog`, shared with `_run_stage` (unchanged behaviour there, except
  that a watchdog that fails to start no longer leaks its pipe). A SIGTERM/SIGHUP handler for the probe's duration
  was tried and dropped: the watchdog already covers those signals, so a mutant removing it survived.
- Fix round 1 (review MINOR 2): `test_the_probes_time_counts_against_the_wait` no longer races a 1 s holder: the
  probe itself ends the holder, then answers no after 3 s, so the freed lock is taken after the probe whatever the
  machine's load.
- Fix round 1 (review NIT 4): the schema's `exclusive_lanes` description names the wait, the green-tree skip and the
  cache probe as the ways a run of a held lane still runs. NIT 3 (resetting `at` after a long probe) is left: it adds
  to the record, which the brief does not give leave for.

## Verification notes
