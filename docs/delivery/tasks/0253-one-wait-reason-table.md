---
task_id: 0253-one-wait-reason-table
title: One wait-reason table, the retired steerer wait refused on set, and the retired snapshot's schema removed
status: pending
kind: feature
depends_on: ["0243-one-source-for-syntax-events-and-config"]
clashes_with: ["0191-the-grace-release-ends", "0218-idle-runner-slots-are-recorded-and-measured"]
spec_refs: ["S10", "S23"]
review_refs: ["ar-20261121T020523Z-1d5f#F02", "ar-20261121T020523Z-1d5f#F03", "ar-20261121T020523Z-1d5f#F09", "ar-20261121T020523Z-1d5f#F14"]
review_point: R17
paths: ["scripts/observability/set-waiting-on.sh", "scripts/observability/lib.py", "scripts/observability/CLAUDE.md", "scripts/observability/README.md", "ccp/cli.py", "ccp/lifecycle.py", "ccp/usage.py", "contracts/task.schema.json", "contracts/observability_now.schema.json", "docs/design/observability.md", "docs/spec/04-observability.md", "docs/cli/02-delivery.md", "docs/cli/04-observability.md", "plugin/skills/spec-maintainer/SKILL.md", "plugin/skills/writing-tasks/SKILL.md", "plugin/skills/review-triage/SKILL.md", "tests/test_wait_reasons.py", "tests/test_operator_rename.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0253-one-wait-reason-table

## Intent

The reasons a task may wait on are listed once, in the shared library, and the single writer, the
task contract and the SPEC agree with that list, held by a test. The retired `steerer` wait is only
read, as §10.1 says, and no skill presents the steerer as a live role. `ccp tasks wait` takes every
option the writer takes, so no `ccp` module builds its own call to the writer. The retired
snapshot's schema, which nothing writes or reads, is gone, and the observability docs stop
describing an alias table that does not exist.

## Context (not checked)

From architect pass `ar-20261121T020523Z-1d5f`, findings F02, F03, F09 and F14, triaged by the lead
on 2026-11-21. Measured at `aaa81b2`. `depends_on` 0243 because it also rewrites
`scripts/observability/lib.py` and `ccp/cli.py`'s docstring and adds the test holding `docs/cli` to
the parser, which this task's new flag must satisfy.

- **F02, the lists.** `scripts/observability/set-waiting-on.sh` validates `set` against its own
  literal tuple (`git grep -n '"design_seat", "null-class"' -- scripts/observability/set-waiting-on.sh` at `aaa81b2`: 1 line) and repeats the list in its usage text. `scripts/observability/lib.py`
  `WAIT_REASONS` is read only by a test (`git grep -n WAIT_REASONS -- ccp scripts tests` at `aaa81b2`: lib.py and 2 lines of `tests/test_operator_rename.py`). `contracts/task.schema.json`'s
  `waiting_on` enum lists them again. The SPEC's §23.2 payload row omits `design_seat`, which §10.1
  and the code include. Ruling: lib holds `WAIT_REASONS` (what `set` accepts, without `steerer`) and
  `WAIT_READ_ONLY = ("steerer",)` (read, never written, house rule E9); the writer imports lib (it
  already does for the lock) and validates against `WAIT_REASONS`; its usage text names the reasons by
  pointing at §10.1 instead of listing them. The new `tests/test_wait_reasons.py` asserts that the
  schema's `waiting_on` enum, less `null`, equals `WAIT_REASONS` plus `WAIT_READ_ONLY`, and reads the
  §23.2 `waiting_on` `set` row of `docs/spec/04-observability.md`: of the backticked names inside the
  parentheses after `reason`, those before the `;` equal `WAIT_REASONS` and those after it equal
  `WAIT_READ_ONLY`.
- **F02, the callers.** `git grep -n 'OBS / "set-waiting-on.sh"' -- ccp` at `aaa81b2`: 4 lines
  (`ccp/lifecycle.py` 3, `ccp/usage.py` 1). `ccp tasks wait` takes `--until` and `--detail` only
  (`./bin/ccp tasks wait -h | grep -c -- --quota-class` at `aaa81b2`: 0), so `ccp/usage.py`
  `"def _set_wait"` calls the script itself with `--task-only` and `--quota-class`. Ruling: one
  function in `ccp/lifecycle.py`, `"def set_wait"` (public), builds every call to the writer and
  takes `actor` (default `queue.actor()`; the release site passes its `who`), `task_only`,
  `quota_class`, `resets_at` and `detail`, and raises `QueueError` with the writer's code at every
  site: a writer exit 1 and a writer exit 2 pass through, any other code becomes exit 1. Today
  `"def _apply"`'s in-log clear always raises exit 1. The three
  lifecycle call sites and usage.py call it, and usage.py's `_set_wait` goes. `ccp tasks wait` gains `--quota-class
  {session,credit}`. `docs/cli/02-delivery.md`'s row gains the flag. `docs/cli/04-observability.md`
  says `set-waiting-on.sh` is waiting_on's single writer, which `ccp tasks wait|resume` call, instead
  of listing it among the wrappers over `ccp`.
- **F03, steerer.** `docs/spec/02-delivery.md` §10.1: "`steerer` is read for older queues." The writer
  still accepts it on `set`. The skills present the steerer as a role:
  `git grep -n -i steerer -- plugin/skills | wc -l` at `aaa81b2`: 4 lines (`spec-maintainer` 2,
  `writing-tasks` 1, `review-triage` 1). Ruling: `set … steerer` is refused (exit 2, as any other
  unknown reason), `clear` and every reader still accept it; the skills say the team lead (the spec
  maintainer) in place of the steerer, and the triage JSON's `answered_by` example reads
  `"spec_maintainer"`. `contracts/task.schema.json` and
  `contracts/architecture_review_triage.schema.json` keep `steerer` in their enums (read alias);
  task.schema.json's description of it says it is read for older queues and never written.
- **F09.** `contracts/observability_now.schema.json` has no writer or reader since task 0012:
  `git grep -l observability_now -- . ':!docs/delivery/tasks' ':!docs/delivery/reviews'` at `aaa81b2`: 3 files (the schema, `docs/design/observability.md`, `scripts/observability/README.md`).
  House rule E9: a contract no code writes or reads is removed.
- **F14.** `scripts/observability/CLAUDE.md` and `lib.py`'s module docstring say lib holds "the alias
  table for values renamed over time"; it holds none (`git grep -n -i 'alias table' -- scripts/observability` at `aaa81b2`: those 2 lines). Ruling: both name `WAIT_READ_ONLY` (above) and the read-only legacy
  event types 0243 adds as lib's read-only values, and drop "alias table".
- No SPEC rule beyond the §23.2 row changes: §10.1 already lists `design_seat` and says `steerer` is
  only read.
- **Lead's rulings on spec question `sm-20261121T225816Z-2535`** (ruling round 1), verbatim:

  > Ruling 0253-one-wait-reason-table-r1: wr-02 step 1 holds as "prints at least 1", since argparse prints each flag twice.
  >
  > Ruling 0253-one-wait-reason-table-r2: (a) the writer's unknown-reason refusal exits 2, steerer included, and set_wait passes 2 through: keep the change. (b) Only --quota-class goes on `ccp tasks wait`; planned_resume_at stays a set_wait parameter that usage.py calls directly.

## Scope

- **In:**
  - `scripts/observability/lib.py`, `scripts/observability/set-waiting-on.sh`,
    `scripts/observability/CLAUDE.md`, `scripts/observability/README.md`.
  - `ccp/lifecycle.py` (`set_wait`), `ccp/usage.py`, `ccp/cli.py` (`tasks wait --quota-class`).
  - `contracts/task.schema.json` (the `waiting_on` description), `contracts/observability_now.schema.json` (removed),
    `docs/design/observability.md` (its line naming that schema).
  - `docs/cli/02-delivery.md`, `docs/cli/04-observability.md`.
  - `plugin/skills/spec-maintainer/SKILL.md`, `plugin/skills/writing-tasks/SKILL.md`,
    `plugin/skills/review-triage/SKILL.md`.
  - `tests/test_wait_reasons.py` (new), `tests/test_operator_rename.py`.
  - SPEC, signed before the claim (`sign_off: brief`):
  - `docs/spec/04-observability.md` §23.2, the `waiting_on` `set` row of the payload table:

    CURRENT (`docs/spec/04-observability.md` at `aaa81b2`):
    > | `waiting_on` | `set` | `reason` (`quota`, `reauth`, `operator_decision`, `runner`, `steerer`, `spec_maintainer`, `null-class`, `operator_step`), `resets_at?` (RFC3339), `quota_class?` (`session`, `credit`), `detail?` |

    PROPOSED:
    > | `waiting_on` | `set` | `reason` (`quota`, `reauth`, `operator_decision`, `runner`, `spec_maintainer`, `design_seat`, `null-class`, `operator_step`; `steerer` only in older ledgers), `resets_at?` (RFC3339), `quota_class?` (`session`, `credit`), `detail?` |
- **Out:**
  - Dropping the `steerer` read alias (the operator's call once no queue holds it) and the
    spec_maintainer.py branches that read it.
  - Moving lib.py into the `ccp` package (deferred, ar-20261120T234012Z-27eb F17).

## dod_checks

- id: `wr-01`
  story: As a plane developer, the wait reasons live in one table that the writer and the task contract follow, and the test bites.
  setup: a checkout of the PR head; then a separate copy of it with `design_seat` removed from the `waiting_on` enum of `contracts/task.schema.json`.
  steps:
    1. On the head, run `git grep -n '"design_seat", "null-class"' -- scripts/observability/set-waiting-on.sh`.
    2. On the head, run `python3 -B -m unittest -q tests.test_wait_reasons tests.test_operator_rename`.
    3. In the copy, run `python3 -B -m unittest -q tests.test_wait_reasons`.
  expect: step 1 prints nothing; step 2 exits 0; step 3 exits non-zero.
  dry run (`aaa81b2`): step 1 printed 1 line (`set-waiting-on.sh:154`); steps 2 and 3 n/a, `tests/test_wait_reasons.py` is new.
- id: `wr-02`
  story: As a runner, `ccp tasks wait` takes every option the writer takes, and only one ccp function calls the writer.
  setup: a checkout of the PR head.
  steps:
    1. Run `./bin/ccp tasks wait -h | grep -c -- --quota-class`.
    2. Run `git grep -n 'OBS / "set-waiting-on.sh"' -- ccp`.
  expect: step 1 prints `1`; step 2 prints exactly one line, in `ccp/lifecycle.py`.
  dry run (`aaa81b2`): step 1 printed `0`; step 2 printed 4 lines (`ccp/lifecycle.py` 3, `ccp/usage.py` 1).
- id: `wr-03`
  story: As a lead, the retired steerer wait can no longer be set, and no skill names the steerer as a role.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_wait_reasons 2>&1 | grep -i steerer | grep -c ' ok$'`.
    2. Run `git grep -n -i steerer -- plugin/skills`.
  expect: step 1 prints a number of at least 1 (a test, named for steerer, that `set … steerer` exits non-zero and leaves the task's `waiting_on` unchanged); step 2 prints nothing.
  dry run (`aaa81b2`): step 1 n/a, the module is new; step 2 printed 4 lines.
- id: `wr-04`
  story: As a reader of contracts/, the retired snapshot's schema is gone and nothing names it.
  setup: a checkout of the PR head.
  steps:
    1. Run `test -e contracts/observability_now.schema.json; echo $?`.
    2. Run `git grep -l observability_now -- . ':!docs/delivery/tasks' ':!docs/delivery/reviews'`.
  expect: step 1 prints `1`; step 2 prints nothing.
  dry run (`aaa81b2`): step 1 printed `0`; step 2 printed 3 files.
- id: `wr-05`
  story: As a reader of the observability docs, they describe lib's read-only values as they are and name the writer as ccp's callee.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -i 'alias table' -- scripts/observability`.
    2. Run `git grep -c WAIT_READ_ONLY -- scripts/observability/CLAUDE.md scripts/observability/lib.py`.
    3. Run `grep -n 'wrappers over' docs/cli/04-observability.md | grep -c set-waiting-on`.
  expect: step 1 prints nothing; step 2 prints a count of at least 1 for each of the two files; step 3 prints `0`.
  dry run (`aaa81b2`): step 1 printed 2 lines; step 2 printed nothing; step 3 printed `1`.
- id: `wr-06`
  story: As the operator, the §23.2 row reads as I signed it.
  setup: a checkout of the PR head; the brief sign-off recorded.
  steps:
    1. Run `./bin/ccp verify spec-text 0253`.
  expect: exit 0, the PROPOSED passage found in `docs/spec/04-observability.md`.
  dry run: n/a — the passage lands with the task.

## Implementation notes

- `scripts/observability/lib.py` holds `WAIT_REASONS` (what `set` accepts, no `steerer`) and
  `WAIT_READ_ONLY = ("steerer",)`; its docstring and `scripts/observability/CLAUDE.md` name
  `WAIT_READ_ONLY` and `LEGACY_EVENT_TYPES` as the values only read, in place of the "alias table".
- `set-waiting-on.sh` imports `WAIT_REASONS` from lib and refuses any other reason on `set`, `steerer`
  included, with exit 2 (it was lib's `die` default, exit 1, for every unknown reason; the ruling asks for
  exit 2). `clear` takes any reason, so a `steerer` wait from an older queue still clears. Its usage text
  points at SPEC §10.1 instead of listing the reasons.
- `ccp/lifecycle.py` `set_wait` builds every `ccp` call to the writer: `actor`, `task_only`, `quota_class`,
  `resets_at`, `detail`, and also `planned_resume_at`, which the session park passes (§25.4). A writer exit
  1 or 2 passes through, any other failure (and a writer silent for 30 s, the timeout usage.py had) is exit
  1. `wait`, `_apply` (sync), `release` and usage.py's `clear_park` and `_park` call it; usage.py's
  `_set_wait` is gone. `ccp tasks wait` gains `--quota-class {session,credit}` only, as ruled.
- `contracts/observability_now.schema.json` is removed, with its lines in `docs/design/observability.md`
  and `scripts/observability/README.md`.
- `tests/test_session_park.py` patched `usage._set_wait`; it now patches `lifecycle.set_wait`.
- wr-02 step 1: argparse prints a flag on the usage line and under options, so `grep -c -- --quota-class`
  prints 2, as `--until` does at the base; the flag is there once, as one option.
- Ruling round 1 (`0253-one-wait-reason-table-r1`, `-r2`, on `sm-20261121T225816Z-2535`) confirms the
  code as built: wr-02 step 1 reads as "at least 1"; the writer's exit 2 on an unknown reason, `steerer`
  included, and `set_wait` passing 2 through stay; `ccp tasks wait` takes `--quota-class` only and
  `planned_resume_at` stays a `set_wait` parameter usage.py passes. No code, test or doc changed in this
  round; the rulings are recorded in Context.
- Fix round 1 (review MINOR and NITs): `SetWait`'s default-actor test sets `ACTOR=design-seat`, a valid
  actor other than `queue.actor()`'s own default, so a hard-coded `"task-runner"` in `set_wait` fails it;
  `set_wait`'s docstring says a timeout can leave work.json behind the ledger (the writer appends the event
  and writes the task file before it waits on work.json's lock); the spec-maintainer skill's line 28 reads
  "you hold the task-log authority as well", as line 129 does.

## Verification notes
