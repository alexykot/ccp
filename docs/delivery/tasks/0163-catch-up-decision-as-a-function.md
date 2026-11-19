---
task_id: 0163-catch-up-decision-as-a-function
title: Close's catch-up decision as a pure function with unit tests, and the shared test fixtures documented
status: done
kind: refactor
depends_on: ["0162-git-merge-helper"]
spec_refs: ["S16", "S21"]
review_refs: ["sh-20261119T072530Z-663f#F03", "sh-20261119T072530Z-663f#F09"]
review_point: R11
paths: ["ccp/lifecycle.py", "tests/test_catch_up_decision.py", "tests/CLAUDE.md"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0163-catch-up-decision-as-a-function

## Intent

Whether `ccp tasks close` may catch a verified head up itself (§16.5 rule 4) is decided by one
function on plain values, tested in milliseconds, so the patch-id branch and the schedule switch that
ADR-0042 adds to close are each a unit test, not another end-to-end test in the suite's slowest
module. The tests' package doc names the fixtures modules really share and the rule for reusing one.
Nothing the plane does changes.

## Context (not checked)

- Shape report `sh-20261119T072530Z-663f`, findings F03 and F09; this is its task T2. The task that
  builds close's catch-up by patch id under `parallel.schedule: clashes` depends on this one and
  extends the function's inputs (the patch-id match, the schedule).
- F03: `_catch_up` in `ccp/lifecycle.py` mixes three decisions with git, worktree and gate I/O. Each is
  a `_NoCatchUp` raise: `git grep -n "no declared paths: \|overlap: the tip\|build sign-off: the tip" -- ccp` at `b9e58ce`:
  3 lines, all in `_catch_up` (`"no declared paths: the task declares no `paths`..."`, before the gate-lane
  check; `"overlap: the tip's new commits change ..."` and `"build sign-off: the tip's new commits change ..."`,
  inside the catch-up loop after the merge commit is made).
- The order of refusals is behaviour (a test reads which condition is named first):
  `tests/test_sign_off_beyond_intent.py` `test_a_verdict_listing_text_beyond_intent_no_longer_refuses_the_catch_up_by_itself`
  calls `lifecycle._catch_up` directly and expects "no gate lane", not "sign-off". So `_catch_up`'s name,
  signature and `_NoCatchUp` stay, and the "no declared paths" condition is still judged before the gate lane.
- The end-to-end tests do not reach every branch: with `_catch_up`'s `f in own or` dropped (a file the task's
  own diff changes but does not declare), `test_a_tip_changing_a_file_the_task_changes_refuses_naming_overlap`
  and `test_a_tip_renaming_a_file_the_task_changes_refuses_naming_overlap` still passed at `b9e58ce`
  (`python3 -B -m unittest -q` of the two, in a scratch copy: `OK`), because their file is also declared.
  The unit tests close that gap.
- Cost: `tests.test_behind_tip_catch_up` at `b9e58ce`: 38 tests in 102 s (`/usr/bin/time -p python3 -B -m unittest -q tests.test_behind_tip_catch_up`).
  This task adds no test to it.
- F09: `tests/CLAUDE.md` says every test builds its product with `helpers.py`'s `Product`. Measured at `b9e58ce`:
  `git grep -l "from tests.helpers import\|from tests import helpers" -- tests | wc -l`: 66 modules;
  `git grep -hoE "^from tests\.test_[a-z_]+ import" -- tests | sort | uniq -c` at `b9e58ce`: 57 import from `tests.test_toolkit` (`ToolkitFixture`, a bare origin, a clone and a runner worktree with a fake `gh`), 8 from `tests.test_team_hosting` (`TeamCase`), 4 from `tests.test_init` (`InitCase`), and others from `test_board_quality`, `test_board_drill`, `test_verify`, `test_suite`.
- F09's proposed reuse rule ("import a fixture module, never a TestCase class by name, because that makes
  discovery run its tests twice") is not what the suite does, and the double run does not happen today: an
  AST scan of every `from tests.test_* import` at `b9e58ce` finds 13 imports of a `TestCase` subclass by name
  (`GateFixture`, `InitCase`, `TeamCase`), and `unittest.TestLoader().getTestCaseNames` of each is `[]`: they hold
  no tests, so nothing runs twice. The rule this task writes is the one that prevents the double run: a fixture
  shared across modules is a class with no test methods, imported by name; a class that holds tests is never
  imported into another module. No test module changes.
- No SPEC change: the refusal texts and their order are close's catch-up rule (§16.5) as it stands.
- House rules this follows (docs/ENGINEERING.md): E15 (decision logic separate from I/O), E4 (fixtures).

## Scope

- **In:**
  - `ccp/lifecycle.py`: a pure function `catch_up_blocked(declared, tip_files, task_files, shared, signed_due) -> str | None`
    returns the first condition that fails, with today's text, in today's order (no declared paths; overlap;
    build sign-off), or None. It does no git, file or queue access, and reads `parallel.meets` and
    `parallel.covered` only. `_catch_up` calls it before the gate-lane check with empty file lists (only the
    declared-paths condition can fail there) and in the loop with the tip's and task's files, and raises
    `_NoCatchUp` with what it returns. The three texts appear in `ccp/lifecycle.py` only inside the function.
    `_catch_up`'s docstring points at the function for the conditions.
  - `tests/test_catch_up_decision.py` (new), plain values only (no repository, subprocess or temp dir): no
    declared paths; a tip file the task's own diff changes but does not declare; a tip file under a declared
    directory the diff leaves; a tip file covered by `shared` (no overlap); a build sign-off due with the tip
    changing a `shared` file the task changes (refused, naming it); a build sign-off due with a disjoint tip
    (allowed); with several conditions failing, the first in order is named; texts list at most five files.
  - `tests/CLAUDE.md`: names the fixture families (`helpers.py`'s `Product`; `test_toolkit.py`'s
    `ToolkitFixture`; the `TestCase` bases without tests in `test_team_hosting.py`, `test_init.py` and
    `test_gate_parallel.py`), what each builds in a line, and the reuse rule from Context.
  - No existing test changes.
- **Out:**
  - The patch-id input, `parallel.schedule`, or any change to a condition (the close-by-patch-id task).
  - The merge, union, gate and push steps of `_catch_up`.
  - Moving existing end-to-end tests out of `tests/test_behind_tip_catch_up.py`.
  - docs/ENGINEERING.md (E4's text is the lead's).

## dod_checks

- id: `cu-01`
  story: As a plane developer, each catch-up condition is a unit test on plain values.
  setup: a checkout of the PR head.
  steps:
    1. Run `/usr/bin/time -p python3 -B -m unittest -q tests.test_catch_up_decision`.
    2. Run `git grep -nwE "subprocess|tempfile|ToolkitFixture" -- tests/test_catch_up_decision.py`.
  expect: step 1 exits 0 with a test for each case in Scope and `real` under 1.0 s; step 2 prints nothing.
  dry run: n/a (new module).
- id: `cu-02`
  story: As a plane developer, close's conditions live in the function alone.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n "no declared paths: \|overlap: the tip\|build sign-off: the tip" -- ccp`.
  expect: exactly 3 lines, all in `ccp/lifecycle.py`, all inside `def catch_up_blocked`.
  dry run (`b9e58ce`): 3 lines, `ccp/lifecycle.py` 1529, 1555, 1558, inside `_catch_up`.
- id: `cu-03`
  story: As a runner, close catches up and refuses exactly as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_behind_tip_catch_up tests.test_sign_off_beyond_intent tests.test_sign_off tests.test_parallel_merging`.
    2. Run `git diff --name-only origin/main...HEAD -- tests/`.
  expect: step 1 exits 0; step 2 lists only `tests/CLAUDE.md` and `tests/test_catch_up_decision.py`.
  dry run (`b9e58ce`): step 1's modules passed (catch-up 38 tests in 102 s; `test_sign_off` 38 tests OK; `test_sign_off_beyond_intent` and `test_parallel_merging` OK in a run with the review modules).
- id: `cu-04`
  story: As a plane developer, the unit tests catch the branch the end-to-end tests miss.
  setup: a separate copy of the PR head (not the branch's worktree) with `f in own or` (the task's own files) removed from `catch_up_blocked`'s overlap test.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_catch_up_decision`.
  expect: exit non-zero, the failing test the one with a tip file the task changes but does not declare.
  dry run (`b9e58ce`): the same mutation in `_catch_up` left the two end-to-end overlap tests passing (`OK`), the gap this check closes; the new module is n/a.
- id: `cu-05`
  story: As a test author, the package doc tells me which fixtures to reuse and how.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -c "ToolkitFixture\|TeamCase\|InitCase\|GateFixture\|Product" tests/CLAUDE.md` and read the reuse rule there.
  expect: the count is at least 5, and the doc says a shared fixture holds no test methods and a class that holds tests is never imported into another module.
  dry run (`b9e58ce`): 1 (only `Product`).
- id: `suite-01`
  story: As a plane developer, the plane's own checks still pass.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: the three checks exit 0 and the branch list is empty.
  dry run (`b9e58ce`): `ccp docs check` printed `docs: clean`.

## Implementation notes

*Append-only, newest last.*

- `catch_up_blocked(declared, tip_files, task_files, shared, signed_due)` sits just above `_catch_up` in
  `ccp/lifecycle.py` and imports `ccp.parallel` lazily, as the module does elsewhere. `_catch_up` calls it with
  empty lists before the gate-lane check (so "no declared paths" is still judged before "no gate lane") and in
  the loop with the tip's and task's files. The three texts moved verbatim.
- Premise check at `cf65d46`: the three `git grep` lines, the 66 `helpers` importers and the imports of
  `test_toolkit` (58, against 57 at `b9e58ce`: one more importer since) hold. `tests/CLAUDE.md` states no count,
  so the figures cannot go stale there.
- `tests/CLAUDE.md` also loses its claim that every test builds its product with `Product`, which the 58
  `ToolkitFixture` importers contradict; `Product` is now one entry of the fixtures list.
- The task's Scope names `GateFixture` under "the `TestCase` bases without tests"; it lives in
  `test_gate_parallel.py` as written and is listed there.

## Verification notes
- 2026-11-19 — verifier, PR #183 head `9320539` (squash `9b59aa6`): APPROVE. Passed: cu-01, cu-02, cu-03, cu-04, cu-05, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0163-catch-up-decision-as-a-function.json.

