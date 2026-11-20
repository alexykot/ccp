---
task_id: 0197-usage-read-once-per-machine
title: Usage is read once per machine, a failed read backs off, and every rule judges the latest good reading
status: pending
kind: feature
depends_on: ["0186-account-facts-on-the-machine"]
spec_refs: ["S3", "S16", "S25"]
review_point: R12
paths: ["ccp/usage.py", "ccp/parallel.py", "ccp/lifecycle.py", "ccp/prompt.py", "ccp/notify.py", "contracts/allowance.schema.json", "contracts/machine.schema.json", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "tests/test_usage_reading.py", "tests/"]
clashes_with: ["0189-spec-states-behaviour", "0191-the-grace-release-ends"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0197-usage-read-once-per-machine

## Intent

When the endpoint behind `allowance_cmd` rate-limits, the plane today runs the command on every
claim and every prompt, records each failure as a reading, and then lets that failed row idle every
free slot and switch the weekly stop off. With this task, every product on a machine shares one
reader: a reading younger than a minute is reused, a failed read backs off before anyone runs the
command again, and the rules (the weekly checkpoint, the session park, the parallel claim rule)
judge the latest good reading no older than 15 minutes, never a failed one. If the account goes
unread for an hour, new claims stop and the operator is told, so the weekly stop cannot lapse
unseen.

## Context (not checked)

All file:line references are at `1774a22` (origin/main when the task was written).

- **Every claim reads.** `ccp/lifecycle.py:283`, in the claim path:
  `sample = usage.sample_allowance(cfg, q, gate=not resumed)`, after the auth probes and before the
  stopped-runner check and `parallel.join_refusal`.
- **Every prompt reads, before its refusal gates.** `ccp/prompt.py:679`, in `build`:
  `usage.session_step(cfg, q, tid, lambda: usage.sample_allowance(cfg, q, gate=False), ...)` runs
  before `resolution_gate`, `review_gate`, `repeat_gate`, `tip_gate`, `body_gate`,
  `runs.check_pending` and `runs.check_running_rounds`. So a prompt that one of them refuses has
  already read usage. None of those gates writes state:
  `for fn in resolution_gate review_gate repeat_gate tip_gate body_gate; do awk "/^def $fn/,/^def [a-z]/" ccp/prompt.py | grep -n "save_\|append\|write\|emit(\|fire("; done`
  at `1774a22` printed nothing.
- **Other readers:** `ccp allowance status --sample` (`usage.status`, `ccp/usage.py:733`),
  `ccp allowance session-wake --sample` (`usage.session_wake`, `ccp/usage.py:998`) and
  `--fire` (`usage.session_fire`, `ccp/usage.py:1080`). `git grep -n "sample_allowance" -- ccp` at
  `1774a22`: those five call sites and the definition.
- **No cache, lock or backoff.** `sample_allowance` (`ccp/usage.py:576`) runs
  `subprocess.run(["/bin/sh", "-c", cmd], ..., timeout=8)` each time it is called.
  `grep -n "flock\|backoff\|retry_after" ccp/usage.py` at `1774a22`: no match.
- **A failed read becomes the latest row.** On a non-zero exit or unparsable output, `wins = []`,
  and the row is appended with `five_hour` and `seven_day` null (`ccp/usage.py:582-592`).
  - `parallel.next_choice` (`ccp/parallel.py:314`, `time.time() - ... < 15 * 60`) treats the
    latest row as fresh for a quarter of an hour, whatever it holds, and `join_refusal`
    (`ccp/parallel.py:257-261`) refuses a second task when `five_hour` is None and `no_five_hour_limit` is false. A failed row has both
    figures null, so `ccp tasks next` reports slots full for up to 15 minutes after one failure, and
    the claim, which judges the row it just wrote, refuses too.
  - The weekly stop skips a failed row: `if seven is None:` (`ccp/usage.py:594`) adds a warning, and
    the stop loop only looks at windows whose `pct` is not None. So spend is unbounded while the
    endpoint fails. SPEC §25.1 states this: an unknown reading "gates nothing".
- **The endpoint answers HTTP 429** when read too often. The claim and prompt paths read on every
  attempt, so a runner retrying a refused launch reads usage on each retry, which keeps the endpoint
  rate-limiting. That is the failure that motivated this task.
- **SPEC drift.** §25.1 says "`ccp tasks claim` and `ccp board build` run the machine's
  `allowance_cmd`". The board never reads: `ccp/board.py:343` and `ccp/forecast.py:1288` call
  `usage.status(cfg, q, sample=False)`. `contracts/machine.schema.json` (`allowance_cmd`'s
  description) says the same as the SPEC.
- **The machine file's directory.** `scripts/observability/lib.py` `def machine_path`:
  `bindings_dir() / MACHINE_FILE`, so `CCP_BINDINGS_DIR` moves it. `tests/__init__.py` points
  `CCP_BINDINGS_DIR` at `/nonexistent/control-plane-bindings-guard`, which cannot be created. Tests
  that set `telemetry.allowance_cmd` in plane.json without a bindings dir:
  `grep -ln allowance_cmd tests/*.py` plus `grep -c CCP_BINDINGS_DIR` on each at `1774a22`:
  `test_account_accessor`, `test_allowance_windows`, `test_notify_lead`, `test_notify`,
  `test_parallel_claims`, `test_session_park`, `test_toolkit` (seven files). Several change the stub's
  output between two claims, so a working cache would break them. Hence the uncached fallback below.
- **The lock.** `ccp/queue.py` `def file_lock(path)` takes an exclusive flock on `<path>.lock`;
  use it.
- **The notice.** `notify.fire(cfg, q, trigger, task_id=..., ident=..., reason=...)`
  (`ccp/notify.py:176`) already takes a reason. The claim fires `allowance_checkpoint` on exit 5
  (`ccp/lifecycle.py:286`).
- **The operator's decision on the unread policy** (2026-11-20, verbatim: "T1 - (a)"): option (a),
  as Scope states it. The parallel claim rule still refuses a second claim with no reading in force
  (the current rule), and after an hour unread a new claim stops at the checkpoint and the operator
  is told.
- **Clashes.** Task 0191 edits `ccp/usage.py` (`account`'s old-place fallback) and 0189 rewrites
  §16 and §25 to drop default numbers. Both are pending. If either merges first, the CURRENT quotes
  below move, and the brief must be re-quoted and signed again before the claim.

## Scope

- **In:** `ccp/usage.py`, `ccp/parallel.py`, `ccp/lifecycle.py`, `ccp/prompt.py`, `ccp/notify.py`
  (module docstring only), `contracts/allowance.schema.json`, `contracts/machine.schema.json`,
  `docs/spec/01-model.md`, `docs/spec/02-delivery.md`, `docs/spec/04-observability.md`,
  `tests/test_usage_reading.py` (new), and existing tests that the shared reader breaks.

### The constants (in `ccp/usage.py`, by these names)

`READ_TTL_S = 60`, `BACKOFF_MIN_S = 60`, `BACKOFF_MAX_S = 900`, `RETRY_AFTER_MAX_S = 3600`,
`IN_FORCE_S = 900`, `UNREAD_STOP_S = 3600`. None of them is a setting. `ccp/parallel.py`'s
`15 * 60` becomes `usage.IN_FORCE_S`.

### 1. One reader per machine: `usage.reading(cfg, q, purpose)`

- **Who calls it.** It replaces every call of `sample_allowance`. `purpose` is one of `claim`,
  `prompt`, `fire` and `sample` (`ccp allowance status --sample`, `session-wake --sample`). Every
  purpose follows the same TTL and backoff. `purpose` is not recorded.
- **The cache file.** `allowance-cache-<first 12 hex of sha256(cmd)>.json`, in the machine file's
  directory (`lib.bindings_dir()`). It is read and written under `queue.file_lock(<cache>)`, and the
  lock is held while the command runs, so a concurrent caller waits and then reuses. It holds:
  - `good`: the last good reading (the row as appended, with its `at`);
  - `failing_since`: when the current run of failures began, null after a success;
  - `backoff_s` and `backoff_until`.

  No output text goes in it.
- **A good reading** is one where the command exits 0 and prints JSON in which at least one window
  has a known `pct`. Anything else is a failed read.
- **Under the lock, in order:**
  1. **Inside the backoff** (`now < backoff_until`): the command does not run and no failed row is
     appended.
  2. **Reuse:** if `good` is younger than `READ_TTL_S`, it is reused and the command does not run.
  3. **Otherwise the command runs.** On a good reading: append the row as today, emit
     `allowance/sample` as today, store it as `good`, and clear `failing_since`, `backoff_s` and
     `backoff_until`.
- **A reused reading reaches the product's log.** Whenever the command did not run and `good` is
  newer than the product's latest good row in `board/allowance.jsonl`, `good` is appended to that log
  with its original `at` and `reused: true`, and nothing is emitted. So the product's log always
  holds the freshest good reading the machine has, and readers of the latest row keep working.
- **Uncached fallback.** When the directory cannot be created or locked (the tests' guard path), the
  reader runs the command uncached, as today, and appends its row with `shared: false`. No warning
  is given: in production a product's binding lives in that directory, so it exists.
- **Return value.** `reading` returns the reading in force (§3) together with what this call did
  (`ran`, `reused`, `backed_off`, `failed`), for the callers' warnings.

### 2. A failed read backs off

- **The row.** A failed run appends the unknown row as today, plus `failed: true` and `exit`: the
  exit code, `0` for a zero exit with an unusable reading, and null when the command did not exit (a
  timeout, or no shell). It never holds stderr or stdout text. It emits `allowance/sample` as today.
- **The backoff.** `backoff_s` is `BACKOFF_MIN_S` on the first failure and doubles on each further
  failure, up to `BACKOFF_MAX_S`. `failing_since` is set on the first failure only.
- **`retry_after_s`.** Stdout is parsed as JSON whatever the exit code, for `retry_after_s` only;
  windows are read only on exit 0. A number `retry_after_s` sets
  `backoff_until = now + max(backoff_s, min(retry_after_s, RETRY_AFTER_MAX_S))`. `parse_windows`
  already ignores a top-level non-object value in the legacy form; keep it so.
- **The schema.** `contracts/allowance.schema.json` accepts an optional top-level `retry_after_s`
  (a number, minimum 0) in both forms, and an object holding only `retry_after_s` (what a
  rate-limited reader prints). Its description names it. In the legacy branch, `properties:
  {retry_after_s: ...}` exempts it from `additionalProperties`.

### 3. The reading in force

- **What it is:** the product's latest row in `board/allowance.jsonl` that is good (`failed` not
  true, and `five_hour` or `seven_day` known), with an `at` no older than `IN_FORCE_S`. A function
  `usage.in_force(q)` returns it, or None.
- **Who judges it:**
  - **The weekly checkpoint** at the claim: the `over` loop of `sample_allowance` judges the windows
    of the reading in force, not of the row just written. So a failed read with a good reading from
    10 minutes ago still stops a claim when that reading is past the checkpoint.
  - **The session park**, at the claim and at `ccp prompt`: `session_step` gets the reading in force.
  - **§16.3 rule 5**, at the claim: `join_refusal` gets the reading in force. With none, a second
    claim refuses ("no good usage reading in the last 15 minutes, so no second task is taken
    (rule 5)").
  - **§16.3 rule 5**, at `ccp tasks next`: `next_choice` judges the reading in force. With none, it
    does not judge rule 5 (`five_known=False`, as today for a stale row) and leaves it to the claim,
    which reads. A failed row is never in force, so it never makes `next` report slots full.
- **With no reading in force**, the checkpoint and the park gate nothing and lift nothing, and the
  claim and the prompt carry a `warning:` naming how long the account has gone unread.

### 4. `ccp prompt` and refused retries

- In `ccp/prompt.py` `build`, the `session_step` call moves below the refusal gates: after
  `runs.check_running_rounds`, before `runs.next_round`. It calls `reading(cfg, q, "prompt")`. So a
  prompt one of those gates refuses reads nothing, and a prompt that passes them reads at most once
  per `READ_TTL_S` per machine and never inside a backoff.
- The claim keeps its place in the order. Its reads are bounded the same way, so a refused claim
  retried in a loop runs the command at most once per `READ_TTL_S` per machine, and not at all inside
  a backoff.
- `session_fire` and the two `--sample` paths call `reading` with their purpose. `--fire` judges the
  reading in force.

### 5. The unread checkpoint (operator's option (a))

- **Unread since:** the cache's `failing_since`. Under the uncached fallback, it is the `at` of the
  first failed row after the product's latest good row (or the log's first failed row if none is
  good).
- **The stop.** When `allowance_cmd` is set, no reading is in force, and `now - unread since >=
  UNREAD_STOP_S`, a **new** claim refuses with exit 5:
  "allowance checkpoint: the account's usage has not been read for N minutes (SPEC §25.3) ...".
  The message tells the runner to stop and tell the lead, and the lead to check `allowance_cmd`. The
  claim then fires `allowance_checkpoint` with `reason="usage unread"` through the existing exit-5
  handler.
  - A resumed claim is never refused.
  - `ccp allowance continue` does not clear it. The next good reading does.
- Between `IN_FORCE_S` and `UNREAD_STOP_S` unread, a claim into an empty active set proceeds with the
  warning, and a second claim refuses by rule 5.
- `ccp/notify.py`'s module docstring names the second cause of `allowance_checkpoint`.

### 6. SPEC changes (signed in the brief, §31)

CURRENT texts are verbatim at `1774a22`.

**a. §16.3 rule 5**, `docs/spec/02-delivery.md`.

CURRENT:
> 5. The account's session-window usage, sampled at this claim, is below the session ceiling (the
>    gating session window, §25). A sample whose weekly figure is known but has no session figure
>    means the account has no session limit: the rule passes. A sample with neither (a failed
>    read) refuses. A machine without `allowance_cmd` reads no usage: the rule passes (§25.1).

PROPOSED:
> 5. The account's session-window usage, in the reading in force (the latest good reading no older
>    than 15 minutes, §25.1), is below the session ceiling (the gating session window, §25). A
>    reading whose weekly figure is known but has no session figure means the account has no
>    session limit: the rule passes. With no reading in force, a second claim refuses; a failed read
>    is never judged. `ccp tasks next` judges this rule on the reading in force and, with none,
>    leaves it to the claim, which reads. A machine without `allowance_cmd` reads no usage: the rule
>    passes (§25.1).

**b. §25.1**, `docs/spec/04-observability.md`: the whole paragraph is replaced.

CURRENT:
> `ccp tasks claim` and `ccp board build` run the machine's `allowance_cmd`, from the machine file
> beside the bindings (§8.3), shared by every product on the machine. Without it no usage is read
> and nothing bounds spend: `ccp init` and the session-start check warn, naming the key, and the
> board shows `usage unread`. The command prints the account's usage windows as JSON
> (`contracts/allowance.schema.json`): `{windows: [{name, pct, resets_at}]}`, or the legacy form,
> one object per window with `utilization` and `resets_at`. Each run appends a sample to
> `board/allowance.jsonl` and emits `allowance/sample`. If the command fails or prints something
> unexpected, the sample is recorded as unknown, never as zero, and an unknown reading is a
> `warning:` on the claim that gates nothing.

PROPOSED:
> `ccp tasks claim`, `ccp prompt` (once its other refusal gates pass), `ccp allowance status
> --sample` and `ccp allowance session-wake --sample` and `--fire` take a reading of the machine's
> `allowance_cmd`, from the machine file beside the bindings (§8.3), shared by every product on the
> machine. Without it no usage is read and nothing bounds spend: `ccp init` and the session-start
> check warn, naming the key, and the board shows `usage unread`. The command prints the account's
> usage windows as JSON (`contracts/allowance.schema.json`): `{windows: [{name, pct, resets_at}]}`,
> or the legacy form, one object per window with `utilization` and `resets_at`. It may add
> `retry_after_s`, the seconds to wait before it is run again.
>
> - **One reader per machine.** A reading is taken under an exclusive lock on a cache file in the
>   machine file's directory, one per command. The last good reading (exit 0, at least one window
>   figure known) is reused while it is younger than 60 seconds; otherwise the command runs. Each
>   run appends a sample to `board/allowance.jsonl` and emits `allowance/sample`. A reused reading
>   newer than the product's latest good sample is appended with its own `at` and `reused: true`,
>   and emits nothing.
> - **A failed read backs off.** If the command fails or prints something unexpected, the sample is
>   recorded as unknown, never as zero, with `failed: true` and its exit code, and never its output.
>   No caller then runs the command for 60 seconds, doubling at each further failure up to
>   15 minutes, or for the `retry_after_s` it printed when that is longer (at most 60 minutes). The
>   next good reading ends the backoff.
> - **The reading in force** is the product's latest good sample no older than 15 minutes. The
>   weekly checkpoint (§25.3), the session park (§25.4) and the parallel claim rule (§16.3 rule 5)
>   judge only it, never a failed sample. With none in force, the checkpoint and the park gate
>   nothing, and the claim and the prompt say so in a `warning:`. Once the account has gone unread
>   for 60 minutes (no good reading since its failures began), a new claim refuses (§25.3).

This retires "`ccp board build` run[s] the machine's `allowance_cmd`", which was never true (a
description fix), and "an unknown reading is a `warning:` on the claim that gates nothing".

**c. §25.3**, `docs/spec/04-observability.md`.

CURRENT:
> - When a sample reaches it, `ccp tasks claim` refuses a **new** claim (exit 5, "allowance
>   checkpoint"). A resumed claim of a runner's own lease is never refused.

PROPOSED:
> - When the reading in force (§25.1) reaches it, `ccp tasks claim` refuses a **new** claim (exit 5,
>   "allowance checkpoint"). A resumed claim of a runner's own lease is never refused.
> - **An account gone unread.** When the account has had no good reading for 60 minutes (§25.1),
>   `ccp tasks claim` refuses a **new** claim the same way (exit 5, "allowance checkpoint", usage
>   unread), and fires `allowance_checkpoint` with the reason `usage unread`, so the checkpoint
>   cannot lapse unseen. A resumed claim is never refused. The next good reading clears it; no
>   decision does.

**d. §25.4**, `docs/spec/04-observability.md`, three sentences.

CURRENT:
> `ccp tasks claim`
>   (new or resumed) and `ccp prompt` (before it opens a run) take a sample; when the window is at or
>   above the park, they refuse with **exit 6** ("session park"),

PROPOSED:
> `ccp tasks claim` (new or resumed) and `ccp prompt` (once its other refusal gates pass, before it
>   opens a run) take a reading (§25.1) and judge the reading in force; when the window is at or above
>   the park, they refuse with **exit 6** ("session park"),

(the rest of that sentence is unchanged).

CURRENT:
> - An unknown reading, or no `allowance_cmd`, gates nothing and lifts nothing.

PROPOSED:
> - No reading in force (§25.1), or no `allowance_cmd`, gates nothing and lifts nothing.

CURRENT:
> - **`--fire`** (what the wake runs) takes a fresh sample;

PROPOSED:
> - **`--fire`** (what the wake runs) takes a reading (§25.1) and judges the reading in force;

**e. §3.6 trigger table**, `docs/spec/01-model.md`, the `allowance_checkpoint` row.

CURRENT:
> | `allowance_checkpoint` | `ccp tasks claim` refused at a weekly checkpoint (exit 5, §25.3) | the task |

PROPOSED:
> | `allowance_checkpoint` | `ccp tasks claim` refused at a weekly checkpoint, or with the account's usage unread for 60 minutes (exit 5, §25.3) | the task; the reason `usage unread` for the latter |

**f. Contract text, not a § rule:**
- `contracts/machine.schema.json`, `allowance_cmd`'s description: "run by `ccp tasks claim` and
  `ccp board build` for every product on this machine" becomes "read through one shared reader
  per machine by `ccp tasks claim` and `ccp prompt` (§25.1) for every product on this machine".
- `contracts/allowance.schema.json`: as in §2 above.

### 7. Tests: `tests/test_usage_reading.py` (new)

Fenced per `tests/__init__.py`:
- every test sets `CCP_BINDINGS_DIR` to a temp dir and uses a temp queue and product;
- the allowance command is a stub script that appends a line to a counter file on each run and
  prints what the test sets (a reading, `{"retry_after_s": N}` with exit 1, or stderr text with
  exit 1);
- time is moved by patching `time.time` in `ccp.usage`, or by writing `at`, `failing_since` and
  `backoff_until` into the log and the cache.

Class `SharedReading`, these six tests:
- `test_two_claims_within_the_ttl_read_once`: two claims of two tasks within 60 s run the stub
  once. The second appends nothing, since the product's log already holds that reading. A
  `reading()` from a second temp queue (another product on the machine) appends the reading with
  `reused: true` and its original `at`.
- `test_a_failed_read_backs_off`: the stub exits 1 and writes `secret-text` on stderr.
  - A claim appends one row with `failed: true` and `exit: 1`, and no field holds `secret-text`.
  - A second claim 30 s later runs the stub no more and appends no row.
  - After 61 s, a claim runs it again; on a second failure the backoff is 120 s.
  - After a good reading, the backoff is cleared.
- `test_retry_after_is_honoured`: the stub prints `{"retry_after_s": 300}` and exits 1. A claim at
  +200 s does not run it. A claim at +301 s does.
- `test_a_failed_read_keeps_the_good_reading_in_force`: the log holds a good reading from 10 minutes
  ago, `five_hour` 20 and `seven_day` 50; the stub now exits 1, as on HTTP 429. A claim beside a task
  in flight (parallel on, `max_in_flight` 2, no clash) is not refused by rule 5, and `ccp tasks next`
  does not report slots full. With the same reading but `seven_day` 95 against the default
  checkpoint of 90, a new claim refuses with exit 5.
- `test_an_hour_unread_refuses_a_new_claim`: the cache's `failing_since` is 61 minutes ago, no good
  row is newer than 15 minutes, and the backoff is in force. A new claim exits 5 with "usage" and
  "not been read" in the message, and the queue's ledger holds a `notify` `pending` event
  (`notify.record_pending`) for `allowance_checkpoint` with reason `usage unread`. At 59 minutes, a claim into an empty active set
  proceeds, with a warning.
- `test_a_refused_prompt_reads_nothing`: a claimed task whose last verify round reported with no fix
  round since. `ccp prompt verify --pr 1 --head <sha>` with no `--note` exits 4 (`repeat_gate`), and
  the stub's counter file is empty.

Existing tests that a working cache or the moved prompt step breaks are updated to clear the cache
or use a fresh `CCP_BINDINGS_DIR`. No expectation of an existing test changes otherwise; any test
whose expectation changes is named in the Implementation notes with why.

- **Out:** the board and the forecast, which read the log and never the command; the session-park
  percentages, the checkpoint, the ceiling and the decisions; the receiver's telemetry whitelist (no
  new emitted field); `ccp allowance continue`.

## dod_checks

- id: `ur-01`
  story: As the plane, the shared reader, its backoff, the reading in force and the unread stop are
  tested.
  setup: a checkout of the PR head (any seat).
  steps:
    1. Run `python3 -B -m unittest -v tests.test_usage_reading 2>&1 | grep -E '^test_|^OK|FAILED'`.
  expect: six `... ok` lines, one for each of `test_two_claims_within_the_ttl_read_once`,
    `test_a_failed_read_backs_off`, `test_retry_after_is_honoured`,
    `test_a_failed_read_keeps_the_good_reading_in_force`, `test_an_hour_unread_refuses_a_new_claim`
    and `test_a_refused_prompt_reads_nothing`, then `OK`.
  dry run (`1774a22`): `tests/test_usage_reading.py` does not exist.

- id: `ur-02`
  story: As the plane, the tests bite on the TTL, the reading in force and the prompt's order.
  setup: three separate copies of the PR head (`git worktree add <tmp> HEAD`, never the branch's
    own worktree), each with one planted fault:
    (a) `READ_TTL_S = 0` in `ccp/usage.py`;
    (b) `IN_FORCE_S = 0` in `ccp/usage.py`;
    (c) in `ccp/prompt.py` `build`, the `session_step` line moved back above `resolution_gate`.
  steps:
    1. In each copy, run `python3 -B -m unittest tests.test_usage_reading 2>&1 | tail -3`.
  expect: (a) fails `test_two_claims_within_the_ttl_read_once`; (b) fails
    `test_a_failed_read_keeps_the_good_reading_in_force`; (c) fails
    `test_a_refused_prompt_reads_nothing`. Each run ends in `FAILED`.
  dry run (`1774a22`): n/a, the constants and the test file do not exist yet.

- id: `ur-03`
  story: As the SPEC reader, §16.3, §25.1, §25.3, §25.4 and §3.6 say what the code does, and the
  contracts agree.
  setup: a checkout of the PR head.
  steps:
    1. `grep -c "the latest good reading no older than 15 minutes" docs/spec/02-delivery.md`
    2. `grep -c "One reader per machine\|younger than 60 seconds\|gone unread for 60 minutes\|An account gone unread\|No reading in force (§25.1)" docs/spec/04-observability.md`
    3. `grep -c "usage unread for 60 minutes" docs/spec/01-model.md`
    4. `grep -c retry_after_s contracts/allowance.schema.json`
    5. `grep -c "and \`ccp board build\`" docs/spec/04-observability.md contracts/machine.schema.json`
  expect: step 1 prints `1`; step 2 prints `5`; step 3 prints `1`; step 4 prints at least `1`; step 5
    prints `0` for both files.
  dry run (`1774a22`): steps 1 to 4 print `0`; step 5 prints `1` for each file.

- id: `ur-04`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh; echo rc=$?`.
    2. Run `ccp --root . tasks check`, `ccp --root . docs check`, then `git branch --list 'state/*'`.
  expect: step 1 ends `rc=0`; both checks in step 2 exit 0, and the branch list prints nothing.
  dry run: n/a, the gate runs on the PR head.

## Refs

- SPEC §3.6 (the notice), §16.3 rule 5, §25.1, §25.3, §25.4.
- Task 0186 (the account's facts in the machine file, which this builds on).
- The operator's decision on the unread policy, 2026-11-20: "T1 - (a)".

## Implementation notes

## Verification notes
