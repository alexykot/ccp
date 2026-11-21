---
task_id: 0212-full-role-runs-the-gate-lane-and-a-pregate-lane
title: A product with no full lane runs the gate lane for the full role, and a declared pre-gate lane replaces the rendered pre-gate list
status: pending
kind: feature
depends_on: []
clashes_with: ["0221-workers-reach-the-pr-host-through-ccp-pr", "0223-a-follow-up-is-tracked-not-left-in-notes", "0238-the-runner-runs-marked-checks-before-verify"]
spec_refs: ["S13", "S14"]
review_point: R15
paths: ["ccp/config.py", "ccp/prompt.py", "templates/prompts/implement.md", "templates/prompts/fix.md", "templates/prompts/ruling.md", "templates/prompts/merge.md", "docs/spec/02-delivery.md", "tests/test_full_lane_prompt.py"]
adopt: "plane.json suite.lanes.pregate: a lane that runs the product's fail-fast checks, if it wants one"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0212-full-role-runs-the-gate-lane-and-a-pregate-lane

## Intent

Many products have one test command: the gate is the full suite. Today such a product must declare
the same command twice, as `full` and as `gate`, or its implementer and fixer are told to run the
full suite as `--lane full` with a command they make up. And a product that wraps its fail-fast
checks in a lane of its own still gets the brief's rendered list of `architect.checks` beside it, so
the worker is told two ways to do one thing. After this task, a product that declares a gate lane and
no full lane runs the gate lane wherever the full role is asked for, and a product that declares a
`pregate` lane gets that lane in the briefs in place of the rendered list of house-rule checks.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: two accepted plane proposals (triage item T6).
- **The full role's lane is named by role.** `ccp/config.py` `def lane_for(cfg, role)` returns
  `suite.roles[role]`, else `SUITE_DEFAULTS["roles"][role]`, `"full"` for the full role
  (`git grep -n 'def lane_for' -- ccp/config.py` at `1b734dd`). It never looks at which lanes are
  declared. `prompt.suite_lanes` renders a role whose lane is declared as `--lane <lane>` with nothing
  after `--`, and one whose lane is not declared as `--lane <lane>` for a command the worker supplies.
  So a product declaring only `gate` gets "`--lane full` for …" in the implement and fix briefs.
- **Who asks for the full role's lane.** `git grep -n 'lane_for(cfg, "full")' -- ccp` at `1b734dd`:
  `suite.py` (a run with no `--lane` counts as the full lane for the exclusive lock and the usual
  duration, five sites) and `prompt.py` (`full_lane`, one site; `suite_lanes` asks each role through
  `lane_for(cfg, r)`). All go through `lane_for`, so a
  change there reaches each.
- **The pre-gate list.** `ccp/prompt.py` renders `architect_checks` from `architect.checks`
  (`git grep -n '"architect_checks"' -- ccp/prompt.py` at `1b734dd`: one line). Four templates use it
  in their "Fail fast first" sentence (`git grep -c 'architect_checks' -- templates/prompts` at
  `1b734dd`: `fix.md`, `implement.md`, `merge.md`, `ruling.md`, one line each). Nothing reads a lane
  named `pregate` (`git grep -n pregate -- ccp templates` at `1b734dd`: no line).
- **§14.1 today** says each role's lane is the `suite.lanes` lane of the role's own name; nothing says
  what happens when the full lane is not declared. `config.validate`'s "suite.roles must give each
  role its own lane name" stays: `suite.roles` is not changed here.
- `tests/test_full_lane_prompt.py` holds the full-lane prompt tests
  (`python3 -B -m unittest tests.test_full_lane_prompt` at `1b734dd`: 5 tests, OK).
- The repo's own plane.json declares both `full` and `gate`, so nothing changes for it.
- No R14 task edits these passages: 0199 edits `ccp/suite.py`'s `--wait` and §16.6, not `lane_for`
  or §13.5 and §14.1.
- **Clashes.** 0221, 0223 and 0238 edit `templates/prompts/implement.md`, whose instructions are one
  long line holding the pre-gate sentence this task changes, so each pair conflicts on that line.
  R16's 0244 edits the line of `templates/prompts/ruling.md` that has the ruling written into the
  Context; this task edits its "Fail fast first" line. Separate lines, so the two merge cleanly and no
  clash is declared: `grep -n -e 'The ruling is binding' -e 'Fail fast first' templates/prompts/ruling.md` at `8aefa59` prints lines 5 and 9.

## Scope

- **In:** `ccp/config.py`, `ccp/prompt.py`, `templates/prompts/implement.md`,
  `templates/prompts/fix.md`, `templates/prompts/ruling.md`, `templates/prompts/merge.md`,
  `docs/spec/02-delivery.md`, `tests/test_full_lane_prompt.py`.
- **The full role falls back to the gate lane.** `lane_for(cfg, "full")` returns
  `lane_for(cfg, "gate")` when plane.json `suite.lanes` declares the gate role's lane and not the full
  role's (the name `suite.roles` gives each). Every other case is unchanged, and so is every other
  role. So the briefs render the full suite as `--lane gate` with nothing after `--`, and a run with no
  `--lane` counts as the gate lane for the exclusive lock.
- **A declared pre-gate lane.** `PREGATE_LANE = "pregate"`, a constant in `ccp/config.py`. When
  `suite.lanes` declares it, `ccp/prompt.py` renders `pregate_lane` (`ccp suite run --lane pregate`)
  and leaves `architect_checks` empty. The four templates' "Fail fast first" sentence then reads "run
  the product's pre-gate lane (`ccp suite run --lane pregate`, as plane.json gives it) and the run
  `ccp suite affected` …", in place of the house-rule checks clause. The `ccp suite affected` run
  stays in both forms. Without the lane, the briefs are unchanged.
- **Tests** in `tests/test_full_lane_prompt.py`:
  - a product declaring only `gate` renders the implement and fix briefs' full suite as `--lane gate`
    with nothing after `--`, and `lane_for(cfg, "full")` is `gate`;
  - a product declaring `full` and `gate` still renders `--lane full`;
  - a product declaring `pregate` and `architect.checks` renders `--lane pregate` and none of the
    checks' commands in the implement, fix, merge and ruling briefs; without `pregate`, the checks'
    commands are rendered as today.

### SPEC changes (signed in the brief, §31)

**a. §14.1, the roles' lanes.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> reviewer's modules or a mutation check). Each role's lane is the `suite.lanes` lane of the role's own
> name. The gate

PROPOSED:
> reviewer's modules or a mutation check). Each role's lane is the `suite.lanes` lane of the role's own
> name, except that a product declaring a gate lane and no full lane runs the gate lane for the full
> role too (in the briefs, and for a run with no `--lane`). The gate

**b. §13.5, Fail fast.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> - **Fail fast.** Before the full suite, the implementer and fixer run a pre-gate: the product's `architect.checks` commands (rendered from plane.json) and the run `ccp suite affected` prints on stderr (§14.7), through `ccp suite run`: the part lane, or, when it says the change reaches most of the suite, no pre-gate and the full lane. It never stands in for the full suite, which runs on the final code and must be green.

PROPOSED:
> - **Fail fast.** Before the full suite, the implementer and fixer run a pre-gate: the product's `architect.checks` commands (rendered from plane.json), or, when plane.json `suite.lanes` declares a `pregate` lane, that lane through `ccp suite run --lane pregate` in their place, and the run `ccp suite affected` prints on stderr (§14.7), through `ccp suite run`: the part lane, or, when it says the change reaches most of the suite, no pre-gate and the full lane. It never stands in for the full suite, which runs on the final code and must be green.

- **Out:** `suite.roles` and its validation, the part role, the gate lane's requirement, and what a
  `pregate` lane runs (the product's choice).

## dod_checks

- id: `ln-01`
  story: As a lead with one test command, I declare it once as the gate lane.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_full_lane_prompt 2>&1 | tail -20`.
  expect: exit 0, with the Scope's tests listed `ok`: the gate-only product's `--lane gate`, the
    two-lane product's `--lane full`, and the pre-gate lane in the four briefs.
  dry run (`1b734dd`): 5 tests, OK; the new tests do not exist yet.

- id: `ln-02`
  story: As a plane developer, the tests bite.
  setup: a checkout of the PR head; then two copies (`git worktree add --detach <tmp> HEAD`): in copy
    A, `lane_for` returns the role's own name again; in copy B, `architect_checks` is rendered whether
    or not `pregate` is declared.
  steps:
    1. In copy A, run `python3 -B -m unittest -q tests.test_full_lane_prompt`.
    2. In copy B, run the same.
  expect: each step has at least one failure.
  dry run: n/a — the tests are new.

- id: `ln-03`
  story: As a lead, the role is resolved where every caller reads it.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -c "from ccp import config; from types import SimpleNamespace as N; print(config.lane_for(N(suite={'lanes': {'gate': ['true']}, 'roles': {}}), 'full'), config.lane_for(N(suite={'lanes': {'gate': ['true'], 'full': ['true']}, 'roles': {}}), 'full'))"`.
  expect: prints `gate full`.
  dry run (`1b734dd`): prints `full full`.

- id: `ln-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0212 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`1b734dd`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
