---
task_id: 0180-parallel-by-default
title: A product with no parallel block runs three tasks at once, scheduled by clashes
status: pending
kind: feature
depends_on: ["0172-fixtures-name-their-config", "0173-plane-json-block-registry", "0174-config-readers-go-through-ccp"]
spec_refs: ["S16"]
adr_refs: ["0043 D2"]
review_point: R12
paths: ["ccp/config.py", "contracts/plane_config.schema.json", "README.md", "docs/spec/02-delivery.md", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md", "tests/test_parallel_defaults.py", "tests/test_parallel_by_default.py"]
adopt: "none"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0180-parallel-by-default

## Intent

A product that says nothing about parallel work runs up to three tasks at once, and keeps apart only
the tasks its task-log owner says clash. `parallel: false`, `parallel.exclusive` and `clashes_with`
still keep tasks apart, and a product that wants the old behaviour sets `max_in_flight: 1` or
`schedule: paths`.

## Context (not checked)

- ADR-0043 D2, accepted 2026-11-19. It replaces ADR-0012 D1 (parallel is opt-in) and D5 (paths decide
  co-scheduling), and ADR-0042 D1's clause that the default schedule changes only after a measurement.
- Depends on 0172 (the fixtures state `max_in_flight: 1` and `schedule: paths`, so this flip does not
  move them), 0173 (the schema's defaults are held to the code by one test) and 0174 (the idle hook and
  the runner spawn read the loaded configuration, so they follow the new default without an edit).
- Today, measured at `e9ff0fc` on a temp product whose plane.json holds only `project_id`:
  `parallel.settings(config.load(d))` gives `max_in_flight` 1 and `schedule` `paths` (dry run below).
- This repo's own plane.json already sets `max_in_flight: 3` and `schedule: clashes`; it is unchanged.
- The new SPEC text states the behaviour, not the number (house rule E10 as amended in this triage);
  the value 3 lives in `config.PARALLEL_DEFAULTS` and the schema.
- Any other SPEC sentence the new default makes false is corrected under §31.1 (a correction limited to
  passages this change makes false) and quoted in the PR body; the passages below are the rules.
- This task marks ADR-0043 D2 built (`ccp adr decide 43 D2 built`) in its own PR (ruling
  sm-20261119T113130Z-8831: a task marks built every decision it cites).

## Scope

- **In:**
  - `ccp/config.py` `PARALLEL_DEFAULTS`: `max_in_flight` 3, `schedule` `clashes`.
    `contracts/plane_config.schema.json`: the same two defaults, and their descriptions.
  - `README.md`: the `parallel.schedule` row of the adoption checklist says `clashes` is the default
    and `paths` keeps apart tasks whose paths meet; a `parallel.max_in_flight` row says `1` runs one task
    at a time.
  - `tests/test_parallel_by_default.py` (new): a product with no `parallel` block gets three slots
    under `clashes`, through `ccp tasks claim` (two tasks whose paths meet both claim); `team.py`'s
    `max_in_flight` and the idle hook's parallel test agree.
  - `docs/spec/02-delivery.md` §16.1: CURRENT (at `e9ff0fc`): "Under `parallel.schedule: paths`, the default, declared paths decide what to start together; under `clashes`, the writer's `clashes_with` does, and paths still decide what `parallel.exclusive` keeps alone (§16.3). Off (`max_in_flight: 1`) is the
    single-runner behaviour, exactly." PROPOSED:
    > Under `parallel.schedule: clashes`, the default, the writer's `clashes_with` decides what to start together, and paths still decide what `parallel.exclusive` keeps alone (§16.3); under `paths`, declared paths decide. Parallel work is on by default; `max_in_flight: 1` is the single-runner behaviour, exactly.
  - `docs/spec/02-delivery.md` §16.2: CURRENT (at `e9ff0fc`): "No `parallel` block, or `max_in_flight: 1`: one task at a time." PROPOSED:
    > With no `parallel` block, several tasks run at once, scheduled by clashes (the defaults are in code and the schema); `max_in_flight: 1` runs one task at a time.
  - `docs/spec/02-delivery.md` §16.2: CURRENT (at `e9ff0fc`): "`schedule` picks claim rule 3 (§16.3): `paths`, the default, keeps apart tasks whose paths meet; `clashes` keeps apart only tasks that clash (`clashes_with`, §5), whatever their paths, and `shared` then matters only at close (§16.5 rule 4)." PROPOSED:
    > `schedule` picks claim rule 3 (§16.3): `clashes`, the default, keeps apart only tasks that clash (`clashes_with`, §5), whatever their paths, and `shared` then matters only at close (§16.5 rule 4); `paths` keeps apart tasks whose paths meet.
  - `docs/spec/02-delivery.md` §16.5 rule 4: CURRENT (at `e9ff0fc`): "(under `parallel.schedule: paths`, the default), or, under `parallel.schedule: clashes`, the task's own patch is unchanged by the merge" PROPOSED:
    > (under `parallel.schedule: paths`), or, under `parallel.schedule: clashes`, the default, the task's own patch is unchanged by the merge
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D2 marked built; `docs/adr/INDEX.md`
    regenerated.
- **Out:**
  - The `--count` default of `team.sh runner spawn` (§16.4), and `parallel.max_in_flight`'s range (1 to 4).
  - This repo's own plane.json.
  - Other defaults' SPEC numbers (0189).

## dod_checks

- id: `par-01`
  story: As an operator of a new product, parallel work under clash scheduling is on without a parallel block.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -c "import tempfile,json,pathlib; from ccp import config, parallel; d=pathlib.Path(tempfile.mkdtemp()); (d/'docs/delivery').mkdir(parents=True); (d/'docs/delivery/plane.json').write_text(json.dumps({'project_id':'demo'})); s=parallel.settings(config.load(d)); print(s['max_in_flight'], s['schedule'])"`.
  expect: prints `3 clashes`.
  dry run (`e9ff0fc`): printed `1 paths`.
- id: `par-02`
  story: As a runner of such a product, two tasks whose paths meet both claim, and the hook and spawn agree with ccp.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_parallel_by_default tests.test_parallel_defaults tests.test_plane_config_defaults`.
  expect: exits 0.
  dry run: n/a — `tests.test_parallel_by_default` is new; `tests.test_plane_config_defaults` comes with 0173.
- id: `par-03`
  story: As an operator, setting the knobs back gives the old behaviour.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_parallel_claims tests.test_next_passes_over tests.test_clashes_with tests.test_parallel_hook tests.test_team_hosting`.
  expect: exits 0 (these modules' products name `max_in_flight` and `schedule` through the fixtures, 0172).
  dry run (`e9ff0fc`): the five modules pass at the base (a regression guard).
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed, and D2 is recorded as built.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0180-parallel-by-default --base origin/main`.
    2. Run `grep -n '"D2 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: step 1 exits 0 with all four passages found; step 2's output contains `- "D2 built"`.
  dry run (`e9ff0fc`): step 2 printed `- "D2 not_built"`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*
- 2026-11-19 — Built as written: `PARALLEL_DEFAULTS` and the schema now default to three slots and the `clashes` schedule; the README, the four SPEC passages (§16.1, §16.2 twice, §16.5 rule 4) carry the signed text; ADR-0043 D2 is marked built. The premise held at the base (`1 paths`).
- Tests the flip broke, updated in the same PR (setup only, no expectation weakened): fixtures that wrote a `parallel` block naming only `max_in_flight` or `shared` now name `schedule: paths` (`test_parallel_claims`, `test_behind_tip_catch_up`, `test_parallel_merging`, `test_next_passes_over`); tests whose subject is one runner now say `max_in_flight: 1` (`test_parallel_claims`, `test_parallel_merging`, `test_parallel_records`, `test_parallel_runner`); `test_clashes_with` now asserts `clashes` as the default and sets `paths` where `clashes_with` must not be read; `test_parallel_hook` and `test_team_hosting` flip direction (the default has several slots, a patched default of one gives one) and still prove the readers follow ccp's default; `test_tasks_migrate` leaves warnings out of its failing-files list, since an adopted product now gets the parallel warnings.
- Not changed, outside Scope: comments that still call one slot or `paths` the default (`ccp/parallel.py` module docstring, `ccp/lifecycle.py` `catch_up_blocked` docstring, `scripts/observability/team.py` `max_in_flight` docstring, the `.get("schedule", "paths")` fallbacks in `ccp/parallel.py` and `ccp/lifecycle.py`, which `settings` never reaches).
- 2026-11-19 — Fix round 1 (review MINOR 1): the `ccp/parallel.py` module docstring and the `ccp/lifecycle.py` `catch_up_blocked` docstring no longer call `paths` or one slot the default, and now name `clashes` the default; comments only, no behaviour change. `team.py`'s `max_in_flight` docstring was not stale (its 1 is the fallback when the configuration does not load). The unreachable `.get("schedule", "paths")` fallbacks are left as they are.

## Verification notes
