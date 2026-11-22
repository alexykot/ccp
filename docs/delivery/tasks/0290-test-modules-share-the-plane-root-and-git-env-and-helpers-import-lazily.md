---
task_id: 0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily
title: Test modules take the plane root and the git environment from tests/helpers.py, which loads no ccp module on import, the plugin test names no plane checkout path, and the implement prompt's refactor line points back
status: pending
kind: refactor
depends_on: []
rule_refs: ["E4", "E13"]
review_point: R25
paths: ["tests/helpers.py", "templates/prompts/implement.md", "templates/prompts/_common.md", "tests/gate_parallel_fixture.py", "tests/init_fixture.py", "tests/notify_fixture.py", "tests/sandbox_fixture.py", "tests/suite_fixture.py", "tests/team_hosting_fixture.py", "tests/test_adr.py", "tests/test_architect_default_on.py", "tests/test_board.py", "tests/test_ci_template.py", "tests/test_cli_reference.py", "tests/test_contract_layout.py", "tests/test_doclang_test_facts.py", "tests/test_event_registry.py", "tests/test_fence.py", "tests/test_gate_time.py", "tests/test_init_telemetry.py", "tests/test_language_key.py", "tests/test_leak_check.py", "tests/test_machine_account.py", "tests/test_models_block.py", "tests/test_notify_upgrade.py", "tests/test_obs_ids.py", "tests/test_operator_rename.py", "tests/test_orientation_command.py", "tests/test_orientation_hook.py", "tests/test_parallel_defaults.py", "tests/test_parallel_state.py", "tests/test_plane_check.py", "tests/test_plane_config_defaults.py", "tests/test_plane_json_constants.py", "tests/test_plugin.py", "tests/test_preexisting_checks.py", "tests/test_prhost_only.py", "tests/test_prompt_model.py", "tests/test_role_models.py", "tests/test_rotation_model.py", "tests/test_self_hosting.py", "tests/test_short_plane_json.py", "tests/test_snapshot_retired.py", "tests/test_stale_blockers_retired.py", "tests/test_suite_stages.py", "tests/test_task_format.py", "tests/test_task_placeholders.py", "tests/test_task_state_contract.py", "tests/test_tasklog_adopt.py", "tests/test_tasklog_spec_signoff.py", "tests/test_tasks_close.py", "tests/test_upgrade.py", "tests/test_usage.py", "tests/test_verify_as_written.py", "tests/test_wait_reasons.py", "tests/toolkit_fixture.py"]
clashes_with: ["0270-the-friction-trigger-counts-noted-tasks-and-scales-with-tasks-in-flight", "0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests", "0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope", "0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log", "0283-the-retired-watchdog-and-seat-cadences-leave-the-writers-and-docs", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes", "0288-every-seat-names-its-actor-and-the-lead-s-records-need-the-lead-s", "0289-the-runner-s-actor-id-is-named-once-and-tests-read-the-lead-s", "0291-wt-remove-clears-a-cache-only-leftover-mutant-file-names-the-line-break-and-leak-check-reads-only-a-clean-where"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily

## Intent

The test leftovers of 0284 and 0277, and the template leftover of 0276, are closed. Every test and
fixture module takes the plane checkout's root from `tests/helpers.py`'s `PLANE_ROOT` and the git
environment from its `GIT_ENV`, instead of working each out again. Importing `tests/helpers.py` loads
no `ccp` module, so the modules that now import it for a path pay nothing for it. `ccp docs check`
gives no warning on `tests/test_plugin.py`. The implement prompt for a refactor no longer says "too"
about a rule the worker has not read yet. Behaviour does not change.

## Context (not checked)

Measured at `329ff75` unless a line says otherwise.

Follow-ups covered (the lead's worker follow-up log):
`0284-shared-test-fixtures-live-in-modules-that-hold-no-tests/implement#1` (the plane root),
`…/implement#2` (`GIT_ENV`), `…/review#2` and `…/verify#2` (helpers' imports), `…` there being
`0284-shared-test-fixtures-live-in-modules-that-hold-no-tests`;
`0277-code-leftovers-of-r15-and-r17/fix#1` (the docs check warning);
`0276-docs-contract-and-template-leftovers-of-r15-and-r17/implement#1` and `…/review#1` (the refactor
line), `…` there being `0276-docs-contract-and-template-leftovers-of-r15-and-r17`.

- **The plane root, worked out again.** `git grep -n 'Path(__file__).resolve().parents\[1\]' -- tests ':(exclude)tests/helpers.py'` at `329ff75`: 56 lines in 53 files (the test and fixture modules in `paths`), bound to `PLANE`, `ROOT`, `REPO`, `CCP`, `PLUGIN`, `CONTRACTS` or `SCHEMA`, or used inline. `tests/helpers.py` already defines `PLANE_ROOT = Path(__file__).resolve().parents[1]`.
- **`GIT_ENV`, twice.** `git grep -n '^GIT_ENV = ' -- tests` at `329ff75`: 2 lines, `tests/helpers.py` and
  `tests/test_plugin.py`, with the same six keys and values.
- **Helpers' imports.** `tests/helpers.py` imports `from ccp import board, config, otel, prhost, prompt, runs, tasklog, verify` at module level. `python3 -B -c "import sys, tests.helpers; print(len([m for m in sys.modules if m.split('.')[0]=='ccp']))"` at `329ff75`: 27 `ccp` modules loaded by the import alone. Each name is used inside functions only (`config` also in a return annotation, which `from __future__ import annotations` leaves unevaluated).
- **The docs check warning.** `CCP_DEV=1 ./bin/ccp --root . docs check 2>&1 | grep -c 'tests/test_plugin.py'` at `329ff75`: 1,
  "names a control-plane checkout path". The follow-up blames the `run()` docstring, but that line names no
  path: the warning comes from `PLANE_PATH_RE` (`ccp/cli.py`, `/control-plane(-run)?/` followed by `bin/ccp` and
  others) matching the two fixture strings of the docs-check test, `"Run /opt/src/control-plane/bin/ccp tasks next.\n"`
  and `"history: /opt/src/control-plane/bin/ccp\n"` (`git grep -nE '/control-plane(-run)?/(bin/ccp|scripts/|templates/|plugin/|projects/|SPEC\.md)' -- tests/test_plugin.py` at `329ff75`: 2 lines).
  Those strings are the test's input, so the test keeps them; only their spelling in the source changes.
- **The refactor line.** `templates/prompts/implement.md`'s `{{#refactor}}` block says "The suite and the
  product's scenario checks pass too.", and `ccp prompt` renders `_common.md` after the phase template
  (`"body = render_phase(phase, values)"` in `ccp/prompt.py`), so its "too" points at `_common.md`'s refactor
  bullet, which comes later. Rendered at `329ff75` with the check's command below: the phrase appears once,
  before `kind: refactor`. `git grep -n 'scenario checks' -- docs/spec` at `329ff75`: 1 line, §20.3's standing DoD
  for a refactor, which this restates and does not change.
- **No size cap on helpers.** `docs/ENGINEERING.md` has no house rule on a test module's length, and plane.json sets no `budgets` (`python3 -c "import json;print(json.load(open('docs/delivery/plane.json')).get('budgets'))"` at `329ff75`: `None`), so `tests/helpers.py` (438 lines) is not split.
- **Behaviour unchanged.** Every module gets the same path and the same environment as before, so no test
  expectation changes; the gate holds it. Importing `tests.helpers` from the modules that did not import it
  before costs only the standard library once its `ccp` imports are lazy.
- **Other tasks on these files.** 0288 and 0289 change `tests/helpers.py`, `implement.md`, `_common.md` and
  some of these test modules; 0270, 0271, 0275, 0282, 0283, 0285 and 0291 change one or more of the files in
  `paths` for their own ends. Recorded as clashes, since the paths overlap.
- **Run it last in R25.** It clashes with every pending task its `clashes_with` names, so the lead prefers it after the other R25 tasks
  (`ccp tasks prefer`), where it waits on none of them and its sweep covers the test modules they leave.

### Rulings for the build (the lead's)

- **The plane root.** Every module in `paths` other than `tests/helpers.py` imports `PLANE_ROOT` from
  `tests.helpers` and binds its own name to it (`PLANE = PLANE_ROOT`, `ROOT = PLANE_ROOT`, `CONTRACTS = PLANE_ROOT / "contracts"`)
  or uses it inline; none computes `Path(__file__).resolve().parents[1]`.
- **`GIT_ENV`.** `tests/test_plugin.py` imports `GIT_ENV` from `tests.helpers` and drops its own.
- **Lazy imports.** `tests/helpers.py` imports no `ccp` module at module level: each function imports the
  `ccp` modules it uses inside its body (`from ccp import prompt  # noqa: PLC0415`, as `ccp/` does).
- **The fixture path.** `tests/test_plugin.py` names the docs-check test's plane path through a module constant,
  `FAKE_PLANE = "/opt/src/control-plane"`, and writes the two strings as `f"Run {FAKE_PLANE}/bin/ccp tasks next.\n"`
  and `f"history: {FAKE_PLANE}/bin/ccp\n"`. The `run()` docstring stays.
- **The refactor line.** `implement.md` drops "The suite and the product's scenario checks pass too.";
  `_common.md`'s refactor bullet ends "…, and SPEC does not change; the suite and the product's scenario checks pass."

## Scope

- **In:** `tests/helpers.py`, `templates/prompts/implement.md`, `templates/prompts/_common.md`, and the test and
  fixture modules in `paths`.
- **Out:** splitting `tests/helpers.py`; `ccp suite affected`'s Python reader; `ccp/cli.py`'s `PLANE_PATH_RE`.

## dod_checks

- id: `test-01`
  story: As a plane developer, the plane checkout's root is worked out once, in tests/helpers.py.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'Path(__file__).resolve().parents\[1\]' -- tests ':(exclude)tests/helpers.py'`.
    2. Run `git grep -n '^GIT_ENV = ' -- tests`.
  expect: step 1 prints nothing (exit 1); step 2 prints exactly one line, in `tests/helpers.py`.
  dry run (`329ff75`): step 1 printed 56 lines in 53 files; step 2 printed 2 lines (`tests/helpers.py:211`, `tests/test_plugin.py:21`).
- id: `test-02`
  story: As a plane developer, importing the shared test helpers loads no plane module.
  setup: A checkout of the PR head; run from its root.
  steps:
    1. Run `python3 -B -c "import sys, tests.helpers; print(sorted(m for m in sys.modules if m.split('.')[0]=='ccp'))"`.
  expect: prints `[]`.
  dry run (`329ff75`): printed a list of 27 modules, from `ccp` to `ccp.verify`.
- id: `docs-01`
  story: As a plane developer, `ccp docs check` gives no plane-path warning on the plugin test.
  setup: A checkout of the PR head; run from its root.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp --root . docs check 2>&1 | grep -c 'tests/test_plugin.py'`.
    2. Run `git grep -n 'FAKE_PLANE' -- tests/test_plugin.py`.
  expect: step 1 prints `0`; step 2 prints at least three lines (the constant and the two strings).
  dry run (`329ff75`): step 1 printed `1`; step 2 printed nothing.
- id: `text-01`
  story: As an implementer of a refactor, my prompt states the refactor DoD once, after nothing it refers back to.
  setup: A checkout of the PR head; run from its root.
  steps:
    1. Run `python3 -B -c "from ccp import prompt; from tests.helpers import phase_values as v; x=v(refactor=True, change_round=True); t=prompt.render_phase('implement', x)+prompt.render((prompt.TEMPLATES/'_common.md').read_text(), x); print(t.count('scenario checks pass'), t.find('scenario checks pass') > t.find('kind: refactor') > -1)"`.
    2. Run `grep -c 'pass too' templates/prompts/implement.md`.
  expect: step 1 prints `1 True`; step 2 prints `0`.
  dry run (`329ff75`): step 1 printed `1 False`; step 2 printed `1`.

## Implementation notes

- 2026-11-22 (implementer). Premises re-measured at `deca5ed2`: 56 lines in 53 files, the same files as `paths`; 2
  `GIT_ENV` lines; 27 `ccp` modules on importing `tests.helpers`; docs check 1 warning on `tests/test_plugin.py`.
  Two module-level constants in `tests/helpers.py` read `ccp` at import, not only functions: `DONE_SECTIONS`
  (`runs.CHANGE_PHASES`, already so at `329ff75`) and `LEAD_ENV` (`lib.LEAD`, added by 0288). `DONE_SECTIONS`, used
  only by `done_report`, became the function `done_sections()`; `LEAD_ENV` is served by a module `__getattr__`
  (PEP 562) backed by `lead_env()`, so the four modules that import it stay unchanged. `config.Config` in the `cfg`
  annotation is imported under `TYPE_CHECKING`.
- `tests/test_tasks_close.py` computes the root only in its run-as-a-script bootstrap, before `tests` is
  importable: it now imports `PLANE_ROOT` as `helpers` (the script's directory leads `sys.path`), which loads only
  the standard library, then puts the root on `sys.path` as before.
- The modules that had no `tests.helpers` import gained `from tests.helpers import PLANE_ROOT`; `from pathlib
  import Path` was dropped where nothing else used it.
- `tests/test_fence.py` gains a test that importing `tests.helpers` loads no `ccp` module (a subprocess, as the
  fence test does), so the lazy imports hold past this task.

## Verification notes
