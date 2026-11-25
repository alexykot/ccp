---
task_id: 0342-ccp-tasks-migrate-is-retired-and-the-task-writing-docs-name-adr-refs-count-steps-and-the-section-helpers
title: ccp tasks migrate is retired with its §5.3 paragraph, tasks check's pointer to it in §21.1 and its tests; the managed task template and README name adr_refs beside spec_refs; the writing-tasks skill says a count step names the exit it accepts; ccp/CLAUDE.md maps mdsection.py and spec.py
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S21"]
review_refs: ["ar-20261124T234643Z-3c95#F09", "ar-20261125T094654Z-c8a0#F08", "ar-20261125T094654Z-c8a0#F11"]
review_point: R37
paths: ["ccp/taskmigrate.py", "ccp/cli.py", "ccp/tasklog.py", "ccp/init.py", "ccp/CLAUDE.md", "docs/cli/02-delivery.md", "docs/spec/01-model.md", "docs/spec/03-quality.md", "plugin/skills/writing-tasks/SKILL.md", "templates/docs-delivery/README.md", "templates/docs-delivery/TEMPLATE-task.md", "tests/test_tasks_migrate.py", "tests/test_tasklog.py", "tests/test_init.py", "tests/test_mdsection.py"]
clashes_with: ["0191-the-grace-release-ends"]
sign_off: brief
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0342-ccp-tasks-migrate-is-retired-and-the-task-writing-docs-name-adr-refs-count-steps-and-the-section-helpers

## Intent

The plane no longer carries a converter for a task-file format no product or adopter still holds: `ccp tasks
migrate` is gone, and no command, message or doc points at it. A task file with no frontmatter is still one
failure of `ccp tasks check`, named as such. A product's task writer, starting from the managed template, sees that
a feature task may cite `adr_refs` in place of `spec_refs`; the writing-tasks skill tells them a count step names the
exit it accepts and a test check never counts a class's tests; and an implementer looking for the Markdown section
helper or the SPEC resolver finds both in `ccp/CLAUDE.md`'s map.

## Context (not checked)

The roadmap's deferral of `ar-20261124T234643Z-3c95` F09 (`docs/ROADMAP.md`), which the operator ruled on 2026-11-25
(3c95 question 2, recorded in `docs/delivery/reviews/ar-20261124T234643Z-3c95.md`):

> Accept both recommendations.

That chose option (a): "Retire `ccp tasks migrate`, its §5.3 text, `tasks check`'s pointer to it and its tests, in a
signed task of the next triage; keep `ccp tasks backfill-review-points` until every bound product's `--dry-run`
stamps nothing." `backfill-review-points` is out of this task. Also findings F08 and F11 of architect pass
`ar-20261125T094654Z-c8a0`, and the follow-up of 0338 the lead passed to that pass (the managed templates naming
`spec_refs` alone). See `docs/delivery/reviews/ar-20261125T094654Z-c8a0.md`.

Measured at `704ca8de`:

- **Sites.** `git grep -n -e 'tasks migrate' -e 'taskmigrate' -- ccp tests docs/spec docs/cli plugin templates`: 36
  lines in 13 files (`ccp/CLAUDE.md` 1, `ccp/cli.py` 4, `ccp/init.py` 2, `ccp/tasklog.py` 6, `ccp/taskmigrate.py` 2,
  `docs/cli/02-delivery.md` 1, `docs/spec/01-model.md` 1, `docs/spec/03-quality.md` 2,
  `plugin/skills/writing-tasks/SKILL.md` 1, `tests/test_init.py` 2, `tests/test_mdsection.py` 3, `tests/test_tasklog.py`
  4, `tests/test_tasks_migrate.py` 7). Two more name the command across a line break: `"def has_frontmatter"`'s
  docstring (`ccp/tasklog.py`, "which `ccp tasks\n    migrate` converts") and the skill's "convert an earlier
  generation's file with\n`ccp tasks migrate`".
- `CCP_DEV=1 ./bin/ccp tasks migrate --dry-run` on this repo: `0 converted, 341 already current, 0 cannot convert`
  (with this triage's tasks), exit 0.
- **The `texts` parameter.** `"def load(cfg: Config, texts"` and `"def check(cfg: Config, texts"` (`ccp/tasklog.py`)
  take `texts` for `ccp tasks migrate` alone (`git grep -n 'texts' -- ccp | grep -v taskmigrate` names no other
  caller passing it); `_requires_lines`'s docstring says so.
- **F08.** `grep -ow -e 'mdsection\.py' -e 'spec\.py' ccp/CLAUDE.md | sort -u | wc -l`: 0.
- **F11.** `grep -c 'exit it accepts' plugin/skills/writing-tasks/SKILL.md`: 0. 0339's code-01 expected "10 tests"
  from a class run; 0338's `grep -c` steps showed in dry-run as "exited 1" on a zero count.
- **Templates.** `grep -c 'adr_refs' templates/docs-delivery/README.md`: 0; `TEMPLATE-task.md`'s frontmatter has a
  `spec_refs: []` line and no `adr_refs` key (only the refactor comment names it).

**Ruled.**

- Delete `ccp/taskmigrate.py` and `tests/test_tasks_migrate.py`; remove `cmd_tasks_migrate` and the `migrate`
  subparser of `ccp tasks` from `ccp/cli.py`, and the row from `docs/cli/02-delivery.md`. `ccp tasks migrate` then
  exits 2 as any unknown subcommand.
- `ccp/tasklog.py`: `NO_FRONTMATTER` becomes `"no frontmatter: not a task file in the canonical format (SPEC §5.2)"`;
  the gone-file message drops its earlier-generation branch (`"It is an earlier plane generation's task file"`), so a
  gone file is told its restore and the `done`/`dropped` line, whatever its last text; `load` and `check` lose the
  `texts` parameter; the module, `has_frontmatter`, `_requires_lines` and the gone-file docstrings stop naming the
  command. `ccp tasks list`'s stderr line (`"def cmd_tasks_list"`) ends after "`ccp tasks check` names what is wrong".
- `ccp/init.py`: the warning becomes `"<n> task file(s) in <dir> have no frontmatter: `ccp tasks check` names each
  (SPEC §5.2)"`; the docstring stops naming the command.
- Tests: the asserts that a message names `ccp tasks migrate` (`tests/test_tasklog.py`, `tests/test_init.py`) assert
  instead that it does not; the two `taskmigrate` asserts in `tests/test_mdsection.py` go with the module. New tests
  `tests.test_tasklog.TaskLogTest.test_no_message_names_a_retired_converter` (a file with no frontmatter and a gone
  file whose last committed text has none: neither `check`'s failures nor `ccp tasks list`'s stderr holds
  `tasks migrate`, and the no-frontmatter failure ends with `NO_FRONTMATTER`) and
  `tests.test_init.EarlierTaskFiles.test_the_warning_names_tasks_check_not_a_converter`.
- `ccp/CLAUDE.md`, the Durable formats line: drop the `taskmigrate.py` clause; add, after `tasklog.py`'s clause,
  "`mdsection.py` (the one fence-aware finder of a Markdown section, house rule E22), `spec.py` (a SPEC ref resolved
  to its section, §7.2)".
- `plugin/skills/writing-tasks/SKILL.md`: "a task file that is gone (restore it; convert an earlier generation's file
  with `ccp tasks migrate`)" becomes "a task file that is gone (restore it)"; and, after the bullet "**A check that
  runs tests runs them through `ccp suite run`**", a new bullet: "- **A count step names the exit it accepts.** A
  test check names its test ids and never expects a count of a class's or a module's tests, which a sibling test
  moves; `grep -c` exits 1 when it counts nothing, so an expect of a zero count says `prints 0 (exit 1)`."
- `templates/docs-delivery/TEMPLATE-task.md`: after the `spec_refs: []` line, `adr_refs: []             #
  ["0031 D2"] — the ADR decisions it builds; a feature cites spec_refs or adr_refs (plane SPEC §5.4)`.
  `templates/docs-delivery/README.md`: "`spec_refs` cited in its text" becomes "`spec_refs` or `adr_refs` cited in
  its text".
- No other test expectation changes. House rule E21's text (the count of a class's tests) was applied in the triage
  PR; this task does not touch `docs/ENGINEERING.md`.

## Scope

- **In:** `ccp/taskmigrate.py` (removed); `tests/test_tasks_migrate.py` (removed); `ccp/cli.py`; `ccp/tasklog.py`;
  `ccp/init.py`; `ccp/CLAUDE.md`; `docs/cli/02-delivery.md`; `plugin/skills/writing-tasks/SKILL.md`;
  `templates/docs-delivery/README.md`; `templates/docs-delivery/TEMPLATE-task.md`; `tests/test_tasklog.py`;
  `tests/test_init.py`; `tests/test_mdsection.py`; the SPEC, signed:

  CURRENT (`docs/spec/01-model.md` at `704ca8de`), §5.3, its last paragraph:
  > A task file from an earlier plane generation (no frontmatter: a Meta and a Refs table) is converted
  > in place by `ccp tasks migrate [--dry-run] [--drop-open]`: its frontmatter from those tables and the
  > title from the committed `INDEX.yaml`, its old text kept under `Context (not checked)`, a done or
  > dropped record marked converted and not re-verified. An open task is converted only with
  > `--drop-open`, as `dropped`; a file it cannot convert is named with the reason and left as it is
  > (exit 1).

  Retired whole, with no text in its place: §5.3 ends at "it reads as `pending`, and `ccp tasks check` warns."

  CURRENT (`docs/spec/03-quality.md` at `704ca8de`), §21.1, the gone-file bullet's tail:
  > the message names the restore, `ccp tasks migrate` for an earlier generation's file and, for a
  > file git shows renamed, the `renamed_from` line to add; a task file with no frontmatter is one
  > failure naming `ccp tasks migrate`;

  PROPOSED:
  > the message names the restore and, for a file git shows renamed, the `renamed_from` line to add; a task file
  > with no frontmatter is one failure;

  Retired: "`ccp tasks migrate` for an earlier generation's file" and "naming `ccp tasks migrate`".
- **Out:** `ccp tasks backfill-review-points` and `ccp/backfill.py` (kept by the ruling); `ccp review-points
  migrate` and `ccp adr migrate` (other commands); `docs/ENGINEERING.md`; done task files and `INDEX.yaml`, which
  keep their history.

## dod_checks

- id: `cmd-01`
  story: As the lead, the retired converter is gone from the command line and from every doc, message and test.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp tasks migrate --dry-run`.
    2. Run `git grep -n -e 'tasks migrate' -e 'taskmigrate' -- ccp docs/spec docs/cli plugin templates`.
    3. Run `git ls-files tests/test_tasks_migrate.py`.
  expect: step 1 exits 2 (an unknown subcommand); step 2 prints nothing (git grep's exit 1, no match); step 3 prints nothing (exit 0). `tests/` is left out of step 2: the ruled tests name `tasks migrate` in asserts that it is absent.
  dry run (`704ca8de`): step 1 exit 0, `0 converted, 341 already current, 0 cannot convert`; step 2 printed 20 lines, exit 0; step 3 printed `tests/test_tasks_migrate.py`.
- id: `code-01`
  story: As a task writer, a task file with no frontmatter is still one failure, and no message points at a converter.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_tasklog.TaskLogTest.test_no_message_names_a_retired_converter tests.test_init.EarlierTaskFiles.test_the_warning_names_tasks_check_not_a_converter`.
  expect: exit 0.
  dry run (`704ca8de`): exit 1 (`AttributeError: type object 'TaskLogTest' has no attribute 'test_no_message_names_a_retired_converter'`).
- id: `spec-01`
  story: As the operator, §21.1 says what I signed and §5.3 no longer describes the converter.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0342`.
    2. Run `git grep -n 'earlier plane generation' -- docs/spec`.
  expect: step 1 exits 0, the PROPOSED passage found; step 2 prints nothing (git grep's exit 1, no match).
  dry run (`704ca8de`, with this brief): step 1 exit 1, the PROPOSED passage missing; step 2 printed `docs/spec/01-model.md:536`, exit 0.
- id: `doc-01`
  story: As a product's task writer, the managed template and README show that a feature can cite adr_refs in place of spec_refs.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c '^adr_refs: \[\]' templates/docs-delivery/TEMPLATE-task.md`.
    2. Run `grep -c 'adr_refs' templates/docs-delivery/README.md`.
  expect: step 1 prints `1`; step 2 prints `1`.
  dry run (`704ca8de`): step 1 printed `0`, exit 1; step 2 printed `0`, exit 1.
- id: `doc-02`
  story: As a task writer, the skill tells me a count step names the exit it accepts and a test check counts no class.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'exit it accepts' plugin/skills/writing-tasks/SKILL.md`.
  expect: prints `1`.
  dry run (`704ca8de`): printed `0`, exit 1.
- id: `doc-03`
  story: As an implementer, ccp/CLAUDE.md's map names the section helper and the SPEC resolver.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -ow -e 'mdsection\.py' -e 'spec\.py' ccp/CLAUDE.md | sort -u | wc -l`.
  expect: prints `2` (wc's leading spaces aside).
  dry run (`704ca8de`): printed `0`.

## Implementation notes

## Verification notes
