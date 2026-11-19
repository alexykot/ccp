---
task_id: 0187-short-plane-json
title: plane.json keeps only what a product decides; removed keys warn, merged keys move, tuning values are constants, and the upgrade status lists each
status: pending
kind: feature
depends_on: ["0172-fixtures-name-their-config", "0173-plane-json-block-registry", "0181-models-block-and-role-defaults", "0182-language-is-a-required-key"]
spec_refs: ["S3", "S8", "S12", "S14", "S15", "S22", "S24", "S26", "S29"]
review_point: R12
paths: ["ccp/config.py", "ccp/refs.py", "ccp/lifecycle.py", "ccp/backfill.py", "ccp/estimator.py", "ccp/prompt.py", "ccp/usage.py", "ccp/board.py", "ccp/upgrade.py", "ccp/cli.py", "contracts/plane_config.schema.json", "templates/docs-delivery/example-plane.json", "README.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/spec/04-observability.md", "tests/test_short_plane_json.py", "tests/"]
clashes_with: ["0185-architect-on-by-default", "0186-account-facts-on-the-machine"]
adopt: "plane.json spec_paths (ccp upgrade status lists each removed, merged and constant key the product still sets, with its replacement)"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0187-short-plane-json

## Intent

A product's plane.json holds where things are, what only the product knows, and the choices it makes;
nothing else. Every other key has one outcome, the one ADR-0043's appendix gives it, and the plane
tells the product which of its keys to delete or move: a removed key is ignored with a warning, a
merged key is read at its new place (and at its old one, with a warning, during the grace), and a
tuning value becomes a constant whose non-default value still applies, with a warning, until the
product deletes it. Four defaults change: estimates start by themselves, ADRs are shaped, the
product's `WORKERS.md` is the prompt fragment, and the lead's expected model follows `models.lead`.

## Context (not checked)

- ADR-0043 D9 (plane.json half; the binding half is 0188), accepted 2026-11-19. This task cites no
  `adr_refs`: D9 is marked built by 0191, which ends its grace.
- Depends on 0173 (the block registry: this task adds each key's outcome to it), 0182 (§29.3's grace
  rule, which this task applies), 0181 (`models.lead`, which `telemetry.design_seat` now follows) and
  0172 (the fixtures).
- The shape's F05 is right that four keys the appendix calls dead are read today; this task classes
  them as merged:
  - `adapter.post_close` runs at close (`"The legacy adapter.post_close commands"` in
    `ccp/lifecycle.py`); it merges into `reconcile.hooks`.
  - `adapter.worktree_dir`, `adapter.worktree_links` are read as `worktrees.dir`, `worktrees.links`.
  - `task_log.review_point_pattern` is read with its own default, `^R[0-9]+$`, against
    `ids.review_point.pattern`'s `R[1-9][0-9]*` (probe at `e9ff0fc`: a plane.json setting
    `task_log.review_point_pattern` `^Q[0-9]+$` loads it as given while `cfg.ids.review_point_pattern`
    stays `R[1-9][0-9]*`). It merges into `ids.review_point.pattern`.
- Measured at `e9ff0fc` (`python3 -B -c "…config.load(d)…"` on temp products): a top-level
  `spec_paths` loads with `unknown key(s) spec_paths ignored`; with `adr: {}`, `architect: {}` and a
  `docs/delivery/WORKERS.md`, `estimate.auto` is `False`, `prompts.fragment` `None`,
  `architect.shape_adrs` `False`, `telemetry.design_seat` `None` (no `config.design_seat` exists); `gate.shell_limit_seconds: 99` loads
  with no warning.
- Decided here, key by key (ADR-0043's appendix, with F05's correction):
  - **Moved:** `spec_paths` becomes one top-level key, merging `task_log.spec_paths` and
    `estimate.spec_paths` (default the task log's `["docs/SPEC.md", "SPEC.md", "docs/spec/", "spec/"]`;
    the estimator reads directories as their `*.md`).
  - **Merged** (old place read when the new one is unset, with a warning naming the new one):
    `task_log.spec_paths`, `estimate.spec_paths` → `spec_paths`; `adapter.worktree_dir`,
    `adapter.worktree_links` → `worktrees.dir`, `worktrees.links`; `adapter.post_close` → still run at
    close, with a warning that it moves to `reconcile.hooks` (`$TASK_ID` for `{task_id}`);
    `task_log.review_point_pattern` → `ids.review_point.pattern`.
  - **Removed** (ignored, with a warning): `task_log.statuses`, `suite.summary.modules_ran_re`,
    `suite.summary.modules_cached_re`. (`telemetry.otel_port` goes with 0184, `workers.implementer_model`
    with 0181, the account keys with 0186.)
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
  - The schema marks every removed, merged and constant key `deprecated` with its outcome; the registry
    (0173) holds each key's outcome, and one loader applies it, so no outcome is written twice.
  - `ccp upgrade status` gains one step listing, for the product, each key it sets that is removed,
    merged (with its replacement) or a constant set to a value other than the constant.
- The SPEC passages that describe a constant as a setting (the §8 tables, the default parentheticals)
  are rewritten by the bulk text of 0189, signed once (operator ruling on shape F10, 2026-11-19); this
  task changes only the passages below.

## Scope

- **In:**
  - `ccp/config.py`: the outcomes, the warnings, the new defaults; `ccp/refs.py`, `ccp/backfill.py`,
    `ccp/cli.py` (the review-point pattern), `ccp/lifecycle.py` (`post_close`), `ccp/estimator.py`
    (`spec_paths`), `ccp/prompt.py` (the fragment), `ccp/usage.py`, `ccp/board.py` (the design seat).
  - `ccp/upgrade.py`: the step.
  - `contracts/plane_config.schema.json`, `templates/docs-delivery/example-plane.json`, `README.md`.
  - `tests/test_short_plane_json.py` (new); tests that set a removed or merged key move it.
  - `docs/spec/01-model.md` §3.5: CURRENT (at `e9ff0fc`): "(plane.json `task_log.spec_paths`, default `["docs/SPEC.md", "SPEC.md", "docs/spec/", "spec/"]`, the files `estimate.spec_paths` names by default;" PROPOSED:
    > (plane.json `spec_paths`, default `["docs/SPEC.md", "SPEC.md", "docs/spec/", "spec/"]`;
  - `docs/spec/01-model.md` §8.1, the `task_log` row: CURRENT (at `e9ff0fc`): "| `task_log` | task directory, required keys and sections, `refs_any`, `kinds`, `max_checks`, soft words, `dry_run`, `spec_paths`, `reviews_dir`, `index`; the statuses are fixed | §5, §10 |" PROPOSED:
    > | `spec_paths` | the SPEC files, read by the sign-off checks and the estimator | §3.5, §26 |
  - `docs/spec/01-model.md` §8.1, after "The schema gains a required key, or drops or moves one, only as §29.3 allows." (0182's PROPOSED): CURRENT: none (a new bullet). PROPOSED:
    > - A key that is not the product's to decide is a constant in code. The schema keeps a key that was removed, merged or made constant, marked deprecated with its outcome, and `ccp upgrade status` lists each one a product still sets (§29.3).
  - `docs/spec/01-model.md` §7: CURRENT (at `e9ff0fc`): "`task_log.review_point_pattern` keeps its meaning for a product without
    a register (§22)." PROPOSED:
    > Without a register, a task's review point is held to `ids.review_point.pattern` (§22).
  - `docs/spec/02-delivery.md` §12.4: CURRENT (at `e9ff0fc`): "`adapter.worktree_dir` and `adapter.worktree_links` read as `worktrees.dir` and `worktrees.links`
    (setting both is an error). `adapter.post_close` commands (`{task_id}`, `{nnnn}`, run in the main
    checkout) still run once at close, before the worktrees are removed." PROPOSED:
    > `adapter.worktree_dir`, `adapter.worktree_links` and `adapter.post_close` are merged keys (§29.3): the first two read as `worktrees.dir` and `worktrees.links` (setting both is an error); `adapter.post_close` commands (`{task_id}`, `{nnnn}`, run in the main checkout) still run once at close, before the worktrees are removed, with a warning that they move to `reconcile.hooks`. After the grace release none is read.
  - `docs/spec/02-delivery.md` §14.4: CURRENT (at `e9ff0fc`): "Their older names `modules_ran_re` and `modules_cached_re`
    are read; given both, the new name wins and `ccp tasks check` warns." PROPOSED:
    > Their older names `modules_ran_re` and `modules_cached_re` are removed keys (§29.3).
  - `docs/spec/02-delivery.md` §15: CURRENT (at `e9ff0fc`): "2. **The product fragment**: the file plane.json `prompts.fragment` names," PROPOSED:
    > 2. **The product fragment**: `docs/delivery/WORKERS.md` when it exists, or the file plane.json `prompts.fragment` names,
  - `docs/spec/03-quality.md` §22: CURRENT (at `e9ff0fc`): "A `task_log.review_point_pattern`
    key is then ignored, with a warning." PROPOSED:
    > A `task_log.review_point_pattern` key, merged into `ids.review_point.pattern` (§29.3), is then ignored, with a warning.
  - `docs/spec/03-quality.md` §22: CURRENT (at `e9ff0fc`): "a task's `review_point` is held to `task_log.review_point_pattern` (default
    `^R[0-9]+$`), with no strict error;" PROPOSED:
    > a task's `review_point` is held to `ids.review_point.pattern` (its old place, `task_log.review_point_pattern`, is read during the grace release, §29.3), with no strict error;
  - `docs/spec/03-quality.md` §19.11, the row as 0185 leaves it: CURRENT: "| `shape_adrs`, `shape_from_task` | off, — | The shaping check (§19.6); `shape_from_task` is the adoption point |" PROPOSED:
    > | `shape_adrs`, `shape_from_task` | on with an `adr` block, — | The shaping check (§19.6); `shape_from_task` is the adoption point |
  - `docs/spec/04-observability.md` §24: CURRENT (at `e9ff0fc`): "The product's `plane.json` names the lead's expected values
    (`telemetry.design_seat`);" PROPOSED:
    > The lead's expected model is `models.lead` (§2.4);
  - `docs/spec/04-observability.md` §26.2: CURRENT (at `e9ff0fc`): "(looked up in `estimate.spec_paths`,
    globs relative to the root)," PROPOSED:
    > (looked up in `spec_paths`, §3.5),
  - `docs/spec/04-observability.md` §26.3: CURRENT (at `e9ff0fc`): "with **`estimate.auto`** on (default `false`)," PROPOSED:
    > with **`estimate.auto`** on (by default),
  - The two §13 and §16 mentions of `task_log.spec_paths` become `spec_paths` under §31.1, quoted in the PR body with any other sentence this makes false.
- **Out:**
  - The binding's keys (0188). Ending the grace (0191). The SPEC's remaining default numbers (0189).

## dod_checks

- id: `cfg-01`
  story: As an operator, the SPEC paths are one top-level key.
  setup: a checkout of the PR head; a temp product whose plane.json is `{"project_id": "demo", "language": "none", "spec_paths": ["spec/"]}`.
  steps:
    1. Run `python3 -B -c "from ccp import config; c=config.load('<dir>'); print(config.spec_paths(c))"` and read its stderr.
  expect: prints `['spec/']`; stderr carries no `unknown key`.
  dry run (`e9ff0fc`): stderr `unknown key(s) spec_paths ignored` (and `config.spec_paths` does not exist).
- id: `cfg-02`
  story: As an operator, four defaults now work without my setting them.
  setup: a checkout of the PR head; a temp product with plane.json `{"project_id": "demo", "language": "none", "adr": {}, "models": {"lead": "opus"}}` and a `docs/delivery/WORKERS.md`.
  steps:
    1. Load it with `config.load` and print `estimate["auto"]`, `prompts["fragment"]`, `architect["shape_adrs"]` and `config.design_seat(c)["model"]`.
  expect: `True`, `docs/delivery/WORKERS.md`, `True`, `opus`.
  dry run (`e9ff0fc`): `False`, `None`, `False`, `None` (with `architect: {}` given, as the seat needs a block today).
- id: `cfg-03`
  story: As the lead of a product with history, every key I must delete or move is named, and a tuning value I set still applies until I take the step.
  setup: a checkout of the PR head; then a separate copy where the loader ignores a constant's given value.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_short_plane_json`.
    2. In the copy, run the same.
  expect: step 1 exits 0, its tests covering: each removed key ignored with its warning; each merged key read at its old place with a warning naming the new one, and the new place winning when both are set; `gate.shell_limit_seconds: 99` applying with a warning; every key in the registry having exactly one outcome that matches the schema's `deprecated` marking; `ccp upgrade status` listing the product's keys with their replacement; step 2 exits non-zero.
  dry run: n/a — new module.
- id: `cfg-04`
  story: As an operator, a review-point pattern has one default.
  setup: a checkout of the PR head; a temp product with no review-point register whose plane.json is `{"project_id": "demo", "language": "none", "task_log": {"review_point_pattern": "^Q[0-9]+$"}}`.
  steps:
    1. Load it and print `cfg.ids.review_point_pattern`, and its stderr.
  expect: prints `^Q[0-9]+$` and a warning naming `ids.review_point.pattern`.
  dry run (`e9ff0fc`): prints `R[1-9][0-9]*`, no warning.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0187-short-plane-json --base origin/main`.
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

## Verification notes
