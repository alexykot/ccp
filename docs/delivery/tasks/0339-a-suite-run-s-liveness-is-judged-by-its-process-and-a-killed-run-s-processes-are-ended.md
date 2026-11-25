---
task_id: 0339-a-suite-run-s-liveness-is-judged-by-its-process-and-a-killed-run-s-processes-are-ended
title: A suite run is open while its recording ccp process lives, not for a fixed 30 minutes, the board reads that state, and the plane ends a run whose worker run reported or was abandoned, so nothing it started keeps holding the lane's resources
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S28"]
review_point: R36
paths: ["ccp/suite.py", "ccp/runs.py", "ccp/report.py", "ccp/board.py", "tests/test_suite_liveness.py", "tests/test_board_staleness.py", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "docs/design/board.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver", "0333-every-docs-cli-part-takes-one-table-shape-e25-reads-every-line-and-the-cli-reference-tests-run-on-their-own-docs", "0340-a-pending-run-whose-agent-never-started-expires-and-no-longer-blocks-its-agent-type", "0341-an-exclusive-lane-may-declare-a-cache-probe-that-lets-a-fully-cached-run-skip-the-lock"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0339-a-suite-run-s-liveness-is-judged-by-its-process-and-a-killed-run-s-processes-are-ended

## Intent

A product's long suite run is reported as what it is. A run still going past 30 minutes stays `open` in `ccp suite
list`, the suite totals, `ccp suite wait` and the board, instead of being called killed while it runs; a run whose
recording `ccp` died with no `ended` row is `killed` at once, instead of `open` for half an hour. When a worker run
reports or is abandoned while one of its suite runs is still going, the plane ends that suite run (its whole process
group), which is recorded interrupted, so no test process it started keeps holding the lane's resources. Where the
plane cannot tell whether a process is the run's, it judges as today and signals nothing.

## Context (not checked)

An accepted plane proposal, with two more of the product's merged into it, all generic as stated here. A product's
full lane runs longer than 30 minutes under load. `ccp suite wait` and the totals call such a run killed while it is
still going, so a worker waiting on it is told it failed and reruns it; and a test process left running by a run the
plane counts as killed went on holding a resource the next run needed. The lead accepted the design on 2026-11-24:
liveness is judged from the run's process, and a run the plane counts as killed has its processes ended.

Measured at `554fe3a`:

- `"KILLED_AFTER_S = 30 * 60"` in `ccp/suite.py`; `"def fold(q: Path"` marks an open row `killed` when its worker run
  has a `stopped_at`, `reported_at` or `abandoned_at` after it started, or when it is older than `KILLED_AFTER_S`.
  `"def _killed"` and `ccp suite wait` (its message `or it started over {KILLED_AFTER_S // 60} min ago`) read `fold`.
- The `started` row (`started = {"op": "started", ...}` in `ccp/suite.py`) records no process id, host or start time.
- `ccp/board.py` judges a running suite apart from `fold`: `"SUITE_LIVE_MINUTES = 60"`, read in `"def _live"` (a
  row of an open run started within 60 minutes with no `ended_at`); §28.3 *Plane health* states the same 60 minutes,
  and `docs/design/board.md` repeats it.
- The recording `ccp` waits on every stage of the run, and each stage run in its own process group gets a watchdog
  (`WATCHDOG`) that ends the group if `ccp` dies; SIGTERM sent to `ccp` reaches the stage's whole group and the run
  is recorded `interrupted` (§14.2). So the recording `ccp` lives exactly as long as the run, and signalling it ends
  the run cleanly.
- A run started moments earlier and still going, with its `started` row's time set back to 2026-01-01, is listed
  `killed`; a run whose recording `ccp` was killed with SIGKILL is listed `open` (the dry runs of cmd-01 and cmd-02).

**Ruled.**

- **The row.** A recorded run's `started` row gains `pid` (the recording `ccp`'s `os.getpid()`), `host`
  (`socket.gethostname()`) and `pstart` (that process's start time as `ps -o lstart= -p <pid>` prints it, stripped;
  left out when `ps` gives nothing): optional fields (§29.3). Both `ps -o lstart=` calls, the one that records
  `pstart` and the one `_alive` compares it with, run with `TZ=UTC0 LC_ALL=C` in their environment, so the same
  process prints the same start time whatever the caller's time zone or locale.
- **Liveness, three-valued.** One function in `ccp/suite.py`, `_alive(row)`, returns `alive`, `dead` or `unknown`:
  - `unknown` when the row lacks `pid`, `host` or `pstart`, names another host, or `ps` cannot answer (it is
    missing, fails, or takes over 5 s) for a process that exists;
  - `dead` when the process does not exist (`os.kill(pid, 0)` raises `ProcessLookupError`), or it exists but its
    `ps -o lstart=` differs from `pstart`, or its `ps -o command=` split on whitespace has no token `suite`
    followed at once by the token `run` (a reused process id is not the run);
  - `alive` when it exists, its start time equals `pstart` and its command line has `suite` then `run` as tokens.
- **fold.** An open row that `_alive` calls `alive` is `open`, and one it calls `dead` is `killed`, whatever its age
  and whatever its worker run did (seconds: to its worker run's stop or report when that is known, else unknown, as
  today). An `unknown` row keeps today's rules, 30 minutes included. `ccp suite wait`'s killed message says which
  rule applied.
- **Ending a run.** One function in `ccp/suite.py`, `end_bound_runs(q, run_id)`: for each open row bound to
  `run_id` that `_alive` calls `alive`, it sends SIGTERM to the row's `pid`; a `dead` or `unknown` row is never
  signalled. It is called, its errors ignored, when the worker run's report closes it (where `ccp/report.py` sets
  `reported_at`) and when the worker run is abandoned (`"def abandon"` in `ccp/runs.py`). It is never called when a
  worker run stops (`"def stop"`, the `SubagentStop` hook): a turn's end is not final, and a background suite run
  outlives it. The signalled `ccp` records the run interrupted, as any SIGTERM does.
- **The board.** `"def _live"` in `ccp/board.py` counts a suite of an open run as still running when `fold` gives
  it state `open`, in place of the 60-minute window; `SUITE_LIVE_MINUTES` goes. `docs/design/board.md`'s sentence
  on the 60 minutes says the same (non-normative).
- **Tests.**
  - `tests/test_suite_liveness.py` (new), class `Liveness(unittest.TestCase)`:
    `test_a_live_run_past_thirty_minutes_is_open`, `test_a_run_whose_process_is_gone_is_killed_at_once`,
    `test_a_row_without_a_pid_keeps_the_age_rule`, `test_a_reused_pid_is_not_the_run` (a live process whose start
    time or command line differs is `dead` and is never signalled), `test_when_ps_cannot_answer_the_age_rule_holds`,
    `test_a_reported_or_abandoned_workers_live_run_is_ended_and_recorded_interrupted` and
    `test_a_stopped_workers_live_run_is_left_running`. They start real short `ccp suite run`s under the test fence.
  - `tests/test_board_staleness.py` `Staleness`: `test_a_suite_still_running_of_the_open_run_says_live_for_an_hour`
    becomes `test_a_suite_fold_counts_open_says_live` (a row with no `pid` started 20 minutes ago says
    `live (suite running since …)`); `test_a_suite_started_over_an_hour_ago_with_no_end_does_not_count` becomes
    `test_a_suite_fold_counts_killed_does_not_count` (a row with no `pid` started 35 minutes ago leaves `work` and
    `runs` stale); new `test_a_live_suite_past_an_hour_still_says_live` (a row started 90 minutes ago, with
    `suite._alive` patched to return `alive`).
  - No other test expectation changes.

## Scope

- **In:** `ccp/suite.py` (the row fields, `_alive`, `fold`, `end_bound_runs`, the wait message), `ccp/runs.py` (one
  call, in `abandon`), `ccp/report.py` (one call), `ccp/board.py` (`_live`), `tests/test_suite_liveness.py` (new),
  `tests/test_board_staleness.py` (three tests), `docs/design/board.md` (one sentence); the SPEC, describing this
  task's own feature (§31.1, the accepted proposal): the three passages below, which describe the new fields, the
  liveness rule and the ending, and correct the two sentences the change makes false. No other § sentence changes.

  CURRENT (`docs/spec/02-delivery.md` at `3539c23`), §14.4, the sentence the new one follows, unchanged (the new
  sentence goes right after it and retires none):
  > A staged
  > lane's `started` row has `cmd` `stages` and its stage count as `argc`.

  PROPOSED:
  > A recorded run's `started` row adds `pid`, `host` and `pstart`: the recording `ccp`'s process id, host name and process start time (*Totals*, below).

  CURRENT (`docs/spec/02-delivery.md` at `3539c23`), §14.4, *Totals*, its first sentence (the rest of the item
  unchanged):
  > - **Totals.** A `started` row with no end is `open` while the run may still be going and `killed`
  >   once its run has stopped, reported or been abandoned since, or after 30 minutes (its time runs to
  >   that stop or report when known).

  PROPOSED:
  > - **Totals.** A `started` row with no end, read on the host it names, is `open` while its recording `ccp` is alive (it exists, its start time matches, and its command line is a `ccp suite run`) and `killed` once it is not, whatever its age. A row with no `pid` or `pstart`, a row read on another host, and a row whose process the host's `ps` cannot answer for are `open` while the run may still be going and `killed` once its run has stopped, reported or been abandoned since, or after 30 minutes. A killed run's time runs to its run's stop or report when known. When a worker run reports or is abandoned, `ccp` sends SIGTERM to the recording `ccp` of each of its suite runs it judges alive, which ends the command's whole process group and records the run interrupted, so nothing it started keeps holding the lane's resources; a run it cannot judge is never signalled, and a worker run that only stops ends none.

  CURRENT (`docs/spec/04-observability.md` at `3539c23`), §28.3 *Plane health*, the clause:
  > or a suite of an open run still running (started within 60 minutes, no end
  >    yet; past 60 minutes with no end it no longer counts).

  PROPOSED:
  > or a suite of an open run still running (a `started` row with no end that §14.4 counts as `open`).
- **Out:** the exclusive-lane lock (an flock already dies with its process); judging a row written on another host;
  `ccp suite wait`'s exit codes; ending suite runs when a worker run only stops; a run with no worker run bound to
  it, which nothing ends but itself.

## dod_checks

- id: `cmd-01`
  story: As a product's worker, a suite run still going past 30 minutes is listed open, not killed.
  setup: A checkout of the PR head (any seat); the step builds its scratch product, starts a run in the background, waits for its started row, sets that row's time back to 2026-01-01, and ends the run afterwards.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && S="$D/queue/runs/_suites.jsonl" && (QUEUE_ROOT="$D/queue" CCP_DEV=1 ./bin/ccp --root "$P" suite run --summary -- sleep 30 </dev/null >/dev/null 2>&1 &) && for i in $(seq 150); do grep -q started "$S" 2>/dev/null && break; sleep 0.1; done && python3 -c 'import json, sys; p = sys.argv[1]; rows = [json.loads(l) for l in open(p)]; rows[0]["at"] = "2026-01-01T00:00:00Z"; open(p, "w").write("".join(json.dumps(r) + "\n" for r in rows))' "$S" && QUEUE_ROOT="$D/queue" CCP_DEV=1 ./bin/ccp --root "$P" suite list 2>/dev/null | python3 -c 'import json, sys; print([s["state"] for s in json.load(sys.stdin)["suites"]])'; pkill -f "$P suite run"`.
  expect: prints `['open']`.
  dry run (`3539c23`): printed `['killed']`.
- id: `cmd-02`
  story: As a product's worker, a suite run whose recording ccp died is killed at once, not open for 30 minutes.
  setup: A checkout of the PR head (any seat); the step builds its scratch product, starts a run in the background, waits for its started row, kills its recording ccp with SIGKILL and waits for that process to be gone.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && S="$D/queue/runs/_suites.jsonl" && (QUEUE_ROOT="$D/queue" CCP_DEV=1 ./bin/ccp --root "$P" suite run --summary -- sleep 37 </dev/null >/dev/null 2>&1 &) && for i in $(seq 150); do grep -q started "$S" 2>/dev/null && break; sleep 0.1; done && pkill -9 -f "$P suite run" && for i in $(seq 150); do pgrep -f "$P suite run" >/dev/null || break; sleep 0.1; done && QUEUE_ROOT="$D/queue" CCP_DEV=1 ./bin/ccp --root "$P" suite list 2>/dev/null | python3 -c 'import json, sys; print([s["state"] for s in json.load(sys.stdin)["suites"]])'`.
  expect: prints `['killed']`.
  dry run (`3539c23`): printed `['open']`.
- id: `code-01`
  story: As a plane developer, the tests hold the three-valued liveness rule, the age rule where it cannot judge, the ending on report and abandon only, and the board reading fold.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_suite_liveness.Liveness tests.test_board_staleness.Staleness.test_a_suite_fold_counts_open_says_live tests.test_board_staleness.Staleness.test_a_suite_fold_counts_killed_does_not_count tests.test_board_staleness.Staleness.test_a_live_suite_past_an_hour_still_says_live`.
  expect: exit 0, and the run's summary counts 10 tests (the seven `Liveness` tests and the three board tests).
  dry run (`3539c23`): exit 1, the run FAILED (`tests.test_suite_liveness` and the three board tests do not exist yet).
- id: `spec-01`
  story: As the operator, §14.4 describes the new fields, the liveness rule and the ending, and §28.3 reads it.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0339`.
  expect: exit 0, all three PROPOSED passages found.
  dry run (`3539c23`, with this brief): exit 1, all three passages `not found in the SPEC`.

## Implementation notes

## Verification notes
