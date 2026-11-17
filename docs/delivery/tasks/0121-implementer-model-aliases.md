---
task_id: 0121-implementer-model-aliases
title: The implementer-model knob takes the aliases the Agent call accepts, and warns when a task has no estimate
status: pending
kind: feature
depends_on: []
spec_refs: ["S2"]
review_point: R8
sign_off: brief
paths: ["ccp/prompt.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/delivery/plane.json", "docs/spec/01-model.md", "tests/test_prompt*.py", "tests/test_config*.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0121-implementer-model-aliases
## Intent

The implementer-model trial can run: the model `ccp prompt implement` prints is one the Agent call
accepts, the SPEC no longer says both "passes the printed model" and "never passes `model`", and a
runner learns when the `small` arm cannot apply because the task has no estimate.

## Context (not checked)

- The Agent tool's `model` parameter takes only the aliases `sonnet`, `opus`, `haiku` and `fable`,
  not full model ids (its schema in a lead session, 2026-11-17). The plane's own plane.json sets
  `workers.implementer_model` to a full id (`python3 -c "import json;print(json.load(open('docs/delivery/plane.json'))['workers'])"` at `b4de6ad`), so the first trial call would fail or land off-pin.
- The `small` arm reads an estimate row; the plane's queue holds only `actual` rows until
  `ccp tasks estimate --all --baseline` runs (an operator step before the trial, not this task).
- The signed §2.4 paragraph of the task that added the knob says the runner passes the printed model;
  the bullet below it still says the runner never passes `model`.

## Scope

- **In:**
  - `ccp/config.py`, `contracts/plane_config.schema.json`: `workers.implementer_model` values are
    `sonnet`, `opus`, `haiku` or `fable`; any other value is refused (exit 2), naming the accepted ones.
  - `ccp/prompt.py`: `ccp prompt implement` prints the alias; with the knob set, a `small` arm, and no
    estimate row for the task, it warns on stderr that the `small` arm cannot apply.
  - `docs/delivery/plane.json`: `workers.implementer_model` `{"small": "sonnet", "refactor": "sonnet"}`.
  - `docs/spec/01-model.md` §2.4, the opening paragraph. CURRENT (at `b4de6ad`): "Each seat's model and effort is fixed in its agent definition (or launch flags) and never depends on the lead session's settings, except the implementer's model, which plane.json `workers.implementer_model` may set per task: `{"small": <model>, "refactor": <model>}`, where `small` is a task whose estimate is at most `workers.small_estimate_minutes` (default 30) and `refactor` a task of that kind; unset (the default) leaves the definition's model. `ccp prompt implement` prints the model in its Agent call, and the runner passes it as given:" PROPOSED:
    > Each seat's model and effort is fixed in its agent definition (or launch flags) and never depends on the lead session's settings, except the implementer's model, which plane.json `workers.implementer_model` may set per task: `{"small": <alias>, "refactor": <alias>}`, an alias being one the Agent call's `model` accepts (`sonnet`, `opus`, `haiku`, `fable`), where `small` is a task whose estimate is at most `workers.small_estimate_minutes` (default 30) and `refactor` a task of that kind; unset (the default) leaves the definition's model. `ccp prompt implement` prints the alias in its Agent call, and the runner passes it as given; with the knob set and no estimate for the task, it warns that the `small` arm cannot apply:
  - `docs/spec/01-model.md` §2.4, the bullet on full ids. CURRENT (at `b4de6ad`): "Models are **full ids**, never aliases: with an alias (`opus`, `sonnet`) or `inherit`, a subagent of the lead's model family runs on the lead's exact model, including its `[1m]` suffix. Moving to a newer model is a deliberate change of the definitions." PROPOSED:
    > Models in agent definitions are **full ids**, never aliases: with an alias (`opus`, `sonnet`) or `inherit`, a subagent of the lead's model family runs on the lead's exact model, including its `[1m]` suffix. Moving to a newer model is a deliberate change of the definitions. `workers.implementer_model` alone takes aliases, because the Agent call's `model` accepts nothing else.
  - `docs/spec/01-model.md` §2.4, the bullet on `model`. CURRENT (at `b4de6ad`): "The runner launches each worker by its agent type and **never passes `model`** in the Agent call: a call's `model` overrides the definition." PROPOSED:
    > The runner launches each worker by its agent type and **never passes `model`** in the Agent call, except the alias `ccp prompt implement` prints from `workers.implementer_model`: a call's `model` overrides the definition.
- **Out:**
  - Running the trial or recording estimates.
  - Changing any agent definition's model.

## dod_checks

- id: `cmd-01`
  story: As a runner, the printed model is one my Agent call accepts.
  setup: a scratch product with `workers.implementer_model` `{"refactor": "sonnet"}` and a pending refactor task.
  steps:
    1. Run `ccp prompt implement <task>`.
  expect: the printed Agent call carries `model: sonnet`.
  dry run: n/a.
- id: `cmd-02`
  story: As an operator, a full id is refused before it reaches a runner.
  setup: a scratch product with `workers.implementer_model` `{"small": "claude-sonnet-5-5"}`.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 2, naming `workers.implementer_model` and the accepted aliases.
  dry run: n/a.
- id: `cmd-03`
  story: As a runner, I learn when the small arm cannot apply.
  setup: a scratch product with `workers.implementer_model` `{"small": "sonnet"}` and a pending feature task with no estimate row.
  steps:
    1. Run `ccp prompt implement <task>`.
  expect: exit 0; stderr says the `small` arm cannot apply for want of an estimate; the Agent call carries no `model`.
  dry run: n/a.
- id: `cmd-04`
  story: As the plane, my own plane.json loads.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -c "import json;print(json.load(open('docs/delivery/plane.json'))['workers'])"`, then `ccp tasks check`.
  expect: prints `{'implementer_model': {'small': 'sonnet', 'refactor': 'sonnet'}}`; the check exits 0.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the three §2.4 edits with the PROPOSED text above.
  expect: they match word for word, and no other § rule changes.
  dry run: n/a.
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
