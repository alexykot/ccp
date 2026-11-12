# Allowance, estimation and forecast: implementation notes

Non-normative notes behind SPEC §25 and §26. The rules are in `docs/spec/04-observability.md`.

## 28.20 Implementation notes: the checkpoint and the advisory design seat (2026-10-21, non-normative)

- `ccp tasks claim` refuses a new claim at the checkpoint in force (exit 5, "allowance checkpoint").
  The message tells the runner to stop and the lead to ask the operator. The checkpoint in force is the
  project's `allowance_stop_weekly`, raised by the decisions recorded for the current window (the
  latest sample's `resets_at`).
- `ccp allowance continue --to <percent> --reason "<the operator's words>"` (the lead) appends to
  `board/allowance-decisions.jsonl` and emits `allowance/decided`. It refuses without a reason, a
  `--to` that does not raise the checkpoint, or a missing sample with a reset time.
  `ccp allowance status [--sample]` shows the latest sample, the checkpoint in force, the project's
  own and this window's decisions.
- The runner's stop condition (d) and the lead's protocol (the spec-maintainer skill, "When you are
  the team lead") say this.
- `plane.json` `telemetry.design_seat: {model, effort}`.
  `ccp usage` gives `advice` lines when none of the lead's calls ran on that model (a `[1m]`
  suffix still matches), or none at that effort. The lead's small helper calls on other models
  (session titles) are not advice.
- `run/stopped` is emitted once per run. SubagentStop fires each time an agent's turn ends, and the
  run keeps the latest `stopped_at`.

## Estimation, forecast and calibration in detail

The estimator's usage rows carry `seat: estimator`. Baselines for every open task: `ccp tasks estimate --all --baseline`.

The design has four phases: **A** (this section) the records, actuals at close, a statistical
baseline with no LLM, the accuracy panel and a backfill over history; **B** the estimator seat (a
headless Sonnet run at medium effort) writing `source: "agent"` rows of the same shape; **C** the
forecast (a Monte Carlo over `tasks.ranked()`) and the allowance fit; **D** calibration fed back
into the seat's prompt and the optional gating rules, each needing the operator's ruling when proposed.

- **Advisory.** Estimates gate nothing: no claim is blocked, no order changes, no check reads them.
  `ccp tasks next`, `ranked()`, the verifier and the merge gate are unchanged.
- **Records** (`ccp/estimate.py`). `QUEUE_ROOT/estimates/<task_id>.jsonl`, append-only, one file per
  task, appended under the file's lock (`queue.append_jsonl`). An estimate row:
  `{at, as_of, task_id, source, version, task_hash, inputs, phases, total, tokens, cost_usd, rounds,
  notes}`. `source` is `baseline` (phase A) or `agent` (phase B); `version` counts that source's rows
  for the task; `as_of` is when the estimate stands (`at` for a live row, the task's start for a
  backfilled one, which also carries `backfill: true`). `inputs` holds the `features`, the
  `novelty` counts, `reference_tasks` (wall) and `reference_tasks_tokens`, `deps_done`, and
  `method` `{name: reference-class, v, tier, tokens_tier, k, pool, tokens_pool, reference_since}`.
  `phases` maps implement, review, fix and verify to `{p50_s, p90_s}`; `total` is `{p50_s, p90_s}`;
  `tokens` and `cost_usd` are `{p50, p90}` (null without token history); `rounds` is
  `{review_p50, fix_risk}` (the share of the class with a fix round). An actual row
  (`source: "actual"`): `{merged_at, start_at, merge_sha, wall_s, phases, phases_from, tokens,
  cost_usd, rounds, findings, telemetry}`, from the sources the drill-down reads (§28): `ccp
  health`'s row (wall time, the phase spans, rounds), the usage fold and the run records. Phases
  are, when the task has runs, the union of each phase's run windows (`phases_from: runs`), else
  `ccp health`'s spans laid end to end from the start, where review includes any fix (`spans`, fix
  null). Both are clipped to the task's window, the drill-down's (its `wall_s`, first recorded event
  to the merge), so no phase outruns the wall time. Tokens and cost only
  where the drill-down has run telemetry. `findings` sums the review runs' `severity` (else the
  review reports' `Severity:` lines). Rows hold numbers, ids and short labels only, never task text.
- **Features** (`features`), read from the task file with its Implementation and Verification notes
  and its `status`, `updated` and `review_point` lines left out (what the task said before the
  work): kind; the task-id family (the slug's first token, `ab` in `0179-ab-arm`, via `ids`); the
  areas (the first two path components of each backticked path citation; a citation is a path when it
  has a slash or one of `estimate.path_suffixes`, default the built-in list); cited files that exist and their total lines; ADR
  refs (count and numbers), spec refs, rule refs; dod_checks by id prefix, and the mutation and story
  mentions in them; dependencies; text length. Pure reads. The test modules depending on the cited
  paths are left out: no product exposes a dependents command the plane can call cheaply; phase B's
  seat may read them through the product's own discovery command (§13.5).
- **`task_hash`** is the sha256 of that same text, so a status flip or a note does not re-estimate.
- **The baseline** (`baseline`, no LLM). Every merged task with a wall time is a candidate, with its
  actual (the stored actual row, else measured now). Similarity is a weighted mean: same kind (1),
  same family (2), shared areas (2, Jaccard) and ADRs (1.5, Jaccard, when either has any), and
  closeness in cited lines, dod_checks, text length and dependencies (0.5 each, `exp(-|log ratio|)`).
  Each score is halved for every 30 tasks merged since the candidate (recent tasks weigh more). The
  class is the k best (`plane.json estimate.k`, 5–8, default 6) among the tasks that share the
  family, an area or an ADR (tier `similar`); with fewer than 3 of those, the same kind (`kind`);
  then all (`all`). P50 and P90 (linear interpolation) of the class's actuals give each phase and
  the total. Tokens and cost choose their own class, from the tasks with telemetry only.
  `estimate.reference_since` (a date) leaves tasks merged before a process change out of every class.
- **When a row is written.** `ccp tasks estimate ID --baseline` and `--all --baseline` (every task
  not done or dropped) write a row when the task has none, its hash changed, a dependency merged
  since the last row (`deps_done` grew), or the method version changed; `--force` writes anyway,
  `--dry-run` writes nothing. A done or dropped task is skipped: the backfill covers history.
  `ccp tasks estimate show ID` prints the rows and the latest of each source. Phase B runs these
  from task preparation and `ccp tasks check`; phase A runs them by hand.
- **Actuals at close.** `ccp tasks close` appends the actual row after the merge, the reconcile and
  the queue update, as its last step. A failure is a warning in close's output, never a failed
  close; a re-run of close writes it once (a task with an actual row is skipped).
- **The backfill, with no leakage.** `ccp estimate backfill [--dry-run]`: for each merged task, the
  baseline it would have got from the tasks merged before it started (its merge less its wall
  time), with its features as before its work (the notes left out, as above, and the cited files'
  lines at the commit it started from: the integration branch's first-parent tip at its start time,
  else its merge's first parent; `git cat-file --batch`), written with `as_of` = its start and
  `backfill: true`; and its actual row. A task already estimated (a backfill of this method, or a
  live baseline made before it started) and one with an actual row keep theirs; a second run writes
  nothing. Not leakage-free: the task file is today's, so an Intent or Scope edited during the work
  shows its final form.
- **Accuracy** (`ccp estimate accuracy [--json]`). Each task with an actual is scored on the latest
  estimate of each source made before the task started (its start: the drill-down's window start;
  the merge only when the start is unknown), a live one ahead of a backfilled one, so an estimate
  written while the task was in flight (`--all` reaches in-flight tasks) is never scored: the share of
  actuals at or under P50 (target about 50%) and P90 (about 90%) for wall time, tokens and cost; the
  median actual/P50 (above 1: the estimates run low); and the wall-time figures by kind and by
  family (groups of 2 or more).
- **The board** (§28.3). `board.json` gains `estimates`: per task the latest baseline and agent
  views, the actual, and the estimate each was scored on, and the accuracy. The build reads the
  stored rows only and computes no estimate. Queue tab: P50–P90 wall and P50
  tokens on the ready queue and in the task board's Estimate column. Quality tab: an *Estimation*
  card (≤P50 / ≤P90 shares, actual/P50 and sample sizes for baseline and agent, wall-time bias by
  kind and family). Drill-down: estimate against actual per phase, total, tokens and cost. Every
  string goes through `esc()`.
- **Order.** Readers order `estimates/*.jsonl` rows by time and version; rows are never removed.


**Phase B: the estimator seat (2026-10-22).** Under the same approval. It adds `agent` rows; it changes no
baseline, no accuracy rule and nothing that gates.

- **The seat** (`ccp/estimator.py`). `ccp tasks estimate ID` (without `--baseline`) runs
  `claude -p --model claude-sonnet-5-5 --effort medium --output-format json`, pinned in the plane
  (`estimator.HEADLESS_MODEL`, like the architect's), with **no tools** (`--tools ""`),
  `--safe-mode --setting-sources local`, `--strict-mcp-config`, `--no-session-persistence` and
  `--max-budget-usd 1.00`, in an empty temporary directory: no CLAUDE.md (the user's or a
  product's), auto-memory, settings file (not `~/.claude/settings.json`), hook, plugin, skill or MCP
  server joins the context, while the OAuth login still authenticates (`--bare` would be stricter
  but reads no OAuth login). The user settings' telemetry keys (§24: `CLAUDE_CODE_ENABLE_TELEMETRY`,
  the `OTEL_*` exporter keys), which the seat no longer loads, are copied into its environment
  (`estimator.child_env`; a key the shell sets wins), so its usage is still exported. Everything it
  needs is in the prompt, so a call is one model turn, cannot read or write anything, and costs
  about $0.04–0.07. A read-only allowlist (`Read, Grep, Glob`) was the
  alternative; it was not taken because it adds turns and cost and makes the answer depend on
  what the model chose to open. The environment drops `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY` and
  `ANTHROPIC_AUTH_TOKEN` and carries `ccp.seat=estimator` (`spec_maintainer.headless_env`, §24);
  the prompt is audited (`prompts/estimator/`, phase `estimate`); the call's `modelUsage` goes to
  `board/headless-usage.jsonl` (kind `estimator`). The live-seats panel (§28.3) shows a running
  batch as a headless row with these pins.
- **Prompt inputs** (`templates/prompts/estimate.md`, plain text, every part bounded): the task file
  without its notes and volatile frontmatter (`strip_notes`, at most 12,000 characters); each cited
  ADR decision (`0035 D1`: its `D1` heading or `D1.` paragraph; a bare ADR: its title and decision
  titles), 1,500 characters each and 6,000 in all; each cited SPEC section (the heading starting
  with the ref, in the files `estimate.spec_paths` names, in order: globs relative to the root,
  default `docs/SPEC.md`, `SPEC.md`, `docs/spec/*.md`, `spec/*.md`), 1,200 each and 4,000 in all;
  the cited paths with their lines (existing files first, at most 40; the rest named as not found);
  phase A's features; the reference class (the baseline's wall and token tasks, at most 8, each
  with its similarity, kind, areas, size, actual wall and phases in minutes, tokens, cost, rounds
  and findings, and a title cut at 80 characters); the baseline (P50–P90 per phase and in total,
  tokens, cost, rounds, tier, novelty); the calibration (phase A's accuracy text, at most 1,500
  characters; phase D deepens it); and the criteria table of the design: suite runs needed,
  context size, fix-round risk, DoD shape, novelty, waits. Placeholders are filled in one pass, so
  text in a task is never expanded.
- **Output.** One JSON object: `complexity` (each criterion `{rating: low|med|high, reason}`, one
  line of at most 200 characters), `rounds` `{review_p50 1–10, fix_risk 0–1}`, `phases` (implement,
  review, fix, verify, each `{p50_min, p90_min}`), `total`, `tokens` and `cost_usd` (`{p50, p90}`),
  `reference_tasks` (at least one of the class offered), `waits` (at most 5 short strings) and
  `reasoning` (at most 600 characters, naming the reference tasks and any departure from the
  baseline). Validated strictly: every key present, numbers that are not booleans, P50 ≤ P90,
  positive values (fix may be 0), sane ceilings (a week, 10⁹ tokens, $1,000). An invalid answer is
  retried once with the errors and the answer; a second failure, or a call that fails outright, is
  a failed attempt with no row (the baseline stands), its raw answer kept in
  `estimator/<run>-<task>.failed.txt`. A quota failure stops the batch.
- **The row.** `source: "agent"`, the estimate row's shape in seconds, plus `complexity`, `waits`,
  `reasoning` and `seat` `{run_id, attempts, cost_usd, tokens, duration_ms, models, session_id}`;
  `inputs` adds `offered` (the class shown), `baseline` (its version and bands), and `method`
  `{name: estimator-seat, v, prompt_v, model, effort, tier, pool, k}`; `inputs.reference_tasks`
  is the tasks the seat named. These rows carry model-written text (the reasons and the reasoning,
  bounded), unlike the baseline's. Accuracy scores them as before: only an estimate made before
  the task started counts.
- **When.** A task needs an agent estimate when it has none, its `task_hash` changed, or a
  dependency merged since its last one (`deps_done` grew); done, dropped and in-flight tasks
  (`work.json`) are left out of `--all` and the triggers, since an estimate made after the start
  is never scored (a named task is estimated anyway). `ccp tasks estimate --all [--max N]`
  estimates them one at a time, at most N per batch (default 10; the rest are reported as
  deferred), under `QUEUE_ROOT/estimator.lock`; `--detach` runs that batch in its own session and
  returns; `--dry-run` renders the prompts and calls nothing; `--print-prompt ID` prints one
  prompt; `--force` re-estimates. **`plane.json estimate.auto`** (default `false`, until the
  operator enables it): with it on, `ccp tasks check` and `ccp tasks index` (run after a task is
  written) print one note naming the tasks that need an estimate and also start `--all` detached, unless a
  batch is running or the checkout is a linked worktree (a verifier's: the
  main checkout's task files are the ones estimated). The note and the launch never block the
  command or change its exit code.
- **Cost.** Every attempt is a line in `QUEUE_ROOT/estimator/calls.jsonl` (`run_id`, task, attempt,
  outcome, cost, tokens, duration, models, errors); the Quality tab's Estimation card shows the
  seat's calls, estimates, failures, cost in all and in the last 7 days, and the cost per estimate.
- **The board.** The Queue tab's estimate cells show the agent's P50–P90 with the baseline beside it
  ("· base …"), its reasoning in the tooltip; the Estimation card's agent column fills once scored
  agent estimates exist, with its own wall-time bias table; the drill-down adds the reasoning and
  the complexity ratings. Every string goes through `esc()`.


**Phase C: the completion forecast and the allowance fit (2026-10-22).** Under the same approval. `ccp/forecast.py`, `ccp forecast [--point R<n> | --backlog] [--json]`, and the
board's `forecast`. **Advisory**, like the estimates: nothing claims, orders, stops or checks by it.

- **The order.** The open tasks are replayed in the order `ccp tasks next` takes them: the task in
  flight first, then `ranked()`'s first row (the shared selection: the lead's preference, holds,
  the review point's refactors, `refactor_every`, the dependencies), marked merged, then `ranked()`
  again, so a task joins once its dependencies merge. When the runner's scope runs out the replay
  goes on over the whole log. `ranked()` gains an optional `since` (features merged since the last
  refactor) so the replay keeps its own count instead of one `git log` per step; the board passes
  its merged tasks in merge order. A held task, one waiting on a dropped or missing task, and one
  not `pending` are left out and listed (`unreached`).
- **The review point.** The open tasks tagged with the runner's `review_point` (else the register's
  current point; `--point` names another); with none tagged, the runner's scope.
- **The durations.** Each task takes its latest `agent` estimate, else its latest `baseline`. Wall
  time is a lognormal through the estimate's P50 and P90 (mu = ln P50, sigma = ln(P90/P50) / 1.2816,
  at least 0.05, and the P90 capped at 4 x P50, so sigma is at most ln 4 / 1.2816);
  tokens and cost likewise, drawn with the wall time's normal deviate. One trial's
  deviates share a common part so that any two correlate at 0.3 (z = sqrt(0.3) Z + sqrt(0.7) e, the
  task in flight included): estimates made the same way err the same way,
  and independent draws would make a backlog's P90 implausibly close to its P50 (a baseline P90
  typically covers fewer than 90% of single tasks). The task in flight is drawn conditioned on not
  having finished (its own part of the deviate drawn above the bound the common part leaves): at
  least its elapsed time (the drill-down's start, else its claim), and its
  remaining time and tokens are what is left of that draw. A task with no estimate takes the median
  P50 and P90 of the others and is counted.
- **The throughput model** is the slot model of SPEC §26.4 (`parallel.max_in_flight` slots). The gaps
  are drawn from the latest 40 observed between consecutive tasks (each task's start, the
  drill-down's first recorded event, less the latest merge before it); a negative gap is an observed
  overlap.
- **Waits on the operator** are not modelled: no calendar time for gates, questions or the allowance
  checkpoint. The remaining tasks with a wait, gate or question open now are listed
  (`waits_flagged`), and those whose agent estimate (phase B) names a wait (`waits_expected`). The estimates' wall times include whatever waits their reference tasks had.
- **Output.** For the review point and for the open backlog: done and remaining, completion P50 and
  P90 as times, the hours to it, tokens and cost P50 and P90 (summed, the task in flight's remainder
  only); 1,000 seeded trials, so a rebuild with the same inputs gives the same figures.
- **The allowance fit.** From `board/allowance.jsonl`, consecutive samples in one weekly window
  (`same_window`) whose weekly % did not fall are joined into intervals of at least 30 minutes (the
  samples are whole percents) and at most 12 hours. Each interval's Claude usage is summed from the
  telemetry: every bound project's `board/usage-requests.jsonl` and the system sink (§24, the
  use outside every project), one row per request id, from when both were recording. Four models
  are fitted through the origin, weekly % per token, per dollar of cost, and each of those by model
  family (when two or more families have usage in 3 intervals or more; a negative coefficient
  rejects a model), and the one with the lowest leave-one-out RMSE (percentage points per interval)
  is used (within 5% of the lowest, the simpler one); its error, the in-sample error and every model's error are reported. The non-plane burn
  is the system sink's usage over the last 7 days (or since it started), per hour, times the fit;
  the plane's own project (a binding whose `product_root` is a checkout of the plane) counts with the
  system sink, not as product work.
  The fit is cached in `board/forecast-fit.json`, keyed by the allowance samples and each
  telemetry file's size, mtime and inode: a file replaced or shorter means a re-fit, and a file
  that grew is read from its old size only, re-fitting when the appended part holds a row inside
  the fitted span (a late row); so a build usually re-fits only when a sample arrives. Row times
  are parsed as UTC datetimes, never compared as strings.
- **The projection.** In each trial the weekly % starts from the latest sample plus the fitted %
  of the usage recorded since, and rises by the non-plane burn per hour and by each task's tokens
  or cost (the fitted measure), spread evenly between task completions. Reported: the rise and the
  % at the review point's and the backlog's completion (P50, P90); when the project's checkpoint
  and the checkpoint in force are crossed (P50, and P90 on the early side: 90% of trials cross
  later), with the share of trials that cross before `resets_at`; when 100% is reached before the work ends (the
  allowance runs out: "exhausts the weekly allowance around …", P50 and the early P90, with its
  share of trials); and the share of trials that fit (end before `resets_at` without reaching 100%),
  with the % that spills into the next week (P50, P90). A projection past 100% never reads "fits". A sample whose window
  has ended starts again from 0 at the next reset.
- **The non-plane burn's floor (2026-10-23).** The sink's usage is divided by at least 72 hours
  (`BASELINE_MIN_SPAN_H`): a shorter history is averaged as if it covered 3 days, so one busy day does
  not set a round-the-clock rate. The fit reports `baseline_hours` (the history's span), `baseline_floored` and
  `baseline_span_h`. This replaces "The non-plane burn is the system sink's usage over the last 7 days
  (or since it started), per hour, times the fit" in the allowance fit above, which now reads: over
  the last 7 days, or since it started, per hour over at least 72 hours, times the fit.
- **The 5-hour window (2026-10-23, §25.4 the session park, under the same approval).** `r5`, the
  5-hour % per weekly %, is fitted from `allowance.jsonl`: consecutive samples in one 5-hour window
  (the 5-hour % did not fall; both rows' `five_hour_resets_at`, where both have one, within 10 minutes;
  at most 5 hours apart) and one weekly window, whose weekly % rose by 1 or more (a smaller rise carries
  the start forward); r5 = sum of the 5-hour rises / sum of the weekly rises (least squares through
  the origin weighted by 1/Δweekly: each interval counts by its weekly rise, and the whole-percent
  rounding of a chain of samples cancels). Fewer than 3 intervals: no 5-hour modelling, with a note. In each trial the 5-hour % rises at r5 times the weekly % rate (the non-plane burn
  plus the running task's burn spread evenly over its run). The current window ends at the latest
  sample's `five_hour_resets_at` (when known and ahead; else a fresh window starts now at 0%), from
  the latest 5-hour % plus r5 times the weekly % fitted since that sample. A window that ends while
  work goes on is followed at once by the next at 0% (it rolls from first use). When a window would
  reach `session_park_pct` before its end, work pauses until its end plus the wake margin; the next
  window starts at that resume, at 0%. A pause shifts every later start and end (the trial's draws are
  unchanged: the pauses draw no random numbers). Each target reports its pauses and paused hours (P50,
  P90) and the share of trials with any; `ccp forecast` prints "5-hour limit: pauses P50 2 (1.6 h) /
  P90 3 (2.4 h), r5 6.4 (n 9)", and the board's Forecast card a *5-hour limit* row. With
  `session_park_pct` null, nothing is modelled and the forecast is as before. `FORECAST_V` 2, `FIT_V` 2
  (the cached fit is re-fitted once). The 4x draw cap (2026-10-23, below) is `FORECAST_V` 3 and `CALIB_V` 4
  (the cached calibration is rebuilt once).
- **The board.** `board.json` gains `forecast`. Queue tab: a *Forecast* card, the review
  point and the backlog side by side, the weekly % now and the checkpoint crossings, and the models
  in words. The header strip's weekly-allowance tile: one line, "R3 P50: +45% → 87% by Fri 19:10;
  fits before the reset", "spills ~6% (P90)", or, first of all, "exhausts the weekly allowance ~Sat
  02:00" when 100% comes before the work ends. Plane health's *Allowance* card: the fit (model, its
  rate, leave-one-out error, intervals, the models tried) and the non-plane burn. Every figure says
  P50/P90 or estimate; every string goes through `esc()`.


**Phase D: the calibration loop (2026-10-22).** Under the same approval.
`ccp/calibrate.py`, `ccp estimate calibration [--json]`. **Advisory**: it rewrites no row and gates
nothing. The two optional gating rules of the design (split a task whose P90 is over N hours; warn
when the next task's P90 tokens would cross the allowance checkpoint) are **not** built: each
needs its own ruling from the operator.

- **The pairs.** Each task with an actual is scored on the estimate it had before it started
  (phase A's rule). Per source (baseline, agent) and metric (wall, tokens, cost): (actual, P50,
  P90), with the estimate's kind and family, oldest merge first. Each pair weighs
  0.5^(age / half-life), its age in merges among the source's pairs (`plane.json
  estimate.calibration.half_life`, default 40).
- **The bias.** The weighted median of actual/P50, overall, by kind and by family. A group's log
  factor is shrunk toward its prior (a kind toward the overall, a family toward its kind) by
  n/(n+k), n its effective size (Kish). k is fitted (empirical Bayes): the pooled within-group
  variance of the log ratios gives each family median's sampling variance ((pi/2) sigma^2 / n), and
  DerSimonian-Laird's method of moments over the families gives the between-family variance
  tau^2, so k = (pi/2) sigma^2 / tau^2, within 5–100 (a group of 5 pairs carries at most half its
  own weight); 10 with fewer than 3 families of 2+ pairs; `estimate.calibration.k` fixes it. A task
  takes its family's factor when the family has 2+ pairs, else its kind's, else the overall.
- **The width.** After the bias, each pair needs s_i = log(actual/P50') / log(P90/P50) to be
  covered; s is the weighted 0.9 quantile of s_i, shrunk toward 1 by n/(n+20), never under 1
  (calibration widens a P90, never narrows one). One per source and metric. The widening stops at
  P90' = 4 x P50' (a raw band already wider keeps its own), so an already wide band is not raised to
  a power into a lognormal whose mean is many times its median.
- **Too few pairs.** Fewer than `estimate.calibration.min_pairs` (default 8) for a source and
  metric: factors 1.0, `fitted: false`, and the reason, in every place the factors show.
- **Applied at read time.** P50' = P50 x bias, P90' = P50' x (P90/P50)^width.
  `estimate.latest(rs, source, calibrated=True, cal=model)` returns the row with the calibrated
  `total`, `tokens` and `cost_usd`, the stored ones under `raw`, the factors under `calibration`.
  Phases stay raw (the factors are fitted on totals). The model is cached in
  `QUEUE_ROOT/board/estimate-calibration.json`, keyed by a hash of the pairs and the settings: a
  build re-fits only when an actual or an estimate arrives.
- **The rolling-origin check.** For each task in start order, the calibration is fitted only on
  the tasks merged before it started (the backfill's no-leakage rule) and applied to its estimate;
  the shares at or under P50 and P90, raw and calibrated, per source and metric, are reported
  beside the factors.
- **Rho.** The forecast's correlation of any two tasks' deviates stays 0.3 (phase C) by default.
  A fitted rho is computed and shown: from the rolling check's out-of-sample wall residuals
  z = log(actual/P50') / (log(P90'/P50') / 1.2816), in start order, only where the calibration had
  enough pairs, winsorized at ±3; in windows of 20 consecutive tasks (a review point's backlog) the
  variance of the window means is Var(z) (1 + 19 rho) / 20, so rho = (20 Var(means) / Var(z) - 1) /
  19, kept within 0–0.8, with its n and standard error (a moving-block bootstrap); none with fewer
  than 40 residuals or a standard error over 0.15. The fitted rho **replaces 0.3 only when a
  backtest on the same history favours it** (2026-10-22): for
  windows of 19 consecutive tasks (every third start), the out-of-sample calibrated bands are drawn
  as the forecast draws them (400 seeded trials per window), once with 0.3 and once with the fitted
  rho, and the one whose share of actual sums at or under the draws' P50 is closer to 50% is used.
  Both backtests are computed in the calibration step and cached with it.
- **Who reads it.** The board's estimate views carry `cal` beside the raw bands, and `estimates`
  carries `calibration` (the factors, groups, sample sizes, the rolling check, rho). The forecast
  draws from the calibrated bands and the fitted rho (`collect(..., calibrated=False)` gives the raw
  forecast for comparison); `ccp forecast` names rho and how many estimates were calibrated.
  `ccp tasks estimate show ID` prints each latest estimate raw and calibrated with its factors.
- **The estimator seat** (phase B) gets the factors in place of phase A's accuracy text (prompt v2,
  at most 1,500 characters): per source and metric, "P50 runs low by 14% overall (n=22); widen P90:
  (P90/P50)^1.28, so a P90 1.6x its P50 becomes 1.8x", up to four kinds or families whose factor is
  10% or more from 1, with their n, and rho. The template tells the seat to correct the raw baseline
  by the baseline's factors and not to re-apply its own, which the plane applies to its answer.
- **The board.** Queue tab: estimates show the calibrated P50–P90 by default, the raw on hover.
  Quality tab, Estimation card: the raw accuracy as before, then a *Calibration* table (per source
  and metric: ≤P50 / ≤P90 raw and calibrated from the rolling check, bias, width, n, k or why not
  fitted), the wall-time bias by kind and family (shrunk factor, raw median, n, own weight), and
  rho. Drill-down: total, tokens and cost raw and calibrated, the factors on hover, the marks
  against the calibrated band. Every string goes through `esc()`.

