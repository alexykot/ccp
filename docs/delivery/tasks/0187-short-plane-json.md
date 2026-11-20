---
task_id: 0187-short-plane-json
title: plane.json keys that were removed warn, merged keys move, and a constant's non-default value applies with a warning; the upgrade status lists each
status: pending
kind: feature
depends_on: ["0172-fixtures-name-their-config", "0173-plane-json-block-registry", "0182-language-is-a-required-key"]
spec_refs: ["S3", "S7", "S8", "S12", "S14", "S22", "S26", "S29"]
review_point: R12
paths: ["ccp/config.py", "ccp/refs.py", "ccp/lifecycle.py", "ccp/backfill.py", "ccp/estimator.py", "ccp/upgrade.py", "ccp/cli.py", "contracts/plane_config.schema.json", "templates/docs-delivery/example-plane.json", "README.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/spec/04-observability.md", "tests/test_short_plane_json.py", "tests/test_allowance_windows.py", "tests/test_behind_tip_catch_up.py", "tests/test_board_plan.py", "tests/test_config_unknown_keys.py", "tests/test_estimate.py", "tests/test_refs.py", "tests/test_review_points.py", "tests/test_suite.py", "tests/test_tasklog_spec_signoff.py", "tests/test_tasks_close.py", "tests/test_team_hosting.py", "tests/test_toolkit.py", "tests/test_verify_spec_text.py", "tests/test_worker_efficiency.py", "tests/test_wt.py", "tests/test_wt_outside.py"]
clashes_with: ["0185-architect-on-by-default"]
adopt: "plane.json spec_paths (ccp upgrade status lists each removed, merged and constant key the product still sets, with its replacement)"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0187-short-plane-json

## Intent

Every plane.json key that is not the product's to decide gets one outcome, the one ADR-0043's appendix
gives it, and the plane tells the product which of its keys to delete or move: a removed key is ignored
with a warning, a merged key is read at its new place (and at its old one, with a warning, during the
grace), and a key that becomes a constant keeps a non-default value, with a warning, until the product
deletes it. This task builds that mechanism once, with the moved, merged and removed keys; 0192 marks
the constants and changes four defaults through it, and 0186 and 0188 reuse it.

## Context (not checked)

- ADR-0043 D9 (plane.json half; the constants are 0192, the binding 0188), accepted 2026-11-19. This
  task cites no `adr_refs`: D9 is marked built by 0191, which ends its grace.
- Depends on 0173 (the block registry: this task adds each key's outcome to it), 0182 (§29.3's grace
  rule, which this task applies) and 0172 (the fixtures).
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
  `spec_paths` loads with `unknown key(s) spec_paths ignored`; `gate.shell_limit_seconds: 99` loads
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
  - **The constant mechanism.** A registry entry (0173) may carry the outcome `constant` with its
    value. The loader then uses the value in code; a plane.json that sets the key to another value keeps
    that value, with one warning per key per load naming the key and the constant; one that sets it to
    the constant's value warns that the key can be deleted. Any reader (0186's account knobs, 0188's
    runner numbers in the binding) calls the same function, `config.constant_override`. This task marks
    no plane.json key constant; 0192 does, and the tests here register a test-only entry.
  - The schema marks every removed, merged and constant key `deprecated` with its outcome; the registry
    holds each key's outcome, and one loader applies it, so no outcome is written twice.
  - `ccp upgrade status` gains one step listing, for the product, each key it sets that is removed,
    merged (with its replacement) or a constant set to a value other than the constant.
- The SPEC passages that describe a constant as a setting (the §8 tables, the default parentheticals)
  are rewritten by the bulk text of 0189, signed once (operator ruling on shape F10, 2026-11-19); this
  task changes only the passages below.

## Scope

- **In:**
  - `ccp/config.py`: the outcomes, the warnings, `constant_override`; `ccp/refs.py`, `ccp/backfill.py`,
    `ccp/cli.py` (the review-point pattern), `ccp/lifecycle.py` (`post_close`), `ccp/estimator.py`
    (`spec_paths`).
  - `ccp/upgrade.py`: the step.
  - `contracts/plane_config.schema.json`, `templates/docs-delivery/example-plane.json`, `README.md`.
  - `tests/test_short_plane_json.py` (new); the modules that set a moved, merged or removed key move it
    (`git grep -l 'spec_paths\|review_point_pattern\|post_close\|worktree_dir\|worktree_links\|modules_ran_re\|modules_cached_re' -- tests`
    at `e9ff0fc`: 16 modules, listed in `paths`).
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
  - `docs/spec/03-quality.md` §22: CURRENT (at `e9ff0fc`): "A `task_log.review_point_pattern`
    key is then ignored, with a warning." PROPOSED:
    > A `task_log.review_point_pattern` key, merged into `ids.review_point.pattern` (§29.3), is then ignored, with a warning.
  - `docs/spec/03-quality.md` §22: CURRENT (at `e9ff0fc`): "a task's `review_point` is held to `task_log.review_point_pattern` (default
    `^R[0-9]+$`), with no strict error;" PROPOSED:
    > a task's `review_point` is held to `ids.review_point.pattern` (its old place, `task_log.review_point_pattern`, is read during the grace release, §29.3), with no strict error;
  - `docs/spec/04-observability.md` §26.2: CURRENT (at `e9ff0fc`): "(looked up in `estimate.spec_paths`,
    globs relative to the root)," PROPOSED:
    > (looked up in `spec_paths`, §3.5),
  - The two §13 and §16 mentions of `task_log.spec_paths` become `spec_paths` under §31.1, quoted in the PR body with any other sentence this makes false.
- **Out:**
  - The constants and the new defaults (0192). The binding's keys (0188). Ending the grace (0191). The
    SPEC's remaining default numbers (0189).

## dod_checks

- id: `cfg-01`
  story: As an operator, the SPEC paths are one top-level key.
  setup: a checkout of the PR head; a temp product whose plane.json is `{"project_id": "demo", "language": "none", "spec_paths": ["spec/"]}`.
  steps:
    1. Run `python3 -B -c "from ccp import config; c=config.load('<dir>'); print(config.spec_paths(c))"` and read its stderr.
  expect: prints `['spec/']`; stderr carries no `unknown key`.
  dry run (`e9ff0fc`): stderr `unknown key(s) spec_paths ignored` (and `config.spec_paths` does not exist).
- id: `cfg-02`
  story: As the lead of a product with history, every key I must delete or move is named, and a value I set for a constant still applies until I take the step.
  setup: a checkout of the PR head; then a separate copy where `config.constant_override` ignores the given value.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_short_plane_json`.
    2. In the copy, run the same.
  expect: step 1 exits 0, its tests covering: each removed key ignored with its warning; each merged key read at its old place with a warning naming the new one, and the new place winning when both are set; a test-registered constant set to another value applying with a warning, and set to its own value warning that it can be deleted; every key in the registry having exactly one outcome that matches the schema's `deprecated` marking; `ccp upgrade status` listing the product's keys with their replacement; step 2 exits non-zero.
  dry run: n/a — new module.
- id: `cfg-03`
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

- `config.KEY_OUTCOMES` holds each key's outcome (`removed`, `merged`, `constant`); `_apply_outcomes` is the one loader
  that applies it, before the blocks are validated, and `config.constant_override` is the one reader of a constant.
  A removed or merged key is no longer in a block's defaults (the schema lists it, `deprecated`, through
  `config.old_keys`); `adapter.post_close` is the one merged key kept in a default, because it is read in place.
- Rules the task left open, written narrowest: with both old `spec_paths` set and the new unset, `task_log.spec_paths`
  moves and `estimate.spec_paths` is ignored with a warning; `adapter.worktree_dir` and `adapter.worktree_links` set to a
  value other than their new place's stay an error, as §12.4's PROPOSED text says, while null or `[]` at either place is
  unset; with a review-point register, `task_log.review_point_pattern` is ignored (§22) and not moved, found by the
  register file's existence when plane.json loads; the review-point pattern without a register is `ids.review_point.pattern`
  alone, whose default `R[1-9][0-9]*` refuses `R0`, which the old default `^R[0-9]+$` accepted.
- `ccp upgrade status` appends one step, task `plane.json keys`, when the product sets a removed or merged key or a
  constant set to another value; it is no task's step, so `ccp upgrade decline|take` do not apply and the release notice
  leaves it out.
- Files outside the task's `paths` that had to change: `ccp/tasklog.py`, `ccp/health.py`, `ccp/taskmigrate.py`,
  `ccp/verify.py` (read `config.spec_paths(cfg)`; tasklog also holds the review point to `ids.review_point.pattern`),
  `ccp/reviewpoints.py` (the same, and its register warning moved to the loader), `ccp/suite.py` (the old
  `suite.summary` names are no longer read), `tests/test_plane_config_defaults.py`; prose only: the writing-tasks skill,
  `scripts/observability/team.py`, `docs/design/allowance.md`. `ccp/refs.py` needed no change. The `task_log` row of §8.1 also
  loses `spec_paths`, which is now the row after it. 14 test modules hold the old key names at this base, not 16.

## Verification notes
