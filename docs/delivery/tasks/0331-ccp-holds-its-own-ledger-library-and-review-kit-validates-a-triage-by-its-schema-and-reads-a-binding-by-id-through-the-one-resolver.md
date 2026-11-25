---
task_id: 0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver
title: ccp holds the ledger library and the architect's review kit and imports nothing from scripts/, which E7 checks; a triage is validated against its contract; the telemetry commands and the docs sync read a binding by project id through the one resolver, honouring PROJECT_YAML; the estimator's failure file and the rendered prompt are written atomically
status: pending
kind: feature
depends_on: []
spec_refs: ["S8", "S10", "S19", "S23"]
rule_refs: ["E7", "E17", "E27"]
review_refs: ["ar-20261120T234012Z-27eb#F17", "ar-20261122T162238Z-9098#F03", "ar-20261124T034246Z-e089#F06", "ar-20261124T234643Z-3c95#F07"]
review_point: R35
paths: ["scripts/observability/lib.py", "scripts/observability/architecture_review.py", "ccp/lib.py", "ccp/architecture_review.py", "ccp/", "scripts/", "tests/", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "docs/cli/04-observability.md", "docs/ENGINEERING.md", "docs/delivery/plane.json"]
clashes_with: ["0191-the-grace-release-ends", "0332-one-fence-aware-markdown-section-helper-and-ccp-spec-show-prints-a-cited-section", "0333-every-docs-cli-part-takes-one-table-shape-e25-reads-every-line-and-the-cli-reference-tests-run-on-their-own-docs", "0334-the-implementer-brief-leaves-its-phase-template-s-instructions-to-it-and-the-lanes-line-renders-the-worker-s-ccp", "0335-absence-checks-allow-indented-forms-the-repo-s-task-rules-point-at-e21-and-init-counts-only-files-git-keeps"]
sign_off: brief
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver

## Intent

`ccp` is one package that imports nothing from `scripts/`: the ledger library and the architect's review kit live in
`ccp`, and the observability scripts are single writers built on that library, as §10.6, §23.4, the command reference
and house rule E7 now say, E7 with a command check. A triage the architect seat records is held to its contract,
`contracts/architecture_review_triage.schema.json`, through the plane's one schema checker, and a test keeps the code's
disposition lists equal to the contract's enums. `ccp otel` and `scripts/sync-product-docs.sh` find a product's
binding by its id through the one resolver, so a sandbox's `PROJECT_YAML` reaches them as it reaches every other
reader. The estimator's failure file and `ccp prompt`'s rendered prompt are written atomically, like every other
queue write.

## Context (not checked)

The roadmap's deferral F17 (`docs/ROADMAP.md`, "Deferred from architect passes"), tasked here as the first task of
this triage, ahead of its new findings, as the operator ruled on 2026-11-24 (4ce8 question 2):

> "Agree with all recommendations. Go ahead." Question 2 is (a): F17 stays deferred, the first task of the next
> triage, ahead of new findings, carrying e089 F06 and the binding readers.

It carries the operator's earlier rulings: E7 is amended with this move, with a command check then (11aa question 5,
answered (a) on 2026-11-22), and this task states the observability scripts' direction where §10.6, §23.4,
`docs/cli/04-observability.md` and E7 call them wrappers over `ccp` (9098 question 1, answered (b) on 2026-11-23). It
also carries finding F07 of architect pass `ar-20261124T234643Z-3c95` (`docs/delivery/reviews/ar-20261124T234643Z-3c95.md`).

Measured at `1a575497`:

- The triage commit after `1a575497` (`docs/ENGINEERING.md`: E5, E19 and E26 rewrapped, words unchanged;
  `docs/delivery/plane.json`: `E4`'s alias grep at `^\s*`) leaves every figure below as measured.
- **The imports.** `git grep -nP '^\s*(sys\.path\.(insert|append)|(import|from) (lib|architecture_review|spec_maintainer|team)\b)' -- ccp | wc -l`:
  7 lines, in `ccp/architect.py`, `ccp/health.py` and `ccp/queue.py` (three `sys.path.insert`, four imports). The two
  modules that move add 4 more, which the same grep finds once they are under `ccp/` (`git grep -nP '…' -- scripts/observability/lib.py scripts/observability/architecture_review.py`):
  `architecture_review.py`'s two `sys.path.insert` and its `from lib import`, and the `sys.path.insert` in lib's
  `"def _config"`, a fallback for importing `ccp.config` from a script; 11 in all. At module level `lib.py` imports
  only the standard library (`grep -nE '^(import|from) ' scripts/observability/lib.py`); `_config` imports
  `ccp.config` inside the function.
  `git grep -lP 'from ccp\.queue import [^#\n]*\blib\b|\bqueue\.lib\b' -- ccp | wc -l`: 26 modules take `lib` through
  `ccp.queue`. `git grep -lP '^\s*(import (lib|architecture_review)\b|from (lib|architecture_review) import)' -- tests | wc -l`:
  9 test modules import them by bare name. `git grep -lP '^\s*(import (lib|architecture_review)\b|from (lib|architecture_review) import)' -- scripts`:
  `architecture_review.py`, `emit-event.sh`, `heartbeat.sh`, `set-waiting-on.sh`, `spec_maintainer.py`, `team.py`,
  `write-prompt-audit.sh` (all in `scripts/observability/`) and `scripts/sync-product-docs.sh`.
- **The path.** `git grep -n 'scripts/observability/lib\.py\|observability" / "lib\.py' -- docs/ENGINEERING.md docs/delivery/plane.json docs/cli docs/spec ccp scripts tests plugin README.md | wc -l`:
  11 lines (E17's text, the `E17` and `E27` cmds, `scripts/run-checkout.sh` ×3, `tests/test_binding_reader.py`,
  `tests/test_event_registry.py`, `tests/test_sync_on_release.py` ×3). `git grep -n 'architecture_review\.py' -- ccp scripts`:
  `ccp/architect.py`'s docstring, `ccp/seats.py`'s `source` string, `scripts/observability/CLAUDE.md`.
- **The triage check.** `"def validate_triage"` (`scripts/observability/architecture_review.py`) checks `review_id`,
  three required keys, each disposition against `DISPOSITIONS`, `tasks_created`'s type, the commit sha and secrets
  by hand; `ccp/architect.py` checks `rule_changes` against `RULE_DISPOSITIONS`. The contract requires eight keys
  (`schema_version`, `review_id`, `project_id`, `triaged_at`, `record`, `tasks_created`, `dispositions`,
  `answered_by`) and gives the two enums. A triage missing `schema_version`, `project_id` or `triaged_at` is accepted
  today; it is refused once the contract holds it (a change of behaviour, so this is a feature).
- **The binding readers.** `git grep -nF 'bindings_dir() / f"{' -- ccp scripts ':(exclude)ccp/lib.py' | wc -l`: 5
  (`ccp/otel.py` ×3: `"def queue_for"`, `"def env_off"`, `"def env_for_project"`; `scripts/sync-product-docs.sh` ×1;
  lib's own `"def product_binding"`, which moves with lib). None honours `PROJECT_YAML`.
- **F07.** `git grep -nF 'prompt_file.write_text(' -- ccp/prompt.py`: 1; `git grep -nF '.failed.txt").write_text(' -- ccp/estimator.py`: 1.
- 0191 (pending, on hold) names `scripts/observability/lib.py` in its `paths`; the lead re-anchors it to `ccp/lib.py`
  before its claim. The two rulings do not overlap: 0191 ends a grace, this task moves the module.
- **Ruled.**
  - `scripts/observability/lib.py` moves to `ccp/lib.py` and `scripts/observability/architecture_review.py` to
    `ccp/architecture_review.py` (`git mv`, so history follows). `ccp/queue.py` takes it as `from ccp import lib`; the
    26 modules that take `lib` through `ccp.queue` stay as they are. `ccp/architect.py` and `ccp/health.py` import
    from `ccp`. No `sys.path` edit stays in `ccp`; the `boot` string `ccp/queue.py` builds for a child process is not
    an edit of `ccp`'s own path and stays.
  - The scripts that import lib (the seven in `scripts/observability/` and `scripts/sync-product-docs.sh`) put the
    plane root on their path and import `ccp.lib` (`from ccp.lib import …`, or `from ccp import lib`).
    `scripts/run-checkout.sh` runs `"$RUN/ccp/lib.py"`; `ccp/lib.py` keeps importing only the standard library at
    module level, so it still runs as a file. `"def _config"`'s `sys.path` fallback goes: inside the package
    `from ccp import config` always resolves. The 9 test modules import `from ccp import lib` (and `architecture_review` likewise);
    the three that name the path name `ccp/lib.py`. `ccp/seats.py`'s `source` names `ccp/architecture_review.py`.
  - `ccp architect triage` holds a triage to `contracts/architecture_review_triage.schema.json` with
    `ccp/schema.py` `"def schema_errors"`; `validate_triage` keeps only what the contract cannot say (the review id
    matches, a task or ruling has a commit sha, no secret). `DISPOSITIONS` and `RULE_DISPOSITIONS` stay in code. New
    module `tests/test_architect_triage_schema.py`, class `TriageSchema`:
    `test_a_triage_missing_a_key_the_contract_requires_is_refused_naming_it` (a triage without `triaged_at` is
    refused, the error naming `triaged_at`) and `test_the_disposition_lists_equal_the_contract_enums`.
  - `ccp/lib.py` gains `"def binding_for_id(project_id: str) -> Path | None"`: the file `PROJECT_YAML` names, when it
    is a file whose `project_id` is `project_id`; else `<bindings_dir()>/<project_id>.yaml` when it is a file; else
    None. `ccp/otel.py`'s three sites and `scripts/sync-product-docs.sh` (when `--project-yaml` is not given) call it.
    New module `tests/test_binding_by_id.py`, class `BindingById`:
    `test_project_yaml_naming_the_ids_binding_wins`, `test_project_yaml_naming_another_id_falls_back`,
    `test_otel_env_reads_the_binding_project_yaml_names` (`ccp otel env --project <id>` names the
    `product_root` of the binding `PROJECT_YAML` names, outside the bindings directory) and
    `test_sync_reads_the_binding_project_yaml_names` (`scripts/sync-product-docs.sh <id> --check` reads that
    binding: its `product_root`, not the bindings directory's).
  - F07: both files go through `lib.write_atomic`.
  - **E7, E17** (`docs/ENGINEERING.md`): E7's four lines are replaced by these four, E17's two by these two, so the
    doc's line count does not change:

    > - **E7** Every queue write goes through `ccp` and records its own event, and `ccp` imports nothing from scripts/. A
    >   script a seat or product calls only wraps `ccp` or Git, or is a single writer built on ccp/lib.py; a plane-development
    >   script (the gate's, the house checks') may hold its own program and writes no queue state.
    >   check: command — architect.checks `E7` (no sys.path edit or scripts/ import in ccp); pass — the architect lists the scripts/ files that write the queue or that a seat calls, and compares them with ccp

    > - **E17** One module, ccp/lib.py, resolves a binding (by queue or project id) and parses it; every other reader calls it.
    >   check: command — architect.checks `E17` (the parser, and no binding path built outside ccp/lib.py); pass — the architect looks for binding paths resolved outside lib.py

  - **plane.json** `architect.checks`: a new entry `{"id": "E7", "cmd": …}` before `E13`, whose cmd is

    ```
    ! git grep -nP '^\s*(sys\.path\.(insert|append)|(import|from) (lib|architecture_review|spec_maintainer|team)\b)' -- ccp
    ```

    `E17`'s cmd becomes
    `! git grep -nE '_BINDING_LINE|def read_binding' -- ccp scripts ':(exclude)ccp/lib.py' && ! git grep -nF 'bindings_dir() / f"{' -- ccp scripts ':(exclude)ccp/lib.py'`,
    and `E27`'s exclude `':(exclude)scripts/observability/lib.py'` becomes `':(exclude)ccp/lib.py'`.
  - `docs/cli/04-observability.md`'s closing paragraph ("Scripts kept as wrappers over `ccp`: …") says the scripts
    are single writers built on `ccp/lib.py`, naming §10.6; `scripts/observability/CLAUDE.md` and `ccp/CLAUDE.md`
    name `ccp/lib.py` and `ccp/architecture_review.py` where they name the old paths.
- **The triage fixtures.** Once the contract holds a triage, a fixture triage without `triaged_at` or `project_id`
  is refused before the check its test exercises. `tests/test_architect.py` (the triage files written at lines 62-65,
  254-255, 279-280, 298-299 and 336-339) and `tests/test_review_aliases_retired.py:48` gain the missing keys: their
  inputs change, their expectations do not. `tests/board_quality_fixture.py`'s triage file is read by the board, not
  through `ccp architect triage`, and stays.
- No other test expectation changes.

## Scope

- **In:** `scripts/observability/lib.py` (removed) → `ccp/lib.py` (new); `scripts/observability/architecture_review.py`
  (removed) → `ccp/architecture_review.py` (new); `ccp/queue.py`, `ccp/architect.py`, `ccp/health.py`, `ccp/seats.py`,
  `ccp/otel.py`, `ccp/estimator.py`, `ccp/prompt.py`, `ccp/CLAUDE.md`; `scripts/observability/` (the seven importers,
  `CLAUDE.md`), `scripts/sync-product-docs.sh`, `scripts/run-checkout.sh`; the 9 test modules and the 3 that name the
  path (Context); `tests/test_architect.py` and `tests/test_review_aliases_retired.py` (the triage fixtures' keys,
  Context); `tests/test_architect_triage_schema.py` (new); `tests/test_binding_by_id.py` (new);
  `docs/cli/04-observability.md`; `docs/ENGINEERING.md` (E7, E17, the text above); `docs/delivery/plane.json`
  (`architect.checks` `E7`, `E17`, `E27`); the SPEC, signed:

  CURRENT (`docs/spec/02-delivery.md` at `1a575497`), §10.6, the last bullet:
  > - The runner brief (`plugin/agents/delivery-runner.md`) names these commands at each step and describes no step in prose. `scripts/observability/*.sh` stay as thin wrappers over `ccp`.

  PROPOSED:
  > - The runner brief (`plugin/agents/delivery-runner.md`) names these commands at each step and describes no step in prose. `ccp` imports nothing from `scripts/`: the scripts in `scripts/observability/` are single writers built on `ccp`'s own library, which `ccp` calls or the operator runs.

  CURRENT (`docs/spec/04-observability.md` at `1a575497`), §23.4, the last sentence:
  > The board is the status: the older snapshot (`now.json`, `STATUS.md`) and the scripts that write or read it (`status.sh`, `rebuild-now.sh`) are retired; `emit-event.sh` and `set-waiting-on.sh` remain as wrappers over `ccp`.

  PROPOSED:
  > The board is the status: the older snapshot (`now.json`, `STATUS.md`) and the scripts that write or read it (`status.sh`, `rebuild-now.sh`) are retired; `emit-event.sh` and `set-waiting-on.sh` remain as single writers built on `ccp`'s own library (§10.6).

  CURRENT (`docs/spec/01-model.md` at `1a575497`), §8.3, the second bullet's second sentence:
  > For a queue, the resolver takes `PROJECT_YAML` when it names a file, else the binding whose `queue_root` is that queue.

  PROPOSED:
  > For a queue, the resolver takes `PROJECT_YAML` when it names a file, else the binding whose `queue_root` is that queue; for a project id, it takes the file `PROJECT_YAML` names when that file binds the id, else `<project_id>.yaml` in the bindings directory.

  Retired: "`scripts/observability/*.sh` stay as thin wrappers over `ccp`." (§10.6) and "remain as wrappers over
  `ccp`" (§23.4), both false since `ccp` calls these scripts and they write the ledger themselves.
- **Out:** `scripts/observability/team.py` and `spec_maintainer.py` staying in `scripts/` (seat scripts, not `ccp`'s
  library); what the shell scripts do; the contract's text; any other module's import of `lib` through `ccp.queue`;
  the 0191 brief.

## dod_checks

- id: `code-01`
  story: As a plane developer, ccp imports nothing from scripts/, and E7's command check holds it.
  setup: A checkout of the PR head (any seat), with a scratch `QUEUE_ROOT`.
  steps:
    1. Run `git grep -nP '^\s*(sys\.path\.(insert|append)|(import|from) (lib|architecture_review|spec_maintainer|team)\b)' -- ccp`.
    2. Run `CCP_DEV=1 ./bin/ccp docs check --only E7; echo "exit $?"`.
    3. Run `test -e scripts/observability/lib.py || test -e scripts/observability/architecture_review.py; echo $?`.
  expect: step 1 prints nothing (exit 1); step 2's last line is `exit 0`; step 3 prints `1`.
  dry run (`1a575497`): step 1 printed 7 lines (the 4 in the two modules that move are found after the move); step 2 printed `ccp docs check: --only E7: ccp docs check runs no check E7 (…)`, `exit 2`; step 3 printed `0`.
- id: `code-02`
  story: As the lead, a triage that breaks its contract is refused naming the key, and the code's disposition lists cannot drift from the contract's enums.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_architect_triage_schema.TriageSchema.test_a_triage_missing_a_key_the_contract_requires_is_refused_naming_it tests.test_architect_triage_schema.TriageSchema.test_the_disposition_lists_equal_the_contract_enums`.
  expect: exit 0.
  dry run (`1a575497`): exit 1 (`ModuleNotFoundError: No module named 'tests.test_architect_triage_schema'`).
- id: `code-03`
  story: As an operator in a sandbox, ccp otel and the docs sync read the binding PROJECT_YAML names, through the one resolver.
  setup: As `code-02`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_binding_by_id.BindingById.test_project_yaml_naming_the_ids_binding_wins tests.test_binding_by_id.BindingById.test_project_yaml_naming_another_id_falls_back tests.test_binding_by_id.BindingById.test_otel_env_reads_the_binding_project_yaml_names tests.test_binding_by_id.BindingById.test_sync_reads_the_binding_project_yaml_names`.
    2. Run `git grep -nF 'bindings_dir() / f"{' -- ccp scripts ':(exclude)ccp/lib.py'`.
  expect: step 1 exits 0; step 2 prints nothing (exit 1).
  dry run (`1a575497`): step 1 exit 1 (`ModuleNotFoundError: No module named 'tests.test_binding_by_id'`); step 2 printed 5 lines.
- id: `code-04`
  story: As a plane developer, the estimator's failure file and the rendered prompt are written atomically, like every other queue write.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nF -e 'prompt_file.write_text(' -e '.failed.txt").write_text(' -- ccp/prompt.py ccp/estimator.py`.
  expect: prints nothing (exit 1).
  dry run (`1a575497`): printed 2 lines (`ccp/estimator.py`, `ccp/prompt.py`).
- id: `doc-01`
  story: As a plane developer, the house rules, their checks, the scripts and the tests name the library where it lives.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n 'scripts/observability/lib\.py\|observability" / "lib\.py' -- docs/ENGINEERING.md docs/delivery/plane.json docs/cli docs/spec ccp scripts tests plugin README.md`.
    2. Run `grep -c 'ccp/lib.py' docs/ENGINEERING.md`.
  expect: step 1 prints nothing (exit 1); step 2 prints `3`.
  dry run (`1a575497`): step 1 printed 11 lines; step 2 printed `0`, exit 1.
- id: `spec-01`
  story: As the operator, §10.6, §23.4 and §8.3 say what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0331`.
  expect: exit 0, every PROPOSED passage found.
  dry run (`1a575497`, with this brief): exit 1, the PROPOSED passages missing (`not found in the SPEC`).

## Implementation notes

- `ccp/lib.py` and `ccp/architecture_review.py` are `git mv`s of the two modules. Paths that were relative to
  `scripts/observability/` now go through `parents[1]`: `bindings_dir()`'s default `projects/`, `PLUGIN_DIR`, and
  `wait_writer_cmd`'s `scripts/observability/set-waiting-on.sh`. `_config` imports `ccp.config` when called, with no
  `sys.path` fallback, so the module still runs as a file with the standard library alone.
- `ccp/queue.py`, `architect.py` and `health.py` import from `ccp`; no `sys.path` edit stays in `ccp` (E7's check passes).
  `spec_maintainer.py` and `team.py` put the plane root on their path and import `ccp.lib`; the four shell scripts
  export the plane root as `PYTHONPATH` and import `ccp.lib`.
- `binding_for_id` honours `PLANE_PROJECT_YAML` as well as `PROJECT_YAML`, as `binding_path` does: the narrowest
  reading that keeps one resolver's environment the same for a queue and an id.
- `validate_triage` runs `schema.schema_errors` on `contracts/architecture_review_triage.schema.json` first, then keeps
  the review id, the commit sha for a task or ruling, and the secret check. `DISPOSITIONS` stays in code and only the
  new test reads it; `triage_check`'s `RULE_DISPOSITIONS` check is now reached only when the contract's enum passed.
- `ccp prompt` takes `lib` from `ccp.queue` at module level, since its local import in `build` would otherwise make
  `lib` local to the whole function.
- The triage fixtures in `tests/test_architect.py` and `tests/test_review_aliases_retired.py` gained `triaged_at` (and
  `project_id`, `tasks_created` in the latter); expectations unchanged.
- Added beyond the task's tests: `test_the_rendered_prompt_is_written_atomically` (`tests/test_prompt_end.py`),
  `test_the_failure_file_is_written_atomically` (`tests/test_estimator.py`) and
  `test_the_bindings_directory_defaults_to_projects_beside_the_plane_code` (`tests/test_binding_by_id.py`).

## Verification notes
