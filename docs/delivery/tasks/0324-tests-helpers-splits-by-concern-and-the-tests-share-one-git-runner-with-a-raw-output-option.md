---
task_id: 0324-tests-helpers-splits-by-concern-and-the-tests-share-one-git-runner-with-a-raw-output-option
title: tests/helpers.py splits by concern into a git, a ledger, a report and a render helper module, so an edit to one concern marks only its importers affected, and the tests share one git runner with a raw-output option
status: pending
kind: refactor
depends_on: []
review_refs: ["ar-20261124T034246Z-e089#F04", "ar-20261122T162238Z-9098#F09", "ar-20261122T162238Z-9098#F11"]
review_point: R33
paths: ["tests/helpers.py", "tests/git_helpers.py", "tests/ledger_helpers.py", "tests/report_helpers.py", "tests/render_helpers.py", "tests/CLAUDE.md", "tests/architect_fixture.py", "tests/review_flow.py", "tests/test_allowance_lapse.py", "tests/test_backfill.py", "tests/test_board.py", "tests/test_board_layout.py", "tests/test_board_staleness.py", "tests/test_formal_submit.py", "tests/test_full_lane_prompt.py", "tests/test_gate_cache.py", "tests/test_gate_time.py", "tests/test_health.py", "tests/test_health_conflicts.py", "tests/test_health_signoff.py", "tests/test_kinds.py", "tests/test_lead_records.py", "tests/test_lead_ruling.py", "tests/test_marked_checks_loop.py", "tests/test_marked_checks_record.py", "tests/test_model_alias.py", "tests/test_orphans.py", "tests/test_plane_json_constants.py", "tests/test_plane_workers_run_head.py", "tests/test_prhost_only.py", "tests/test_prompt_end.py", "tests/test_prompt_rounds.py", "tests/test_prompt_tools.py", "tests/test_prompt_verify_early.py", "tests/test_report_correction.py", "tests/test_report_fields.py", "tests/test_report_follow_ups.py", "tests/test_report_sections.py", "tests/test_review_points.py", "tests/test_rotation_model.py", "tests/test_run_checkout_upgrade.py", "tests/test_sign_off_beyond_intent.py", "tests/test_stale_context_audience.py", "tests/test_suite.py", "tests/test_suite_affected.py", "tests/test_suite_cold.py", "tests/test_suite_full_log.py", "tests/test_suite_run_affected.py", "tests/test_sync_on_release.py", "tests/test_tasks_release_keep_branch.py", "tests/test_toolkit.py", "tests/test_usage.py", "tests/test_usage_advice.py", "tests/test_usage_by_model.py", "tests/test_verify.py", "tests/test_verify_adr.py", "tests/test_verify_as_written.py", "tests/test_verify_judge.py", "tests/test_verify_producer.py", "tests/test_worker_efficiency.py", "tests/toolkit_fixture.py"]
clashes_with: ["0191-the-grace-release-ends", "0311-suite-affected-and-suite-run-affected-run-a-staged-part-lane-as-declared", "0319-the-pack-stops-matching-a-path-the-affected-map-names-by-name-so-a-plane-json-edit-runs-the-tests-that-read-it"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0324-tests-helpers-splits-by-concern-and-the-tests-share-one-git-runner-with-a-raw-output-option

## Intent

A change to one shared test helper costs a part-lane run of the tests that use it, not most of the suite.
`tests/helpers.py` keeps the product fixture (`Product`, the task and plane templates, the binding and machine-file
writers, the actor helpers, the plane's own paths) and the git, ledger, report and render helpers move into four
modules of their own, each imported only by the tests that use it. The tests share one git runner, which returns
the output stripped or, on request, as written, so a test no longer keeps a private runner because the shared one
strips its output.

## Context (not checked)

Finding F04 of architect pass `ar-20261124T034246Z-e089` (`docs/delivery/reviews/ar-20261124T034246Z-e089.md`): the
roadmap's deferral of `ar-20261122T162238Z-9098` F09 and F11 ("once the R26 tasks that edit shared test fixtures
(0293, 0302) are done") met its trigger; 0293 and 0302 are done (reconciles `31c3e1cd` and `aee65114`). Behaviour is
unchanged: no test's assertions change, only where its helpers come from.

Measured at `9691fd9c` (origin/main after 0317's reconcile):

- **The fan-in.** `wc -l < tests/helpers.py`: 470. An AST read of every `from tests.helpers import …` in `tests/*.py`
  (`python3 -B` over `ast.walk`, the probe in the triage record): 184 modules import it; `Product` 105, `PLANE_ROOT` 65,
  `TASK` 33, `binding` 26. `CCP_DEV=1 ./bin/ccp suite affected --paths tests/helpers.py 2>/dev/null | wc -l`: 171.
  Under the split below, the same read gives 28 importers of the report helpers, 16 of the ledger helpers and 5 of
  the render helpers. Report helpers' transitive fan-in (what code-01 counts) is 36 by the triage review's import-graph
  read, against code-01's limit of 40.
- **The git runners.** `tests/helpers.py` has `git_run` (any command with `GIT_ENV`, a `CompletedProcess`),
  `release_git` (stripped, asserting exit 0), `repo_git` and `health_git` (output as written, `check=True`).
  `git grep -nE '^def git\(' -- tests` at `9691fd9c`: 6 module-level runners, in `tests/architect_fixture.py`,
  `tests/toolkit_fixture.py`, `tests/test_kinds.py`, `tests/test_marked_checks_record.py`, `tests/test_orphans.py`
  and `tests/test_suite_affected.py`, each a `git -C <root>` with a test identity that fails on a non-zero exit.
- **E4's greps** exclude `tests/helpers.py` for `__file__).resolve().parent` and `GIT_AUTHOR_NAME`; both stay there
  (`PLANE_ROOT`, `GIT_ENV`), so `architect.checks` `E4` does not change.
- **Ruled.**
  - `tests/git_helpers.py` (new): `run(cmd, **kw)` (was `git_run`), `git(cwd, *args, env=None, raw=False) -> str`
    (a `git -C <cwd>` with `GIT_ENV` and `env` over `os.environ`; it fails the test naming the command and stderr on
    a non-zero exit; it returns stdout stripped, or as written with `raw=True`), `commit(root, msg, at, *extra)` (was
    `health_commit`) and `HEALTH_T0`. `release_git`, `repo_git` and `health_git` go: their importers call `git`
    (`raw=True` where they used `repo_git` or `health_git` and read the output as written). The six module-level
    `def git(` runners above go; those modules import `git` from `tests.git_helpers`.
  - The shared runner passes `GIT_ENV`, which sets `GIT_CONFIG_GLOBAL=/dev/null`, so the converted runners become
    hermetic: a test that relied on the operator's global git config sets what it needs explicitly (`env=`).
  - `tests/ledger_helpers.py` (new): `ledger_event`, `spawn_event`, `lease_event`, `suite_started`, `suite_ended`,
    `SUITE_RUN_ID`, `good_then_failed`, `api_request`, `advice_row`, `ADVICE_SPANS`, `FoldRuns`.
  - `tests/report_helpers.py` (new): `done_sections`, `done_report`, `implement_report`, `REPORT_HEAD`,
    `approve_verdict`, `judge_merge_ok`, `held_otherwise`, `HEAD_A`, `HEAD_B`, `MARKED_CHECK_ID`, `MARKED_TASK_ID`,
    `MARKED_BLOCK`.
  - `tests/render_helpers.py` (new): `phase_values`, `render_phase_values`, `PROMPT_TEMPLATES`, `BoardPage`.
  - A constant goes with the functions that read it; one the moved functions and `tests/helpers.py` both read stays
    in `tests/helpers.py`. `tests/helpers.py` imports none of the four new modules (a re-export would make every
    importer depend on them again), and each new module holds no tests (E4).
  - `tests/CLAUDE.md` names the five modules and what each holds, in place of its `git_run` and `*_git` line.
- **No SPEC change**: the SPEC names no test helper (`git grep -n 'helpers.py' -- docs/spec` at `9691fd9c`: no line).

## Scope

- **In:** `tests/helpers.py`; `tests/git_helpers.py` (new); `tests/ledger_helpers.py` (new);
  `tests/report_helpers.py` (new); `tests/render_helpers.py` (new); `tests/CLAUDE.md`; the import lines of every
  module under `tests/` that uses a moved name, and the six module-level git runners: the modules `paths` lists (an
  AST read at `9691fd9c` of the `from tests.helpers import` lines naming a moved name, plus `helpers.<name>` uses and
  the six runners' modules: 55). A module the build finds beyond them is in scope too and is named in the report.
- **Out:** test assertions; private git runners defined inside a test class or under another name (a later edit of
  that module may move it to the shared runner); `architect.checks`; `ccp/`.

## dod_checks

- id: `code-01`
  story: As a plane developer, an edit to the report helpers marks only the tests that use them affected.
  setup: A checkout of the PR head (any seat), with a scratch `QUEUE_ROOT`.
  steps:
    1. Run `test -f tests/report_helpers.py && CCP_DEV=1 ./bin/ccp suite affected --paths tests/report_helpers.py 2>/dev/null | wc -l`.
  expect: exit 0 and a number of at most 40.
  dry run (`9691fd9c`): printed nothing, exit 1 (no such file).
- id: `code-02`
  story: As a plane developer, an edit to the ledger helpers marks only the tests that use them affected.
  setup: As `code-01`.
  steps:
    1. Run `test -f tests/ledger_helpers.py && CCP_DEV=1 ./bin/ccp suite affected --paths tests/ledger_helpers.py 2>/dev/null | wc -l`.
  expect: exit 0 and a number of at most 25.
  dry run (`9691fd9c`): printed nothing, exit 1 (no such file).
- id: `code-03`
  story: As a test writer, one git runner returns output stripped or as written, and no module keeps its own module-level runner.
  setup: As `code-01`.
  steps:
    1. Run `python3 -B -c 'import inspect, tests.git_helpers as g; print(list(inspect.signature(g.git).parameters))'`.
    2. Run `git grep -nE '^def (git|git_run|release_git|repo_git|health_git)\(' -- tests ':(exclude)tests/git_helpers.py'`.
  expect: step 1 prints `['cwd', 'args', 'env', 'raw']`; step 2 prints nothing (exit 1).
  dry run (`9691fd9c`): step 1 printed `ModuleNotFoundError: No module named 'tests.git_helpers'`, exit 1; step 2 printed 10 lines (the six module-level runners and `tests/helpers.py`'s four).
- id: `code-04`
  story: As a plane developer, tests/helpers.py holds only the product fixture and re-exports nothing.
  setup: As `code-01`.
  steps:
    1. Run `wc -l < tests/helpers.py`.
    2. Run `git grep -nE '(git|ledger|report|render)_helpers' -- tests/helpers.py`.
  expect: step 1 prints a number of at most 320; step 2 prints nothing (exit 1).
  dry run (`9691fd9c`): step 1 printed `470`; step 2 printed nothing (exit 1).

## Implementation notes

## Verification notes
