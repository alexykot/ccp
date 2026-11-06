# Design notes: the seat toolkit and test runs

Non-normative. The rules are SPEC §10–§14; these notes record why the toolkit is shaped as it is,
how it is built, and how to check it.

## Why the toolkit exists

Telemetry that depends on a seat remembering to emit decays: a ledger fed by a seat calling an emit
script stopped recording work, a runner grew its own unversioned scripts that emitted nothing and
carried rules in no template, and nothing recorded tokens, model or effort. A duty that exists only in
a prompt is lost silently. Hence: every state change is a `ccp` command that records itself; worker
prompts come from plane templates; usage comes from the harness's OpenTelemetry export (the API's own
counts and the harness's own model and effort; transcripts are an internal format, and an agent
cannot see its own usage); runs join usage to tasks (OpenTelemetry knows the agent and session, not
the task); one read model, `board.json`, built without an LLM; numbers are diagnostics, never targets.

## Implementation notes

- **Modules.** `ccp/queue.py` (`QUEUE_ROOT`, events through `lib.validate_event` and
  `append_event`, `work.json`, the task's queue file, the queue's script check), `ccp/runs.py`,
  `ccp/prompt.py`, `ccp/report.py`, `ccp/lifecycle.py` (claim, phase, wait, close), `ccp/plane.py`
  (proposals, `plane check`, the agent hooks). Tests: `tests/test_toolkit.py`, with a real bare
  origin, a runner worktree and a fake `gh` that squash-merges.
- **Single writers stay single.** `ccp tasks wait|resume` call `set-waiting-on.sh`, and the toolkit's
  heartbeats call `heartbeat.sh`.
- **Binding keys.** `reconcile.log` is `{path, entry, before}`: `entry` is a format string over date,
  task_id, nnnn, pr, head, head7, merge_sha, merge7, summary, review_point and title, placed before
  the first line matching `before`; `reconcile.hooks` remain for anything else.
- **Phases.** `reviewing` and `fixing` were added to `lib.STATUS_ENUM`, `MID_FLIGHT`, `WORK_PHASES`
  and the task and progress contracts.
- **`ccp tasks close`** commits exactly what it changed, by path, through `git status -z`.
  `CCP_COMMIT_TRAILER` adds trailer lines to the commit.
- **Checks added in review.** `task_meta` refuses a task whose `task_id` is not its file name in the
  task-id shape, because the id becomes paths and command arguments; `reconcile.log.entry` and
  `adapter.post_close` are format-checked when the binding loads; friction bullets may wrap; worktree
  links are named in `info/exclude`.
- **`ccp plane check`** lists the queue's own scripts and `.orig` leftovers, apart from the binding's
  `auth_check.script`.
- **Test runs, summary mode.** In summary mode the command's stdout and stderr are the log file
  itself, opened once (mode 0600), so the order is the command's own and no pipe is pumped; counts
  and failing sections are read back from the file line by line in bounded memory. A gate log can be
  large, hence the pruning; the model sees a summary that cannot lose a failure's name to `tail`.
- **Test runs, the environment.** `bin/ccp` once ran as a bash script exporting `PYTHONPATH`, so
  every command `ccp` started inherited the plane on `PYTHONPATH` and bash's `SHLVL` and `_`, and a
  product test cache that hashed the environment missed entries. `bin/ccp` is now a Python script that
  sets no variable. `tests/test_suite.py` `CallerEnvironment` compares the command's environment with
  the caller's.
- **Test runs, processes.** Without a terminal on stdin the command runs in its own process group
  with a watchdog (a separate `python3 -I` process) that ignores forwarded signals and waits on a pipe
  only `ccp` writes; if `ccp` dies without saying it is done, the watchdog sends the group SIGTERM,
  then SIGKILL two seconds later. With a terminal on stdin the command stays in `ccp`'s foreground
  group to read the terminal, and Ctrl-C reaches it twice. With two output destinations, order is kept
  within each stream, not across them. `ccp prompt` records the run's `worktree` for the binding by
  directory.
- **Suite series** are separate metric names (`suite_seconds`, `suite_seconds_warm`, …), not one
  metric with a `kind` field, so every existing reader of `metrics.jsonl` keeps the cold series
  without a filter; each entry also carries `kind`, `suite_id` and `lane`, and the kind is fixed when
  the report is filed.
- **Adopting test runs.** A product optionally names its lanes in `plane.json` and points its worker
  rules at `ccp suite run`.

## Worker efficiency: what the settings rest on

- A plugin agent's frontmatter honours `tools` and `disallowedTools`, and ignores `mcpServers`,
  `hooks` and `permissionMode` there (those need a `.claude/agents/` copy). With an allowlist that has
  no `Skill`, the `skill_listing` attachment is not sent and the deferred-tool list shrinks; a probe of
  one allowlisted and one default subagent showed a first request about a third the size. `Grep` and
  `Glob` are named for builds that expose them; naming an absent tool is harmless.
- With `experimental.cacheTtl: 1h` a subagent writes its cache as `ephemeral_1h_input_tokens` rather
  than `ephemeral_5m_input_tokens`. A 1-hour write costs more than a 5-minute one and saves a full
  rewrite on every gap between 5 and 60 minutes (a long suite run). The OpenTelemetry `api_request`
  event carries `cache_creation_5m_tokens` and `cache_creation_1h_tokens`, which `ccp otel serve`
  keeps, so whether the setting took effect is visible per run.
- The self-check and exploration-hygiene rules began as trials; they are standing rules now (§13,
  ADR-0034).

An example failing summary:

```
ccp suite: st-20261022T113654Z-30a292: the output goes to …/implement-suite-st-20261022T113654Z-30a292.log; a summary follows when it ends (--full streams it)
ccp suite: failing tests' sections (1):
FAIL: test_bad (tests.test_x.T.test_bad)
…
AssertionError: 1 != 2 : one is not two
ccp suite: st-20261022T113654Z-30a292: FAILED, exit 1, lane full, 0.4 s; 4 tests, 1 failed, 1 skipped
ccp suite: full log: …/implement-suite-st-20261022T113654Z-30a292.log (read it with grep -n or sed -n; never cat it whole)
```

## Acceptance checks (walkable)

1. A task run end to end produces runs for implement, review and verify (times, outcome, usage);
   `phase`, `lease`, `run`, `review`, `verify` and `durable` events; a closed lease; and the reconcile
   commit dated from the clock.
2. `ccp tasks close` refuses without a recorded approve at the PR head, and merges nothing.
3. `ccp prompt verify <id>` renders the same text on every run, apart from paths.
4. A file dropped into `QUEUE_ROOT/scripts/` appears on the board's Plane health page and in the next
   `ccp tasks claim`'s stderr.
5. `ccp board build` with the telemetry receiver down still builds, showing usage as stale, not zero;
   a failing `allowance_cmd` shows the allowance as unknown.
6. `index.html` opened from disk shows the views and reloads after a rebuild.
7. Usage from a telemetry spike: ≥ 99% of a task's `api_request` tokens attributed to runs, each run's
   observed model and effort equal to its agent definition's.
