---
task_id: 0284-shared-test-fixtures-live-in-modules-that-hold-no-tests
title: Shared test fixtures live in modules that hold no tests, no test module imports another, and the brief-rule test counts only each rule's own token
status: pending
kind: refactor
depends_on: []
clashes_with: ["0268-the-local-pr-record-keeps-the-plane-s-state-words-and-writes-ledger-events", "0270-the-friction-trigger-counts-noted-tasks-and-scales-with-tasks-in-flight", "0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope", "0276-docs-contract-and-template-leftovers-of-r15-and-r17", "0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log"]
rule_refs: ["E4"]
review_refs: ["ar-20261122T055103Z-11aa#F05", "ar-20261122T055103Z-11aa#F10"]
review_point: R25
paths: ["tests/", "docs/ENGINEERING.md", "docs/delivery/plane.json"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0284-shared-test-fixtures-live-in-modules-that-hold-no-tests

## Intent

A test edit in one module stays an input of that module alone: no test module imports another, so the
gate's cache and `ccp suite affected` stop treating an edited test module as every module's input. Every
shared fixture and helper lives in a module that holds no tests and is listed in `tests/CLAUDE.md`, so a
writer finds it instead of copying it. House rule E4 says so and its command holds it. Three test gaps
found by workers close on the way: a brief may use a common phrase such as "merge base" twice, the
bold-lead decision mark `**D1**` has a test, and the PR-host test no longer exempts `ccp/init.py`.

## Context (not checked)

From architect pass `ar-20261122T055103Z-11aa`, F05 (`test-cost`) and F10 (`test-brittle`), and house
rule E4 as that pass proposed it (applied with this task); the record is in `docs/delivery/reviews/`. Also
the worker follow-ups `0264-one-parser-for-signed-blocks-and-task-id-patterns/review#1`, `…/fix#1` and
`…/verify#1` (the bold-lead mark untested) and `0266-github-knowledge-stays-in-the-pr-host-module/implement#1`,
`…/review#1`, `…/fix#1` and `…/verify#1` (the `ccp/init.py` exemption).

Measured at `072d9f9`.

- **Test modules imported by others.** With the pattern
  `^[[:space:]]*(from tests\.test_|from tests import test_|import tests\.test_|from \.test_)`:
  `git grep -lE '<pattern>' -- tests | wc -l` at `072d9f9`: 136 files; `git grep -nE '<pattern>' -- tests | wc -l`: 218 lines;
  `git grep -hoE …` over the same pattern, the distinct sources: 34 names, of which 33 are modules (`test_architect`, `test_backfill`,
  `test_binding_reader`, `test_board`, `test_board_drill`, `test_board_quality`, `test_board_seats`, `test_estimate`,
  `test_gate_cache`, `test_gate_parallel`, `test_gate_time`, `test_health`, `test_init`,
  `test_init_permissions`, `test_notify`, `test_parallel_claims`, `test_report_fields`, `test_review_points`,
  `test_rotation`, `test_sandbox`, `test_suite`, `test_suite_stages`, `test_sync_on_release`, `test_team_hosting`,
  `test_toolkit`, `test_upgrade`, `test_usage`, `test_usage_advice`, `test_verify`, `test_verify_as_written`,
  `test_verify_cache`, `test_worker_efficiency`, `test_wt`), of `ls tests/test_*.py | wc -l` at `072d9f9`: 205 test modules.
  The 34th name, `test_helper`, is no module: `tests/test_gate_cache.py` writes `from tests.test_helper import VALUE`
  inside a fixture string (its `HELPER` users), where a later string writes `from {pkg} import test_helper`.
- **What the gate counts.** `scripts/gate_parallel.py`'s `shared_tests` also reads a dotted `tests.test_x` in any
  string: `cd scripts && python3 -B -c 'import gate_parallel as g; print(len(g.shared_tests(g.modules())))'` at `072d9f9`: 35,
  the source modules above plus `tests.test_behind_tip_catch_up` and `tests.test_catch_up_decision`, each named in
  the other's module docstring.
- **Clashes.** Pending tasks whose `paths` name one of the source modules above (a `python3` scan of each pending
  task's `paths` against them at `072d9f9`): 0268 (`tests/test_toolkit.py`), 0270 (`tests/test_architect.py`,
  `tests/test_board_quality.py`), 0275 (`tests/test_review_points.py`), 0276 (`tests/test_worker_efficiency.py`)
  and 0282 (`tests/test_usage.py`). Each edits the module this task moves fixtures out of, so `clashes_with`
  names all five; 0268, 0270 and 0275 have signed briefs, so the clash is recorded here only (it is symmetric).
  `tests.test_toolkit` (47 tests) alone has 90 importers (`git grep -h '^from tests.test_toolkit import' -- tests | wc -l` at `072d9f9`).
- **Why it costs.** `scripts/gate_parallel.py`'s docstring: "A test module some test module imports (a
  shared helper) is an input of every module." `tests/CLAUDE.md`'s "Shared fixtures" names four fixtures
  that sit in test modules (`ToolkitFixture`, `TeamCase`, `InitCase`, `GateFixture`); it does not name
  `UpgradeFixture`, `SuiteFixture`, `WtFixture`, `RotationFixture` or `SandboxCase`.
- **The copied fixture.** `tests/test_gate_cache.py`'s `CacheFixture(GateFixture)` writes
  `.gitignore` `__pycache__/` ("as the plane's own repo has it"); `GateFixture` does not.
  `tests/test_verify_cache.py` defines a second, unrelated `class CacheFixture(ToolkitFixture)`.
- **F10.** `tests/test_plugin.py` `WorkerRules.test_each_worker_brief_states_each_rule_once` asserts
  `text.count(t) == 1` for every token of every rule in `WORKER_RULES`; `LESSONS` already counts only the
  last token, "the one only that rule uses".
- **The bold-lead mark.** `ccp/adr.py`'s `"_MARK_END = r"` has `\*\*` alternatives for a mark whose bold
  closes right after the id (`**D1**: First`). `tests/test_adr_decisions.py`'s `BOLD` writes `**D1 — First**`,
  which the dash alternative matches; per the 0264 reviewer, removing the `\*\*` alternatives survives
  `tests.test_adr` and `tests.test_adr_decisions`.
- **The init exemption.** `tests/test_prhost_only.py` `"ADAPTER_MODULES = {"` holds `ccp/prhost.py` and
  `ccp/init.py` ("the permission list and init warning"). A probe at `65065dc`
  (`python3 -B -c '…forge_literals(Path("ccp/init.py"))'`): `[]`; init's only forge text is `gh repo delete` in `DENY`.
- **E4's long-literal count** stays as `architect.checks` `E4` has it (at most 345 lines;
  `LC_ALL=C git grep -hE 'assert(Not)?In\("[^"]{40,}' -- 'tests/*.py' | wc -l` at `072d9f9`: 344) unless the operator's answer to this triage's
  question on F06 changes it; the lead then amends this brief before the claim.
- **Other tasks.** Most pending tasks add tests; one that adds a module importing a test module after
  this task merges fails the new E4 command at its catch-up, and its worker imports the fixture module instead.

### Rulings for the build (the lead's)

- Each source module's shared names (classes, helpers and constants other modules import) move together
  into one module that holds no tests, `tests/<source name without test_>_fixture.py` (new), such as
  `tests/toolkit_fixture.py`; a source whose shared names are only constants and functions under 30 lines
  each moves them into `tests/helpers.py` instead. Two sources whose fixture modules would share a name
  keep distinct class names (the two `CacheFixture`s: the gate-cache one becomes `GateCacheFixture`). No
  re-export stays in the source test module.
- `GateFixture` writes `.gitignore` `__pycache__/` itself; `CacheFixture` no longer does.
- `tests/test_gate_cache.py`'s fixture string `from tests.test_helper import VALUE` becomes
  `from {pkg}.test_helper import VALUE`, as its later `from {pkg} import test_helper` string is written,
  and its call site writes it with `USER.format(pkg="tests")` (`self.module("test_user", USER)` at
  `tests/test_gate_cache.py:163`), so the module it writes is unchanged.
- The module docstrings of `tests/test_behind_tip_catch_up.py` and `tests/test_catch_up_decision.py` name each
  other in words ("the catch-up decision tests", "the close-path tests"), not as `tests.test_…`.
- `tests/CLAUDE.md`'s "Shared fixtures" lists every fixture module with its classes, one line each.
- House rule E4 becomes, in `docs/ENGINEERING.md` (the architect's text): "A test checks behaviour, not
  wording: no assertion on prose, help text or prompt text beyond the token it pins. A test names a plane
  constant or shared fixture fact (the worktrees directory, a binding) through the code or a fixture helper,
  never as a copied literal. A fixture or helper other modules reuse lives in a module that holds no tests;
  no module imports a test module or binds another module's test-class methods." Its `check:` line names
  the new grep, and `architect.checks` `E4` appends
  `&& ! git grep -nE '^[[:space:]]*(from tests\\.test_|from tests import test_|import tests\\.test_|from \\.test_)' -- tests`
  (JSON-escaped in plane.json). The rules doc stays within its 150-line budget.
- `WorkerRules` asserts every token present and only the last token of each rule exactly once, through a
  plain function over a brief's text (`rule_count_errors(text)`), unit-tested on synthetic text.
- `ADAPTER_MODULES` is `{"ccp/prhost.py"}`, with its comment naming only the adapter.

## Scope

- **In:** `tests/` (the 33 source modules, the 136 importing modules, the two catch-up modules' docstrings, `tests/helpers.py`, the new
  `tests/*_fixture.py` modules, `tests/CLAUDE.md`, `tests/test_plugin.py`, `tests/test_adr_decisions.py`,
  `tests/test_prhost_only.py`, `tests/test_gate_parallel.py`, `tests/test_gate_cache.py`),
  `docs/ENGINEERING.md` (E4), `docs/delivery/plane.json` (`architect.checks` `E4`).
- **Out:** sentence assertions (the roadmap's deferred `ar-20261120T234012Z-27eb` F10); private-name
  patches (F11, rejected); the gate's cache keys; any `ccp/` or `scripts/` file.

## dod_checks

- id: `code-01`
  story: As the gate's cache, no test module is an input of another.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nE '^[[:space:]]*(from tests\.test_|from tests import test_|import tests\.test_|from \.test_)' -- tests; echo "exit=$?"`.
    2. Run `python3 -B -c "import json;print([c['cmd'].count('from tests') for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E4'])"`.
    3. Run `cd scripts && python3 -B -c 'import gate_parallel as g; print(sorted(g.shared_tests(g.modules())))'`.
  expect: step 1 prints only `exit=1`; step 2 prints `[2]`; step 3 prints `[]`.
  dry run (`072d9f9`): step 1 printed 218 lines and `exit=0`; step 2 printed `[0]`; step 3 printed a list of 35 modules.
- id: `code-02`
  story: As a test writer, every shared fixture module is listed where I look first, and none holds a test.
  setup: A checkout of the PR head.
  steps:
    1. Run `for f in tests/*_fixture.py; do grep -q "$(basename $f)" tests/CLAUDE.md || echo "unlisted $f"; grep -l 'def test_' $f; done; echo done`.
  expect: prints only `done`.
  dry run (`072d9f9`): no fixture module exists yet, so the glob stays literal: printed `unlisted tests/*_fixture.py`, a grep error, then `done`.
- id: `cmd-01`
  story: As a brief writer, a common phrase used twice passes, and a rule's own token used twice fails.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_plugin 2>&1 | grep -e rule_count -e '^OK'`.
  expect: prints, each `ok`, a test where a brief text holding every rule with "merge base" twice gives no error from `rule_count_errors`, and one where a rule's last token appears twice names that rule and token; then `OK`.
  dry run: n/a — the tests are new.
- id: `cmd-02`
  story: As an ADR writer, a decision mark whose bold closes after its id is found.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_adr_decisions 2>&1 | grep -e bold -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_adr_decisions --mutant-file <file>`, the file's mutant removing both `\*\*` alternatives from `_MARK_END` in `ccp/adr.py`.
  expect: step 1 prints, `ok`, a test where an ADR whose decisions are written `**D1**: First` and `**D2** Second` lists both decisions; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the test is new.
- id: `cmd-03`
  story: As the PR-host rule's test, only the adapter is exempt.
  setup: A checkout of the PR head.
  steps:
    1. Run `grep -n 'ADAPTER_MODULES = ' tests/test_prhost_only.py; python3 -B -m unittest -q tests.test_prhost_only 2>&1 | tail -1`.
  expect: the first line holds `{"ccp/prhost.py"}` and no `ccp/init.py`; the last line is `OK`.
  dry run (`072d9f9`): printed the set with both modules, then `OK`.
- id: `cmd-04`
  story: As a gate test, the gate fixture ignores bytecode as the plane's repo does.
  setup: A checkout of the PR head.
  steps:
    1. Run `grep -c '__pycache__' tests/gate_parallel_fixture.py; python3 -B -m unittest -q tests.test_gate_parallel tests.test_gate_cache tests.test_gate_time 2>&1 | tail -1`.
  expect: the count is at least 1; the last line is `OK`.
  dry run: n/a — `tests/gate_parallel_fixture.py` is new.

## Implementation notes

## Verification notes
