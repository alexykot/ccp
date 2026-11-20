---
task_id: 0188-short-binding
title: The binding holds only where the product and its queue are, its integration branch, its CI and notes
status: done
kind: feature
depends_on: ["0175-one-binding-reader", "0182-language-is-a-required-key", "0184-init-turns-telemetry-on", "0187-short-plane-json"]
spec_refs: ["S4", "S8", "S9", "S10", "S29"]
review_point: R12
paths: ["ccp/init.py", "ccp/lifecycle.py", "ccp/usage.py", "ccp/seats.py", "ccp/prompt.py", "ccp/plane.py", "ccp/runs.py", "ccp/config.py", "ccp/upgrade.py", "scripts/observability/", "plugin/hooks/runner-idle.sh", "plugin/agents/delivery-runner.md", "contracts/project.schema.json", "templates/", "README.md", "docs/spec/01-model.md", "tests/test_short_binding.py", "tests/test_architect.py", "tests/test_board_drill.py", "tests/test_init.py", "tests/test_init_session_settings.py", "tests/test_parallel_claims.py", "tests/test_parallel_hook.py", "tests/test_plugin.py", "tests/test_prompt_rounds.py", "tests/test_review_aliases_retired.py", "tests/test_rotation.py", "tests/test_rotation_refill.py", "tests/test_run_abandon.py", "tests/test_run_checkout_upgrade.py", "tests/test_runner_idle_rotation.py", "tests/test_suite.py", "tests/test_tasklog.py", "tests/test_tasklog_adopt.py", "tests/test_team_hosting.py", "tests/test_toolkit.py", "tests/test_upgrade.py", "tests/test_usage.py", "tests/test_usage_advice.py", "tests/test_usage_by_model.py", "tests/test_verify.py"]
adopt: "binding: delete the keys ccp upgrade status lists (production_branch, durable_docs_path, display_name, adapter, adapter_config_path, hosting, grok, runner, lead, spec_maintainer, auth_check, seats, cadence, email, verifier_access, architecture_review)"
sign_off: brief
created: 2026-11-19
updated: 2026-11-20
---

# Task: 0188-short-binding

## Intent

A product's binding says where the product and its queue are, its integration branch, and its CI and
notes; nothing else. Everything the plane derived or tuned from the binding is now derived or a
constant: the runner's agent, name and worktree, its rotation numbers, the task-log directory and the
lead's compaction window (the product's own settings hold that one). `ccp init` writes the short
binding, and a binding that still holds a removed key is told which to delete.

## Context (not checked)

- ADR-0043 D9 (binding half; the plane.json half is 0187), accepted 2026-11-19. This task cites no
  `adr_refs`: D9 is marked built by 0191, which ends its grace.
- Depends on 0175: every binding read goes through `lib.read_binding` and `lib.product_binding`, so
  each removed key is dropped in one place, and the derived values have one home. Depends on 0182 for
  §29.3's grace rule, 0184 (its §4.5 PROPOSED is this task's CURRENT, and both edit init's settings
  writer) and 0187 (the constant mechanism, `config.constant_override`, which the runner constants
  here reuse; this task builds none of its own).
- Today, at `e9ff0fc`: `ccp sandbox create` writes a binding with `project_id`, `integration_branch`,
  `production_branch`, `product_root`, `durable_docs_path`, `queue_root` and a `runner` block
  (`agent_type`, `name`, `worktree`) (dry run below); `contracts/project.schema.json` `required` is
  `['project_id', 'integration_branch', 'queue_root', 'durable_docs_path']`
  (`python3 -c "…json.load(open('contracts/project.schema.json'))['required']…"` at `e9ff0fc`).
- Decided here (ADR-0043's appendix, "Binding"):
  - **Kept:** `project_id`, `integration_branch`, `product_root`, `queue_root`, `ci`, `notes`.
  - **Derived:** `runner.agent_type` `ccp:delivery-runner`; `runner.name` `runner`; `runner.worktree`
    `<product_root>`/`<worktrees.dir>`/`runner`; the task-log directory `docs/delivery` (`durable_docs_path`
    duplicated it).
  - **Constants**, at today's defaults: `runner.rotate_after_tasks` 4,
    `runner.rotate_at_context_tokens` off, `runner.idle_block_limit` 3.
  - **Moved:** `lead.auto_compact_window`: `ccp init` writes `autoCompactWindow` 350000 into the
    product's `.claude/settings.json` when absent; a binding value is used for that write during the
    grace, with a warning.
  - **Removed:** `production_branch`, `durable_docs_path`, `display_name`, `adapter`,
    `adapter_config_path`, `hosting`, `grok`, `spec_maintainer`, `auth_check` (`script`,
    `includes_*`), `seats`, `cadence`, `email`, `verifier_access`, `architecture_review`. The last
    readers of `seats.*` go.
  - A binding that sets a removed key loads with one warning per key naming it; one that sets a
    runner constant to another value keeps that value, with a warning (§29.3). `ccp init` on a kept
    binding lists them as obsolete, as it does today for ignored keys.
  - The schema's `required` becomes `project_id`, `integration_branch`, `queue_root`, `product_root`;
    removed keys are marked deprecated, not dropped, so an old binding still validates.
  - `ccp upgrade status` gains one step listing the removed and constant keys the binding sets.
- Plugin text that names a removed binding key (`plugin/agents/delivery-runner.md` names the rotation
  keys) is corrected in this task.

## Scope

- **In:**
  - `scripts/observability/lib.py` (the one binding reader, 0175): the derived values and the warnings in the one
    reader; the readers of removed keys in `ccp/` and `scripts/observability/` (named by
    `git grep -l` for each key at the base) read the derived value or the constant.
  - `ccp/init.py`: the short binding; `autoCompactWindow` without the binding.
  - `plugin/hooks/runner-idle.sh`, `plugin/agents/delivery-runner.md`: the constants.
  - `ccp/upgrade.py`: the step. `contracts/project.schema.json`; the binding templates under
    `templates/`; `README.md`.
  - `tests/test_short_binding.py` (new); the modules that build bindings with a removed key drop it
    (`git grep -lwP` over the removed key names in `tests` at `e9ff0fc`: 24 modules, listed in `paths`).
  - `docs/spec/01-model.md` §8.3: CURRENT (at `e9ff0fc`): "Contract: `contracts/project.schema.json`; required: `project_id`,
    `integration_branch`, `queue_root`, `durable_docs_path`." PROPOSED:
    > Contract: `contracts/project.schema.json`; required: `project_id`, `integration_branch`, `queue_root`, `product_root`. Optional: `ci` and `notes`. Nothing else is read: the runner's agent (`ccp:delivery-runner`), name (`runner`) and worktree (`<product_root>/<worktrees.dir>/runner`, the prefix with several runners, §16) are derived, and its rotation (after 4 tasks, §10.2) and idle limit are constants.
  - `docs/spec/01-model.md` §8.3, the example: CURRENT (at `e9ff0fc`): the fenced block from "project_id: example-product" to "auto_compact_window: 350000            # autoCompactWindow ccp init writes (§4.5)". PROPOSED:
    > ```yaml
    > project_id: example-product
    > integration_branch: main
    > product_root: /path/to/example-product          # the product's main checkout
    > queue_root: /path/to/.delivery-queue/example-product
    > ```
  - `docs/spec/01-model.md` §8.3: CURRENT (at `e9ff0fc`): "naming each missing key (the schema's required keys, `product_root`, a `runner` block with
    `agent_type` and `name`) and each obsolete one (the ignored keys below, a key the schema marks ignored
    or retired, a key it does not list)." PROPOSED:
    > naming each missing key (the schema's required keys) and each obsolete one (a key the schema marks deprecated, a key it does not list).
  - `docs/spec/01-model.md` §8.3: CURRENT (at `e9ff0fc`): "- A `spec_maintainer` block is accepted, deprecated: the lead is every project's spec maintainer
  (§17). `seats.runner`, `seats.verifier`, `seats.watchdog` and `email` are
  ignored, as is a leftover `hosting:` line; the operator's channel is plane.json `notify` (§3.6). `cadence.verify_stale_minutes` is retired with the
  `verify_stale` blocker (§18.3)." PROPOSED:
    > - A binding key not listed above is a removed key (§29.3): it loads with a warning naming it and is otherwise ignored. The lead is every project's spec maintainer (§17), and the operator's channel is plane.json `notify` (§3.6).
  - `docs/spec/01-model.md` §4.5, the settings item as 0184 leaves it: CURRENT: "`autoCompactWindow` (the binding's `lead.auto_compact_window`, default `350000`)," PROPOSED:
    > `autoCompactWindow` (`350000`),
  - Any other SPEC sentence naming a removed binding key (`runner.agent_type` in §9.1, `runner.worktree` in §16, `rotate_after_tasks` in §10.2) is corrected under §31.1 and quoted in the PR body.
- **Out:**
  - plane.json keys (0187). Ending the grace (0191).

## dod_checks

- id: `bnd-01`
  story: As an operator adopting a product, init writes the short binding.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp sandbox create <dir>` and read `<dir>/bindings/product.yaml`.
  expect: its keys are exactly `project_id`, `integration_branch`, `product_root`, `queue_root`.
  dry run (`e9ff0fc`): 7 top-level keys: also `production_branch`, `durable_docs_path`, `runner` (`agent_type`, `name`, `worktree`).
- id: `bnd-02`
  story: As an operator with an old binding, everything still works, and I am told what to delete.
  setup: a checkout of the PR head; then a separate copy where the reader ignores a binding's `runner.rotate_after_tasks`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_short_binding`.
    2. In the copy, run the same.
  expect: step 1 exits 0, its tests covering: a binding as `e9ff0fc`'s init wrote it loading with one warning per removed key and the same derived runner name, agent and worktree; `runner.rotate_after_tasks: 2` applying with a warning; a binding with no `durable_docs_path` validating against the schema; `ccp upgrade status` listing the keys to delete; step 2 exits non-zero.
  dry run: n/a — new module.
- id: `bnd-03`
  story: As a plane developer, no code reads a removed binding key.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nwP 'production_branch|durable_docs_path|adapter_config_path|verifier_access|alert_to|idle_block_limit|rotate_after_tasks' -- ccp scripts plugin ':!ccp/upgrade.py' ':!scripts/observability/lib.py'`.
  expect: prints nothing.
  dry run (`e9ff0fc`): prints lines in `ccp/init.py`, `ccp/lifecycle.py`, `plugin/hooks/runner-idle.sh`, `plugin/agents/delivery-runner.md`, `scripts/observability/team.py`.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0188-short-binding --base origin/main`.
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

- The one reader (`scripts/observability/lib.py`) now holds the whole mechanism: `binding_findings` (per
  dotted leaf key: `removed`, `constant`, `moved`), `warn_binding` (one warning per key, once per process,
  through `config._warn_once`), `binding_constants` (a binding registry of its own, because
  `config.KEY_OUTCOMES` is plane.json's and `test_short_plane_json` iterates it against that schema;
  `config.constant_override` got a `registry` parameter to take it), `runner_limits`, `runner_worktree`
  (`<product_root>/<worktrees.dir>/runner`, read from the raw plane.json: `worktrees.dir`, else the old
  `adapter.worktree_dir`, else `.plane-runtime`) and the constants `RUNNER_AGENT`, `RUNNER_NAME`,
  `TASK_LOG_DIR`. `binding_runner_name` and `project_seat_agent` are gone.
- `ccp init` writes the four keys, writes `autoCompactWindow` 350000 (a binding's value is used for that
  write, with a warning, during the grace), and reports one "carries" warning per removed key of a kept binding.
- The idle hook takes its limit from a new `idle_limit` field of `ccp where` (a managed copy of the hook
  uses 3). The rotation-due JSON keys became `after_tasks` and `at_context_tokens` and the messages were
  reworded, so the removed key names occur only in `lib.py` and `upgrade.py`.
- `ccp upgrade status` has the step `binding keys` (`upgrade.BINDING_STEP`), listing each removed, constant
  and moved key with what to do.
- The schema's `required` is `project_id`, `integration_branch`, `queue_root`, `product_root`; every removed key
  stays in `properties`, marked `deprecated`.
- Decisions and flags:
  - `auth_check.script` is no longer read (`ccp plane check` no longer sanctions that script, and the queue
    leftover check no longer exempts it); `auth_check.probes` in plane.json is untouched.
  - `scripts/observability/sync-product-docs.sh` still reads the `spec_maintainer` block; it is outside this
    task's scope and untouched.
  - Every spawn now makes the derived runner worktree from `origin/<integration_branch>`, so spawn fixtures
    (`TeamCase`) got a git origin; the dry-run test that relied on a binding with no `runner.worktree` was
    deleted (there is no such binding any more).
  - The task's Context counts 24 test modules with a removed key; at the base `git grep -lwP` found more
    (the modules that build a binding, plus the ones asserting the removed names in messages). All that the
    change broke are updated in this PR.
  - SPEC: the exact text of the task is in; the example block's comment alignment is narrowed to one that
    shows the block as an added line, so `ccp verify spec-text` finds it (the diff had only unchanged lines
    there). §31.1 corrections to the other sentences naming a removed key are in `01-model.md` (§2.6, §9.1,
    §9.2), `02-delivery.md` (§10.2, §12.1, §16.4, §18.2 and the dry-run sentence), `04-observability.md`
    (§24) and `05-operations.md`; each is quoted in the PR body.
- Fix round 1 (review at `720db5f`): SPEC §3.4 now names only `integration_branch`, and §17's sentence says a
  `spec_maintainer` block is a removed key and not read (§31.1). `scripts/sync-product-docs.sh` no longer reads the
  binding's `spec_maintainer` block: the managed `docs/delivery/SPEC-MAINTAINER.md` is kept current where the
  product already has that file (the lead is every project's maintainer, so the binding decides nothing), and the
  `claude-session` note is gone. Help text and docstrings that named `runner.worktree`, `runner.name` or the
  binding's `runner` block say the derived value. `contracts/project.schema.json` is written back unescaped
  (`§` not `\u00a7`). The `warn_binding` call in `ccp init` is dropped: a kept binding's keys reach the caller
  through the result's `warnings`, which init also prints on stderr.

## Verification notes
- 2026-11-20 — verifier, PR #217 head `94967ce` (squash `d95f0cb`): APPROVE. Passed: bnd-01, bnd-02, bnd-03, spec-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0188-short-binding.json.

