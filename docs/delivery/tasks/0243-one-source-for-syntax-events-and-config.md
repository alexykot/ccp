---
task_id: 0243-one-source-for-syntax-events-and-config
title: One source for plane.json reads, command syntax, the event registry and the detached launch, and multi-line schemas
status: pending
kind: refactor
depends_on: ["0203-follow-up-fixes"]
review_refs: ["ar-20261120T234012Z-27eb#F03", "ar-20261120T234012Z-27eb#F05", "ar-20261120T234012Z-27eb#F06", "ar-20261120T234012Z-27eb#F20", "ar-20261120T234012Z-27eb#F21"]
rule_refs: ["E12", "E16"]
review_point: R16
paths: ["scripts/observability/lib.py", "ccp/cli.py", "docs/cli/", "docs/cli.md", "ccp/queue.py", "ccp/architect.py", "ccp/board.py", "ccp/estimator.py", "contracts/escalation.schema.json", "contracts/progress.schema.json", "contracts/question.schema.json", "contracts/result.schema.json", "contracts/review.schema.json", "contracts/verification.schema.json", "docs/ENGINEERING.md", "docs/delivery/plane.json", "tests/test_cli_reference.py", "tests/test_event_registry.py", "tests/test_contract_layout.py", "tests/test_init.py", "tests/test_notify_lead.py", "tests/test_plane_built.py", "tests/test_plane_check.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0243-one-source-for-syntax-events-and-config

## Intent

Five facts the plane keeps in more than one place get one source each, held by a test or a house-rule
check, so the next change edits one place and a missed copy fails loudly. The shared library takes
plane.json values from the loaded config instead of reading the file with its own defaults. The
command surface is argparse, and the command reference is held to it by a test. The ledger's event
types and ops are compared with their schema as a whole. The detached `ccp` launch is one helper.
The schemas edited most are multi-line, so two tasks touching one no longer conflict on the whole
file. Nothing the plane does changes.

## Context (not checked)

From architect pass `ar-20261120T234012Z-27eb`, findings F03, F05, F06, F20 and F21, triaged by the
lead on 2026-11-21, with the triage's rule changes to E16, E12 and the new E19, which land here
because their checks fail or do not exist until this task is built. Measured at `8aefa59`.
`depends_on` 0203 because it also edits `scripts/observability/lib.py`.

- **F03.** `scripts/observability/lib.py` `"def _product_plane"` reads
  `product_root / _config().CONFIG_REL` itself; `"def runner_worktree"` defaults `worktrees.dir`,
  falls back to the merged `adapter.worktree_dir` itself (`ccp/config.py` merges that key into
  `worktrees.dir` already), and `"def resolve_durable_docs_dir"` defaults `task_log.dir`.
  `grep -nE '^(WORKTREES_DIR|TASK_LOG_DIR) = ' scripts/observability/lib.py` at `8aefa59`: 2 lines,
  copies of `ccp/config.py`'s. Ruling: both functions load the product's `ccp.config` Config (lib
  imports `ccp.config` lazily already, `"def _config"`) and read `worktrees.dir` and `task_log.dir`
  from it; `_product_plane` and the two constants go. A product whose plane.json does not load gives
  the defaults, as today. Tests that reach these functions:
  `git grep -ln 'runner_worktree\|resolve_durable_docs_dir' -- tests` at `8aefa59`: 7 modules.
- **F05.** `ccp/cli.py`'s module docstring carries a usage table:
  `python3 -B -c "import ccp.cli as c; print(sum(l.startswith('  ccp ') for l in c.__doc__.splitlines()))"`
  at `8aefa59`: 37 lines. Two copies already disagree with the parser (the docstring's `tasks list`
  has no `--json`; `docs/cli/02-delivery.md`'s `tasks next` has no `--allow-overdue`). Ruling: the
  docstring keeps its first line and points at `ccp -h` and `docs/cli.md`; a new
  `tests/test_cli_reference.py` walks `ccp.cli.build_parser()` and fails when a subcommand or a long
  flag is missing from `docs/cli/*.md`, or when `docs/cli/*.md` names a `ccp` subcommand or flag the
  parser does not define. `docs/cli/` is corrected until it passes. Help text is left as it is.
- **F06.** `lib.EVENT_TYPES` and `lib.EVENT_OPS` against the schema's enums, compared by `python3 -B -c` with `set()` differences at `8aefa59`: ops agree (35 each); types differ by one, `hosting`, which the schema allows and lib
  only reads past (`lib.py`: "an old ledger's hosting switch … read past it"). Ruling: lib names
  read-only legacy types in one tuple (house rule E9's alias), and the new
  `tests/test_event_registry.py` asserts that the schema's type enum equals writer types plus legacy
  types, its op enum equals `EVENT_OPS`, and every `REQUIRED_PAYLOAD` key is a known type or op. The
  per-op schema assertions go: `git grep -l 'observability_event.schema.json' -- tests` at `8aefa59`: 4 modules (`test_init`, `test_notify_lead`, `test_plane_built`, `test_plane_check`).
- **F20.** `wc -l contracts/*.schema.json` at `8aefa59`: 6 of 23 are one line (escalation,
  progress, question, result, review, verification). Pretty-print them with `json.dumps(indent=2)`
  plus a trailing newline, no content change; `tests/test_contract_layout.py` (new) fails on a
  one-line schema. progress, result and review may later go with finding F07 (an operator
  question); pretty-printing them meanwhile costs nothing.
- **F21.** `git grep -n 'from ccp.cli import main; sys.exit' -- ccp` at `8aefa59`: 3 lines, in
  `ccp/architect.py`, `ccp/board.py`, `ccp/estimator.py`. Ruling: one helper in `ccp/queue.py`
  builds that bootstrap and starts the detached child (`start_new_session=True`, `QUEUE_ROOT` set,
  the caller's stdout and stderr); the three call it.
- **House rules, applied here** (text agreed in the triage record
  `docs/delivery/reviews/ar-20261120T234012Z-27eb.md`):
  - E16 text: "Only ccp/config.py reads plane.json. A hook, script or shared library that needs a
    setting asks `ccp` (JSON out) or takes it from ccp.config's loaded Config; it never opens the
    file, by literal name or by `CONFIG_REL`, and never defaults a key itself." Check and
    `architect.checks` `E16`: `! git grep -nE '(plane\.json"|CONFIG_REL)\)\.read_text' -- plugin scripts`.
  - E12 text: "One source per enumerated concept: a list of values (round phases, event types and
    ops, plane.json's blocks, their keys and defaults, the roles and their default models) is defined
    once in code. Other code derives from it. One test compares every plane.json block's keys and
    defaults with contracts/plane_config.schema.json, one compares the ledger's event types, ops and
    required payloads with contracts/observability_event.schema.json, and one compares the agent
    definitions' models with the role table." Check and `architect.checks` `E12`:
    `python3 -B -m unittest -q tests.test_plane_config_defaults tests.test_event_registry`.
  - E19 (new, under Architecture) text: "The parser is the one source of the command surface. Call
    syntax is written by hand in one place (docs/cli), held to the parser by a test; no module
    docstring carries a usage table." Check and `architect.checks` `E19`:
    `python3 -B -m unittest -q tests.test_cli_reference`.

## Scope

- **In:**
  - `scripts/observability/lib.py` (F03, F06's legacy tuple).
  - `ccp/cli.py` docstring, `docs/cli/`, `docs/cli.md`; `tests/test_cli_reference.py` (new).
  - `tests/test_event_registry.py` (new); the four modules' per-op assertions removed.
  - The six one-line schemas, pretty-printed; `tests/test_contract_layout.py` (new).
  - `ccp/queue.py` (the detached-launch helper), `ccp/architect.py`, `ccp/board.py`, `ccp/estimator.py`.
  - `docs/ENGINEERING.md` (E12, E16 amended, E19 added) and `docs/delivery/plane.json`
    (`architect.checks` E12, E16 changed, E19 added).
- **Out:**
  - Moving lib.py into the `ccp` package (F17, deferred to the roadmap).
  - Help strings that restate exit codes.
  - Deleting any contract (F07).

## dod_checks

- id: `one-01`
  story: As a plane developer, the shared library takes plane.json values from the loaded config, and the widened E16 check holds.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE '(plane\.json"|CONFIG_REL)\)\.read_text' -- plugin scripts`.
    2. Run `grep -nE '^(WORKTREES_DIR|TASK_LOG_DIR) = ' scripts/observability/lib.py`.
    3. Run `python3 -B -m unittest -q tests.test_binding_reader tests.test_short_binding tests.test_wt tests.test_toolkit tests.test_tasks_close`.
  expect: steps 1 and 2 print nothing; step 3 exits 0.
  dry run (`8aefa59`): step 1 printed 1 line (`scripts/observability/lib.py`); step 2 printed 2 lines.
- id: `one-02`
  story: As a plane developer, the command reference is held to the parser, and the test bites.
  setup: a checkout of the PR head; then a separate copy with the `--allow-overdue` flag deleted from `docs/cli/02-delivery.md`.
  steps:
    1. On the head, run `python3 -B -c "import ccp.cli as c; print(sum(l.startswith('  ccp ') for l in c.__doc__.splitlines()))"`.
    2. On the head, run `python3 -B -m unittest -q tests.test_cli_reference`.
    3. In the copy, run `python3 -B -m unittest -q tests.test_cli_reference`.
  expect: step 1 prints `0`; step 2 exits 0; step 3 exits non-zero.
  dry run (`8aefa59`): step 1 printed `37`; steps 2 and 3 n/a, the test is new.
- id: `one-03`
  story: As a plane developer, the ledger's event registry is compared with its schema in one test, and the test bites.
  setup: a checkout of the PR head; then a separate copy with one op removed from the `op` enum of `contracts/observability_event.schema.json`.
  steps:
    1. On the head, run `git grep -l 'observability_event.schema.json' -- tests`.
    2. On the head, run `python3 -B -m unittest -q tests.test_event_registry`.
    3. In the copy, run `python3 -B -m unittest -q tests.test_event_registry`.
  expect: step 1 lists only `tests/test_event_registry.py`; step 2 exits 0; step 3 exits non-zero.
  dry run (`8aefa59`): step 1 listed 4 modules; steps 2 and 3 n/a, the test is new.
- id: `one-04`
  story: As a plane developer, every schema is multi-line with its content unchanged.
  setup: a checkout of the PR head with `origin/main` fetched.
  steps:
    1. Run `wc -l contracts/*.schema.json | awk '$1<=1'`.
    2. Run `for f in contracts/*.schema.json; do git cat-file -e origin/main:$f 2>/dev/null || continue; python3 -c "import json,subprocess,sys; a=json.loads(subprocess.check_output(['git','show','origin/main:'+sys.argv[1]])); sys.exit(a != json.load(open(sys.argv[1])))" $f || echo $f; done`.
    3. Run `python3 -B -m unittest -q tests.test_contract_layout`.
  expect: steps 1 and 2 print nothing; step 3 exits 0.
  dry run (`8aefa59`): step 1 printed 6 lines; step 2 printed nothing; step 3 n/a, the test is new.
- id: `one-05`
  story: As a plane developer, a detached `ccp` child is started in one place.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'from ccp.cli import main; sys.exit' -- ccp`.
    2. Run `python3 -B -m unittest -q tests.test_architect tests.test_board tests.test_estimator`.
  expect: step 1 prints exactly one line, in `ccp/queue.py`; step 2 exits 0.
  dry run (`8aefa59`): step 1 printed 3 lines.
- id: `one-06`
  story: As the architect, the amended house rules and their checks are in force.
  setup: a checkout of the PR head; `QUEUE_ROOT` an empty temp dir.
  steps:
    1. Run `python3 -B -c "import json; c={x['id']: x['cmd'] for x in json.load(open('docs/delivery/plane.json'))['architect']['checks']}; print('CONFIG_REL' in c['E16'], 'test_event_registry' in c['E12'], 'test_cli_reference' in c.get('E19', ''))"`.
    2. Run `grep -c '^- \*\*E19\*\*' docs/ENGINEERING.md`.
    3. Run `ccp wt exec -- docs check`.
  expect: step 1 prints `True True True`; step 2 prints `1`; step 3 exits 0.
  dry run (`8aefa59`): step 1 printed `False False False`; step 2 printed `0`.

## Implementation notes

## Verification notes
