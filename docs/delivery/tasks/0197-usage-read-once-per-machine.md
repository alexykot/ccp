---
task_id: 0197-usage-read-once-per-machine
title: Usage is read once per machine, a failed read backs off, and every rule judges the latest good reading
status: pending
kind: feature
depends_on: ["0186-account-facts-on-the-machine"]
spec_refs: ["S3", "S8", "S16", "S25"]
review_point: R12
paths: ["ccp/usage.py", "ccp/parallel.py", "ccp/lifecycle.py", "ccp/prompt.py", "ccp/notify.py", "ccp/forecast.py", "contracts/allowance.schema.json", "contracts/machine.schema.json", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "plugin/agents/delivery-runner.md", "plugin/skills/spec-maintainer/SKILL.md", "plugin/orientation.md", "tests/__init__.py", "tests/test_usage_reading.py", "tests/"]
clashes_with: ["0189-spec-states-behaviour", "0191-the-grace-release-ends"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0197-usage-read-once-per-machine

## Intent

Today, when the endpoint behind `allowance_cmd` rate-limits, every claim and every prompt still
runs the command and records each failure as a reading. That failed row then idles every free slot
and switches the weekly stop off. After this task:
- every product on a machine shares one reader, and a reading younger than a minute is reused;
- after a failed read, nobody runs the command again until a backoff has passed;
- a failed reading is never judged. A rule that lets work through judges the latest good reading
  no older than 15 minutes. A rule that stops work judges the latest good reading of any age, as
  long as its window has not reset;
- if the account goes unread for an hour, new claims stop and the operator is told, so the weekly
  stop cannot lapse unseen.

## Context (not checked)

File:line references are at `1774a22`. None of the files this task reads changed between it and
`438c97f`: `git diff --stat 1774a22 438c97f -- docs/spec ccp contracts plugin tests/__init__.py`
printed nothing.

- **Every claim reads.** `ccp/lifecycle.py:283`, in the claim path:
  `sample = usage.sample_allowance(cfg, q, gate=not resumed)`. It runs after the auth probes and
  before the stopped-runner check and `parallel.join_refusal`.
- **Every prompt reads, before its refusal gates.** `ccp/prompt.py:679`, in `build`:
  `usage.session_step(cfg, q, tid, lambda: usage.sample_allowance(cfg, q, gate=False), ...)` runs
  before `resolution_gate`, `review_gate`, `repeat_gate`, `tip_gate`, `body_gate`,
  `runs.check_pending` and `runs.check_running_rounds`. So a prompt that one of them refuses has
  already read usage.
- **None of the five prompt gates writes state.** Each was searched for `save_`, `append`, `write`,
  `emit(` and `fire(` with
  `awk -v f=$fn '$0 ~ "^def "f"\\(" {p=1} p && /^def / && $0 !~ "^def "f"\\(" {p=0} p' ccp/prompt.py | grep -c 'save_\|append\|write\|emit(\|fire('`
  at `1774a22`. Body lines / matches: `resolution_gate` 45/0, `review_gate` 36/0, `repeat_gate`
  15/0, `tip_gate` 40/0, `body_gate` 30/0.
- **Other readers:**
  - `ccp allowance status --sample` (`usage.status`, `ccp/usage.py:733`);
  - `ccp allowance session-wake --sample` (`usage.session_wake`, `ccp/usage.py:998`);
  - `--fire` (`usage.session_fire`, `ccp/usage.py:1080`).

  `git grep -n "sample_allowance" -- ccp` at `1774a22`: those five call sites and the definition.
- **No cache, lock or backoff.** `sample_allowance` (`ccp/usage.py:576`) runs
  `subprocess.run(["/bin/sh", "-c", cmd], ..., timeout=8)` every time it is called.
  `grep -n "flock\|backoff\|retry_after" ccp/usage.py` at `1774a22`: no match.
- **Each product works out its own fields from the raw windows.** `project(cfg, wins, q, prev)`
  (`ccp/usage.py:552`) uses the product's own checkpoint (its decisions) and the previous row's
  gating window names. So the same raw reading can give different fields for different products,
  and the cache must hold the raw windows, not one product's row.
- **A failed read becomes the latest row.** On a non-zero exit or unparsable output, `wins = []`.
  The row is appended with `five_hour` and `seven_day` null (`sed -n 582,592p ccp/usage.py`).
  - `parallel.next_choice` (`ccp/parallel.py:314`, `time.time() - ... < 15 * 60`) treats the
    latest row as fresh for a quarter of an hour, whatever it holds.
  - `join_refusal` (`ccp/parallel.py:257-261`) refuses a second task when `five_hour` is None and
    `no_five_hour_limit` is false. A failed row has both figures null. So after one failure,
    `ccp tasks next` reports slots full for up to 15 minutes, and the claim refuses too, since it
    judges the row it has just written.
  - The weekly stop skips a failed row: `if seven is None:` (`ccp/usage.py:594`) only adds a
    warning, and the stop loop looks only at windows whose `pct` is not None. So spend is unbounded
    while the endpoint fails. SPEC §25.1 says so: an unknown reading "gates nothing".
- **Readers of the last row**, each listed by `grep -n "_latest(q)\|\[-1\]" ccp/usage.py ccp/forecast.py`
  at `1774a22`:
  - `project`'s `prev` (`ccp/usage.py:587`);
  - `continue_` (`ccp/usage.py:708`);
  - `status` (`ccp/usage.py:734`);
  - `session_wake` (`ccp/usage.py:999-1000`) and `session_armed` (`ccp/usage.py:1055`);
  - the forecast's allowance projection (`ccp/forecast.py:1050-1052`);
  - `session_fire`'s fallback, `rec or _latest(q)` (`ccp/usage.py:1081`).

  The other matches are `_latest` itself (`ccp/usage.py:988`), a decision list
  (`ccp/usage.py:745`) and the fit's sample list (`ccp/forecast.py:913`). Scope §3 says which
  readers move to the latest good row.
- **The endpoint answers HTTP 429** when it is read too often. The claim and prompt paths read on
  every attempt, so a runner retrying a refused launch reads usage on each retry, and the endpoint
  keeps rate-limiting. That is the failure that motivated this task.
- **SPEC drift.** §25.1 says "`ccp tasks claim` and `ccp board build` run the machine's
  `allowance_cmd`". The board never reads: `ccp/board.py:343` and `ccp/forecast.py:1288` call
  `usage.status(cfg, q, sample=False)`. `contracts/machine.schema.json` (`allowance_cmd`'s
  description) repeats the SPEC's wording.
- **The machine file's directory.** In `scripts/observability/lib.py`, `def machine_path` returns
  `bindings_dir() / MACHINE_FILE`, so `CCP_BINDINGS_DIR` moves it. `tests/__init__.py` points
  `CCP_BINDINGS_DIR` at `/nonexistent/control-plane-bindings-guard`, which cannot be created.
  - Tests that set `telemetry.allowance_cmd` without a bindings dir, found with
    `grep -ln allowance_cmd tests/*.py` and then `grep -c CCP_BINDINGS_DIR` on each at `1774a22`:
    `test_account_accessor`, `test_allowance_windows`, `test_notify_lead`, `test_notify`,
    `test_parallel_claims`, `test_session_park`, `test_toolkit` (seven files).
  - Several of them change the stub's output between two claims, so a shared cache would break
    them. Hence the test-only switch in Scope §1.
- **The lock.** `ccp/queue.py` `def file_lock(path)` takes an exclusive flock on `<path>.lock`.
  Use it.
- **The notice.** `notify.fire(cfg, q, trigger, task_id=..., ident=..., reason=...)`
  (`ccp/notify.py:176`) already takes a reason, which `record_pending` records on the ledger's
  `notify` `pending` event. The claim fires `allowance_checkpoint` on exit 5
  (`ccp/lifecycle.py:286`).
- **Who reads the exit 5 handling.**
  - `plugin/agents/delivery-runner.md` ("Stop, report, rotate", item (c): "tell the lead the weekly
    usage and the reset time it printed");
  - `plugin/skills/spec-maintainer/SKILL.md` ("The allowance checkpoint is the operator's call",
    `sed -n 145,149p` at `1774a22`), which tells the lead to record a `continue` decision;
  - `plugin/orientation.md` (the notice list, "the allowance checkpoint", `sed -n 42,43p` at
    `1774a22`).

  An unread stop needs no decision, so each must say what to do instead.
- **The operator's decision on the unread policy** (2026-11-20, verbatim: "T1 - (a)"): option (a),
  as Scope states it. The parallel claim rule still refuses a second claim when no reading is in
  force (the current rule). After an hour unread, a new claim stops at the checkpoint and the
  operator is told.
- **A reader with no figures.** An account whose reader legitimately prints no window figure (no
  usage limit, say) is a failing reader under this task: it backs off, and after an hour it stops
  new claims. Such a machine unsets `allowance_cmd` instead: no usage is read, and the existing
  §25.1 warning says that nothing bounds spend. The task does not special-case it.
- **Clashes.** Two pending tasks touch the same ground:
  - 0191 edits `ccp/usage.py` (`account`'s old-place fallback);
  - 0189 rewrites §16 and §25 to drop default numbers.

  If either merges first, the CURRENT quotes below move, and the brief must be re-quoted and
  signed again before the claim.

## Scope

- **In:** `ccp/usage.py`, `ccp/parallel.py`, `ccp/lifecycle.py`, `ccp/prompt.py`, `ccp/forecast.py`,
  `ccp/notify.py` (module docstring only), `contracts/allowance.schema.json`,
  `contracts/machine.schema.json`, `docs/spec/01-model.md`, `docs/spec/02-delivery.md`,
  `docs/spec/04-observability.md`, `plugin/agents/delivery-runner.md`,
  `plugin/skills/spec-maintainer/SKILL.md`, `plugin/orientation.md`, `tests/__init__.py`,
  `tests/test_usage_reading.py` (new), and the existing tests that the moved prompt step breaks.

### The constants and the clock (in `ccp/usage.py`)

- **Constants**, by these names: `READ_TTL_S = 60`, `BACKOFF_MIN_S = 60`, `BACKOFF_MAX_S = 900`,
  `RETRY_AFTER_MAX_S = 3600`, `IN_FORCE_S = 900`, `UNREAD_STOP_S = 3600`. None of them is a
  setting. `ccp/parallel.py`'s `15 * 60` becomes `usage.IN_FORCE_S`.
- **One clock:** `usage.now()`, which returns `time.time()`. Every time this task computes reads it:
  - the reader (TTL, backoff, `failing_since`, the `at` it stamps on a row);
  - `in_force`, `latest_good` and the unread time;
  - the stop judgments (`resets_at` ahead);
  - `parallel.next_choice`'s freshness.

  The tests patch `ccp.usage.now` and nothing else.

### 1. One reader per machine: `usage.reading(cfg, q)`

- **Who calls it.** It replaces every call of `sample_allowance`: the claim, `ccp prompt`,
  `ccp allowance status --sample`, `session-wake --sample` and `--fire`. It takes no purpose
  argument, since every caller follows the same TTL and backoff.
- **What counts as good.** One predicate, `usage.good(windows)`, decides it in every place: at
  least one window in the list has a known `pct`.
  - A read is good when the command exits 0 and `good(parse_windows(json))` holds.
  - A row in the log is good when it does not say `failed: true` and `good(row["windows"])` holds.
    So a row written before this task is judged by its own windows.
- **The cache file.** It is `allowance-cache-<first 12 hex of sha256(cmd)>.json`, in the machine
  file's directory (`lib.bindings_dir()`). It is read and written under `queue.file_lock(<cache>)`,
  and the lock is held while the command runs, so a concurrent caller waits and then reuses the
  result. It holds:
  - `good`: the last good read, as its raw `windows` (the `parse_windows` output) and its `at`;
  - `failing_since`: when the current run of failures began, or null;
  - `backoff_s` and `backoff_until`.

  It never holds a product's projected fields or any output text.
- **Under the lock, in order:**
  1. **Inside the backoff** (`now() < backoff_until`): the command does not run, and no failed row
     is appended.
  2. **Reuse:** if `good` is younger than `READ_TTL_S`, the command does not run.
  3. **Otherwise the command runs.** On a good read:
     - store it as `good`;
     - clear `failing_since`, `backoff_s` and `backoff_until`;
     - append the product's row as today (`{"at": ..., **project(cfg, wins, q, latest_good(q))}`);
     - emit `allowance/sample` as today.
- **A reused read reaches the product's log.** Whenever the command did not run and the cache's
  `good` is newer than the product's latest good row, the product appends
  `{"at": good.at, **project(cfg, good.windows, q, latest_good(q)), "reused": true}` and emits
  nothing. So each product works out its own fields from the shared raw windows, its log always
  holds the freshest good read the machine has, and the readers of the latest row keep working.
- **When the cache cannot be locked or written in production:**
  - the claim and the prompt carry a `warning:` ("usage reads are not shared: <reason>");
  - the reader works from the product's own log: a good row younger than `READ_TTL_S` is reused,
    and the backoff is computed from the log (§2).
- **Test-only switch.** With `CCP_ALLOWANCE_UNSHARED=1`, the reader runs the command on every call,
  with no cache, no reuse and no backoff, as before this task. It appends its row with
  `shared: false` and gives no warning. `tests/__init__.py` sets the switch, with a comment saying
  why, and the new tests unset it. Nothing else reads it, and the SPEC does not name it.

### 2. A failed read backs off

- **The row.** A failed run appends the unknown row as today, plus:
  - `failed: true`;
  - `exit`: the exit code, `0` for a zero exit with no usable figure, and null when the command did
    not exit (a timeout, or no shell);
  - `retry_after_s`, when the command printed one.

  The row never holds stderr or stdout text. The failure emits `allowance/sample` as today.
- **The backoff.** `backoff_s` is `BACKOFF_MIN_S` on the first failure and doubles on each further
  failure, up to `BACKOFF_MAX_S`. `failing_since` is set on the first failure only. The next good
  read clears both.
- **`retry_after_s`.** Stdout is parsed as JSON whatever the exit code, but only for `retry_after_s`;
  windows are read only on exit 0. A number `retry_after_s` sets
  `backoff_until = now() + max(backoff_s, min(retry_after_s, RETRY_AFTER_MAX_S))`. `parse_windows`
  already ignores a top-level value that is not an object in the legacy form; keep it so.
- **The backoff from the log** (the production fallback in §1):
  - `n` is the number of failed rows after the latest good row;
  - `backoff_s = min(BACKOFF_MIN_S * 2^(n-1), BACKOFF_MAX_S)`, raised to the last failed row's
    `retry_after_s` (capped) when it has one;
  - the backoff runs from that row's `at`.

### 3. Which reading each judgment uses

- **The latest good row**, `usage.latest_good(q)`: the product's latest good row in
  `board/allowance.jsonl`, of any age, or None.
- **The reading in force**, `usage.in_force(q)`: the latest good row when its `at` is no older than
  `IN_FORCE_S`, else None.
- **Judgments that stop work use the latest good row**, of any age, while the window they judge has
  not reset. Usage only grows within a window, so an old figure at or past a threshold still holds.
  - **The weekly checkpoint at the claim.** Each weekly window in the latest good row's `windows`
    whose `resets_at` is still ahead is held to its checkpoint, as the `over` loop of
    `sample_allowance` does today. A window with no `resets_at` is judged only while the row is in
    force.
  - **The session park, at the claim and at `ccp prompt`.** It parks when the latest good row's
    `five_hour` is at or past the park and its `five_hour_resets_at` is still ahead. With no reset
    time, the row must be in force.
- **Judgments that let work through use only the reading in force:**
  - **§16.3 rule 5 at the claim.** `join_refusal` gets the reading in force. With none, a second
    claim refuses ("no good usage reading in the last 15 minutes, so no second task is taken
    (rule 5)").
  - **§16.3 rule 5 at `ccp tasks next`.** `next_choice` judges the reading in force. With none, it
    does not judge rule 5 (`five_known=False`, as today for a stale row) and leaves it to the claim,
    which reads. A failed row is never in force, so it never makes `next` report slots full.
  - **Lifting a park.** A park lifts only when the reading in force shows the window known and under
    the park, when the latest good row's reset has passed, or when the park is off.
- **With no reading in force**, nothing passes on a figure. The claim and the prompt carry a
  `warning:` that says how long the account has gone unread.
- **The other readers of the last row:**
  - `project`'s `prev` and `continue_` read `latest_good(q)`. A failed latest row no longer resets
    the stable window choice or refuses a decision.
  - `status` keeps `latest` (the raw last row, so failures show) and adds `latest_good` and
    `in_force` (true or false). Its window, resets, checkpoint and decisions come from
    `latest_good`.
  - `session_wake` and `session_armed` take the window, reset and park settings from `latest_good`.
    `session_fire` judges the reading in force, and its `rec or _latest(q)` fallback becomes
    `latest_good(q)`.
  - The forecast's allowance projection (`ccp/forecast.py`, around the `[-1]` read) uses
    `latest_good`, so a failed latest row no longer drops the projection.
  - `counter_resets` already skips unknown rows and is unchanged.

### 4. `ccp prompt` and refused retries

- In `ccp/prompt.py` `build`, the `session_step` call moves below the refusal gates: after
  `runs.check_running_rounds`, before `runs.next_round`. A prompt that one of those gates refuses
  reads nothing. A prompt that passes them reads at most once per `READ_TTL_S` per machine, and never
  inside a backoff.
- The claim keeps its place in the order. Its reads are bounded the same way. So a refused claim
  retried in a loop runs the command at most once per `READ_TTL_S` per machine, and not at all
  inside a backoff.

### 5. The unread checkpoint (operator's option (a))

- **Unread since.** This is the cache's `failing_since`. Under the production fallback, it is the
  `at` of the first failed row after the product's latest good row, or of the log's first failed
  row when no row is good.
- **The stop.** It applies when all three hold:
  - `allowance_cmd` is set;
  - no reading is in force;
  - `now() - unread since >= UNREAD_STOP_S`.

  Then a **new** claim refuses with exit 5: "allowance checkpoint: the account's usage has not been
  read for N minutes (SPEC §25.3). Runner: stop and tell the lead. Lead: check `allowance_cmd`, run
  `ccp allowance status --sample` until it shows a good reading, then tell the runner to resume; no
  decision is recorded". The existing exit 5 handler then fires `allowance_checkpoint` with
  `reason="usage unread"`.
  - A resumed claim is never refused.
  - `ccp allowance continue` does not clear the stop; the next good read does.
- **Between the two limits.** When the account has gone unread for more than `IN_FORCE_S` but less
  than `UNREAD_STOP_S`:
  - a claim into an empty active set proceeds, with the warning;
  - a second claim refuses under rule 5;
  - a stop judged on the latest good row still applies (§3).
- **The recovery, in the plugin's words:**
  - `plugin/agents/delivery-runner.md`, item (c): exit 5 is either the weekly checkpoint or usage
    unread. On either, the runner tells the lead what the claim printed and stops.
  - `plugin/skills/spec-maintainer/SKILL.md`, the allowance checkpoint bullet: on a usage-unread
    stop, the lead checks `allowance_cmd`, then runs `ccp allowance status --sample` until
    `latest_good` is in force. It honours the backoff `status` reports, rather than retrying in a
    loop. Then it tells the runner to resume. No `continue` decision is recorded, and the operator
    is told the outcome.
  - `plugin/orientation.md`: the notice list says "the allowance checkpoint (a weekly checkpoint, or
    usage unread)".
- `ccp/notify.py`'s module docstring names the second cause of `allowance_checkpoint`.

### 6. SPEC changes (signed in the brief, §31)

The CURRENT texts are verbatim at `1774a22` (unchanged at `438c97f`).

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

**b. §10 claim steps**, `docs/spec/02-delivery.md` (around line 161 at `1774a22`).

CURRENT:
> worktree (`ccp wt create --kind impl`, §12), samples the allowance (§25) and writes a heartbeat.

PROPOSED:
> worktree (`ccp wt create --kind impl`, §12), takes an allowance reading (§25.1) and writes a heartbeat.

**c. §25.1**, `docs/spec/04-observability.md`: the whole paragraph is replaced.

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
> `retry_after_s`, the seconds to wait before it is run again. A reading is good when the command
> exits 0 and at least one window has a figure.
>
> - **One reader per machine.** A reading is taken under an exclusive lock on a cache file in the
>   machine file's directory, one per command, which keeps the last good reading's windows. That
>   reading is reused while it is younger than 60 seconds; otherwise the command runs. Each run
>   appends a sample to `board/allowance.jsonl` and emits `allowance/sample`. A reused reading newer
>   than the product's latest good sample is appended with its own `at` and `reused: true`, its
>   fields worked out for this product, and emits nothing. When the cache cannot be locked, the
>   claim and the prompt say so in a `warning:`, and the reader works from the product's own
>   samples, with the same reuse and backoff.
> - **A failed read backs off.** If the command fails or prints no figure, the sample is recorded as
>   unknown, never as zero, with `failed: true`, its exit code and any `retry_after_s`, and never its
>   output. No caller then runs the command for 60 seconds, doubling at each further failure up to
>   15 minutes, or for the `retry_after_s` it printed when that is longer (at most 60 minutes). The
>   next good reading ends the backoff.
> - **Which reading a rule judges.** A failed sample is never judged. A rule that stops work (the
>   weekly checkpoint, §25.3; the session park, §25.4) judges the latest good sample of any age,
>   for each window whose reset is still ahead; a window with no reset time counts only while that
>   sample is in force. A rule that lets work through (the parallel claim rule, §16.3 rule 5;
>   lifting a park) judges only the reading in force: the latest good sample no older than
>   15 minutes. With none in force, the claim and the prompt say so in a `warning:`. Once the
>   account has gone unread for 60 minutes (no good reading since its failures began), a new claim
>   refuses (§25.3).

This retires two things:
- "`ccp board build` run[s] the machine's `allowance_cmd`", which was never true (a description
  fix);
- "an unknown reading is a `warning:` on the claim that gates nothing".

**d. §25.3**, `docs/spec/04-observability.md`.

CURRENT:
> - When a sample reaches it, `ccp tasks claim` refuses a **new** claim (exit 5, "allowance
>   checkpoint"). A resumed claim of a runner's own lease is never refused.

PROPOSED:
> - When the latest good sample reaches it, while its window's reset is still ahead (§25.1),
>   `ccp tasks claim` refuses a **new** claim (exit 5, "allowance checkpoint"). A resumed claim of a
>   runner's own lease is never refused.
> - **An account gone unread.** When the account has had no good reading for 60 minutes (§25.1),
>   `ccp tasks claim` refuses a **new** claim the same way (exit 5, "allowance checkpoint", usage
>   unread), and fires `allowance_checkpoint` with the reason `usage unread`, so the checkpoint
>   cannot lapse unseen. A resumed claim is never refused. The lead checks `allowance_cmd`, runs
>   `ccp allowance status --sample` until a good reading lands, then tells the runner to resume; no
>   decision is recorded, and the next good reading clears it.

**e. §25.4**, `docs/spec/04-observability.md`: four sentences.

CURRENT:
> `ccp tasks claim`
>   (new or resumed) and `ccp prompt` (before it opens a run) take a sample; when the window is at or
>   above the park, they refuse with **exit 6** ("session park"),

PROPOSED:
> `ccp tasks claim` (new or resumed) and `ccp prompt` (once its other refusal gates pass, before it
>   opens a run) take a reading (§25.1); when the latest good sample shows the window at or above the
>   park and its reset is still ahead, they refuse with **exit 6** ("session park"),

The rest of that sentence is unchanged.

CURRENT:
> A later claim or
>     prompt of the task that does not park lifts any park it had (`waiting_on/clear`, reason
>     `session_reset`) when its reading shows the window free: known and under the park, its reset
>     already passed, or the park off.

PROPOSED:
> A later claim or
>     prompt of the task that does not park lifts any park it had (`waiting_on/clear`, reason
>     `session_reset`) when the window is free: the reading in force (§25.1) shows it known and under
>     the park, the latest good sample's reset has passed, or the park is off.

CURRENT:
> - An unknown reading, or no `allowance_cmd`, gates nothing and lifts nothing.

PROPOSED:
> - No good sample whose window is still open, or no `allowance_cmd`, gates nothing; no reading in
>   force lifts nothing.

CURRENT:
> - **`--fire`** (what the wake runs) takes a fresh sample;

PROPOSED:
> - **`--fire`** (what the wake runs) takes a reading (§25.1) and judges the reading in force;

**f. §3.6 trigger table**, `docs/spec/01-model.md`, the `allowance_checkpoint` row.

CURRENT:
> | `allowance_checkpoint` | `ccp tasks claim` refused at a weekly checkpoint (exit 5, §25.3) | the task |

PROPOSED:
> | `allowance_checkpoint` | `ccp tasks claim` refused at a weekly checkpoint, or with the account's usage unread for 60 minutes (exit 5, §25.3) | the task; the reason `usage unread` for the latter |

**g. §8.3 the machine file**, `docs/spec/01-model.md`.

CURRENT:
> **The machine file**, `machine.json` beside the bindings (`contracts/machine.schema.json`), holds what belongs to the machine's account, not to a product: `telemetry` (the operator's consent, §4.5), `allowance_cmd` and `allowance_stop_weekly` (§25).

PROPOSED: the same sentence, followed by:
> Beside it, the shared allowance reader keeps one cache file per allowance command (`allowance-cache-<hash>.json`) and its lock (§25.1); they are state, not configuration, and may be deleted.

**h. Contract descriptions (not § rules), verbatim.**

`contracts/allowance.schema.json`, the top-level `description`.

CURRENT:
> SPEC §25.2: what `telemetry.allowance_cmd` prints: any number of named usage windows, each with its percentage used (0 or more; a figure past 100 is kept as read) and its reset time. Either the generic form, or the legacy one: an object per window with `utilization` and `resets_at` (e.g. `five_hour`, `seven_day`). A window whose figure is null or missing keeps its reset and gates nothing; an empty or unreadable reading is unknown, never zero.

PROPOSED:
> SPEC §25.1, §25.2: what the machine's `allowance_cmd` prints: any number of named usage windows, each with its percentage used (0 or more; a figure past 100 is kept as read) and its reset time. Either the generic form, or the legacy one: an object per window with `utilization` and `resets_at` (e.g. `five_hour`, `seven_day`). Either may carry `retry_after_s`, the seconds to wait before the command is run again; an object holding only `retry_after_s` is a failed read that says when to retry. A window whose figure is null or missing keeps its reset and gates nothing; a reading with no window figure is a failed read, never zero.

New property `retry_after_s` in both forms, and a third branch holding only it, with the
description:
> SPEC §25.1: seconds before the command is run again; the shared reader backs off at least this long, at most 3600 seconds.

The schema is `{"type": "number", "minimum": 0}`. In the legacy branch it goes under `properties`,
which exempts it from `additionalProperties`.

`contracts/machine.schema.json`, `allowance_cmd`'s `description`.

CURRENT:
> SPEC §25.1: the shell command that prints the account's usage windows (contracts/allowance.schema.json), run by `ccp tasks claim` and `ccp board build` for every product on this machine. Absent: no usage is read and nothing bounds spend, and `ccp init`, the session-start check and the board say so. A plane.json `telemetry.allowance_cmd` is the old place, read while this is absent.

PROPOSED:
> SPEC §25.1: the shell command that prints the account's usage windows (contracts/allowance.schema.json), read through one shared reader per machine by `ccp tasks claim`, `ccp prompt`, `ccp allowance status --sample` and `ccp allowance session-wake --sample` and `--fire`, for every product on this machine. Absent: no usage is read and nothing bounds spend, and `ccp init`, the session-start check and the board say so. A plane.json `telemetry.allowance_cmd` is the old place, read while this is absent.

### 7. Tests: `tests/test_usage_reading.py` (new)

Fenced per `tests/__init__.py`:
- every test unsets `CCP_ALLOWANCE_UNSHARED`, sets `CCP_BINDINGS_DIR` to a temp dir, and uses a
  temp queue and product;
- the allowance command is a stub script. On each run it appends a line to a counter file and
  prints what the test sets: a reading; `{"retry_after_s": N}` with exit 1; or stderr text with
  exit 1;
- time moves only by patching `ccp.usage.now`, the one clock. A test may also write `at`,
  `failing_since` and `backoff_until` into the log and the cache.

Class `SharedReading`, with these six tests:
- `test_two_claims_within_the_ttl_read_once`:
  - Two claims of two tasks within 60 s run the stub once. The second appends nothing, since the
    product's log already holds that reading.
  - A `reading()` from a second temp queue (another product on the machine) appends the reading
    with `reused: true` and its original `at`.
  - The second product's fields come from its own `project`: with a decision raising its
    checkpoint, its `weekly_window` choice is its own.
- `test_a_failed_read_backs_off`: the stub exits 1 and writes `secret-text` on stderr.
  - A claim appends one row with `failed: true` and `exit: 1`, and no field holds `secret-text`.
  - A second claim 30 s later does not run the stub and appends no row.
  - After 61 s, a claim runs it again; after this second failure the backoff is 120 s.
  - After a good reading, the backoff is cleared.
- `test_retry_after_is_honoured`: the stub prints `{"retry_after_s": 300}` and exits 1. A claim at
  +200 s does not run it. A claim at +301 s does.
- `test_a_failed_read_keeps_the_good_reading`: the log holds a good reading from 10 minutes ago,
  with `five_hour` 20, `seven_day` 50 and both resets ahead, and the stub now exits 1, as on
  HTTP 429.
  - A claim beside a task in flight (parallel on, `max_in_flight` 2, no clash) is not refused by
    rule 5, and `ccp tasks next` does not report slots full.
  - With the same reading at `seven_day` 95 against the default checkpoint of 90, and the reading
    40 minutes old (past `IN_FORCE_S`) but its weekly reset still ahead, a new claim refuses with
    exit 5.
- `test_an_hour_unread_refuses_a_new_claim`: the cache's `failing_since` is 61 minutes ago, no good
  row is newer than 15 minutes (the latest good row is below every threshold), and the backoff is
  in force.
  - A new claim exits 5, with `usage` and `not been read` in the message.
  - The ledger holds a `notify` `pending` event (`notify.record_pending`) for `allowance_checkpoint`
    with reason `usage unread`.
  - At 59 minutes, a claim into an empty active set proceeds, with a warning.
- `test_a_refused_prompt_reads_nothing`:
  - Claim a task, then empty the counter file and move `ccp.usage.now` past `READ_TTL_S`, so a
    passing prompt would read.
  - Give the task a last verify round that reported, with no fix round since.
  - `ccp prompt verify --pr 1 --head <sha>` with no `--note` exits 4 (`repeat_gate`), and the
    counter file is still empty.

The existing tests run under `CCP_ALLOWANCE_UNSHARED=1`, so the cache does not reach them. A test
that the moved prompt step breaks is updated, and named in the Implementation notes with why. No
other expectation of an existing test changes.

- **Out:**
  - the board, which reads the log and never the command;
  - the session-park percentages, the checkpoint, the ceiling and the decisions;
  - the receiver's telemetry whitelist (no new emitted field);
  - `ccp allowance continue`'s rules, beyond reading the latest good row.

## dod_checks

- id: `ur-01`
  story: As the plane, the shared reader, its backoff, the readings each rule judges and the unread
  stop are tested.
  setup: a checkout of the PR head (any seat).
  steps:
    1. Run `python3 -B -m unittest -v tests.test_usage_reading 2>&1 | grep -E '^test_|^OK|FAILED'`.
  expect: six `... ok` lines, then `OK`. They are `test_two_claims_within_the_ttl_read_once`,
    `test_a_failed_read_backs_off`, `test_retry_after_is_honoured`,
    `test_a_failed_read_keeps_the_good_reading`, `test_an_hour_unread_refuses_a_new_claim` and
    `test_a_refused_prompt_reads_nothing`.
  dry run (`438c97f`): `tests/test_usage_reading.py` does not exist.

- id: `ur-02`
  story: As the plane, the tests bite on the TTL, the reading in force, the prompt's order and the
  stop on an old reading.
  setup: four separate copies of the PR head (`git worktree add <tmp> HEAD`, never the branch's
    own worktree), each with one planted fault:
    (a) `READ_TTL_S = 0` in `ccp/usage.py`;
    (b) `IN_FORCE_S = 0` in `ccp/usage.py`;
    (c) in `ccp/prompt.py` `build`, the `session_step` line moved back above `resolution_gate`;
    (d) in `ccp/usage.py`, the weekly checkpoint judged on `in_force(q)` instead of `latest_good(q)`.
  steps:
    1. In each copy, run `python3 -B -m unittest tests.test_usage_reading 2>&1 | tail -3`.
  expect: each run ends in `FAILED`.
    (a) fails `test_two_claims_within_the_ttl_read_once`;
    (b) fails `test_a_failed_read_keeps_the_good_reading`;
    (c) fails `test_a_refused_prompt_reads_nothing`;
    (d) fails `test_a_failed_read_keeps_the_good_reading`.
  dry run (`438c97f`): n/a, the constants and the test file do not exist yet.

- id: `ur-03`
  story: As the SPEC reader, §8.3, §10, §16.3, §25.1, §25.3, §25.4 and §3.6 say what the code does,
  and the contracts agree.
  setup: a checkout of the PR head. `flat` stands for `tr '\n' ' ' < FILE | tr -s ' '`: the file on
    one line with runs of spaces squeezed, so wrapping and list indentation do not matter.
  steps:
    1. `tr '\n' ' ' < docs/spec/02-delivery.md | tr -s ' ' | grep -o "the latest good reading no older than 15 minutes\|takes an allowance reading (§25.1)" | sort | uniq -c`
    2. `tr '\n' ' ' < docs/spec/04-observability.md | tr -s ' ' | grep -o "One reader per machine\|younger than 60 seconds\|A failed read backs off\|judges the latest good sample of any age\|An account gone unread\|the latest good sample shows the window at or above the park\|takes a reading (§25.1) and judges the reading in force" | sort | uniq -c`
    3. `tr '\n' ' ' < docs/spec/01-model.md | tr -s ' ' | grep -o "usage unread for 60 minutes\|the shared allowance reader keeps one cache file" | sort | uniq -c`
    4. `grep -c retry_after_s contracts/allowance.schema.json`
    5. `grep -c "and \`ccp board build\`" docs/spec/04-observability.md contracts/machine.schema.json`
  expect:
    - step 1: two phrases, each with count 1;
    - step 2: seven phrases, each with count 1;
    - step 3: two phrases, each with count 1;
    - step 4: at least `2`;
    - step 5: `0` for both files.
  dry run (`438c97f`): steps 1 to 3 print nothing, step 4 prints `0`, and step 5 prints `1` for
    each file.

- id: `ur-04`
  story: As the runner and the lead, the plugin says what to do on a usage-unread stop.
  setup: a checkout of the PR head.
  steps:
    1. `grep -c "usage unread" plugin/agents/delivery-runner.md plugin/skills/spec-maintainer/SKILL.md plugin/orientation.md`
    2. `grep -n "allowance status --sample" plugin/skills/spec-maintainer/SKILL.md`
  expect: step 1 gives at least `1` for each file. Step 2 prints at least one line, inside the
    allowance checkpoint bullet.
  dry run (`438c97f`): step 1 prints `0` for each file; step 2 prints nothing.

- id: `ur-05`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh; echo rc=$?`.
    2. Run `ccp --root . tasks check`, `ccp --root . docs check`, then `git branch --list 'state/*'`.
  expect: step 1 ends `rc=0`. Both checks in step 2 exit 0, and the branch list prints nothing.
  dry run: n/a, the gate runs on the PR head.

## Refs

- SPEC §3.6 (the notice), §8.3 (the machine file), §10 (the claim), §16.3 rule 5, §25.1, §25.3,
  §25.4.
- Task 0186 (the account's facts in the machine file, which this builds on).
- The operator's decision on the unread policy, 2026-11-20: "T1 - (a)".

## Implementation notes

## Verification notes
