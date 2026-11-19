---
id: ADR-0043
title: "Opinionated defaults, short configuration"
status: accepted
date: "2026-11-19"
deciders: operator
spec_refs: [S2, S3, S4, S5, S6, S8, S10, S12, S14, S15, S16, S18, S19, S20, S21, S22, S23, S24, S25, S26, S27, S28, S30]
notes: |-
  Proposed from the operator's configuration principles (2026-11-19, in the lead session), quoted in
  Context, and an audit of every per-product setting. It changes stated defaults in many SPEC
  passages and partly supersedes ADR-0012 D1 and D5 and ADR-0042 D1, so the operator decides it.
  Removed keys and new required steps reach products through ADR-0041's upgrade steps. Tasks follow
  the architect's shape.
  2026-11-19: status proposed → accepted: Accepted by the operator 2026-11-19: "accept ADR-0043"
  Operator 2026-11-19: the language is a top-level `language` key; package-doc checks follow it, `none` turns them off (shape F03)
decisions:
  - "D1 not_built"
  - "D2 built"
  - "D3 built"
  - "D4 not_built"
  - "D5 not_built"
  - "D6 built"
  - "D7 not_built"
  - "D8 not_built"
  - "D9 not_built"
---
# ADR-0043 — Opinionated defaults, short configuration

## Context

The operator set these principles for a product's configuration (2026-11-19):

> - The standard configuration should not make assumptions about what the project exactly is or how
>   it should be configured, but it should provide enough of these sane defaults that it can run well
>   without changes.
> - There should be sensible, high-performance settings by default. Parallel execution enabled, path
>   conflicts disabled.
> - Opinionated model settings should be defined for every role by default.
> - It should not make assumptions on the language. If the language setting is required for
>   operation, then it should be left empty, and it should refuse to start without it.
> - Telemetry should be on and fully working by default.
> - Architect should be on and working by default.
> - Values that are unlikely to need to be changed shouldn't really be in configuration at all.

An audit of the configuration against them found:

- **Size.** `plane.json` accepts about 150 leaf settings and the local binding about 50, counting a
  map such as `suite.lanes` as one. Code reads fewer than 20 of the binding's.
- **Dead keys.** Nothing reads `telemetry.otel_port`, `task_log.statuses` or most of the binding.
- **Duplicates.** Several keys exist twice or have legacy aliases. Every default is restated in the
  schema, the SPEC and the README.
- **Account facts per product.** The usage allowance and session-window knobs describe the Claude
  account on the machine, not the product.
- **A language assumption.** `package_docs.language` defaults to Python, and the test-output parsers
  read only Python's unittest.
- **Off by default.** Parallel work is off (`max_in_flight` 1), scheduling is by shared paths, and
  the architect is off without its block. `ccp init` writes no telemetry tag.
- **Models.** They are fixed per seat in the agent definitions. Only the implementer's is
  configurable.

## Decision

### D1. Defaults run well with no changes

Every setting has a default that works for any product, or is required (D4). A setting exists only
when a reasonable product would change it. Anything else is a constant in code, or is removed (D9).
Each default is defined once, in code. The schema is held to it by a test (house rule E12), and the
SPEC states the behaviour, not the number.

### D2. Parallel by default

`parallel.max_in_flight` defaults to 3 and `parallel.schedule` to `clashes`.

- This replaces ADR-0012 D1 (parallel work is opt-in) and ADR-0012 D5 (paths decide
  co-scheduling).
- It replaces ADR-0042 D1's clause that the schedule default changes only after D5's measurement:
  the operator decided it here.
- `parallel: false`, `parallel.exclusive` and `clashes_with` still keep tasks apart.

### D3. A default model for every role

| Role | Default model | Change from today |
|---|---|---|
| Lead | Opus | new: `ccp init` writes it into the product's settings |
| Runner | Sonnet | none |
| Implementer, and its fix, merge and ruling rounds | Opus; Sonnet for a small task or a refactor | the split becomes the default (today the default is Opus for all) |
| Reviewer | Opus | from Sonnet |
| Verifier | Sonnet | none |
| Architect | Opus | none |
| Estimator | Sonnet | none |

- **One block for model choices:** these are defaults. A product may override any role in one
  `models` block, which replaces `workers.implementer_model`.
- **The reviewer moves to Opus:** the reviewer is where defects are caught before verify, and one
  run per round is a small cost.
- **The seat table:** the SPEC's seat table names every role, the estimator included.

### D4. No language default

`package_docs.language` has no default, and `none` is a valid answer.

- **Which commands refuse:** a command that needs the language, and finds it unset, refuses with
  exit 2 and names the key. These are:
  - the package-doc checks, and with them `docs check`;
  - `ccp suite affected`;
  - test-output parsing.

  Other commands run, such as claims, merges and closes. A task already in flight cannot pass its
  gate while the language is unset. The grace release in D9 exists so that never happens by
  surprise.
- **The docs check makes it required in practice:** every task's gate runs `docs check`, so a
  product cannot deliver without the language. That is the operator's condition for refusing:
  required for operation.
- **Test-output parsing:** parsing test counts, failures and skips belongs to the language pack. With
  `none`, the product's patterns apply, or nothing is counted.
- **Init:** `ccp init` asks for the language.

### D5. A gate lane is required

Every task's verify runs the gate lane, and so does its catch-up with the integration tip before
review (ADR-0042 D3). A product with no gate lane cannot deliver. So `suite.lanes` must name a gate
lane, and `ccp tasks claim` and `ccp tasks next` refuse (exit 2) without one. `ccp init` asks for
the command. It assumes no tool or language: the gate is whatever command the product runs.

### D6. Telemetry on and working by default

- **The product's tag:** `ccp init` writes the product's telemetry tag
  (`OTEL_RESOURCE_ATTRIBUTES=ccp.project_id=<id>`) into the product's settings.
- **Machine setup, with consent:** `ccp init` checks the receiver and the user-level keys. With the
  operator's consent, given once per machine, it writes the user-level keys and installs the receiver
  and the board timer.
- **What stays off:** prompt and tool-content logging (`OTEL_LOG_USER_PROMPTS`,
  `OTEL_LOG_TOOL_DETAILS`) is never written and stays off (§24.1).
- **A machine-wide switch:** Claude Code reads the enabling keys only from the user settings (§24.1),
  so turning telemetry on applies to every session on the machine. Consent is the safety case.
  - Before turning it on, `ccp init` says plainly that it covers every session.
  - The operator may decline, and delivery runs without telemetry.
  - Whether a directory can turn it off locally is checked during shaping. If it can, the SPEC says
    how; if not, it says it cannot.
- **The port:** `telemetry.otel_port` is removed, because the receiver owns its port.
- **Accepted limits:**
  - The receiver cannot be started from inside Claude Code. When it is down, `ccp init` prints the
    command to run in a normal terminal.
  - Only macOS has a service definition.

### D7. Architect on by default

- **On without a block:** the architect runs with its defaults when `plane.json` has no `architect`
  block. Only `"architect": false` turns it off.
- **The adoption point:** shaping (`shape_from_task`), the task-kind and refactor-reference checks,
  and the cadence all start from the product's adoption point. That is the next task number when the
  architect turns on. A finished task is never judged by rules written after it, and an upgraded
  product owes no pass at once.
  - A new product records it at `ccp init`.
  - A product with history records it by an ADR-0041 upgrade step, in its own repo. The plane never
    writes it there.
- **Rules:** `ccp init` writes the starter house rules, and `rules_doc` defaults to them. When the
  rules doc is missing, the architect runs without house rules and says so. It never points at
  nothing silently.
- **Blocking:** the architect's existing blocks apply.
  - A pass that is due blocks `ccp tasks next` after `grace_tasks` merges.
  - An untriaged report blocks after `triage_grace_tasks`.
  - A failed pass is due again after the next merge and blocks again. After two failures in a row
    it stops blocking until a pass succeeds.
- **Needs a logged-in Claude Code:** the pass runs headless and needs Claude Code logged in on the
  machine.

### D8. Account facts move to the machine

- **One config per machine:** the allowance command and the weekly stop move from each product's
  `plane.json` into one installation config per machine. The weekly stop gains a default of 90%;
  today it has none, so nothing stops for the weekly allowance at all. Shaping decides where
  it lives.
- **Constants:** the session park, wake and ceiling knobs become constants. The provider's session
  window is optional, and the rules already pass when an account has none.
- **Spend is not bounded until the allowance can be read.** Without an allowance command, no usage is
  read, the weekly stop never fires and the parallel usage rule passes. In that state the plane
  bounds nothing. So:
  - `ccp init` and the session-start check name the missing command as a warning.
  - The board shows "usage unread".
  - A built-in reader, if a supported usage source exists, is a later decision.

### D9. A short configuration

The appendix lists every key with its outcome.

- **Removed:** dead keys, and the binding keys no code reads.
- **Merged:** duplicates, into one key each.
- **Constants:** tuning values a product would not change become constants in code.
- **What stays:**
  - where things are;
  - what only the product knows: its commands, paths, ids and privacy dirs;
  - choices a product makes: refactor capacity, the architect's cadence, quality knobs.
- **`task_log.dry_run`:** it becomes a constant, at today's behaviour.
- **`adr.strict`:** it stays a setting. Fixing it on would turn every product's ADR warnings into
  failures at release.
- **`verify.skip_review_after_clean`:** it stays a setting, default off. It is a quality choice, not
  a constant.
- **Defaults that change with a key becoming a constant:**
  - `estimate.auto`: on, so the per-size implementer models (D3) apply without a manual run.
  - `architect.shape_adrs`: on whenever ADRs are on.
  - `prompts.fragment`: the product's `docs/delivery/WORKERS.md`, when it exists.
  - `worktrees.dir`: `.plane-runtime`, which `ccp init` already writes.

**Migration (ADR-0041):**
- A removed key keeps working for one release. `ccp` warns and ignores it, and that release's
  upgrade step tells each product what to delete.
- **A non-default value of a key that becomes a constant is never dropped silently.** The upgrade
  step lists every such value the product sets. Examples are `task_log.index: false`, its own
  `sections`, or `architect.grace_tasks`. For each, the lead either accepts the constant or files a
  plane proposal to keep the key. Until the step is taken, the old value still applies.
- The required steps for a product with history are:
  - **The language:** set it. The step proposes `python` where the product relied on the old
    default.
  - **The gate lane:** name it.
  - **The architect:** record the adoption point.
- A product is not halted at release. The refusals in D4 and D5 apply only once the step's grace
  release ends.

## Consequences

- **A new product works out of the box:** once its language and gate lane are named, it runs in
  parallel, with the architect on, every role on a set model, and telemetry on if the operator
  consents.
- **Spend rises:** more tasks run at once, the reviewer runs on Opus, and the architect and estimator
  run for every product. Only the weekly stop bounds it, and only once the allowance can be read
  (D8). Until then nothing does, and the plane says so.
- **Products with history change at their next release:** parallel and clash scheduling apply unless
  the product sets them back. The required steps in D9 come with a grace release.
- **Fewer copies of each default:** the SPEC states behaviour rather than numbers.
- **Partly supersedes:** ADR-0012 D1 and D5, and ADR-0042 D1 (the default schedule).

## Appendix: every key and its outcome

The schema's own annotations, `$schema` and `_note`, stay accepted and mean nothing.

"Constant" means it moves into code at today's default unless stated otherwise.

**`plane.json`, kept (some with new defaults):**
- `project_id`
- `spec_paths`: one top-level key, merging `task_log.spec_paths` and `estimate.spec_paths`.
- `package_docs`:
  - `language`: required, D4.
  - `claude_md_dirs`, `source_suffixes`, `exempt_dirs`, `docstring_globs`, `delivery_id_patterns`,
    `rules`.
- `docs`:
  - `checks`;
  - `starter_rules.declined`; init adopts the starter rules by default.
- `architect`:
  - `rules_doc`: default is the starter rules doc.
  - `every_n_tasks`.
  - `shape_from_task`: the adoption point.
  - `refactor_every`, `probes`, `checks`, `budgets`, `metrics`.
  - `areas`: default is the top-level directories.
  - `shape_only_dirs`, `private_dirs`.
- `prompts.worker_env`
- `reconcile`: `log`, `hooks`.
- `worktrees.links`
- `env`: `setup`, `teardown`, `up`, `down`, `urls`.
- `merge`: `command`, `behind_tip_ignore`.
- `auth_check.probes`
- `models`: D3; replaces `workers.implementer_model`.
- `suite`:
  - `lanes`: a gate lane is required, D5.
  - `count_re`: no language default.
  - `summary`: `failed_re`, `skipped_re`, `section_re` (no language default), `show_re`.
  - `affected_map`, `exclusive_lanes`.
- `adr`: `dir`, `index`, `template`, `strict`.
- `verify`: `accept_cache` (`max_age_days`, `cold_tasks`, `review`), `skip_review`,
  `skip_review_after_clean`, `provers`.
- `estimate.reference_since`
- `parallel`:
  - `max_in_flight`: default 3.
  - `schedule`: default `clashes`.
  - `exclusive`, `shared`.
- `mutate`: `command`, `unbuilt_re`.
- `report.required_fields`
- `notify`: `command`, `lead`.
- `upgrade`: `taken`, `declined`.
- `ids`: `task.width`, `adr.prefix`, `adr.width`, `spec.prefix`, `rule.pattern`,
  `review_point.pattern`.

**`plane.json`, removed as dead or duplicate:**
- `task_log.statuses`
- `task_log.review_point_pattern`
- `task_log.spec_paths`, `estimate.spec_paths`: merged into `spec_paths`.
- `workers.implementer_model` (`small`, `refactor`): replaced by `models`.
- `adapter.worktree_dir`, `adapter.worktree_links`, `adapter.post_close`
- `suite.summary.modules_ran_re`, `suite.summary.modules_cached_re`
- `telemetry.otel_port`

**`plane.json`, constants:**
- `task_log`:
  - `dir`: `docs/delivery`;
  - `required`, `refs_any`, `sections`, `kinds`: the canonical task format;
  - `reviews_dir`, `max_checks`, `soft_words`, `index`, `dry_run`.
- `package_docs`:
  - `doc_name`, `size_ratio`, `banned_headings`;
  - `path_ref_suffixes`: derived from the pack;
  - `no_delivery_ids`: always on.
- `docs.workers`: as many as there are checks.
- `architect`:
  - `rules_max_lines`, `max_days`, `notes_due`, `drift_ratio`, `grace_tasks`,
    `triage_grace_tasks`;
  - `shape_adrs`: on when ADRs are on;
  - `refactor_in_scope`, `call_timeout_minutes`, `max_new_tasks`.
- `prompts`:
  - `fragment`: `docs/delivery/WORKERS.md` when it exists;
  - `keep_body`: off;
  - `audit_keep_days`.
- `worktrees.dir`: `.plane-runtime`.
- `env.timeout_seconds`
- `auth_check.timeout_seconds`
- `telemetry.design_seat`: derived from the lead's model.
- The `telemetry` session knobs: `session_park_pct`, `session_wake_arm_pct`,
  `session_wake_margin_s`, `windows`.
- `parallel.session_ceiling_pct`
- `board.refresh_minutes`
- `gate`: `shell_limit_seconds`, `cut_line_seconds`.
- `health`: `small_task_lines`, `slowest_modules`, `suite_trend_runs`.
- `usage.advice`: `cache_5m_share`, `context_tokens`, `coordination_share`, `window_hours`.
- `workers.small_estimate_minutes`
- `suite.summary`:
  - `ran_re`, `cached_re`, `cached_tests_re`: the result file carries these;
  - `tail_lines`, `max_chars`.
- `suite.log_keep_days`
- `suite.roles`: the lane names are the roles.
- `adr`: `statuses`, `transitions`: the plane's ADR lifecycle.
- `review_points.file`
- `estimate`:
  - `auto`: on;
  - `k`, `path_suffixes`;
  - `calibration`: `half_life`, `min_pairs`, `k`. Code accepts these today, but the schema rejects
    them. That drift is what D1's schema test closes.
- `mutate.timeout_seconds`
- `notify.timeout_seconds`

**`plane.json`, moved to the machine:** `telemetry.allowance_cmd`, `telemetry.allowance_stop_weekly`
(D8).

**Binding, kept:** `project_id`, `integration_branch`, `product_root`, `queue_root`, `ci`, `notes`.

**Binding, removed:**
- `production_branch`
- `durable_docs_path`: a duplicate of `task_log.dir`.
- `display_name`, `adapter`, `adapter_config_path`, `hosting`, `grok`
- `runner`:
  - `agent_type`;
  - `name`: `runner`;
  - `worktree`: derived;
  - `rotate_after_tasks`, `rotate_at_context_tokens`, `idle_block_limit`: constants.
- `lead.auto_compact_window`: the product's own settings hold it.
- `spec_maintainer`: `kind`, `alias`, `protocol_doc`.
- `auth_check`: `script`, `includes_gcloud_adc`, `includes_adapter_doctor`,
  `includes_claude_oauth`.
- `seats`: `runner`, `verifier`, `watchdog`, `steerer`; the last read of these goes too.
- `cadence`: `watchdog`, `runner`, `verifier`, `verify_stale_minutes`.
- `email`: `alert_to`, `from`, `from_name`, `subject_prefix`.
- `verifier_access`: `mode`, `tailscale_magicdns_host`.
- `architecture_review.*`
