---
task_id: 0295-package-docs-name-rules-by-id-and-every-test-module-is-a-cache-leaf
title: Package docs name house rules by id, tests/CLAUDE.md keeps only the fixtures worth naming, contracts/CLAUDE.md drops snapshots, fixtures write test modules with def test_, and the gate cache treats every test module as a leaf
status: done
kind: refactor
depends_on: []
rule_refs: ["E26", "E4"]
review_refs: ["ar-20261122T100027Z-dd31#F05", "ar-20261122T100027Z-dd31#F08", "ar-20261122T100027Z-dd31#F09", "ar-20261122T100027Z-dd31#F10", "ar-20261122T100027Z-dd31#F11"]
review_point: R26
paths: ["tests/CLAUDE.md", "scripts/CLAUDE.md", "ccp/doclang/CLAUDE.md", "contracts/CLAUDE.md", "scripts/gate_parallel.py", "tests/test_gate_cache.py", "tests/helpers.py", "tests/gate_parallel_fixture.py", "tests/suite_fixture.py", "docs/ENGINEERING.md"]
clashes_with: ["0191-the-grace-release-ends", "0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s", "0289-the-runner-s-actor-id-is-named-once-and-tests-read-the-lead-s", "0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0295-package-docs-name-rules-by-id-and-every-test-module-is-a-cache-leaf

## Intent

A house rule is stated once (E26): the package docs name E4, E7 and E18 by id instead of restating
them, so amending a rule edits one place. `tests/CLAUDE.md` tells a writer where fixtures live and
names only the fixtures with something to say, not one line per fixture module. `contracts/CLAUDE.md`
lists only formats the directory holds. Fixtures that write test modules spell their methods
`def test_`, without a renaming helper kept for a one-off check. The gate's test cache no longer scans
test modules for imports of other test modules, which E4 now forbids: every test module is an input
of itself alone. Behaviour of the suite and the cache does not change for any tree E4 accepts.

## Context (not checked)

From the triage of architect pass `ar-20261122T100027Z-dd31` (F05, F08, F09, F10, F11; the record is in
`docs/delivery/reviews/`). Measured at `954bd72` (first at `e92f362`; re-measured when the follow-ups below were folded in): every figure holds,
except that 0290 added `tests/test_fence.py`'s docstring "shared helpers", which the F08 grep's `shared helper` matches, so `code-02` names its two files.
E26's own text and check grep were amended in that triage's PR.

- **Restated rules (F05).** `git grep -n 'only wrap\|imports another\|copied literal\|names no language' -- '*/CLAUDE.md'` at `e92f362`: 5 lines:
  `ccp/doclang/CLAUDE.md` (E18: "core code names no language and no test runner"), `scripts/CLAUDE.md` (E7: "a script here only
  wraps `ccp` or Git"), `tests/CLAUDE.md` (E4: "No test module imports another" twice, "never as a copied literal"). The
  last paragraph of `tests/CLAUDE.md` ("**Reuse rule.**") restates E4's fixture and binding sentences at length. E7's amendment
  is an open question for the operator (question five of `ar-20261122T055103Z-11aa`); naming E7 by id leaves nothing to update when it lands.
- **The fixture list (F09).** `wc -l < tests/CLAUDE.md` at `e92f362`: 64 lines; `grep -c 'set up for the\|a .TestCase. base for the' tests/CLAUDE.md` at `e92f362`: 8
  one-liners that repeat their module's name. 0284's `code-02` required every `*_fixture.py` to be named there; that was
  a done task's check, not a standing one.
- **The renaming helper (F10).** `git grep -n 'with_test_methods\|def t_' -- tests` at `e92f362`: 18 lines (in `tests/gate_parallel_fixture.py`,
  `tests/suite_fixture.py`, `tests/helpers.py` and `tests/CLAUDE.md`). It exists because 0284's `code-02` grepped fixture modules
  for the text `def test_`. A `*_fixture.py` module is not collected by unittest discovery (`test*.py`), and E4's command judges
  real imports, so a `def test_` inside a fixture's string is harmless.
- **The shared-test-module rule (F08).** `scripts/gate_parallel.py` holds `DOTTED_RE`, `FROM_PKG_RE`, `FROM_REL_RE` and
  `"def shared_tests"`, and its docstring says "A test module some test module imports (a shared helper) is an input of every
  module": `git grep -n 'shared_tests\|DOTTED_RE\|FROM_PKG_RE\|FROM_REL_RE\|shared helper\|test_helper' -- scripts tests` at `e92f362`: 16 lines
  (in `scripts/gate_parallel.py` and `tests/test_gate_cache.py`). Since 0284, plane.json `architect.checks` `E4` fails on any import
  of a test module. `tests/test_gate_cache.py`'s `test_a_test_module_another_imports_is_everyones_input`,
  `test_a_helper_named_by_from_tests_import_is_everyones_input` and `test_a_helper_named_by_from_dot_import_is_everyones_input`
  build exactly that forbidden shape; `test_editing_one_test_module_reruns_only_it` holds the leaf rule.
  No `ccp` module reads `shared_tests`: `git grep -n 'shared_tests\|gate_parallel' -- ccp` at `e92f362`: no line.
- **The known-intentional note.** `docs/ENGINEERING.md`'s *Known intentional* entry on the gate cache says the shared inputs
  are "every tracked and untracked file but the test modules no other imports"; after this task that is "but the test modules".
- **snapshots (F11).** `contracts/CLAUDE.md`'s first paragraph lists "snapshots" among the queue records with a schema;
  the snapshot schema was removed by 0253, and `git grep -il snapshot -- 'contracts/*.json'` at `e92f362`: no file.
- **Follow-ups folded in.** `tests/CLAUDE.md` is rewritten here, so three open follow-ups about it land here too:
  `0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s/implement#1`, `/review#3` and `/fix#3` (the list of
  `helpers.py` constants does not name `LEAD_ENV` or `as_lead()`), and
  `0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily/implement#2` (it does not say that `helpers.py`
  loads no `ccp` module on import, or that a module takes the plane root from `PLANE_ROOT`).
  `grep -cE 'LEAD_ENV|as_lead|loads no .ccp. module' tests/CLAUDE.md` at `954bd72`: 0. `tests/helpers.py` defines `LEAD_ENV`
  (a PEP 562 module attribute) and `"def as_lead"`; `tests/test_fence.py`'s `test_importing_the_helpers_loads_no_ccp_module` holds the lazy import.
- **Other tasks.** 0288, 0289 and 0293 change `tests/helpers.py` and `docs/ENGINEERING.md` (E27 only); 0290 changes `tests/helpers.py`,
  `tests/gate_parallel_fixture.py` and `tests/suite_fixture.py`. Recorded as clashes.

### Rulings for the build (the lead's)

- `ccp/doclang/CLAUDE.md`, `scripts/CLAUDE.md` and `tests/CLAUDE.md` replace each restated sentence with a pointer to the rule
  id ("(E18)", "(E7)", "(E4)"), keeping the where-to-find guidance. `tests/CLAUDE.md`'s **Reuse rule.** paragraph becomes one
  sentence naming E4 and saying a helper a second module needs moves to a fixture module first.
- `tests/CLAUDE.md` keeps the bullets for `Product`, `binding`, `done_report`, `FoldRuns` and `BoardPage`, the shared constants,
  `ToolkitFixture` (with its shared build), `ReviewFlow` and `SkipFlow`, and replaces the other fixture bullets with one
  sentence: each `<name>_fixture.py` holds the fixture `test_<name>.py` and its neighbours share, and its class docstring says
  what it builds.
- The shared-constants bullet of `tests/CLAUDE.md` names `LEAD_ENV` and `as_lead()` (the environment with the lead's `ACTOR`, for a
  call to a command only the lead may run) and says, in one sentence, that `helpers.py` loads no `ccp` module on import, so the
  fence in `tests/__init__.py` comes first, and that a module takes the plane root from `PLANE_ROOT` and git's identity from `GIT_ENV`.
- The fixtures in `tests/gate_parallel_fixture.py` and `tests/suite_fixture.py` write `def test_` directly; `with_test_methods`
  and its doc mention go.
- `scripts/gate_parallel.py`: `shared_tests` and its three regexes go; every test module of the suite is a leaf (no test module
  is an input of another module's key); the docstring's shared-helper sentence goes. The three `test_gate_cache` tests above
  and the `test_helper` templates go.
- `contracts/CLAUDE.md` drops "snapshots, ".
- `docs/ENGINEERING.md`'s known-intentional gate-cache entry reads "(every tracked and untracked file but the test modules)".

## Scope

- **In:** `tests/CLAUDE.md`, `scripts/CLAUDE.md`, `ccp/doclang/CLAUDE.md`, `contracts/CLAUDE.md`, `scripts/gate_parallel.py`,
  `tests/test_gate_cache.py`, `tests/helpers.py`, `tests/gate_parallel_fixture.py`, `tests/suite_fixture.py`, `docs/ENGINEERING.md`
  (the known-intentional entry only).
- **Out:** the root `CLAUDE.md` (exempt from E26); `ccp suite affected`'s own import reading; any house rule's text.

## dod_checks

- id: `doc-01`
  story: As a rule's editor, no package doc restates E4, E7 or E18.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'only wrap\|imports another\|copied literal\|names no language' -- '*/CLAUDE.md'`.
    2. Run `git grep -nw -e E4 -e E7 -e E18 -- tests/CLAUDE.md scripts/CLAUDE.md ccp/doclang/CLAUDE.md`.
  expect: step 1 prints nothing (exit 1); step 2 prints at least one line in each of the three files.
  dry run (`e92f362`): step 1 printed 5 lines (`ccp/doclang/CLAUDE.md`, `scripts/CLAUDE.md`, `tests/CLAUDE.md` 3); step 2 printed 4 lines (`ccp/doclang/CLAUDE.md` 2, `tests/CLAUDE.md` 2), none in `scripts/CLAUDE.md`.
- id: `doc-02`
  story: As a test writer, tests/CLAUDE.md tells me where fixtures live without a line per fixture module.
  setup: A checkout of the PR head.
  steps:
    1. Run `wc -l < tests/CLAUDE.md`.
    2. Run `grep -c 'set up for the\|a .TestCase. base for the' tests/CLAUDE.md`.
    3. Run `grep -oE 'LEAD_ENV|as_lead\(\)|loads no .ccp. module|PLANE_ROOT' tests/CLAUDE.md | sort -u`.
  expect: step 1 prints a number no greater than 40; step 2 prints `0`; step 3 prints exactly four lines, in any order: `LEAD_ENV`, `PLANE_ROOT`, `as_lead()`, and the phrase that says `helpers.py` loads no ccp module (the pattern's third alternative).
  dry run (`e92f362`): step 1 printed `64`; step 2 printed `8`. Step 3 (`954bd72`): printed only `PLANE_ROOT`.
- id: `doc-03`
  story: As a reader of contracts/, the package doc lists only formats the directory holds.
  setup: A checkout of the PR head.
  steps:
    1. Run `grep -ci snapshot contracts/CLAUDE.md`.
  expect: prints `0`.
  dry run (`e92f362`): printed `1`.
- id: `code-01`
  story: As a fixture writer, a fixture writes a test module's methods as `def test_`, with no renaming helper.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'with_test_methods\|def t_' -- tests`.
    2. Run `python3 -B -m unittest -q tests.test_gate_parallel tests.test_suite 2>&1 | tail -1`.
  expect: step 1 prints nothing (exit 1); step 2 prints `OK`.
  dry run (`e92f362`): step 1 printed 18 lines in 4 files; step 2 printed `OK`.
- id: `code-02`
  story: As a plane developer, the gate's cache treats every test module as a leaf, and editing one still reruns only it.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `git grep -n 'shared_tests\|DOTTED_RE\|FROM_PKG_RE\|FROM_REL_RE\|shared helper\|test_helper' -- scripts/gate_parallel.py tests/test_gate_cache.py`.
    2. Run `python3 -B -m unittest -v tests.test_gate_cache 2>&1 | grep -e reruns_only_it -e '^OK'`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_gate_cache.AChangeRerunsWhatItCanAffect.test_editing_one_test_module_reruns_only_it --mutant-file <file>`, the file's mutant making the leaf set in `scripts/gate_parallel.py` empty (every test module an input of every key).
  expect: step 1 prints nothing (exit 1); step 2 lists `test_editing_one_test_module_reruns_only_it` `ok`, then `OK`; step 3 prints the mutant `killed`.
  dry run (`e92f362`): step 1 printed 16 lines (`scripts/gate_parallel.py` 8, `tests/test_gate_cache.py` 8); step 2 listed the test `ok`, then `OK`.

## Implementation notes

- Premises re-measured at `097a6560`: restated-rule grep 5 lines; `tests/CLAUDE.md` 64 lines and 8 one-liners; `with_test_methods|def t_` 18 lines;
  the shared-test-module grep 17 lines (16 plus `tests/test_fence.py`'s docstring, as the Context says); no `ccp` module reads `shared_tests`;
  no snapshot file under `contracts/`; the `LEAD_ENV|as_lead` count in `tests/CLAUDE.md` 0. Every figure held.
- `tests/CLAUDE.md` is 37 lines. Its **Reuse rule.** paragraph is gone: the intro names E4 in one sentence (a helper a second module needs
  moves to a fixture module first). The old sentence on binding another module's test-class methods is not restated: E4's command check holds it.
- `scripts/gate_parallel.py`: `leaves` is every test module of the suite; `shared_inputs`' `leaves` parameter is kept, so the digest's
  exclusion of test modules is unchanged. The docstring says each test module is an input of its own key alone, by E4.
- Removed from `tests/test_gate_cache.py`: the `HELPER`, `USER` and `FROM_PKG` templates and the three tests that built an import of one test module by another.
- Mutation check: replacing the leaf set with `set()` is killed by `test_editing_one_test_module_reruns_only_it`.
- Fix round 1: `tests/CLAUDE.md` said a fixture's class docstring says what it builds; 10 of the 19 fixture classes have none, but every fixture module has a module docstring, so the sentence now says module docstring.

## Verification notes
- 2026-11-22 — verifier, PR #345 head `f267c43` (squash `d66ffbe`): APPROVE. Passed: doc-01, doc-02, doc-03, code-01, code-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0295-package-docs-name-rules-by-id-and-every-test-module-is-a-cache-leaf.json.

