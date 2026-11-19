---
task_id: 0183-gate-lane-is-required
title: A product must name a gate lane, and claim and next say so when it has none
status: pending
kind: feature
depends_on: ["0172-fixtures-name-their-config", "0182-language-is-a-required-key"]
spec_refs: ["S4", "S8", "S10", "S14"]
adr_refs: ["0043 D5"]
review_point: R12
paths: ["ccp/config.py", "ccp/lifecycle.py", "ccp/selection.py", "ccp/cli.py", "ccp/init.py", "ccp/upgrade.py", "contracts/plane_config.schema.json", "README.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md", "tests/test_gate_lane_required.py"]
adopt: "required: plane.json suite.lanes.gate"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0183-gate-lane-is-required

## Intent

Every task's verify runs the gate lane, and so does its catch-up with the tip before review, so a
product with no gate lane cannot deliver. The plane says so before any work starts: `ccp tasks claim`
and `ccp tasks next` refuse, naming the missing lane, and `ccp init` lists it as a required key still
unset. During the grace release they warn and carry on.

## Context (not checked)

- ADR-0043 D5, accepted 2026-11-19.
- Depends on 0182, which adds the required-key rule to §8.1 and `config.REQUIRED_KEYS_GRACE` (the
  grace switch both use), and the init and upgrade lines for a required key; this task adds the gate
  lane as the second such key. Depends on 0172: the fixtures already name a gate lane.
- Today, at `e9ff0fc`: claim and next do not look at the gate lane. A fresh sandbox
  (`ccp sandbox create`, plane.json with no `suite` block) answers `ccp tasks next` with its task,
  exit 0, no warning (dry run below). Only close's catch-up refuses ("no gate lane: plane.json
  suite.lanes names no lane … for the gate role", `def _catch_up` in `ccp/lifecycle.py`), late.
- Decided here:
  - The gate lane is the lane `suite.lanes` gives the `gate` role (`config.lane_for(cfg, "gate")`).
    It is missing when `suite.lanes` has no such entry, or its argv or stages are empty, or it still
    holds `config.LANE_PLACEHOLDER`.
  - With it missing, `ccp tasks claim` and `ccp tasks next` exit 2 with
    `no gate lane: plane.json suite.lanes names no lane <lane> for the gate role (§14.1); every task's verify runs it`.
    While `REQUIRED_KEYS_GRACE` is true they print that line as a warning and carry on.
  - `ccp init` without `--gate` lists `suite.lanes.gate` among the required keys still unset.
  - `ccp upgrade status` lists this task's step for a product with no gate lane.
- This task marks ADR-0043 D5 built in its own PR.

## Scope

- **In:**
  - `ccp/config.py`: `gate_lane_missing(cfg) -> str | None` (the reason, or None).
  - `ccp/lifecycle.py` (claim), `ccp/selection.py` or `ccp/cli.py` (next): the refusal, or the
    warning during the grace.
  - `ccp/init.py`, `ccp/upgrade.py`: the required key.
  - `contracts/plane_config.schema.json`: `suite.lanes`' description says a gate lane is required.
  - `README.md`: the checklist's gate-lane row says it is required.
  - `tests/test_gate_lane_required.py` (new).
  - `docs/spec/01-model.md` §8.1: CURRENT (0182's PROPOSED, its first sentence): "Two keys are required: `project_id` (lowercase letters, digits and hyphens) and `language`, the product's language pack (§21.4) or `none`; the plane assumes no language." PROPOSED:
    > Two keys are required: `project_id` (lowercase letters, digits and hyphens) and `language`, the product's language pack (§21.4) or `none`; the plane assumes no language. `suite.lanes` must name a gate lane (§14.1): without one, `ccp tasks claim` and `ccp tasks next` refuse with exit 2, naming it.
  - `docs/spec/02-delivery.md` §14.1: CURRENT (at `e9ff0fc`): "plane.json `suite.roles` names the product's lane for each
    (default: the role's own name; a role left out keeps it; two roles may not share a lane);" PROPOSED:
    > plane.json `suite.roles` names the product's lane for each (default: the role's own name; a role left out keeps it; two roles may not share a lane). The gate role's lane is required: every task's verify runs it, and so does its catch-up with the tip before review, so with none `ccp tasks claim` and `ccp tasks next` refuse (exit 2, §8.1); `ccp init --gate` writes it. The other roles' lanes are optional;
  - `docs/spec/02-delivery.md` §10.3: CURRENT (at `e9ff0fc`): "With
    several runners `next` also applies §16.3 (head of line, exit 7)." PROPOSED:
    > With several runners `next` also applies §16.3 (head of line, exit 7). With no gate lane it names no task and exits 2 (§14.1).
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D5 marked built; `docs/adr/INDEX.md`.
- **Out:**
  - Ending the grace (0191). What the gate lane runs (the product's command).

## dod_checks

- id: `gate-01`
  story: As a runner of a product with no gate lane, next tells me before I claim anything, and during the grace release it still hands out the task.
  setup: a checkout of the PR head; `ccp sandbox create <dir>` (no `--gate`); one pending task file added and indexed, committed; the sandbox's `PROJECT_YAML` and `QUEUE_ROOT` exported.
  steps:
    1. In the sandbox's product root, run `ccp tasks next`.
  expect: exit 0, the task named, and a stderr warning containing `no gate lane` and `suite.lanes`.
  dry run (`e9ff0fc`): exit 0, the task named, no warning (`0001-first  Do the first thing`).
- id: `gate-02`
  story: As a runner, once the grace ends, claim and next refuse without a gate lane, and pass with one.
  setup: a checkout of the PR head; then a separate copy where `config.gate_lane_missing` always returns `None`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_gate_lane_required`.
    2. In the copy, run the same.
  expect: step 1 exits 0 and step 2 exits non-zero; the module's tests cover, under a patched `REQUIRED_KEYS_GRACE = False`, `claim` and `next` exiting 2 with `no gate lane` on a product with no `suite` block, with an empty gate lane and with the placeholder, and exiting 0 with a gate lane; and the warning under the grace.
  dry run: n/a — new module.
- id: `gate-03`
  story: As an operator adopting a product, init names the gate lane as required when I give none.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp sandbox create <dir>` and read its stderr and the init result it prints.
    2. Run `ccp sandbox create <dir2> -- --gate "make test"` and read the same.
  expect: step 1's output names `suite.lanes.gate` as a required key still unset; step 2's does not.
  dry run (`e9ff0fc`): step 1's stderr carries only the no-origin warning.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed, and D5 is recorded as built.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0183-gate-lane-is-required --base origin/main`.
    2. Run `grep -n '"D5 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: step 1 exits 0 with every passage found; step 2's output contains `- "D5 built"`.
  dry run (`e9ff0fc`): step 2 printed `- "D5 not_built"`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-19 (implementer): `config.gate_lane_missing(cfg)` returns the refusal line, or None: the lane
  `lane_for(cfg, "gate")` names, with at least one non-blank command (argv words or stage `cmd`s) and none
  holding `LANE_PLACEHOLDER`. `config.require_gate_lane(cfg)` applies the grace switch: during
  `REQUIRED_KEYS_GRACE` it returns the warning (once per product and process, naming the upgrade step and
  `ccp init --gate`), after it raises `MissingKey`. `lifecycle.claim` asks it first, before anything is taken
  (a resumed claim too); `cli.cmd_tasks_next` asks it first and names no task.
- The loader already refuses an empty gate lane and a placeholder one (exit 2, its own message), before
  claim or next run, so on a real plane.json those two shapes never reach `gate_lane_missing`; the tests for
  them hand claim and next a loaded Config with the shape put in (`dataclasses.replace`). Load validation is
  unchanged.
- `ccp init`'s `required_unset` (and its stderr line) adds `suite.lanes.gate` when `gate_lane_missing`.
  `ccp upgrade status` judges the step `plane.json suite.lanes.gate` by `gate_lane_missing` rather than by
  the key's presence, so a product whose `suite.roles` renames the gate lane has taken it.
- README: the checklist had no gate-lane row; a `suite.lanes.gate` row was added, marked required.
- ADR-0043 D5 marked built (`ccp adr decide 43 D5 built`); INDEX.md has no column that changes.

## Verification notes
