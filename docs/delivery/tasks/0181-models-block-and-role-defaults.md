---
task_id: 0181-models-block-and-role-defaults
title: Every role has a default model, the reviewer runs on Opus, and one models block overrides any role
status: pending
kind: feature
depends_on: ["0173-plane-json-block-registry", "0178-role-model-table"]
spec_refs: ["S2", "S4", "S8"]
adr_refs: ["0043 D3"]
review_point: R12
paths: ["ccp/models.py", "ccp/config.py", "ccp/prompt.py", "ccp/runs.py", "ccp/seats.py", "ccp/estimator.py", "ccp/init.py", "scripts/observability/architecture_review.py", "scripts/observability/team.py", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-runner.md", "contracts/plane_config.schema.json", "README.md", "docs/spec/01-model.md", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md", "tests/test_models_block.py", "tests/test_prompt_model.py", "tests/test_role_models.py"]
adopt: "plane.json models (it replaces workers.implementer_model: move its small and refactor aliases to models.implementer_small and models.implementer_refactor)"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0181-models-block-and-role-defaults

## Intent

Every role runs on a set model with no configuration: the lead on Opus (`ccp init` writes it into the
product's settings), the runner on Sonnet, the implementer on Opus with Sonnet for a small task or a
refactor, the reviewer on Opus, the verifier on Sonnet, the architect on Opus and the estimator on
Sonnet. A product overrides any role in one plane.json `models` block, which replaces
`workers.implementer_model`.

## Context (not checked)

- ADR-0043 D3, accepted 2026-11-19. Depends on 0178 (the role table in `ccp/models.py`, the one place
  full ids are written, and the test holding the definitions to it) and 0173 (the block registry: a
  new block is one registry entry).
- Today, at `e9ff0fc`: the reviewer's definition pins `claude-sonnet-5-5`
  (`grep -n '^model' plugin/agents/delivery-reviewer.md`); the implementer's per-task split is off
  unless `workers.implementer_model` is set (`config.WORKERS_DEFAULTS["implementer_model"]` is `None`);
  `ccp init` writes no `model` into a product's `.claude/settings.json` (the sandbox's settings at
  `e9ff0fc` hold the anchor, `subagentPromptCacheTtl` and `autoCompactWindow` only); no `models` key
  exists (an unknown key, warned and ignored).
- Decided here:
  - `models` is a plane.json block of optional keys `lead`, `runner`, `implementer`,
    `implementer_small`, `implementer_refactor`, `reviewer`, `verifier`, `architect`, `estimator`,
    each an alias from `config.WORKER_MODEL_ALIASES`; any other key or value is refused, naming it.
    The defaults are `models.ROLES` (0178), extended: `lead` `opus`, `implementer_small` `sonnet`,
    `implementer_refactor` `sonnet`, `reviewer` `opus`.
  - `implementer_small` applies to a task whose estimate is at most `workers.small_estimate_minutes`;
    `implementer_refactor` to a task of kind `refactor`; the refactor arm wins when both apply (as
    today). With no estimate, the small arm cannot apply and `ccp prompt implement` warns, as today.
    The fix, merge and ruling rounds take the implementer's model for the task.
  - The definitions keep full ids (§2.4); the reviewer's becomes `claude-opus-5-5`. A worker's Agent
    call carries `model` (an alias) only when the role's model for this task differs from its
    definition's family: `ccp prompt <phase>` prints it, and the runner passes it as given. The runner
    spawn (`team.sh runner spawn`) prints the runner's alias the same way. The architect and the
    estimator take `--model` from the role's alias through `models.FULL_IDS`.
  - The lead: `ccp init` adds `"model": "<models.lead>"` to `.claude/settings.json` when it has no
    `model`, and never overwrites one, as it does `autoCompactWindow`.
  - `workers.implementer_model` (`small`, `refactor`) still applies where `models` does not set the
    arm, with a warning naming the move to `models`; it is removed after the grace release (0191).
    The schema marks it deprecated.
  - The seat checks (`ccp board`, `seats.py`) expect the role's resolved model.
- The new SPEC text states the behaviour; the alias values are in code and the schema (E10, E12 as
  amended in this triage). The seat table names every role, the estimator and the lead included (D3).
- This task marks ADR-0043 D3 built in its own PR.

## Scope

- **In:**
  - `ccp/models.py`: the full role defaults; `model_for(cfg, role, task=None)` (the alias, the
    override first); `ccp/config.py`: the `models` block in the registry, validated; the
    `workers.implementer_model` fallback and warning. `contracts/plane_config.schema.json`: `models`
    with each key's default; `workers.implementer_model` described as deprecated.
  - `ccp/prompt.py`, `ccp/runs.py`, `ccp/seats.py`: a worker's alias from `model_for`; the
    expected model of a run and a seat.
  - `ccp/estimator.py`, `scripts/observability/architecture_review.py`: `--model` from `model_for`.
  - `scripts/observability/team.py`: the runner spawn's alias when `models.runner` differs.
  - `ccp/init.py`: the lead's `model` setting.
  - `plugin/agents/delivery-reviewer.md`: `model: claude-opus-5-5`. `plugin/agents/delivery-runner.md`:
    its brief says to pass the alias `ccp prompt` prints for any phase, not only implement.
  - `README.md`: a `models` row in the adoption checklist (when to override a role).
  - `tests/test_models_block.py` (new), and `tests/test_prompt_model.py`, `tests/test_role_models.py`
    where they name today's reviewer model or the implementer-only alias.
  - `docs/spec/01-model.md` §2.4: CURRENT (at `e9ff0fc`): "Each seat's model and effort is fixed in its agent definition (or launch flags) and never depends on
    the lead session's settings, except the implementer's model, which plane.json
    `workers.implementer_model` may set per task: `{"small": <alias>, "refactor": <alias>}`, an alias
    being one the Agent call's `model` accepts (`sonnet`, `opus`, `haiku`, `fable`), where `small` is a
    task whose estimate is at most `workers.small_estimate_minutes` (default 30) and `refactor` a task of
    that kind; unset (the default) leaves the definition's model. `ccp prompt implement` prints the alias
    in its Agent call, and the runner passes it as given; with the knob set and no estimate for the task,
    it warns that the `small` arm cannot apply:" PROPOSED:
    > Every role has a default model, set by the plane, and its effort is fixed in its agent definition (or launch flags); neither depends on the lead session's settings. A product may override any role's model in plane.json `models` (`lead`, `runner`, `implementer`, `implementer_small`, `implementer_refactor`, `reviewer`, `verifier`, `architect`, `estimator`), each an alias the Agent call's `model` accepts (`sonnet`, `opus`, `haiku`, `fable`). The implementer's model is chosen per task: `implementer_small` for a task whose estimate is at most `workers.small_estimate_minutes`, `implementer_refactor` for a task of that kind, else `implementer`; its fix, merge and ruling rounds take the same model. Without an estimate the small choice cannot apply, and `ccp prompt implement` warns. The defaults:
  - `docs/spec/01-model.md` §2.4, the seat table: CURRENT (at `e9ff0fc`): the rows "| Design seat (lead) | the operator's choice (the plane advises; it cannot set it) | the operator's choice |" and "| Reviewer | `claude-sonnet-5-5` | `high` |" and "| Implementer | `claude-opus-5-5` | `high` |". PROPOSED (the table becomes):
    > | Role | Model | Effort |
    > |---|---|---|
    > | Design seat (lead) | Opus: `ccp init` writes it into the product's `.claude/settings.json` when no `model` is set there, and never overwrites one | the operator's choice |
    > | Runner | Sonnet | `high` |
    > | Implementer (and its fix, merge and ruling rounds) | Opus; Sonnet for a small task or a refactor | `high` |
    > | Reviewer | Opus | `high` |
    > | Verifier | Sonnet | `high` |
    > | Architect | Opus | `high` (`--model`, `--effort`) |
    > | Estimator | Sonnet | `medium` (`--model`, `--effort`) |
  - `docs/spec/01-model.md` §2.4: CURRENT (at `e9ff0fc`): "`workers.implementer_model` alone takes aliases, because the Agent call's `model` accepts nothing
    else." PROPOSED:
    > `models` takes aliases, because the Agent call's `model` accepts nothing else; a definition's full id is its role's default model, which a test holds to the plane's role table.
  - `docs/spec/01-model.md` §2.4: CURRENT (at `e9ff0fc`): "The runner launches each worker by its agent type and **never passes `model`** in the Agent call,
    except the alias `ccp prompt implement` prints from `workers.implementer_model`: a call's `model`
    overrides the definition." PROPOSED:
    > The runner launches each worker by its agent type and passes `model` in the Agent call only when `ccp prompt` prints an alias for that round: when the role's model for the task (§2.4 `models`, or its default) is not the definition's. A call's `model` overrides the definition. The runner's own spawn carries an alias the same way.
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D3 marked built; `docs/adr/INDEX.md`.
- **Out:**
  - Removing `workers.implementer_model` (0191) and deriving `telemetry.design_seat` from the lead's
    model (0187).
  - Other § passages' default numbers (0189).

## dod_checks

- id: `mdl-01`
  story: As an operator of a new product, every role resolves to its default model with no configuration.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -c "import tempfile,json,pathlib; from ccp import config, models; d=pathlib.Path(tempfile.mkdtemp()); (d/'docs/delivery').mkdir(parents=True); (d/'docs/delivery/plane.json').write_text(json.dumps({'project_id':'demo'})); c=config.load(d); print([models.model_for(c, r) for r in ('lead','runner','implementer','implementer_small','implementer_refactor','reviewer','verifier','architect','estimator')])"`.
  expect: prints `['opus', 'sonnet', 'opus', 'sonnet', 'sonnet', 'opus', 'sonnet', 'opus', 'sonnet']`.
  dry run (`e9ff0fc`): raised `AttributeError: module 'ccp.models' has no attribute 'model_for'`.
- id: `mdl-02`
  story: As an operator, one block overrides a role, and a bad key or alias is refused.
  setup: a checkout of the PR head; fenced temp products whose plane.json sets `"models": {"reviewer": "sonnet"}`, then `"models": {"reviwer": "sonnet"}`, then `"models": {"reviewer": "claude-opus-5-5"}`.
  steps:
    1. Load each with `config.load` and read `models.model_for(cfg, "reviewer")`.
  expect: `sonnet` for the first, with no warning; the second and third are refused with an error naming `models.reviwer` and `models.reviewer` respectively.
  dry run (`e9ff0fc`): the first loads with `unknown key(s) models ignored` in its stderr warning, and `model_for` does not exist.
- id: `mdl-03`
  story: As a runner, the reviewer's definition is Opus, and a worker's Agent call carries an alias only when the task's model differs from the definition's.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n '^model' plugin/agents/delivery-reviewer.md`.
    2. Run `python3 -B -m unittest -q tests.test_models_block tests.test_prompt_model tests.test_role_models`.
  expect: step 1 prints `model: claude-opus-5-5`; step 2 exits 0, its tests covering a small task's implement prompt carrying `sonnet`, a default task's carrying none, and a product with `models.reviewer: sonnet` whose review prompt carries `sonnet`.
  dry run (`e9ff0fc`): step 1 printed `model: claude-sonnet-5-5`.
- id: `mdl-04`
  story: As an operator adopting a product, init sets the lead's model once and keeps mine.
  setup: a checkout of the PR head; `ccp sandbox create <dir>` (a fresh adopted product); then a second sandbox whose `.claude/settings.json` sets `"model": "sonnet"` before `ccp init --force` runs again.
  steps:
    1. Read the first sandbox's `.claude/settings.json` `model`.
    2. Read the second's after the rerun.
  expect: step 1 is `opus`; step 2 is still `sonnet`.
  dry run (`e9ff0fc`): a fresh sandbox's settings hold no `model` key (keys: `extraKnownMarketplaces`, `enabledPlugins`, `env`, `subagentPromptCacheTtl`, `autoCompactWindow`).
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed, and D3 is recorded as built.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0181-models-block-and-role-defaults --base origin/main`.
    2. Run `grep -n '"D3 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: step 1 exits 0 with every passage found; step 2's output contains `- "D3 built"`.
  dry run (`e9ff0fc`): step 2 printed `- "D3 not_built"`.
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
