---
task_id: 0192-plane-json-constants-and-defaults
title: Tuning keys in plane.json become constants, and four defaults change so a product works without setting them
status: pending
kind: feature
depends_on: ["0181-models-block-and-role-defaults", "0185-architect-on-by-default", "0187-short-plane-json"]
spec_refs: ["S8", "S15", "S19", "S24", "S26"]
review_point: R12
paths: ["ccp/config.py", "ccp/prompt.py", "ccp/usage.py", "ccp/board.py", "ccp/estimator.py", "ccp/tasklog.py", "ccp/upgrade.py", "contracts/plane_config.schema.json", "templates/docs-delivery/example-plane.json", "README.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/spec/04-observability.md", "tests/test_plane_json_constants.py", "tests/"]
adopt: "plane.json: delete each constant ccp upgrade status lists, or file a plane proposal to keep it"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0192-plane-json-constants-and-defaults

## Intent

A product's plane.json no longer offers tuning values a product would not change: each becomes a
constant in code, at today's default, and a product that set one to something else keeps it, with a
warning, until it deletes the key or the plane takes its proposal to keep it. Four defaults change:
estimates start by themselves, ADRs are shaped from the adoption point, the product's `WORKERS.md` is
the prompt fragment, and the lead's expected model follows `models.lead`.

## Context (not checked)

- ADR-0043 D9 (the constants and the new defaults), accepted 2026-11-19. This task cites no
  `adr_refs`: D9 is marked built by 0191.
- Depends on 0187 (the constant mechanism, `config.constant_override`, and the upgrade step listing
  constants: this task only marks keys), 0185 (the architect on by default and the adoption point, which
  `shape_adrs` now needs) and 0181 (`models.lead`, which the design seat follows).
- Measured at `e9ff0fc` (`python3 -B -c "…config.load(d)…"` on temp products): with `adr: {}`,
  `architect: {}` and a `docs/delivery/WORKERS.md`, `estimate.auto` is `False`, `prompts.fragment`
  `None`, `architect.shape_adrs` `False`, `telemetry.design_seat` `None`.
- Decided here:
  - **Constants** (each key's current default moved into code; a value other than it still applies,
    with one warning per key per load naming the key and the constant): `task_log` `dir`, `required`,
    `refs_any`, `sections`, `kinds`, `reviews_dir`, `max_checks`, `soft_words`, `index`, `dry_run`;
    `package_docs` `doc_name`, `size_ratio`, `banned_headings`, `path_ref_suffixes` (the pack's),
    `no_delivery_ids` (on); `docs.workers`; `architect` `rules_max_lines`, `max_days`, `notes_due`,
    `drift_ratio`, `grace_tasks`, `triage_grace_tasks`, `refactor_in_scope`, `call_timeout_minutes`,
    `max_new_tasks`; `prompts` `keep_body`, `audit_keep_days`; `worktrees.dir`; `env.timeout_seconds`;
    `auth_check.timeout_seconds`; `board.refresh_minutes`; `gate` `shell_limit_seconds`,
    `cut_line_seconds`; `health` `small_task_lines`, `slowest_modules`, `suite_trend_runs`;
    `usage.advice` `cache_5m_share`, `context_tokens`, `coordination_share`, `window_hours`;
    `workers.small_estimate_minutes`; `suite.summary` `ran_re`, `cached_re`, `cached_tests_re`,
    `tail_lines`, `max_chars`; `suite.log_keep_days`; `suite.roles`; `adr` `statuses`, `transitions`;
    `review_points.file`; `estimate` `k`, `path_suffixes`, `calibration`; `mutate.timeout_seconds`;
    `notify.timeout_seconds`.
  - **Kept as settings:** `adr.strict`, `verify.skip_review_after_clean` (default off), and every key not
    named above.
  - **New defaults:** `estimate.auto` on; `architect.shape_adrs` on whenever the product has an `adr`
    block (it applies from the adoption point, 0185); `prompts.fragment` `docs/delivery/WORKERS.md` when
    that file exists; `telemetry.design_seat` derived from `models.lead`: `config.design_seat(cfg)` returns `{model, effort}` from it and the role table (0178), and the board and `ccp usage` read that (the key becomes a constant).
  - **`shape_adrs` without an adoption point.** Today validation refuses `shape_adrs` on with no
    `shape_from_task` ("shape_adrs needs shape_from_task", in `ccp/config.py`). With the new default
    that would refuse every product with an `adr` block and no adoption point, so the validation is
    relaxed: an unadopted product (no `shape_from_task`) does not shape and loads normally; `ccp tasks
    check` runs the shaping check only from the adoption point (0185).
- Lead's ruling (question sm-20261120T123415Z-e65d, 2026-11-20, verbatim): "(a): worktrees.dir is a constant at
  `.plane-runtime`. ccp init stops writing the key. A plane.json that still sets `.plane-runtime` matches the constant,
  so it loads without a warning. Only a different value warns, through 0187's constant-override mechanism. Check that
  ccp wt and the .gitignore handling read the constant. Record this ruling in the task's Implementation notes."
  Reasoning: ADR-0043 D9 names worktrees.dir's new default as `.plane-runtime`; the task's "today's default (None)"
  is the error; the ADR governs.
- The test modules that set one of these keys follow the constants (`git grep -l` over the key names
  at `e9ff0fc`: 53 modules), so `paths` names `tests/` whole.
- The §8 tables' constants and the default parentheticals are rewritten by 0189; this task changes only
  the passages below.

## Scope

- **In:**
  - `ccp/config.py`: the registry marks the constants; the new defaults; the relaxed `shape_adrs`
    validation; `config.design_seat`. `ccp/prompt.py` (the fragment), `ccp/usage.py`, `ccp/board.py`
    (the design seat), `ccp/estimator.py` (`auto`), `ccp/tasklog.py` (shaping from the adoption point).
  - `ccp/upgrade.py`: the constants in 0187's step.
  - `contracts/plane_config.schema.json` (constants marked deprecated, new defaults),
    `templates/docs-delivery/example-plane.json`, `README.md`.
  - `tests/test_plane_json_constants.py` (new); test modules that set a constant.
  - `docs/spec/02-delivery.md` §15: CURRENT (at `e9ff0fc`): "2. **The product fragment**: the file plane.json `prompts.fragment` names," PROPOSED:
    > 2. **The product fragment**: `docs/delivery/WORKERS.md` when it exists, or the file plane.json `prompts.fragment` names,
  - `docs/spec/03-quality.md` §19.11, the row as 0185 leaves it: CURRENT: "| `shape_adrs`, `shape_from_task` | off, — | The shaping check (§19.6); `shape_from_task` is the adoption point |" PROPOSED:
    > | `shape_adrs`, `shape_from_task` | on with an `adr` block, — | The shaping check (§19.6); `shape_from_task` is the adoption point |
  - `docs/spec/04-observability.md` §24: CURRENT (at `e9ff0fc`): "The product's `plane.json` names the lead's expected values
    (`telemetry.design_seat`);" PROPOSED:
    > The lead's expected model is `models.lead` (§2.4);
  - `docs/spec/04-observability.md` §26.3: CURRENT (at `e9ff0fc`): "with **`estimate.auto`** on (default `false`)," PROPOSED:
    > with **`estimate.auto`** on (by default),
- **Out:**
  - The mechanism (0187). The SPEC's remaining default numbers (0189).

## dod_checks

- id: `con-01`
  story: As an operator, four defaults now work without my setting them.
  setup: a checkout of the PR head; a temp product with plane.json `{"project_id": "demo", "language": "none", "adr": {}, "models": {"lead": "opus"}}` (no `architect` block and no adoption point) and a `docs/delivery/WORKERS.md`.
  steps:
    1. Load it with `config.load` and print `estimate["auto"]`, `prompts["fragment"]`, `architect["shape_adrs"]` and `config.design_seat(c)["model"]`.
  expect: it loads with no error and prints `True`, `docs/delivery/WORKERS.md`, `True`, `opus`.
  dry run (`e9ff0fc`): `False`, `None`, `False`, `None` (with `architect: {}` added, as the seat needs a block today; `config.design_seat` does not exist).
- id: `con-02`
  story: As the lead of a product with history, a tuning value I set still applies, with a warning, and the upgrade status names it.
  setup: a checkout of the PR head; then a separate copy where the registry marks no key constant.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_plane_json_constants`.
    2. In the copy, run the same.
  expect: step 1 exits 0, its tests covering: every key in Context's constant list marked constant in the registry and `deprecated` in the schema; `gate.shell_limit_seconds: 99` applying with a warning naming the constant; `ccp upgrade status` listing it; `shape_adrs` defaulted on with an `adr` block and no `shape_from_task` loading without error; step 2 exits non-zero.
  dry run: n/a — new module.
- id: `con-03`
  story: As an operator, a tuning value I set no longer passes silently.
  setup: a checkout of the PR head; a temp product whose plane.json is `{"project_id": "demo", "language": "none", "gate": {"shell_limit_seconds": 99}}`.
  steps:
    1. Load it with `config.load` and read its stderr.
  expect: stderr carries one warning naming `gate.shell_limit_seconds` and its constant.
  dry run (`e9ff0fc`): loads with no warning.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0192-plane-json-constants-and-defaults --base origin/main`.
  expect: exits 0 with every passage found.
  dry run: n/a — the PROPOSED text is not in the SPEC before the build.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- The constants are registry entries (`config.KEY_OUTCOMES`, built from `config._CONSTANT_KEYS`) at the default the block's
  dict holds, so the loader (`_apply_outcomes`) and `ccp upgrade status` (0187's step, `ccp/upgrade.py` unchanged) handle
  them with no reader change; the blocks still hold the constants for the readers. `telemetry.design_seat` is a constant
  with no value (None): `config.design_seat(cfg)` is `models.lead` and the role table's effort (None for the lead), else a
  value the product still sets.
- `architect.shape_adrs` stays False in the block's defaults; `_architect` turns it on when the product has an `adr`
  block and gives none. The `shape_adrs needs shape_from_task` refusal is gone; the shaping check was already held to the
  adoption point by `tasklog._check_shaping`, so `ccp/tasklog.py` needed no change. `prompts.fragment` is derived in
  `_toolkit` (`config.WORKERS_FRAGMENT`); a fragment the product names wins.
- `worktrees.dir` is a constant at None, as the task says (today's default). `ccp init` writes `.plane-runtime` there and
  this plane's own plane.json sets it, so each warns until the constant is `.plane-runtime` (ADR-0043 D9 says so) or init
  stops writing it: raised to the runner as a scope question.
- Files outside `paths` that changed: `ccp/cli.py`, `ccp/estimate.py`, `ccp/forecast.py`, `ccp/seats.py`,
  `ccp/board_page.html` (the design seat now comes from `config.design_seat`), `docs/design/allowance.md`,
  `docs/design/board.md`; tests `test_init`, `test_board`, `test_suite` (a `without_constant_warnings` helper in
  `tests/helpers.py`: those fixtures set `worktrees.dir` and assert an empty stderr), `test_estimator`, `test_estimate`
  (`estimate.auto` default), `test_rules` (the removed refusal), `test_short_plane_json` (`worktrees.dir` is a constant too).
- Not changed, left as a proposal: `docs/spec/03-quality.md` §19.6 still says `shape_adrs` "needs `shape_from_task`".
- Fix round 1. Lead's ruling on `worktrees.dir` (Context, verbatim): the constant is `.plane-runtime`, not None. Built:
  `config.WORKTREES_DIR` is the one source (`ccp/init.py` takes it); `WORKTREES_DEFAULTS["dir"]` is it; `ccp init` writes
  no `worktrees` key; a plane.json that sets `.plane-runtime` loads with only the "delete it" note (the value equals the
  constant), a different value or null applies with the 0187 warning. `ccp wt`, `lifecycle` and `prompt` read
  `cfg.worktrees["dir"]` from the loaded block, so they follow the constant with no change; init's `.gitignore` line is the
  same constant. A product that named no dir now has plane-made worktrees under `.plane-runtime`: the tests that set none
  to mean "no worktrees" now set null (`test_tasks_close`, `test_behind_tip_catch_up`), and the fixtures that named
  `.rt` use the constant (`ToolkitFixture` names no dir). The `without_constant_warnings` helper is gone. The schema's
  `worktrees.dir` default and description follow; the shape_adrs schema note and the `ARCHITECT_DEFAULTS` comment say the
  value shown is the no-`adr` case. This plane's plane.json drops `task_log.dir`, `worktrees` and `review_points.file`
  (each equal to its constant); `package_docs.doc_name` (CLAUDE.md, not the constant `.claude.md`) and `docs.workers` (4,
  taken in `upgrade.taken`) stay, as removing them changes behaviour. The readers of the lead's expected model each have a
  test now (`TheLeadsExpectedModelReaders`), and the constants' old values are a literal table.
  `docs/spec/01-model.md` (the adoption passage) still says init writes "the worktrees directory" into plane.json: left to a proposal,
  with §19.6's "needs `shape_from_task`" (0189's sweep).

## Verification notes
