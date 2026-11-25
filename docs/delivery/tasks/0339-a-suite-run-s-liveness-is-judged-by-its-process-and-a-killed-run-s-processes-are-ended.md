---
task_id: 0339-a-suite-run-s-liveness-is-judged-by-its-process-and-a-killed-run-s-processes-are-ended
title: A suite run is open while its recording ccp process lives, not for a fixed 30 minutes, and the plane ends a run whose worker run stopped, reported or was abandoned, so nothing it started keeps holding the lane's resources
status: pending
kind: feature
depends_on: []
spec_refs: ["S14"]
review_point: R36
paths: ["ccp/suite.py", "ccp/runs.py", "ccp/report.py", "tests/test_suite_liveness.py", "docs/spec/02-delivery.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver", "0340-a-pending-run-whose-agent-never-started-expires-and-no-longer-blocks-its-agent-type", "0341-an-exclusive-lane-may-declare-a-cache-probe-that-lets-a-fully-cached-run-skip-the-lock"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0339-a-suite-run-s-liveness-is-judged-by-its-process-and-a-killed-run-s-processes-are-ended

## Intent

A product's long suite run is reported as what it is. A run still going past 30 minutes stays `open` in `ccp suite
list`, the suite totals and `ccp suite wait`, instead of being called killed while it runs; a run whose recording
`ccp` died with no `ended` row is `killed` at once, instead of `open` for half an hour. When a worker run stops,
reports or is abandoned while one of its suite runs is still going, the plane ends that suite run (its whole process
group), which is recorded interrupted, so no test process it started keeps holding the lane's resources.

## Context (not checked)

An accepted plane proposal, with two more of the product's merged into it, all generic as stated here. A product's
full lane runs longer than 30 minutes under load. `ccp suite wait` and the totals call such a run killed while it is
still going, so a worker waiting on it is told it failed and reruns it; and a test process left running by a run the
plane counts as killed went on holding a resource the next run needed. The lead accepted the design on 2026-11-24:
liveness is judged from the run's process, and a run the plane counts as killed has its processes ended.

Measured at `3539c23`:

- `"KILLED_AFTER_S = 30 * 60"` in `ccp/suite.py`; `"def fold(q: Path"` marks an open row `killed` when its worker run
  has a `stopped_at`, `reported_at` or `abandoned_at` after it started, or when it is older than `KILLED_AFTER_S`.
  `"def _killed"` and `ccp suite wait` (its message `or it started over {KILLED_AFTER_S // 60} min ago`) read `fold`.
- The `started` row (`started = {"op": "started", ...}` in `ccp/suite.py`) records no process id or host.
- The recording `ccp` waits on every stage of the run, and each stage run in its own process group gets a watchdog
  (`WATCHDOG`) that ends the group if `ccp` dies; SIGTERM sent to `ccp` reaches the stage's whole group and the run
  is recorded `interrupted` (§14.2). So the recording `ccp` lives exactly as long as the run, and signalling it ends
  the run cleanly.
- A run started 3 s earlier and still going, with its `started` row's time set two hours back, is listed `killed`;
  a run whose recording `ccp` was killed with SIGKILL is listed `open` (the dry runs of cmd-01 and cmd-02).

**Ruled.**

- **The row.** The `started` row gains `pid` (the recording `ccp`'s `os.getpid()`) and `host`
  (`socket.gethostname()`): optional fields (§29.3).
- **Liveness.** One function in `ccp/suite.py`, `_alive(row)`: true when the row has a `pid` and its `host` is this
  host, the process exists (`os.kill(pid, 0)` succeeds or raises `PermissionError`), and
  `ps -o command= -p <pid>` prints a line containing `suite run`. The command check guards against a reused process
  id. In `fold`, an open row whose `pid` and `host` say it can be judged here is `open` while `_alive` and `killed`
  once not, whatever its age and whatever its worker run did (seconds: to its worker run's stop or report when that
  is known, else unknown, as today). A row with no `pid`, or another `host`, keeps today's rules, 30 minutes
  included. `ccp suite wait`'s killed message says which rule applied.
- **Ending a run.** One function in `ccp/suite.py`, `end_bound_runs(q, run_id)`: for each open row bound to
  `run_id` whose `_alive` holds, it sends SIGTERM to the row's `pid`, and nothing else (never a signal to a process
  `_alive` does not vouch for). It is called, its errors ignored, when a worker run stops (`"def stop"` in
  `ccp/runs.py`, the `SubagentStop` hook), when its report closes it (where `ccp/report.py` sets `reported_at`), and
  when it is abandoned (`"def abandon"` in `ccp/runs.py`). The signalled `ccp` records the run interrupted, as any
  SIGTERM does.
- **Tests.** `tests/test_suite_liveness.py` (new), class `Liveness(unittest.TestCase)`:
  `test_a_live_run_past_thirty_minutes_is_open`, `test_a_run_whose_process_is_gone_is_killed_at_once`,
  `test_a_row_without_a_pid_keeps_the_age_rule`, `test_a_stopped_workers_live_run_is_ended_and_recorded_interrupted`
  and `test_a_process_that_is_not_a_suite_run_is_never_signalled`. They start real short `ccp suite run`s under the
  test fence. No other test expectation changes.

## Scope

- **In:** `ccp/suite.py` (the row fields, `_alive`, `fold`, `end_bound_runs`, the wait message), `ccp/runs.py` (two
  calls), `ccp/report.py` (one call), `tests/test_suite_liveness.py` (new); the SPEC, describing this task's own
  feature (§31.1, the accepted proposal): the §14.4 sentences below, which only describe the new liveness rule and
  the ending, and correct the sentence the change makes false. No other § sentence changes.

  CURRENT (`docs/spec/02-delivery.md` at `3539c23`), §14.4, *Totals*, its first sentence (the rest of the item
  unchanged):
  > - **Totals.** A `started` row with no end is `open` while the run may still be going and `killed`
  >   once its run has stopped, reported or been abandoned since, or after 30 minutes (its time runs to
  >   that stop or report when known).

  PROPOSED:
  > - **Totals.** A `started` row records the recording `ccp`'s process id and host (`pid`, `host`). A `started` row with no end, read on that host, is `open` while that process is alive (it exists and its command line names `suite run`) and `killed` once it is not, whatever its age. A row with no `pid`, or read on another host, is `open` while the run may still be going and `killed` once its run has stopped, reported or been abandoned since, or after 30 minutes. A killed run's time runs to its run's stop or report when known. When a worker run stops, reports or is abandoned, `ccp` sends SIGTERM to the recording `ccp` of each of its suite runs still alive, which ends the command's whole process group and records the run interrupted, so nothing it started keeps holding the lane's resources.
- **Out:** the exclusive-lane lock (an flock already dies with its process); judging a row written on another host;
  `ccp suite wait`'s exit codes; a run with no worker run bound to it, which nothing ends but itself.

## dod_checks

- id: `cmd-01`
  story: As a product's worker, a suite run still going past 30 minutes is listed open, not killed.
  setup: A checkout of the PR head (any seat); the step builds its scratch product, starts a run in the background, sets its started row two hours back, and ends it afterwards.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && (QUEUE_ROOT="$D/queue" CCP_DEV=1 ./bin/ccp --root "$P" suite run --summary -- sleep 30 </dev/null >/dev/null 2>&1 &) && sleep 3 && python3 -c 'import json, sys; p = sys.argv[1] + "/queue/runs/_suites.jsonl"; rows = [json.loads(l) for l in open(p)]; rows[0]["at"] = "2026-01-01T00:00:00Z"; open(p, "w").write("".join(json.dumps(r) + "\n" for r in rows))' "$D" && QUEUE_ROOT="$D/queue" CCP_DEV=1 ./bin/ccp --root "$P" suite list 2>/dev/null | python3 -c 'import json, sys; print([s["state"] for s in json.load(sys.stdin)["suites"]])'; pkill -f "$P suite run"`.
  expect: prints `['open']`.
  dry run (`3539c23`): printed `['killed']`.
- id: `cmd-02`
  story: As a product's worker, a suite run whose recording ccp died is killed at once, not open for 30 minutes.
  setup: A checkout of the PR head (any seat); the step builds its scratch product, starts a run in the background and kills its recording ccp with SIGKILL.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && (QUEUE_ROOT="$D/queue" CCP_DEV=1 ./bin/ccp --root "$P" suite run --summary -- sleep 37 </dev/null >/dev/null 2>&1 &) && sleep 3 && pkill -9 -f "$P suite run" && sleep 3 && QUEUE_ROOT="$D/queue" CCP_DEV=1 ./bin/ccp --root "$P" suite list 2>/dev/null | python3 -c 'import json, sys; print([s["state"] for s in json.load(sys.stdin)["suites"]])'`.
  expect: prints `['killed']`.
  dry run (`3539c23`): printed `['open']`.
- id: `code-01`
  story: As a plane developer, the tests hold the liveness rule, the age rule for old rows, and the ending of a stopped worker's live run.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_suite_liveness.Liveness.test_a_live_run_past_thirty_minutes_is_open tests.test_suite_liveness.Liveness.test_a_run_whose_process_is_gone_is_killed_at_once tests.test_suite_liveness.Liveness.test_a_row_without_a_pid_keeps_the_age_rule tests.test_suite_liveness.Liveness.test_a_stopped_workers_live_run_is_ended_and_recorded_interrupted tests.test_suite_liveness.Liveness.test_a_process_that_is_not_a_suite_run_is_never_signalled`.
  expect: exit 0.
  dry run (`3539c23`): exit 1, the run FAILED (`tests.test_suite_liveness` does not exist yet).
- id: `spec-01`
  story: As the operator, §14.4 describes the liveness rule and the ending of a stopped worker's runs.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0339`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`3539c23`, with this brief): exit 1, the passage `not found in the SPEC`.

## Implementation notes

## Verification notes
