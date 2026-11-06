# Telemetry: implementation notes

Non-normative notes behind SPEC §24. The rules are in `docs/spec/04-observability.md`.

## The join-key spike

**Spike before build (part of acceptance).** The docs do not say what `agent.name` holds for a
teammate or a subagent, and document `agent_id` only on trace spans. The first implementation step
is to run one real task with telemetry on and establish the join key. **At least 99% of that
task's tokens must be attributed to a run.** If `agent.name` is not enough, use the trace spans
(`agent_id`, `parent_agent_id`), with `OTEL_TRACES_EXPORTER` added and received the same way.
§8.4 records what the spike found.

## 28.18 Step 2 spike: headless results (2026-10-21, non-normative)

Claude Code 2.1.306, `claude -p` with the probe plugin, a `claude-sonnet-5-5` session launching one
`cp-probe:probe-worker` (pinned to `claude-haiku-5-5`, effort `low`), exported to a local OTLP/HTTP
JSON receiver.

- **`claude_code.api_request` (logs)**, one per API call, carry:
  - `model`, `effort` (`medium` for the session, `low` for the worker, as pinned);
  - `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`,
    `duration_ms`, `request_id`;
  - `session.id`, `prompt.id`, `query_source` (`sdk` for the session, `agent:custom` for the
    worker).

  **`agent.name` is `custom`** for a plugin agent, so it cannot tell runs apart. The session and
  the worker share one `session.id` and one `prompt.id`.
- **Trace spans `claude_code.llm_request`** carry the same tokens, `model`, `effort` and
  `request_id`, and, for the worker's calls, **`agent_id`**: exactly the `agent_id` the
  SubagentStart hook reports. That is the join key: span `agent_id` → the run bound to it (§11.1),
  and span `request_id` → the log's `cost_usd`. The main session's spans carry no `agent_id`.
- **Traces need `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`** besides `OTEL_TRACES_EXPORTER=otlp`.
  Without the flag no spans are exported, and no telemetry carries `agent_id`.
- **The fallback without traces** is a time-window join: an `api_request` with
  `query_source: agent:*` between a run's `started_at` and `stopped_at` (from the hooks) belongs to
  that run when exactly one run of its model and effort is open. It is unambiguous while the runner
  launches one worker at a time, and is counted as unattributed otherwise.
- **Teammates** (the operator, interactive agent-team session, 2026-10-21; a `claude-haiku-5-5` lead with
  a `cp-probe:probe-worker` teammate pinned to effort `low`):
  - The teammate's own calls carry span `agent_id: <teammate name>@session-<lead session prefix>`
    (`probe@session-<lead session prefix>`), with `query_source: agent:custom`. The hook's `agent_id` for the
    same teammate is different (an `a…` id). So the runner's calls join by **teammate name**:
    `runner@…` is the runner seat.
  - The lead's own calls carry no `agent_id` (`query_source: repl_main_thread`, plus a
    `generate_session_title` call): they are the design seat's.
  - **The teammate ran at its definition's effort (`low`), not the lead's (`medium`).** On this
    Claude Code version, §2.4's former "a teammate gets the lead's effort" did not hold. §2.4 now
    pins the runner's effort too, and the board flags any difference.
  - The teammate launched no workers of its own. That workers inside a teammate carry their own
    `agent_id` (as headless) is checked on the first real task, by docs/design/toolkit.md's 99% attribution check.
- **The join, then:**
  - span `agent_id` equal to a bound run's `agent_id` → that worker run;
  - `<name>@session-…` → the teammate of that name (`runner`, or any name a `runner` event recorded,
    such as one a rotation bound, → the runner seat);
  - no `agent_id` → the lead (the design seat);
  - logs without spans → the time-window fallback.

## 28.19 Step 2 implementation notes (2026-10-21, non-normative)

- **`ccp otel serve`** (`ccp/otel.py`) is an OTLP/HTTP JSON receiver on 127.0.0.1 (default port
  4318, `telemetry.otel_port`).
  - It keeps `api_request` log records in `board/usage-requests.jsonl` and `claude_code.llm_request`
    spans in `board/usage-spans.jsonl`, numbers and ids only, never content.
  - It routes by the resource attribute `ccp.project_id` to the queue named in the plane's binding
    (`CCP_BINDINGS_DIR` overrides the directory, for tests). A record for an unknown project is
    dropped and counted. Metrics are accepted and ignored. *(Superseded the same day by §24.3:
    session routing, and the system sink instead of dropping.)*
  - `ccp otel install|uninstall|status` manage the launchd agent `<prefix>.control-plane.otel` (`CCP_LAUNCHD_PREFIX`, default `dev.ccp`),
    which runs it from the run checkout. `ccp otel …` needs no product checkout.
- **`ccp otel env --project ID`** prints the static `env` block a product's `.claude/settings.json`
  carries: `CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, the logs and traces exporters, `http/json`, the endpoint, and
  `OTEL_RESOURCE_ATTRIBUTES=ccp.project_id=ID`. A plugin cannot set environment, so this block is
  part of the product's anchor (§4.3). It names the project, not a plane version. *(Superseded
  the same day by §24: Claude Code ignores this block in project settings; `ccp otel env` now
  prints the user-settings block, without a project.)*
- **`ccp usage [--task ID] [--json]`** (`ccp/usage.py`) folds the join of docs/design/telemetry.md into per-run and
  per-seat tokens, cost, observed models and efforts. It also gives coverage (the share of tokens
  attributed), how each request was attributed, and which agent ids lie behind unattributed tokens.
  It flags a run whose observed model or effort differs from its pinned values. The board (step 3)
  reads the same fold.
- **Allowance (§25.1).** `ccp tasks claim` runs `telemetry.allowance_cmd` before it takes the lease,
  appends the sample to `board/allowance.jsonl` and emits `allowance/sample`. It refuses with exit 5
  when `seven_day` is at or above `telemetry.allowance_stop_weekly`. An unreadable sample is
  recorded with nulls and never stops a claim. *(2026-10-23: claim and `ccp prompt` also park at the
  5-hour park %, exit 6, §25.4 the session park.)*
- **Headless runs.** `ccp architect run` and `architecture-review.sh run` append `claude -p`'s
  `modelUsage`, `total_cost_usd` and turns to `board/headless-usage.jsonl`.
- **From the review (2026-10-21).**
  - The receiver refuses what it cannot keep: 415 for a body that is not JSON (an exporter left on
    `http/protobuf`), 400 for a body that is not an OTLP object, 411 or 413 for a bad or oversize
    length. A gzip body is capped after decompression too. `GET /status` reports rows written and
    dropped and bodies refused; `ccp otel status` shows it.
  - A project bound after the receiver starts is found on its next record (only hits are
    cached). Numeric attributes sent as strings are stored as numbers.
  - The fold counts one row per `request_id`. When traces exist, a main-thread call without a span
    goes to `nospan` and is not counted as attributed, so lost spans lower coverage instead of
    hiding as the lead's. A window match needs a run whose agent started. `--task` adds that task's
    totals, and coverage is labelled project-wide.
  - `record_headless` never raises. A resumed claim of a task it already leased is not refused at
    the allowance gate. The allowance command has 8 seconds, numeric strings count, and an unknown
    reading is a `warning:` on the claim.
- **Checked live.** The receiver ran on a spare port; a headless session in a throwaway product
  carried `ccp otel env`'s block and launched a plugin worker. All 5 requests and 5 spans reached
  that project's queue. The lead's calls were attributed to the design seat, and the worker's
  (which had no run) appeared as unattributed under its agent id.


## 28.22 Telemetry system-wide, routed by session (2026-10-21, non-normative)

- **The finding.** Claude Code 2.1.306 filters `CLAUDE_CODE_ENABLE_TELEMETRY` and every `OTEL_*`
  key out of a project's `.claude/settings.json` `env`; a plain variable in the same block does
  reach the session (2026-10-22: `OTEL_RESOURCE_ATTRIBUTES` does too, see "The project key"). So the product block of docs/design/telemetry.md exported nothing. The process environment,
  `--settings <file>` and the user settings (`~/.claude/settings.json`) do work. The operator chose the
  user settings over a launcher (option (b), quoted in §24), so telemetry covers all Claude work
  on the machine, not only the plane's.
- **The project key (2026-10-22).** Claude Code 2.1.308 ignores the six enabling keys in a
  project's settings (a project may only turn telemetry off) and warns, but it honours
  `OTEL_RESOURCE_ATTRIBUTES` there: a product's sessions arrive with its `ccp.project_id` from its project settings (receiver status `routed_by`). So a
  product's settings carry that one key: `ccp otel env` prints only OTEL_RESOURCE_ATTRIBUTES
  (ccp.project_id=<id>) for the project, and the six enabling variables for user settings
  (~/.claude/settings.json) or the shell, and says which goes where. `ccp otel env --project <id>`
  checks the id against the bindings and prints `{"project": {"path", "env"}, "user": {"path",
  "env"}, "note"}`; without `--project` it prints the user block as before. `sync-product-docs.sh`
  notes the six enabling keys left in a product's settings as ignored and removable, and does not
  flag `OTEL_RESOURCE_ATTRIBUTES`. *Replaces* §24's "Claude Code ignores these keys in a
  project's `.claude/settings.json` (§24.3), so a product carries none of them" (now: none of
  the six) and an earlier change `--project is retired` warning. The routing order is unchanged.
- **The routing order** (`ccp/otel.py`):
  1. resource `ccp.project_id` → the binding's queue (set by the product's settings, or by a
     process env);
  2. record attribute `session.id` (on `api_request` log records and on `llm_request` spans alike;
     it is not a resource attribute) → the `cwd` of the first transcript record that carries one
     in `~/.claude/projects/<slug>/<session.id>.jsonl` (every folder is looked in: the recorded cwd
     counts, not the slug) → the binding whose `product_root` holds it, as real paths
     (paths compared after resolving symlinks). Under the root counts
     (`<worktrees dir>/impl-…`), and so does a git worktree of it elsewhere (its `.git` file names
     `<root>/.git/worktrees/…`). The deepest root wins;
  3. otherwise the system sink, `~/.local/state/control-plane/telemetry/usage-{requests,spans}-<UTC
     day>.jsonl` (`CCP_TELEMETRY_DIR`), the same folded fields plus `session_id` and `cwd`. Day
     files older than 90 days are deleted. `ccp usage --system [--since DATE] [--json]` reads it.
  The plane's own development, once it manages itself, routes to its own project like any product
  (`ccp.project_id=control-plane`); for the allowance forecast it is still not product work and is
  counted with the system sink (§26.4).
- **Teammates and subagents.** Both carry the lead's `session.id` in their telemetry (checked on
  the step 2 team capture: teammate spans `probe@session-<lead session prefix>` and the worker's spans all carry
  the lead's session id). Their transcripts sit under the lead's session folder,
  `<slug>/<lead session>/subagents/agent-<id>.jsonl` with `.meta.json` (`taskKind:
  in_process_teammate` for a teammate), and record the lead's `sessionId` and cwd. They route
  with the lead.
- **Caching and waiting.** A session's cwd is cached once found; a miss is not, since the
  transcript may not exist at a session's first export: it is looked up again after 10 seconds.
  Rows of a session that has not resolved wait in memory (at most 5,000 rows; the oldest session
  overflows first) for up to 60 seconds, retried every 5 seconds, then go to the system sink. The
  receiver writes them on shutdown (SIGTERM). A session's project is cached per bindings
  generation; bindings are re-read every 30 seconds. Rows routed by `ccp.project_id` also carry
  the session's cwd when it is known.
- **Seats** (§24.3 "Attributed"). Plane-launched `claude -p` runs set `ccp.project_id` and
  `ccp.seat` in their process environment (`spec_maintainer.headless_env`), which routes them, and
  their subagents, ahead of any cwd. Without that, the product root's cwd would have put them on
  the design seat. A runner started as its own top-level session (`entrypoint: sdk-cli`) has main-thread calls with no `runner@session-…`, placed by its cwd (its merge checkout).
- **Cross-site requests.** The receiver accepts only `Content-Type: application/json` (parameters
  ignored): a web page can POST `text/plain` to 127.0.0.1 without a preflight. An unbound
  `ccp.project_id` is kept as a label only when it is a valid id of at most 64 characters.
- **Status.** `GET /status` and `ccp otel status` report rows written per sink (`project`,
  `system`), how project rows were routed (`project_id`, `session`), `pending` (rows waiting for
  their session), `unresolved` (system rows with no session cwd), `dropped` (write failures) and
  `refused`. `ccp otel status` also checks, read-only and by key name, that the user settings
  carry `ccp otel env`'s block, and warns about every problem it finds: keys missing or different,
  a pinned `ccp.project_id`, and `OTEL_LOG_USER_PROMPTS` or `OTEL_LOG_TOOL_DETAILS` set to anything
  non-empty in the user settings or the environment (the shell, or the settings env a Claude Code
  session passes to its commands), either of which makes Claude Code export prompt text
  or tool details.
- **launchd.** `ccp otel install` and `ccp board install` write the run checkout's `ccp`
  (`CCP_RUN_CHECKOUT`, default the run checkout) into the plist, whichever
  checkout runs the install; the receiver's plist of 2026-10-21 named the development checkout.
  Both report the `ccp` they wrote, and warn when `CCP_RUN_CHECKOUT` names a checkout without
  `bin/ccp` (the plist then falls back to the installing checkout).
  Both boot the old agent out and wait (up to 10 s) until `launchctl print` no longer finds it,
  then bootstrap, retrying `Bootstrap failed: 5: Input/output error` after 1, 2 and 4 s (on
  2026-10-21 a bootstrap straight after the bootout failed so and left the receiver unloaded), and
  then check the agent is loaded and, for the receiver, `state = running`. The result reports
  `bootstrap_attempts`, `loaded`, `state` and any `error`.

