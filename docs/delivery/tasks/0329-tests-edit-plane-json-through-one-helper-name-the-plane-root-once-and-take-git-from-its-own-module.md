---
task_id: 0329-tests-edit-plane-json-through-one-helper-name-the-plane-root-once-and-take-git-from-its-own-module
title: Tests edit the fixture's plane.json through one ToolkitFixture helper, name the plane root only as PLANE_ROOT, take the git runner from tests.git_helpers, pin the house-check import rule's package condition, and drop the retirement guards with no reader left; tests/CLAUDE.md names each helper module's concern, not its inventory
status: pending
kind: refactor
depends_on: []
rule_refs: ["E4"]
review_refs: ["ar-20261124T205520Z-4ce8#F06", "ar-20261124T205520Z-4ce8#F07", "ar-20261124T205520Z-4ce8#F09", "ar-20261124T205520Z-4ce8#F02", "ar-20261121T174754Z-7df5#F10"]
review_point: R34
paths: ["tests/", "docs/delivery/plane.json"]
clashes_with: ["0191-the-grace-release-ends", "0326-a-corrected-review-report-keeps-the-head-and-pr-its-run-was-opened-with", "0327-init-keeps-an-empty-task-log-in-git-and-checks-build-scratch-products-with-sandbox-create", "0328-the-fail-fast-rule-and-the-worker-prompt-name-suite-run-affected-for-a-staged-part-lane"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0329-tests-edit-plane-json-through-one-helper-name-the-plane-root-once-and-take-git-from-its-own-module

## Intent

A plane developer changing how tests reach the fixture or the plane checkout changes one place. A test that edits the
fixture's plane.json calls one `ToolkitFixture` helper that names the file through `config.CONFIG_REL`; the plane
root has one name, `PLANE_ROOT`, so a search for the tests that read a repo file finds them all, and E4's check
refuses a new alias; and every module takes the shared git runner from `tests.git_helpers`, so an edit to that runner
marks the tests that run it affected. The house-check import rule's package condition is pinned by a test, the
retirement guards whose retired thing no code reads any more are gone, and `tests/CLAUDE.md` names each helper module
and its concern without copying its names.

## Context (not checked)

Findings F06, F07 and F09 of architect pass `ar-20261124T205520Z-4ce8`
(`docs/delivery/reviews/ar-20261124T205520Z-4ce8.md`), the retirement guards of F02 (deferred as
`ar-20261121T174754Z-7df5` F10 until 0255 made `ToolkitFixture` cheap), and these open follow-ups
(`QUEUE_ROOT=<queue> ccp --root . tasks follow-ups --open`):

- `0324-…/implement#1`, `/review#1`, `/fix#1`, `/verify#1`: modules import `git` through `tests.toolkit_fixture` or
  `tests.architect_fixture`, so `ccp suite affected --paths tests/git_helpers.py` misses them.
- `0322-…/review#1`, `/fix#1`, `/review-2#1`: no test pins that `from <pkg> import test_x` counts as a test-module
  import only when `<pkg>` is `tests` or `.` (`"def _imports_test_module"` in `scripts/house_checks.py`).

Measured at `cd3a6bf5`:

- **F06.** `git grep -c 'json.loads((self.main / "docs/delivery/plane.json").read_text())' -- tests | wc -l`: 18
  files (27 lines); each then edits the dict and writes it back with `json.dumps`, to the main clone or the runner's.
  `git grep -c 'def edit_plane' -- tests/toolkit_fixture.py`: nothing.
- **F07.** `git grep -nP '^[A-Z_]+ = PLANE_ROOT\s*(#.*)?$' -- 'tests/*.py' | wc -l`: 35 (`PLANE` 21, `ROOT` 12,
  `REPO` 2), one per module, `tests/toolkit_fixture.py` among them;
  `git grep -nwP '^from tests\.\w+ import [^#\n]*\b(PLANE|ROOT|REPO)\b' -- 'tests/*.py' | wc -l`: 43 imports of such
  an alias; `git grep -nwP 'PLANE_ROOT as' -- 'tests/*.py' | wc -l`: 4 imports renaming it on the way in. E4's cmd
  names no `PLANE_ROOT`.
- **0324 follow-up.** `git grep -nwP '^from tests\.(toolkit_fixture|architect_fixture) import [^#\n]*\bgit\b' -- 'tests/*.py' | wc -l`:
  62, 57 of them test modules; `CCP_DEV=1 ./bin/ccp suite affected --paths tests/git_helpers.py 2>/dev/null | wc -l`:
  13, and 70 with those 57 added.
- **F09.** ``grep -o '`[A-Za-z_][A-Za-z_0-9]*`' tests/CLAUDE.md | sort -u | wc -l``: 61.
- **0322 follow-up.** In a scratch clone at `cd3a6bf5`, the mutant `return package and any(` → `return any(` in
  `scripts/house_checks.py` left `tests.test_self_hosting.TestModulesImportNoTestModule` passing (4 tests, OK).
- **The guards.** `git grep -nwF backstop -- ccp scripts plugin templates contracts | wc -l`: 0, and the same for
  `now.json` (the retired snapshot): 0. The other guards' retired things still have a reader: `docs-audit.json` in
  `ccp/queue.py`, `verify_stale_minutes` in `contracts/project.schema.json`, the `queue/` leftover in
  `ccp plane check --archive`, the old waiting reasons refused by `set-waiting-on`. The six modules ran 19 tests in
  15.2 s together (`python3 -B -m unittest` of each, at `cd3a6bf5`).
- **Ruled.**
  - `ToolkitFixture.edit_plane(self, edit, where: Path | None = None) -> dict` reads `self.main / config.CONFIG_REL`,
    calls `edit(cfg)` (which changes the dict in place), writes `json.dumps(cfg)` to `(where or self.main) /
    config.CONFIG_REL` and returns `cfg`. Commits and pushes stay with the callers. The 18 modules' reads and their
    local helpers (`plane_json`, `plane` and the like) call it; a local helper that only wrapped those three lines
    goes.
  - Every alias of the plane root goes: each module uses `PLANE_ROOT`, imported from `tests.helpers`, and the
    re-export `PLANE` in `tests/toolkit_fixture.py` goes. E4's cmd in `docs/delivery/plane.json` gains, after its
    other greps, `! git grep -nP '^[A-Z_]+ = PLANE_ROOT\s*(#.*)?$' -- 'tests/*.py'` and
    `! git grep -nwP 'PLANE_ROOT as' -- 'tests/*.py'`.
  - Every module that takes `git` from `tests.toolkit_fixture` or `tests.architect_fixture` imports it from
    `tests.git_helpers`.
  - `tests/CLAUDE.md` names each helper module, its concern and at most two entry points a new test reaches for;
    each module's docstring holds the rest.
  - `tests/test_self_hosting.py`, class `TestModulesImportNoTestModule`, gains
    `test_a_test_name_imported_from_another_package_is_not_a_test_import` (`from helpers import test_data` is not
    reported).
  - `tests/test_backstop_retired.py` goes. In `tests/test_snapshot_retired.py`, `test_the_snapshot_scripts_are_gone`,
    `test_no_command_writes_a_snapshot` and `test_an_old_snapshot_left_in_the_queue_is_ignored` go;
    `test_board_status_lists_a_wait_a_gate_and_a_question_and_exits_non_zero`, live behaviour, stays.
- No other test expectation changes.

## Scope

- **In:** `tests/toolkit_fixture.py` (`edit_plane`, the `PLANE` re-export); the 18 modules F06 names; the modules
  holding or importing a plane-root alias; the modules taking `git` from a fixture; `tests/CLAUDE.md`;
  `tests/test_self_hosting.py`; `tests/test_backstop_retired.py` (removed); `tests/test_snapshot_retired.py`;
  `docs/delivery/plane.json` (`architect.checks` `E4`'s cmd only).
- **Out:** literal `docs/delivery/plane.json` paths outside the 18 modules' edits (they ride with each module's next
  edit); `Product`'s own plane.json writes; the other retirement guards; the house rules' text.

## dod_checks

- id: `code-01`
  story: As a test writer, I edit the fixture's plane.json through one helper.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -c 'def edit_plane' -- tests/toolkit_fixture.py`.
    2. Run `git grep -c 'json.loads((self.main / "docs/delivery/plane.json").read_text())' -- tests`.
  expect: step 1 prints `tests/toolkit_fixture.py:1`; step 2 prints nothing (exit 1).
  dry run (`cd3a6bf5`): step 1 printed nothing, exit 1; step 2 printed 18 lines.
- id: `code-02`
  story: As a plane developer searching for the tests that read a repo file, the plane root has one name, and E4 refuses a new alias.
  setup: As `code-01`.
  steps:
    1. Run `git grep -nP '^[A-Z_]+ = PLANE_ROOT\s*(#.*)?$' -- 'tests/*.py'`.
    2. Run `git grep -nwP '^from tests\.\w+ import [^#\n]*\b(PLANE|ROOT|REPO)\b' -- 'tests/*.py'`.
    3. Run `python3 -B -c 'import json; c = [x["cmd"] for x in json.load(open("docs/delivery/plane.json"))["architect"]["checks"] if x["id"] == "E4"][0]; print(c.count("PLANE_ROOT"), c.count("PLANE_ROOT as"))'`.
    4. Run `git grep -nwP 'PLANE_ROOT as' -- 'tests/*.py'`.
  expect: steps 1, 2 and 4 print nothing (exit 1); step 3 prints `2 1`.
  dry run (`cd3a6bf5`): step 1 printed 35 lines; step 2 printed 43 lines; step 3 printed `0 0`; step 4 printed 4 lines.
- id: `code-03`
  story: As a plane developer, an edit to the shared git runner marks the tests that run it affected.
  setup: As `code-01`, with a scratch `QUEUE_ROOT`.
  steps:
    1. Run `git grep -nwP '^from tests\.(toolkit_fixture|architect_fixture) import [^#\n]*\bgit\b' -- 'tests/*.py'`.
    2. Run `CCP_DEV=1 ./bin/ccp suite affected --paths tests/git_helpers.py 2>/dev/null | wc -l`.
  expect: step 1 prints nothing (exit 1); step 2 prints a number of at least 65.
  dry run (`cd3a6bf5`): step 1 printed 62 lines; step 2 printed `13`.
- id: `code-04`
  story: As a plane developer, the house check's import rule counts `from <pkg> import test_x` only for the tests package, and a test kills the mutant that drops that condition.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_self_hosting.TestModulesImportNoTestModule.test_a_test_name_imported_from_another_package_is_not_a_test_import`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_self_hosting.TestModulesImportNoTestModule --mutant 'scripts/house_checks.py:return package and any(=>return any('`.
  expect: step 1 exits 0; step 2 reports the mutant `killed`.
  dry run (`cd3a6bf5`): step 1 exit 1 (`AttributeError: type object 'TestModulesImportNoTestModule' has no attribute 'test_a_test_name_imported_from_another_package_is_not_a_test_import'`); step 2 n/a — it needs the verifier's open run (the mutant survived at `cd3a6bf5`, Context).
- id: `code-05`
  story: As a plane developer, the retirement guards whose retired thing no code reads are gone, and the live check beside them stays.
  setup: As `code-01`.
  steps:
    1. Run `test -e tests/test_backstop_retired.py; echo $?`.
    2. Run `grep -c 'def test' tests/test_snapshot_retired.py`.
  expect: step 1 prints `1`; step 2 prints `1`.
  dry run (`cd3a6bf5`): step 1 printed `0`; step 2 printed `4`.
- id: `doc-01`
  story: As a test writer, tests/CLAUDE.md tells me which helper module holds a concern without copying its names.
  setup: As `code-01`.
  steps:
    1. Run ``grep -o '`[A-Za-z_][A-Za-z_0-9]*`' tests/CLAUDE.md | sort -u | wc -l``.
  expect: prints a number of at most 25.
  dry run (`cd3a6bf5`): printed `61`.

## Implementation notes

- `ToolkitFixture.edit_plane(edit, where=None)` reads the main clone's plane.json, calls `edit(cfg)`, writes `json.dumps(cfg)` to
  `(where or main)/config.CONFIG_REL` (creating the directory, as `write` does) and returns `cfg`. The 18 modules' reads call it;
  `notify_fixture.set_plane`, `parallel_claims_fixture.plane`, `test_clashes_with.Fixture.plane`, `test_usage_reading`'s
  setter and `test_behind_tip_catch_up.plane_json` keep their names (the last still commits and pushes) and call it.
  The one remaining match of F06's grep, `test_the_template_holds_the_classs_own_plane_json`, only reads: it names the file
  through `config.CONFIG_REL`.
- Left as they were, under the task's Out: `tests/test_tasks_close.py`'s three reads of the runner's plane.json
  (`self.runner / ...`) and the literal paths in other tests' writes.
- The plane root's aliases (`PLANE`, `ROOT`, `REPO`: 35 definitions, 43 imports, 4 renaming imports) became `PLANE_ROOT`,
  taken from `tests.helpers`; the `PLANE` re-export in `tests/toolkit_fixture.py` is gone. Function-local imports of an alias
  and of `git` from a fixture (14, in 4 modules) follow too. `from ccp.queue import PLANE` is the product's own name and stays.
- The 62 module-level `git` imports from `tests.toolkit_fixture` and `tests.architect_fixture` came from `tests.git_helpers`.
  `ccp suite affected --paths tests/git_helpers.py` now lists 72 modules.
- E4's cmd gained the two greps the task gives.
- `tests/CLAUDE.md` holds 14 backticked names; the detail it dropped moved into each helper module's docstring.
- `tests/test_backstop_retired.py` is removed, and `tests/test_snapshot_retired.py` keeps the live board-status test (its docstring
  now says so).

- Fix round 1: `TemplatesAndContracts.PLANE = PLANE_ROOT` in `tests/test_rules.py` was a surviving class-attribute alias; it is gone
  and its two tests name `PLANE_ROOT`. `tests/git_helpers.py`'s docstring keeps "(a few older private runners remain)", which the
  move from `tests/CLAUDE.md` had dropped. E4's column-0 anchors are left as the task gives them (reported as a follow-up).

## Verification notes
