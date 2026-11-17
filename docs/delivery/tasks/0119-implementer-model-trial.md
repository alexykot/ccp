---
task_id: 0119-implementer-model-trial
title: A plane.json knob picks the implementer's model per task size or kind, and the plane trials a cheaper model on its own small and refactor tasks
status: done
kind: feature
depends_on: []
spec_refs: ["S2", "S24", "S26"]
review_point: R7
sign_off: brief
paths: ["ccp/prompt.py", "ccp/usage.py", "ccp/config.py", "contracts/plane_config.schema.json", "plugin/agents/delivery-runner.md", "docs/spec/01-model.md", "docs/delivery/plane.json", "tests/test_prompt*.py", "tests/test_usage*.py"]
adopt: "none: off by default; plane.json workers.implementer_model turns it on"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0119-implementer-model-trial
## Intent

The plane measures, on its own work, whether a cheaper implementer model holds up on small and
refactor tasks. A plane.json knob lets a product pick the implementer's model by task size or kind,
off by default, and `ccp usage` compares cost, rounds and MAJOR findings by model, so a default
changes only on evidence.

## Context (not checked)

- From an accepted plane proposal (operator, 2026-11-16: accept the trial). A telemetry analysis of 9–16 Nov reported the implementer as the largest worker cost, with first implement rounds a large share of all worker cost; `ccp usage --system --since 2026-11-09` gives the per-seat figures.
- §2.4 fixes each seat's model in its agent definition, and the runner brief forbids passing `model` in the Agent call. The knob changes that rule for the implementer only, hence the brief sign-off.
- The trial itself runs after this task merges: the plane turns the knob on for itself; the lead compares after enough tasks (at least five per arm) and brings the result to the operator.

## Scope

- **In:**
  - `docs/spec/01-model.md` §2.4. CURRENT (at `7094dfe`): "Each seat's model and effort is fixed in its agent definition (or launch flags) and never depends on the lead session's settings:" PROPOSED:
    > Each seat's model and effort is fixed in its agent definition (or launch flags) and never depends on the lead session's settings, except the implementer's model, which plane.json `workers.implementer_model` may set per task: `{"small": <model>, "refactor": <model>}`, where `small` is a task whose estimate is at most `workers.small_estimate_minutes` (default 30) and `refactor` a task of that kind; unset (the default) leaves the definition's model. `ccp prompt implement` prints the model in its Agent call, and the runner passes it as given:
  - `ccp/prompt.py`: the Agent call `ccp prompt implement` prints carries `model` when the knob picks one for the task, else none.
  - `plugin/agents/delivery-runner.md`: pass `model` only when `ccp prompt` prints it.
  - `ccp/usage.py`: `ccp usage --by-model --seat implementer` compares, per model, tasks, cost per task, implement rounds per task and MAJOR findings per task.
  - Knobs in `ccp/config.py` and the schema.
  - `docs/delivery/plane.json`: `workers.implementer_model: {"small": "claude-sonnet-5-5", "refactor": "claude-sonnet-5-5"}` for the trial.
- **Out:**
  - Changing any seat's default model.
  - Judging the trial: that comes after enough tasks.

## dod_checks

- id: `cmd-01`
  story: As a runner, the implement call names the model the knob picks.
  setup: a scratch product with the knob set as above, and three pending tasks: one estimated at 20 minutes, one refactor estimated at 90, one feature estimated at 90.
  steps:
    1. Run `ccp prompt implement` for each.
  expect: the first two Agent calls carry `model: claude-sonnet-5-5`; the third carries no `model`.
  dry run: n/a.
- id: `cmd-02`
  story: As a product that sets nothing, nothing changes.
  setup: a scratch product without the knob.
  steps:
    1. Run `ccp prompt implement` for a small task.
  expect: the Agent call carries no `model`.
  dry run: n/a.
- id: `cmd-03`
  story: As the lead, I compare models on the implementer seat.
  setup: a scratch sink and queue with implementer runs on two models, with known costs, rounds and MAJOR findings.
  steps:
    1. Run `ccp usage --by-model --seat implementer`.
  expect: one row per model with tasks, cost per task, rounds per task and MAJOR findings per task matching the fixture.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §2.4 edit with the PROPOSED text above.
  expect: it matches word for word, and no other § rule changes.
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

- 2026-11-17 (implementer): `ccp prompt implement` picks the model in `prompt.implementer_model`: `refactor`
  for a task of that kind (it wins when both arms apply), else `small` when the task's estimate (its latest
  agent row, else its latest baseline, stored `total.p50_s`, uncalibrated) is at most
  `workers.small_estimate_minutes` × 60; a task with no estimate is not small. Only the implement round
  picks: fix, merge and ruling rounds keep the definition's model. The picked model is the run's
  `expected_model`, so the board does not flag the trial's runs as off-pin. The Agent call carries no
  `model` key otherwise, for every phase (the old `"model": "never pass it"` hint is gone; the runner
  brief says to pass `model` only when printed).
- `workers` is a new plane.json block (config, schema): `implementer_model` null or `{small, refactor}`
  of full model ids (aliases refused, per §2.4), `small_estimate_minutes` an integer >= 1.
- `ccp usage --by-model [--seat S]` (default implementer; wiring in `ccp/cli.py`): a task counts under the
  model that carried most of the cost of its first run of the seat (none observed: that run's
  `expected_model`); cost and rounds count every run of the seat on the task except one abandoned before
  it started; MAJOR findings come from the review runs' severities, else the review reports' lines (the
  estimate actuals' source). The fold now keeps each run's cost by model (`run_models`), which the plain
  `ccp usage` output leaves out.

## Verification notes
- 2026-11-17 — verifier, PR #129 head `5909792` (squash `64e09ea`): APPROVE. Passed: cmd-01, cmd-02, cmd-03, check-01, suite-01. Gate: `scripts/gate.sh (ccp suite run --lane gate)` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0119-implementer-model-trial.json.

