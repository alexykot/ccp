# Part IV — Observability and spend

What the plane records about delivery, how it measures usage and spend, and what it shows. Every
number here is a diagnostic, never a target, and nothing recorded carries content: ids, counts, times
and short summaries only. Implementation notes are in `docs/design/observability.md`,
`docs/design/telemetry.md`, `docs/design/allowance.md` and `docs/design/board.md`; the commands are
listed in `docs/cli/04-observability.md`.

## 23. Ledger, snapshot and queue data

### 23.1 Sources of truth

Two layers: the **ops record** (task states, work against wait time, blockers, seat liveness: what is
happening and why it is slow) and the **prompt audit** (§23.8: exactly what each worker was told).

| Artifact | Path (under `QUEUE_ROOT`) | Role |
| --- | --- | --- |
| Event ledger | `observability/events.jsonl` | **Canonical**, append-only record of timers and state transitions |
| Board | `board/board.json`, page `board/index.html` | The derived current view (§28) |
| Seat heartbeats | `observability/seats/<seat_id>.json` | Last wake and action of a scheduled seat (`event` for an event-only seat) |

The durable task log under `docs/delivery/` is the permanent record. It is not authoritative for
what is happening now until it is reconciled (§23.5). The runtime queue files (leases, `work.json`,
`tasks/*.json`) stay operational, and every change to them **emits an event**: they are never the
only history.

### 23.2 The event ledger

One JSON object per line, append-only, never rewritten (`contracts/observability_event.schema.json`).
Every event has `at`, `project_id`, `task_id` (empty for a seat-only or project-level event), `actor`,
`type`, `op` and `payload`. Actors are seat ids (`design-seat` for the lead, `task-runner` for a
runner, `task-verifier` for the verifier subagent), `operator` and `system`.

| type | op | payload (required keys) |
| --- | --- | --- |
| `phase` | `transition` | `from`, `to`, `note?` |
| `waiting_on` | `set` | `reason` (`quota`, `reauth`, `operator_decision`, `runner`, `steerer`, `spec_maintainer`, `null-class`, `operator_step`), `resets_at?` (RFC3339), `quota_class?` (`session`, `credit`), `detail?` |
| `waiting_on` | `clear` | `reason` (what cleared it), `was` |
| `lease` | `set`, `clear` | `holder`, `expires_at?` |
| `claude` | `launch` | `session_id?`, `phase`, `prompt_ref` (a path under `prompts/…`), `pid?`, `argv_digest?` |
| `claude` | `exit` | `session_id?`, `exit_code`, `api_error_status?`, `result_summary?` (no secrets) |
| `auth` | `transition` | `overall`, `failed_checks?` |
| `seat` | `heartbeat` | `seat_id`, `wake_kind` (`cron`, `priority`, `manual`), `action_summary` |
| `durable` | `reconcile` | `field`, `old`, `new` (e.g. a task status set to done) |
| `note` | `set` | `message` (free text; the structured types are preferred) |
| `question`, `spec_maintainer` | §17 | spec questions and their answers |
| `run` | `opened`, `bound`, `stopped`, `reported` | `run_id`, `phase`, `round`, `agent_type`, `expected_model`, `expected_effort`, `agent_id?`, `outcome?` |
| `run` | `recorded` | `run_id`, `mutants`, `killed`, `survived` (one `ccp mutate` call, §20.6) |
| `review` | `recorded` | `run_id`, `verdict`, `severity` |
| `verify` | `recorded` | `run_id`, `verdict`, `head_sha` |
| `allowance` | `sample` | the sample's gating figures (§25.1) |
| `plane` | `proposed`, `again`, `triaged` | §31 |
| `suite` | `recorded` | `suite_id`, `run_id`, `phase`, `lane`, `exit_code`, `seconds`, `tests`, `failed`, `skipped`, `ran`, `cached`, `cached_tests`, `counts_from`, `interrupted` (§14) |
| `prefer` | `set`, `clear` | `set`: `by`, `reason`; `clear`: `was`, `reason` (`claimed` when the claim took it); `task_id` is the preferred task |

- **The commands emit.** `phase`, `lease`, `waiting_on`, `durable` and the run, review, verify and
  suite events are written by the `ccp` commands that make the change (§10), not by hand. Seats call
  commands; they do not call the emit scripts.
- **Single writer for waits.** A change of wait state appends its `waiting_on` set or clear
  **before** `work.json` or the task's queue file changes, through
  `scripts/observability/set-waiting-on.sh`. The last event wins for "current".
- **Precedence.** A failed credential check does not set `waiting_on=reauth` in a way that stops a
  live session that does not need that credential. The degraded auth is recorded and escalated; a
  task parks or stops only when its next required step needs the credential.
- **Usage rows are not ledger events.** They go to the board's usage files (§24.2), because of their
  volume.

### 23.3 Timers

Folded from the ledger (the formulas are fixed; `scripts/observability/README.md` documents them):

- `wall_hours` = now − `implementation_started_at` (null if never started).
- `wait_hours` = the sum of the intervals where `waiting_on != null` (set → clear), plus the open
  interval while waiting.
- `work_hours` = the sum of the intervals where the phase is an active one (implementing, review,
  verify, merge, and the aliases `implement`, `mk-pr`, `fix-review`) **and** `waiting_on` is null
  **and** a worker launch is open. It is never computed as `wall − wait`.

The board (§28) carries both the durable status (`durable_status`) and the runtime status
(`runtime_status`) of each task, so a divergence is visible until reconciled.

### 23.4 The status command

`ccp board status` prints a terminal summary of the board and **exits non-zero** while any blocker
is open: a task waiting, a gate or question open, a stale source while a runner runs (§28.3), or the
allowance at its checkpoint. A cron wrapper can rely on that exit code. The board is the status: the
older snapshot (`now.json`, `STATUS.md`) and the scripts that write or read it (`status.sh`,
`rebuild-now.sh`) are retired; `emit-event.sh` and `set-waiting-on.sh` remain as
wrappers over `ccp`.

### 23.5 Durable reconciliation

On a terminal success (done, merged) the task file's status is updated in the same step as the
merge, with its `durable/reconcile` event (`ccp tasks close`, §10). Leaving a task `pending` in the
log after its merge is a plane bug. A wait, gate or question whose task is `done` or `dropped` in
its task file is resolved, never a blocker; the board lists it as queue-against-log divergence, and
`ccp tasks sync` repairs the queue (§10).

### 23.6 Quota and auth fields

- On a worker's exit or park, a session-limit or credit message becomes structured fields through
  `set-waiting-on.sh`: `waiting_on=quota`, `quota_class`, `resets_at`, and `planned_resume_at`.
  Structured fields are preferred over prose; a quota resume reads `planned_resume_at` first.
- The credential check writes `auth/status.json` (§12, §30) and emits an `auth` event when the
  overall result changes.
- A product API key present in the environment is recorded (`ambient_api_key`), the overall result
  is at best `degraded`, and worker launches stay stripped of the key (§30).

### 23.7 Who writes the queue files

`ccp` writes the queue files, called by the runner and, for its own report, by each worker.

| File | Writer |
|---|---|
| `work.json`, `tasks/<id>.json`, the lease | the runner, through `ccp` |
| `events.jsonl` | the runner (task events); the lead (`question`/`answered`, `gate`/`decided`, `runner`/`spawn`, `bound`, `scope`, `rotate`, `stop`) |
| `progress/<id>.json`, the verifier packet | the runner |
| `progress/<id>/<phase>-report.md` (`progress/<task_id>/<phase>-report.md`) | each worker submits its full report with `ccp report <run_id> FILE`, then tells the runner by `SendMessage` |
| `verification/<id>.json` | the verifier subagent, through `ccp verify record` |
| `review/` | the reviewer subagent |
| `prompts/<task_id>/<UTC>_<phase>.json` | the runner, before each worker launch (the audit of the prompt it passes, `session_id` replaced by the worker's name; §23.8); the lead, before each runner spawn (`phase: runner-spawn`) |
| `questions/sm-*.json` | the runner |
| `questions/*.answer.json` | the lead |
| `escalations/**` | the runner opens; the lead closes |
| `auth/status.json` | `ccp tasks claim` and `ccp auth check`, running `auth_check.probes` |
| `observability/runner-idle.json`, `observability/runner-idle-inputs.jsonl` | the `TeammateIdle` hook (its block counter; whitelisted input fields) |

The queue may still hold a `spec-maintainer.lock` written before the `claude-session` maintainer was
removed; nothing writes or reads it.

### 23.8 The prompt audit

- Before every worker launch the plane owns, an audit of the prompt is written to
  `QUEUE_ROOT/prompts/<task_id>/<UTC-timestamp>_<phase>.json` (`contracts/prompt_audit.schema.json`,
  `scripts/observability/write-prompt-audit.sh`), and its path is the launch event's `prompt_ref`.
- The file holds the argv, the stripped environment keys, the wallet, the git head, the worktree, the
  task's path and spec refs, and the prompt's sha256 and length (`prompt_chars`). The full prompt text
  (`prompt_body`) is kept only when the product opts in with plane.json `prompts.keep_body`; it is off
  by default, in line with records that carry ids and counts, not content.
- No API key, token or `.env` content goes in it. It lives in the runtime queue only, never in a
  product's git or the plane's.
- Prompt audits are pruned by age when plane.json `prompts.audit_keep_days` is set: each time
  `ccp prompt` writes an audit, it removes the audits under `QUEUE_ROOT/prompts/` whose name stamps
  are older than that many days. Unset (`null`, the default), every audit is kept. Only audit files
  are pruned: the rendered prompt the runner reads (`prompts/<task_id>/<phase>[-n]-prompt.md`) and
  other files stay. `scripts/observability/prune-prompts.sh` prunes by age or count on demand.
- Out of scope: full tool-call transcripts, and browser traces (the verifier's evidence holds those).

### 23.9 Knobs

| Knob | Default |
| --- | --- |
| Full prompt bodies in the audit (`prompts.keep_body`) | `false` (opt-in) |
| Prompt audit retention in days (`prompts.audit_keep_days`) | `null`: every audit is kept |

## 24. Usage and telemetry

### 24.1 Source

Usage comes from Claude Code's OpenTelemetry export. Per API call, the `claude_code.api_request`
event carries `model`, `effort`, `input_tokens`, `output_tokens`, `cache_read_tokens`,
`cache_creation_tokens`, `cost_usd`, `duration_ms`, `request_id`, `agent.name`, `session.id` and
`prompt.id`; trace spans (`claude_code.llm_request`) carry the same tokens and, for a worker's calls,
`agent_id` (the join key, §24.4).

- **Enabled in the user settings** (`~/.claude/settings.json` `env`, printed by `ccp otel env`), for
  every Claude Code session on the machine, not only the plane's: `CLAUDE_CODE_ENABLE_TELEMETRY=1`,
  `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` (needed for trace spans), the logs and traces exporters set
  to `otlp`, protocol `http/json`, endpoint `http://127.0.0.1:<telemetry.otel_port>`, and no project
  id. Claude Code ignores these enabling keys in a project's `.claude/settings.json`, so a product
  carries none of them.
- **Labelled per project, in the product's settings:** a product's `.claude/settings.json` `env`
  carries one key, `OTEL_RESOURCE_ATTRIBUTES=ccp.project_id=<project_id>`, which Claude Code honours
  there. `ccp otel env --project <id>` prints both blocks and says which goes where. The user
  settings never pin a project id.
- **Prompt and tool-content logging stay off.** `OTEL_LOG_USER_PROMPTS` and `OTEL_LOG_TOOL_DETAILS`
  stay unset; `ccp otel status` warns when either is set in the user settings or the environment.

### 24.2 Receiving

`ccp otel serve` is a small OTLP/HTTP receiver run by the machine's service manager and bound to
localhost only. It accepts only `Content-Type: application/json`. It appends one row per
`api_request` to `QUEUE_ROOT/board/usage-requests.jsonl` (`at`, `session_id`, `agent_name`,
`request_id`, `model`, `effort`, the four token counts, the cache writes by lifetime
`cache_creation_5m_tokens` and `cache_creation_1h_tokens`, `cost_usd`, `duration_ms`, and the
session's `cwd` when known) and one per `claude_code.llm_request` span to
`QUEUE_ROOT/board/usage-spans.jsonl`. No content is stored, and nothing is dropped for want of a
project.

### 24.3 Routing

A record goes, in this order:

1. by the resource attribute `ccp.project_id` (set by the product's settings or a process
   environment) to that binding's queue;
2. else by its `session.id`, through the session's transcript `cwd`, to the binding whose
   `product_root` holds that cwd: under the root, or a git worktree of it elsewhere, compared as
   real paths; the deepest root wins. Teammates and subagents carry the lead's session and route
   with it;
3. else to the **system sink** outside every queue, labelled with the session id and cwd, which
   `ccp usage --system` reports by cwd and by day.

Plane-launched headless sessions set `ccp.project_id` and `ccp.seat` in their own environment
(`OTEL_RESOURCE_ATTRIBUTES=ccp.project_id=<id>,ccp.seat=<kind>`), so they route ahead of any cwd. The
plane's own development routes to its own project like any product; for the allowance forecast it is
not product work and counts with the system sink (§26.5).

### 24.4 Attribution

`ccp board build` attributes every request, in this order:

- a plane-launched headless session (architect, estimator) is its kind's seat, its subagents
  included; `board/headless-usage.jsonl` records the session id;
- a span `agent_id` → the run bound to it (§11); `<name>@session-…` → the teammate of that name
  (the runner, or any name a `runner` event recorded);
- a call with no `agent_id` goes by its session's cwd: the product root is the lead's
  (`design-seat`), a runner's merge checkout (`runner.worktree`) is that runner's, and any other cwd
  is `other-sessions`, listed by cwd. Only `design-seat` rows feed the design-seat advice;
- logs without spans fall back to a time window: a request belongs to a run when exactly one open
  run of its model and effort matches it.

Anything unattributed is counted and shown (§28.3, plane health). Headless runs also keep
`claude -p --output-format json`'s `modelUsage` (tokens and cost per model, subagents included) on
their run record (`ccp architect`).

### 24.5 Model and effort

- Expected values come from the installed agent definition's `model` and `effort`, recorded by
  `ccp prompt`; observed values come from each request. The board flags any run whose observed
  values differ. A `CLAUDE_CODE_EFFORT_LEVEL` in the environment overrides a definition's effort
  without warning; this check is what catches it.
- **The design seat is advisory.** The lead is the operator's interactive session, so the plane
  cannot set its model or effort. The product's `plane.json` names the lead's expected values
  (`telemetry.design_seat`); `ccp usage` and the board flag a lead whose calls differ, as advice to
  the operator. Nothing enforces it.
- **`cost_usd` is the client's own estimate.** On a subscription the unit that matters is the
  allowance percentage (§25); the board shows cost only as a relative measure.

## 25. Allowance and usage windows

### 25.1 Samples

`ccp tasks claim` and `ccp board build` run the binding's `telemetry.allowance_cmd`. It prints the
account's usage windows as JSON (`contracts/allowance.schema.json`): `{windows: [{name, pct, resets_at}]}`,
or the legacy form, one object per window with `utilization` and `resets_at`. Each run appends a
sample to `board/allowance.jsonl` and emits `allowance/sample`. If the command fails or prints
something unexpected, the sample is recorded as unknown, never as zero, and an unknown reading is a
`warning:` on the claim that gates nothing.

### 25.2 Usage windows

Each window has a rule, `telemetry.windows`: `{<name>: {kind: weekly|session, stop_pct, park_pct}}`,
merged over two built-in ones: `seven_day` (weekly, `stop_pct` = `telemetry.allowance_stop_weekly`)
and `five_hour` (session, `park_pct` = `telemetry.session_park_pct`, default 95). So, by default, a
reading with a `five_hour` figure parks claims and prompts at 95% of it. A window that is neither
built in nor named by the rules is recorded and otherwise ignored. A config that sets a built-in
window's threshold both ways (the legacy key and `windows.<name>`), a `stop_pct` on a session window
or a `park_pct` on a weekly one, is refused.

- A **weekly** window has a stop (§25.3). **Every** weekly window is held to its own checkpoint: a
  claim is refused when any of them is at or past it. A **session** window has a park (§25.4).
- One window of each kind gates, chosen stably: among the windows at or past their threshold, the
  previous sample's while it still is, else the first by name; with none past, the one nearest its
  threshold, the previous sample's while it is as near, ties by name. Its figure and reset are
  recorded in the sample's `seven_day`/`resets_at` (weekly) and `five_hour`/`five_hour_resets_at`
  (session), with its name (`weekly_window`, `session_window`); every reading in this part reads
  those fields, and the sample keeps the full `windows` list. A window with no figure keeps its
  reset.
- Everything is per window: a decision records the window it was taken for (`window`; one recorded
  without a name is `seven_day`'s) and raises only that window's checkpoint; a counter reset compares
  samples of the same window; the forecast joins only samples whose gating windows are the same.
- A window with no figure gates nothing. A reading with a weekly figure and no session figure means
  no session limit: the park and wake stay off, the forecast models no pauses, and the parallel
  claim rule's session condition passes (§16).

### 25.3 The checkpoint

- The project's checkpoint (the gating weekly window's `stop_pct`; by default
  `telemetry.allowance_stop_weekly`) is drawn on the board. It is a point where the work stops and
  the operator decides, not a hard limit.
- When a sample reaches it, `ccp tasks claim` refuses a **new** claim (exit 5, "allowance
  checkpoint"). A resumed claim of a runner's own lease is never refused.
- On exit 5 the runner stops and tells the lead; the lead asks the operator and records their
  decision: `ccp allowance continue --to <percent> --reason "<the operator's words>"`. It refuses
  without a reason, a `--to` that does not raise the checkpoint, or a missing sample with a reset
  time. Claims then proceed until the weekly usage reaches `--to`, the next checkpoint. Answers about
  a task go to the runner that holds it (the claim's `--holder <slot>`, §10).
- **A decision lapses at its window's end or at a counter reset.** It applies to its weekly window
  (the sample's `resets_at`) from when it was taken until the next counter reset in that window. A
  counter reset is a fall of the weekly percentage by `usage.RESET_DROP_PP` (20 points) or more
  between consecutive known samples of the same window. After the lapse the project's own checkpoint
  applies again until the operator decides anew.
- `ccp allowance status` shows the latest sample, the checkpoint in force, the counter resets
  detected and the window's decisions, each lapsed one with its reset's time (`lapsed_at`); the board
  says "decision lapsed at the counter reset <time>" when the latest decision has lapsed.
- Only the lead records a decision, and only the operator's.

### 25.4 The session park and the session wake

At a session window's limit every session's turn fails, the lead's included, so nothing inside the
team can schedule the resume once it is hit. The park stops before it, and the wake resumes after
the window's reset; the weekly checkpoint still stops for the operator.

- **The sample.** `allowance.jsonl` rows record `five_hour_resets_at` (the gating session window's
  reset, e.g. `five_hour.resets_at`; unknown is null, never zero). A row without it is read as
  unknown.
- **The park.** The gating session window's `park_pct` as configured at the time of the decision
  (null turns the park, the wake and the forecast's pauses off for that window). `ccp tasks claim`
  (new or resumed) and `ccp prompt` (before it opens a run) take a sample; when the window is at or
  above the park, they refuse with **exit 6** ("session park"), naming the percentage, the reset in
  UTC and local time, and what to do: the runner sends the lead one message and idles; the lead runs
  `ccp allowance session-wake --sample`.
  - Before refusing, `ccp` parks the task through `set-waiting-on.sh --task-only`: `waiting_on: quota`,
    `quota_class: session`, `resets_at` the window's reset and `planned_resume_at` the reset plus
    `telemetry.session_wake_margin_s` (default 180 s; `set-waiting-on.sh --planned-resume-at`), with
    its `waiting_on/set` event. It is written on the task's queue file, and on `work.json` only when
    that names the task; a refused new claim gets a queue file of its own (`status: pending`, no
    lease) and never overwrites `work.json`'s account of the task in flight.
  - With the reset unknown, the park is a retry: `planned_resume_at` is 30 minutes on
    (`usage.PARK_RETRY_S`); a live retry park keeps its time.
  - A park whose `planned_resume_at` has passed has expired and holds nothing back. A later claim or
    prompt of the task that does not park lifts any park it had (`waiting_on/clear`, reason
    `session_reset`) when its reading shows the window free: known and under the park, its reset
    already passed, or the park off.
  - An unknown reading, or no `allowance_cmd`, gates nothing and lifts nothing. Only the park itself
    refuses; a failed sample, wait write or wake record is a `warning:` (a park whose wait cannot be
    written still refuses, and says so).
  - **With several runners the park parks every task in flight**, whoever holds it, and the lead's
    wake resumes every runner (§16).
- **The warning.** From `telemetry.session_wake_arm_pct` (default 50), while no wake is recorded for
  the current window, claim and prompt warn that no session wake is armed; the runner forwards it to
  the lead.
- **`ccp allowance session-wake [--sample]`** reports the window's percentage, its reset, `wake_at`
  (the reset rounded to the second, plus the margin, up to the whole minute, UTC; with the reset
  unknown, a parked task's retry time) and `wake_local`, `cron` (five fields in local time, minute,
  hour, day and month pinned), the parked tasks, any wake already armed, and the prompt for the lead's
  scheduler. `arm` is true when the reset is known and ahead, the window is at or above the arm
  percentage or a task is parked, and no wake is recorded for that window (readings within 10 minutes
  of the same reset are the same window). The wake time is always the reading's reset, never now plus
  the window's length.
- **`--armed`** records that the lead armed the wake (`board/session-wakes.jsonl`, `allowance/armed`).
  Once its wake time has passed, a record no longer counts as armed.
- **`--fire`** (what the wake runs) takes a fresh sample; when the window is under the park, or the
  reading's own reset has passed, every parked task due within 2 minutes is un-parked and the lead is
  told to resume each at its recorded phase (with nothing parked, `work.json`'s task). Otherwise it
  says the window has not reset and gives the next wake to arm; a wake still recorded as armed is
  offered again. `allowance/fired`.
- **The lead**, on every runner message and on any session warning, runs
  `ccp allowance session-wake --sample`; when `arm` is true it schedules the printed one-shot `cron`
  with the printed prompt, then runs `--armed`; when the wake fires, it runs `--fire` and acts on it.

## 26. Estimation and forecast

### 26.1 Estimates are advisory

Estimates gate nothing: no claim is blocked, no order changes, no check reads them. `ccp tasks next`,
the ready order, the verifier and the merge gate are unchanged by them. The same holds for the
forecast and the calibration.

### 26.2 Records

`QUEUE_ROOT/estimates/<task_id>.jsonl`, append-only, one file per task, appended under the file's
lock. Readers order rows by time and version; rows are never removed. Rows hold numbers, ids and
short labels only; an agent row also holds the seat's bounded reasons.

- **An estimate row:** `{at, as_of, task_id, source, version, task_hash, inputs, phases, total,
  tokens, cost_usd, rounds, notes}`. `source` is `baseline` or `agent`; `version` counts that
  source's rows for the task; `as_of` is when the estimate stands (`at` for a live row, the task's
  start for a backfilled one, which carries `backfill: true`). `phases` maps implement, review, fix
  and verify to `{p50_s, p90_s}`; `total` is `{p50_s, p90_s}`; `tokens` and `cost_usd` are
  `{p50, p90}` (null without token history); `rounds` is `{review_p50, fix_risk}`.
- **An actual row** (`source: "actual"`): `{merged_at, start_at, merge_sha, wall_s, phases,
  phases_from, tokens, cost_usd, rounds, findings, telemetry}`. Phases are the union of each phase's
  run windows (`phases_from: runs`), else the health spans laid end to end; both are clipped to the
  task's window, so no phase outruns the wall time. Tokens and cost only where run telemetry exists.
  `ccp tasks close` appends it as its last step; a failure is a warning, never a failed close, and a
  re-run writes it once.
- **Features**, read from the task file without its notes and its `status`, `updated` and
  `review_point` lines (what the task said before the work): kind; the task-id family (via `ids`);
  the areas (the first two path components of each cited path; a citation is a path when it has a
  slash or one of `estimate.path_suffixes`); cited files that exist and their total lines; ADR, spec
  and rule refs; dod_checks by id prefix, and the mutation and story mentions in them; dependencies;
  text length.
- **`task_hash`** is the sha256 of that same text, so a status flip or a note does not re-estimate.

### 26.3 The baseline and the estimator seat

- **The baseline** (no LLM). Every merged task with a wall time is a candidate. Similarity is a
  weighted mean: same kind (1), same family (2), shared areas (2, Jaccard) and ADRs (1.5, Jaccard),
  and closeness in cited lines, dod_checks, text length and dependencies (0.5 each,
  `exp(-|log ratio|)`), each score halved for every 30 tasks merged since the candidate. The class is
  the k best (`estimate.k`, 5–8, default 6) among tasks sharing the family, an area or an ADR (tier
  `similar`); with fewer than 3, the same kind; then all. P50 and P90 of the class's actuals give each
  phase and the total; tokens and cost choose their own class from tasks with telemetry.
  `estimate.reference_since` leaves out tasks merged before a process change.
- **The estimator seat** (`ccp tasks estimate ID`) is a headless run pinned in the plane, with no
  tools, no settings, memory, hooks, plugins, skills or MCP servers in its context, in an empty
  temporary directory, its environment stripped of API keys and tagged `ccp.seat=estimator`, its
  prompt audited, its `modelUsage` recorded. Everything it needs is in a bounded prompt: the task
  without its notes, each cited ADR decision and SPEC section (looked up in `estimate.spec_paths`,
  globs relative to the root), the cited paths and their sizes, the features, the reference class,
  the baseline and the calibration (§26.6).
- **Its answer** is one JSON object (complexity per criterion with a short reason, rounds, phases,
  total, tokens, cost, the reference tasks it used, waits, and bounded reasoning), validated strictly;
  an invalid answer is retried once; a second failure leaves no row (the baseline stands). A quota
  failure stops the batch. Its row is `source: "agent"`, same shape, plus its reasons and the seat's
  run, attempts and cost.
- **When.** A task needs an estimate when it has none, its `task_hash` changed, or a dependency merged
  since its last (`deps_done` grew); a baseline is also rewritten when the baseline method's version
  changed (`--force` writes anyway, `--dry-run` writes nothing). Done, dropped and in-flight tasks
  are skipped by the batch (an estimate made after the start is never scored). `ccp tasks check` and
  `ccp tasks index` name the tasks that need one; with **`estimate.auto`** on (default `false`) they
  also start a detached batch (at most `--max`, default 10), unless one is running or the checkout is a
  linked worktree. Neither the note nor the launch blocks the command or changes its exit code.
- **Accuracy** (`ccp estimate accuracy`). Each task with an actual is scored on the latest estimate of
  each source made before it started, a live one ahead of a backfilled one: the share of actuals at or
  under P50 (target about 50%) and P90 (about 90%), and the median actual/P50, for wall time, tokens
  and cost; and the wall-time figures by kind and by family (groups of 2 or more).
- **The backfill** (`ccp estimate backfill`) gives each merged task the baseline it would have got from
  the tasks merged before it started, with its features as they stood then, plus its actual row; a
  second run writes nothing.

### 26.4 The completion forecast

`ccp forecast` replays the open tasks in the order `ccp tasks next` would take them (the task in flight
first, then the ready order, each marked merged in turn) and draws their durations, for the current
review point and for the whole backlog. It is advisory.

- **Durations.** Each task takes its latest agent estimate, else its baseline, calibrated (§26.6). Wall
  time is a lognormal through P50 and P90 (sigma = ln(P90/P50) / 1.2816, at least 0.05), each band's
  P90 capped at 4 × P50; tokens and cost likewise, drawn with the wall time's deviate. Any two tasks'
  deviates correlate at rho (default 0.3). The task in flight is drawn conditioned on not having
  finished. A task with no estimate takes the median band of the others and is counted.
- **Throughput.** The model has `parallel.max_in_flight` slots (§16). A task starts at the earliest
  free slot after its dependencies merge, never before the task ahead of it started; a task without
  paths and without `parallel: true`, or touching an exclusive path, takes every slot. The gap before a
  start is drawn from observed gaps between consecutive tasks (only closes with `peak_in_flight` 1);
  a gap of 30 minutes or more is a stop, left out and counted. With one slot this is the one-at-a-time
  model.
- **Waits on the operator** are not modelled: tasks with a wait, gate or question open now are listed
  (`waits_flagged`), and those whose agent estimate names a wait (`waits_expected`).
- **Output.** Done and remaining, completion P50 and P90, tokens and cost P50 and P90; 1,000 seeded
  trials, so the same inputs give the same figures. Held tasks and tasks waiting on a dropped or
  missing task are left out and listed (`unreached`).

### 26.5 The allowance fit and projection

- **The fit.** From `board/allowance.jsonl`, consecutive samples of one gating weekly window whose
  percentage did not fall are joined into intervals of 30 minutes to 12 hours. Each interval's usage is
  summed from the telemetry (every bound project's usage file and the system sink, one row per request
  id). Weekly percentage per token and per dollar, overall and by model family, are fitted through the
  origin; the model with the lowest leave-one-out error is used (within 5%, the simpler). The fit is
  cached in `board/forecast-fit.json`.
- **The burn outside the products** is the system sink's usage over the last 7 days (or since it
  started), per hour over at least 72 hours, times the fit. The plane's own project counts with the
  system sink.
- **The projection.** Each trial starts from the latest sample plus the fitted usage since, and rises
  by that burn and by each task's tokens or cost. It reports the percentage at completion, when the
  project's checkpoint and the checkpoint in force are crossed, when 100% is reached before the work
  ends, and the share of trials that fit before the reset.
- **Session pauses.** For a gating session window with a park: its percentage per weekly percentage
  (`r5`) is fitted from samples within one session window; with fewer than 3 intervals nothing is
  modelled. In each trial, when a window would reach its park before its end, work pauses until its end
  plus the wake margin. Each target reports its pauses and paused hours.

### 26.6 Calibration

`ccp estimate calibration` derives correction factors from the scored pairs; it rewrites no row and
gates nothing.

- **The pairs:** per source and metric, each task's actual against the estimate it had before it
  started, each weighted 0.5^(age / half-life) (`estimate.calibration.half_life`, default 40).
- **The bias:** the weighted median of actual/P50, overall, by kind and by family, a group's factor
  shrunk toward its parent by n/(n+k) (k fitted, or `estimate.calibration.k`). A task takes its
  family's factor when the family has 2 or more pairs, else its kind's, else the overall.
- **The width:** the P90 is widened (never narrowed) so the pairs are covered at 90%, stopping at
  P90 = 4 × P50.
- **Too few pairs** (under `estimate.calibration.min_pairs`, default 8): factors 1.0, not fitted, with
  the reason shown.
- **Applied at read time:** P50' = P50 × bias, P90' = P50' × (P90/P50)^width; phases stay raw. The
  model is cached in `board/estimate-calibration.json`.
- **The rolling-origin check** fits each task's calibration only on tasks merged before it started and
  reports the shares at or under P50 and P90, raw and calibrated.
- **Rho.** A fitted rho is computed and shown; it replaces 0.3 only when a backtest on the same history
  favours it.
- **The seat** gets the factors in its prompt and corrects the baseline by them; the plane applies its
  own factors to the seat's answer.
- **Not built:** the two optional gating rules (split a task whose P90 is over a threshold; warn when
  the next task's P90 would cross the checkpoint). Each needs its own ruling from the operator.

## 27. Health measurements

### 27.1 Sources and measures

`ccp health` measures delivery from what is already recorded:

- **Sources:** git (the merges that name a task, with files and lines split by the `architect.areas`
  globs); the queue (report times under `progress/<task>/*-report.md`, phase events, fix and verify
  rounds); prompt audits (prompt sizes).
- **Per task:** wall time; the spans of implementing, reviewing and verifying; fix rounds; files and
  lines by area. **Trend:** rolling medians and the drift ratio (§19).
- **From workers:** `ccp report` records the report's `Suite:` line and friction lines from the report
  itself; `ccp health record` and `note` stay for other numbers the product names in
  `architect.metrics`. Every append to `metrics.jsonl` holds `metrics.jsonl.lock`.
- **Diagnostic only.** Nothing here is a target for a worker or part of a DoD.

### 27.2 Suite series

Suite time comes from the recorded test runs (§14). For a report whose outcome is done (for a
verify, verdict `approve`), `ccp report` files the passing `ccp suite run`s recorded against that run,
each once by `suite_id`, under its kind; a blocked, failed or rejecting report files none. The `full`
and `gate` lanes are those of the roles in `suite.roles`; the counters are the run's `ran`, `cached`
and `cached_tests`, and a record that names them `modules_ran` and `modules_cached` is read as `ran`
and `cached`.

- **cold** (`suite_seconds`, `suite_tests`): a full or gate run that counted tests with nothing cached
  (`cached` 0), or any such run before the product had a test cache. The series a product watches.
- **warm** (`suite_seconds_warm`, `suite_tests_warm`): a full or gate run with any unit cached.
- **part** (`suite_seconds_part`, `suite_tests_part`): a run's passing part-lane (or other lane) runs
  as **one entry per run**, seconds and tests summed, with `runs` and `suite_ids`.
- **unverified** (`suite_seconds_unverified`, `suite_tests_unverified`): a full or gate run that cannot
  be shown cold or warm, or counted no tests, and any suite number typed into `ccp health record`.
- **The cache's start** is its earliest evidence: the first recorded run that gave a `cached` count, or
  the first `Suite:` line naming cached units (`ran <r>, cached <c>`, the older
  `<r> modules ran, <c> cached`, or the word warm), whichever is earlier; with `verify.accept_cache`
  set and no evidence, there always was one. Before it, a passing full or gate run is cold; from it
  on, cold needs evidence.
- Failed, interrupted and killed runs are in no series. Warm, part, unverified and duplicate entries
  never enter the cold series. `ccp health` shows each series apart (`suite` in `--json`).
- **Gate time:** `ccp health` judges the latest cold gate run against the shell limit and the
  cut line, and reports gate runs killed at the limit (§14.6; `gate_time` in `--json`).

## 28. The board

### 28.1 The read model

`ccp board build` folds the ledger, runs, usage and allowance samples, the queue files (`work.json`,
questions, gates, verification, architect state), the task log and git into
`QUEUE_ROOT/board/board.json` (`contracts/board.schema.json`), and writes one counters snapshot a day
under `board/history/`. It is idempotent, makes no model call, and replaces the earlier snapshot and
status files. `ccp board status` is its terminal summary (§23.4).

### 28.2 The page and freshness

- `ccp board html` writes `QUEUE_ROOT/board/index.html`: one self-contained page with the board
  embedded, reloading every minute. One project per board.
- **Rebuilt on every change.** After a state-changing command exits 0, `ccp` marks the board dirty and
  starts a detached rebuild unless one is running (a build while the mark is set costs one more
  build). The command never waits for it and keeps its exit code; a failed rebuild is shown by
  `ccp board status` until a later build succeeds. A timer (`ccp board install`, templates in
  `templates/launchd/`) rebuilds every `board.refresh_minutes` (default 5) for changes made outside
  `ccp`; it is a plain
  process, with no agent and no tokens.

### 28.3 Contents

In priority order:

1. **Time and tokens.** Per task: wall time, queue wait (ready → claimed), active time, waits by
   reason, each run's duration, tokens and model and effort check, review, verify and fix rounds,
   rounds to merge, first-pass approval, severity counts, suite size and time, lines by area (§27). Rolled up per seat,
   per review point, per day and per week; tokens per merged task; the cache-read share; the
   allowance against its checkpoint; trends as rolling medians. Estimates and forecast (§26).
2. **Now.** The live team; each runner, its scope and review point; the tasks in flight with their
   phase and how long they have been there; open runs; waits, gates and questions; architect state;
   the allowance.
3. **Plane health.** The age of every source. `work.json` and `runs/*.json` are written only at
   phase changes, so while a runner runs they are **stale past 30 minutes** unless an open run shows
   it is live: a telemetry request or a `runs/_suites.jsonl` row (started or ended) of an open run
   within the 30 minutes, or a suite of an open run still running (started within 60 minutes, no end
   yet; past 60 minutes with no end it no longer counts). A stale source is a blocker for
   `ccp board status` (§23.4); coverage (merged tasks without runs, unattributed usage, runs
   without usage); runtime against durable divergence and queue against log divergence (§23.5); queue
   scripts (`QUEUE_ROOT/scripts/`) that differ from the plane's copy; open tool proposals (§31);
   recurring `--note` text.
4. **Quality.** Architect passes and triage, house-rule checks and budgets, friction notes (§19,
   §20).
5. **Plan and backlog.** The ADR register (status, decision states, built %); review points with
   progress and the fields the register carries (`kind`, `adr_refs`, `spec_refs`, `pr`, `merge_sha`,
   `done_at`; §22); refactors waiting outside the current scope, and the age of the oldest; the task board, the ready queue, the
   dependency graph and burn-up.

`ccp board build --backfill` derives spans and rounds for tasks recorded before runs existed, from
report times, `verification/` and git. Usage starts when telemetry was turned on, with no backfill.

### 28.4 Rules

No secrets and no content: ids, counts, times and short summaries only. Every agent-written string
(a note, a task title, a reason) is embedded escaped and rendered as text. Every number is a
diagnostic, never a target. A part of the board that fails to build shows its error; the rest still
builds.
