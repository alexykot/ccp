---
task_id: 0328-the-fail-fast-rule-and-the-worker-prompt-name-suite-run-affected-for-a-staged-part-lane
title: §13.5's Fail fast rule says what ccp suite run --affected runs for a staged part lane, the worker prompt names --affected for one, and a language pack's affected reader is typed with the named keyword suite passes
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S14"]
review_point: R34
paths: ["docs/spec/02-delivery.md", "ccp/prompt.py", "ccp/doclang/__init__.py", "ccp/suite.py", "tests/test_full_lane_prompt.py"]
clashes_with: ["0191-the-grace-release-ends", "0329-tests-edit-plane-json-through-one-helper-name-the-plane-root-once-and-take-git-from-its-own-module"]
sign_off: brief
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0328-the-fail-fast-rule-and-the-worker-prompt-name-suite-run-affected-for-a-staged-part-lane

## Intent

Since 0311, `ccp suite run --affected` runs a part lane declared with stages as declared. A worker of a product with
such a lane reads the same thing in the SPEC's Fail fast rule and in its prompt's Lanes line: the rule no longer says
`--affected` runs the part lane on the touched modules, and the prompt names `ccp suite run --affected` for that lane
as it does for a part lane declared as an argv. A language pack written against `AffectedReader` takes the `named`
keyword `ccp/suite.py` passes every reader, instead of failing with a `TypeError`.

## Context (not checked)

The open follow-ups of 0311 and 0319 (`QUEUE_ROOT=<queue> ccp --root . tasks follow-ups --open`) and the lead's
friction notes T100 and T101:

- `0311-…/review#1`, `/review-2#1`: §13.5's Fail fast bullet still says `--affected` "runs the part lane on the
  modules the branch's own change touches"; for a staged part lane it now runs the lane as declared (§14.7, signed in
  0311). Rewording it is a § change, so this brief carries the text for the operator to sign.
- `0311-…/implement#1`, `/review#2`, `/review-2#2`: `"def suite_lanes"` (`ccp/prompt.py`) renders a staged part lane
  as `` `--lane part` with nothing after `--` `` and `, as plane.json gives it`, without `ccp suite run --affected`;
  the argv branch adds `, or `ccp suite run --affected` for the modules a change touches`.
- 0311's second review, NIT (not a follow-up): the `"def affected_modules"` docstring (`ccp/suite.py`) says the count
  is "(else 0: plane.json declares the part role's lane)", while it is also 0 when no module is touched and when the
  pack has no suite count.
- `0319-…/implement#1`, `/review#1`, `/fix#1`, `/review-2#1`, `/verify#1`: `"AffectedReader = Callable"`
  (`ccp/doclang/__init__.py`) and its comment give three positional arguments; `ccp/suite.py` calls every reader with
  `named=unmatched` (`"reader(cfg.root, changed, _tracked_files(cfg.root), named=unmatched)"`), and the Python pack's
  `"def affected(root: Path, changed: list[str], files: list[str], *, named"` takes it.

Measured at `cd3a6bf5`: `python3 -B -c 'import ccp.doclang as d; print(getattr(d.AffectedReader, "_is_protocol", False))'`
printed `False`; `grep -c 'no module touched, no pack count' ccp/suite.py` printed `0`.

- **Ruled.**
  - `AffectedReader` becomes a `typing.Protocol` whose `__call__` takes `(root, changed, files, *, named=None)` and
    returns the test ids; its comment names `named` (the changed paths the product's map did not match, which alone
    are matched to tests by name, §14.7).
  - `"def suite_lanes"`: for the part role's lane declared with stages, `part_as` becomes
    `, as plane.json gives it, or `ccp suite run --affected`, which runs it as declared`. The test is
    `test_a_staged_part_lane_names_suite_run_affected` in `tests/test_full_lane_prompt.py` (class
    `DeclaredPartLane`), which asserts the token `ccp suite run --affected` in the implement and review Lanes lines.
  - The `affected_modules` docstring says "(else 0: no module touched, no pack count, or plane.json declares the part
    role's lane)".

## Scope

- **In:** `ccp/doclang/__init__.py` (`AffectedReader`); `ccp/prompt.py` (`suite_lanes`); `ccp/suite.py` (the
  `affected_modules` docstring); `tests/test_full_lane_prompt.py`; `docs/spec/02-delivery.md`, §13.5:

  CURRENT (`docs/spec/02-delivery.md` at `cd3a6bf5`), §13.5, the Fail fast bullet:
  > - **Fail fast.** Before the full suite, the implementer and fixer run a pre-gate: the product's `architect.checks` commands (rendered from plane.json), or, when plane.json `suite.lanes` declares a `pregate` lane, that lane through `ccp suite run --lane pregate` in their place, and `ccp suite run --affected --since origin/<integration>...` (§14.7), which runs the part lane on the modules the branch's own change touches or, when that change reaches most of the suite, the full lane in place of the pre-gate. It never stands in for the full suite, which runs on the final code and must be green.

  PROPOSED:
  > - **Fail fast.** Before the full suite, the implementer and fixer run a pre-gate: the product's `architect.checks` commands (rendered from plane.json), or, when plane.json `suite.lanes` declares a `pregate` lane, that lane through `ccp suite run --lane pregate` in their place, and `ccp suite run --affected --since origin/<integration>...` (§14.7), which runs what §14.7 names for the branch's own change: the part lane on the modules it touches, the part lane as declared when plane.json gives it stages, or, when that change reaches most of the suite, the full lane in place of the pre-gate. It never stands in for the full suite, which runs on the final code and must be green.

  Retired: "which runs the part lane on the modules the branch's own change touches or, when that change reaches most
  of the suite," (now the three cases §14.7 names).
- **Out:** what `--affected` runs (§14.7, 0311); a check that `suite.affected_map` lists every test reading
  plane.json; the other lanes' wording.

## dod_checks

- id: `code-01`
  story: As a worker on a product whose part lane has stages, my prompt names ccp suite run --affected for it.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_full_lane_prompt.DeclaredPartLane.test_a_staged_part_lane_names_suite_run_affected tests.test_full_lane_prompt`.
  expect: exit 0.
  dry run (`cd3a6bf5`): exit 1 (the named test does not exist yet: `AttributeError: type object 'DeclaredPartLane' has no attribute 'test_a_staged_part_lane_names_suite_run_affected'`).
- id: `code-02`
  story: As a language pack writer, the affected reader's type names the named keyword, and the count's docstring names every case.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `python3 -B -c 'import ccp.doclang as d; print(getattr(d.AffectedReader, "_is_protocol", False))'`.
    2. Run `grep -c 'no module touched, no pack count' ccp/suite.py`.
  expect: step 1 prints `True`; step 2 prints `1`.
  dry run (`cd3a6bf5`): step 1 printed `False`; step 2 printed `0`, exit 1.
- id: `spec-01`
  story: As the operator, §13.5's Fail fast rule says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0328`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`cd3a6bf5`, with this brief): exit 1, the PROPOSED passage missing (`not found in the SPEC`); `grep -c 'which runs the part lane on the modules the branch' docs/spec/02-delivery.md` printed `1`.

## Implementation notes

- `AffectedReader` (`ccp/doclang/__init__.py`) is a `typing.Protocol` whose `__call__` takes `(root, changed, files,
  *, named=None)`; its docstring, in place of the old comment, names `named`. The Python pack's `affected` already
  matches it; nothing else changed type.
- `suite_lanes` (`ccp/prompt.py`) appends `, or `ccp suite run --affected`, which runs it as declared` to the part
  role's lane when plane.json declares it and it is not an argv (so: stages); the argv branch is unchanged, and an
  undeclared part lane, or a declared lane of another role, gets no tail. The docstring says so.
- `test_a_staged_part_lane_names_suite_run_affected` (`DeclaredPartLane`) asserts the token in the implement and
  review Lanes lines, once in the verify line (a staged gate lane gets no tail), and not for an undeclared part lane.
- The `affected_modules` docstring and §13.5's Fail fast bullet carry the ruled and signed text.

## Verification notes
