---
task_id: 0172-fixtures-name-their-config
title: The shared test fixtures name the configuration they rely on
status: pending
kind: refactor
depends_on: []
spec_refs: ["S8"]
review_refs: ["sh-20261119T170325Z-8142#F04"]
rule_refs: ["E4"]
review_point: R12
paths: ["tests/"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0172-fixtures-name-their-config

## Intent

The two shared test fixtures write a plane.json that states the settings their tests depend on (a gate
lane, one task in flight under the `paths` schedule, the current worktree keys), instead of relying on
today's defaults. When ADR-0043 changes those defaults, each change is a small diff with its own
tests, not a break in dozens of modules. Nothing the plane does changes.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, finding F04 and preparatory refactor P1. The default changes that
  build on it: parallel by default (0180), the gate lane required (0183), the language key (0182),
  the architect on by default (0185) and the short plane.json (0187).
- The fixtures at `e9ff0fc`:
  - `ToolkitFixture.PLANE_JSON` in `tests/test_toolkit.py`: `project_id`, `prompts`, `reconcile` and
    the legacy `adapter` block (`worktree_dir`, `worktree_links`, `post_close`); no `suite`,
    `parallel` or `architect` key (dry run of `python3 -B -c "from tests.test_toolkit import ToolkitFixture as T; …"`
    below).
  - `Product` in `tests/helpers.py` writes `{"project_id": "demo", **cfg}`.
  - `git grep -l test_toolkit -- tests | wc -l` at `e9ff0fc`: 66 modules;
    `git grep -lE 'from tests.helpers|from tests import helpers|helpers import' -- tests | wc -l`: 67.
- Decided here:
  - Both fixtures start from one base plane.json, `helpers.BASE_PLANE`: `suite.lanes.gate` `["true"]`
    (a gate that passes), `parallel` `{"max_in_flight": 1, "schedule": "paths"}`. `ToolkitFixture`
    adds its own keys to it. `Product(cfg)` merges `cfg` over the base, block by block (a test's
    `suite` replaces the base's `suite`). `Product(cfg, bare=True)` writes only `project_id` and `cfg`,
    for a test whose subject is a missing block.
  - `ToolkitFixture` uses `worktrees` (`dir` `.rt`, `links` `[".venv"]`) in place of
    `adapter.worktree_dir` and `adapter.worktree_links`. The test that asserts `adapter.post_close`
    runs at close (`closed-0002`, in `tests/test_toolkit.py`) sets `adapter.post_close` itself; the
    legacy keys stay covered by the tests that name them (`tests/test_wt_outside.py`,
    `tests/test_wt.py`, `tests/test_refs.py`).
  - What the fixtures cannot name yet waits for the task that makes it valid: the top-level
    `language` key (0182) and `"architect": false` (0185). Today either key would load with an
    unknown-key warning or a type error.
- A test whose expectation relied on a missing block (no gate lane, no parallel block) gets
  `bare=True` or its own explicit block, never a changed assertion; the implementer lists each such
  test in the notes.
- House rules: E4 (a fixture other modules reuse holds no test methods); E15.
- No SPEC change: tests only.

## Scope

- **In:**
  - `tests/helpers.py`: `BASE_PLANE`; `Product(cfg=None, bare=False)` as above.
  - `tests/test_toolkit.py`: `ToolkitFixture.PLANE_JSON` built from `helpers.BASE_PLANE` plus its own
    `prompts`, `reconcile` and `worktrees`; no `adapter` key. The `post_close` test sets it.
  - Any test module whose test depended on a block the base now names: it passes `bare=True` or sets
    the block (each listed in the implementation notes).
  - No file outside `tests/` changes.
- **Out:**
  - Any change under `ccp/`, `scripts/`, `plugin/`, `contracts/` or `docs/`.
  - The `language` key and `"architect": false` (0182, 0185).

## dod_checks

- id: `fix-01`
  story: As a plane developer, the toolkit fixture no longer leans on the legacy adapter keys.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n '"adapter"' -- tests/test_toolkit.py tests/helpers.py`.
  expect: exactly the lines of tests that name the adapter block on purpose (the `post_close` test and the bad-config and schema lists in `tests/test_toolkit.py`); none in `PLANE_JSON` or `tests/helpers.py`.
  dry run (`e9ff0fc`): 3 lines, `tests/test_toolkit.py:75` (`PLANE_JSON`'s adapter block, the positive the check removes), `:204` (the bad-config list) and `:214` (the schema list).
- id: `fix-02`
  story: As a plane developer, both fixtures state a gate lane and one task in flight.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -c "from tests.test_toolkit import ToolkitFixture as T; import json; print(json.dumps({k: T.PLANE_JSON.get(k) for k in ('suite','parallel','adapter','worktrees')}))"`.
    2. Run `python3 -B -c "from tests.helpers import Product; p=Product(); print(open(p.root/'docs/delivery/plane.json').read()); p.cleanup()"`.
  expect: step 1 shows a `suite.lanes.gate`, `parallel` `{"max_in_flight": 1, "schedule": "paths"}`, `adapter` null and `worktrees` `{"dir": ".rt", "links": [".venv"]}`; step 2 shows the same `suite` and `parallel` beside `project_id`.
  dry run (`e9ff0fc`): step 1 printed `{"suite": null, "parallel": null, "adapter": {"worktree_dir": ".rt", …}, "worktrees": null}`; step 2 printed `{"project_id": "demo"}`.
- id: `fix-03`
  story: As a plane developer, the change is tests only and every test still passes.
  setup: a checkout of the PR head.
  steps:
    1. Run `git diff --name-only origin/main...HEAD -- ccp scripts plugin contracts docs`.
    2. Run `python3 -B -m unittest -q tests.test_toolkit tests.test_wt tests.test_wt_outside tests.test_behind_tip_catch_up tests.test_parallel_claims tests.test_suite`.
  expect: step 1 prints nothing; step 2 exits 0.
  dry run (`e9ff0fc`): step 2's modules pass at the base (the regression guard this refactor keeps).
## Implementation notes

*Append-only, newest last.*

## Verification notes
