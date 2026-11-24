---
task_id: 0325-a-measured-premise-is-one-that-sets-scope-and-tasks-check-stops-warning-on-context-numbers
title: A measured premise is one that sets a task's scope (the sites it edits, a figure a check holds), and only it carries a command and commit and is re-run by the implementer; the lead re-measures only the briefs ccp tasks check --stale names; and ccp tasks check stops warning on any number in Context
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S21"]
review_refs: ["ar-20261123T230912Z-197a#F06"]
review_point: R32
paths: ["ccp/tasklog.py", "tests/test_tasklog.py", "tests/test_tasklog_context_checks.py", "tests/test_stale_context_audience.py", "tests/test_plugin.py", "docs/spec/01-model.md", "docs/spec/03-quality.md", "plugin/skills/writing-tasks/SKILL.md", "plugin/agents/delivery-implementer.md", "templates/prompts/implement.md"]
clashes_with: ["0191-the-grace-release-ends", "0320-dry-run-lists-a-placeholder-step-as-not-run-and-here-prints-each-step-s-whole-output", "0322-a-house-check-program-lives-in-a-tracked-script-and-mutate-files-unbuilt-only-on-the-mutant-s-own-files"]
sign_off: brief
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0325-a-measured-premise-is-one-that-sets-scope-and-tasks-check-stops-warning-on-context-numbers

## Intent

A task writer measures, with a command and a commit, only the premises that set the task's scope: the sites the
task edits and the figure a check holds. Other figures in Context (background, an errno, a timeout) are written
as plain prose, and `ccp tasks check` no longer warns about them. The implementer re-runs at its base only the
commands of the scope-setting premises, and the lead re-measures a brief before preferring it only when
`ccp tasks check --stale` names it, not every count of every brief.

## Context (not checked)

Finding F06 of architect pass `ar-20261123T230912Z-197a` (`docs/delivery/reviews/ar-20261123T230912Z-197a.md`), a
`rule-cost` finding, the record's first question. The operator chose option (a) on 2026-11-24, in these words:

> 1. (a)

The option, as the record gives it:

> (a) narrow it: a measured premise is one that sets scope (the sites a task edits, the figure a check holds); only
> those carry a command and commit and are re-run by the implementer; the lead's refresh re-measures only briefs
> that `ccp tasks check --stale` names; `ccp tasks check`'s warning on any Context number goes. One task, with a
> signed brief for the §5 and §21.1 sentences.

Measured at `146cae57` (origin/main after R28, R29 and R31 closed):

- **The warning.** `"def unmeasured_numbers"` in `ccp/tasklog.py` is called once, from `"def warnings"`
  (`git grep -nw unmeasured_numbers -- ccp` at `146cae57`: 2 lines, the definition and the call). It alone reads
  `CONTEXT_NUMBER_RE`, `NOT_MEASURED_RE`, `LIST_MARKER_RE`, `WORD_DATE_RE`, `QUOTED_RE`, `_MONTH`, `_NUM` and `_UNIT`
  (`git grep -nwP 'CONTEXT_NUMBER_RE|NOT_MEASURED_RE|LIST_MARKER_RE|WORD_DATE_RE|QUOTED_RE|_MONTH|_NUM|_UNIT' -- ccp`
  at `146cae57`: every hit in `ccp/tasklog.py`, at their definitions or in `unmeasured_numbers`). All of them go, with
  the comment above `CONTEXT_NUMBER_RE`. `_blank`, `CODE_SPAN_RE`, `FENCE_RE` and `unfence` stay: other readers use them.
- **What it gives today.** At `146cae57`, 5 warnings: `QUEUE_ROOT=<scratch> CCP_DEV=1 ./bin/ccp tasks check 2>&1 | grep -c 'Context states a number'`.
- **The tests that hold it** (`git grep -n 'Context states a number' -- tests` at `146cae57`: 6 lines in 3 files):
  - `tests/test_tasklog.py`, class `TaskLogTest`: `test_a_number_in_context_without_a_command_on_its_line_warns_and_does_not_fail`,
    `test_what_counts_as_a_number_and_as_a_command_in_context`, `test_a_number_joined_to_its_unit_or_a_dash_range_counts_as_a_number`
    and `test_a_stated_limit_or_a_protocol_code_is_not_a_measurement` go. One test replaces them:
    `test_a_number_in_context_without_a_command_raises_no_warning`, in the same class: a pending task whose Context
    line reads `- only 2 call sites exist` gives no warning naming its file, and `ccp tasks check` exits 0.
  - `tests/test_tasklog_context_checks.py`, class `QuotedRulings`: goes whole (it holds only the quoted-block
    exception of the warning).
  - `tests/test_stale_context_audience.py`, class `TasksCheck`: its fixture's third task (`0003-c`, "a number with no
    command") and the assertion that its warning stays go; the stale warnings it tests are unchanged.
- **The prose rule.** No file says "sets scope" yet. Ruled text:
  - `plugin/skills/writing-tasks/SKILL.md`, the bullet "**A measured premise names its measurement.**" becomes:
    "**A premise that sets scope names its measurement.** A premise sets scope when it is the list of sites the task
    edits or the figure a check holds. It names, in Context and on the same line, the command that measured it, in
    backticks, and the commit it ran at: `` `git grep -c foo -- src/` at `abc1234`: 2 call sites ``. The implementer
    re-runs it at its base before building and, if the figure changed materially, stops with a scope question. Any
    other figure in Context needs no command." Its sentences on `ccp tasks check`'s warning, the stated limits and the
    protocol codes go.
  - The same skill, the bullet "**Before a task is preferred**": "and re-measure the counts its Context states"
    becomes "and, when `ccp tasks check --stale` names it, re-measure the premises that set its scope".
  - The same skill, the bullet "**A ruling or sign-off is in git before anyone acts on it**": ", which the number
    warning skips" goes; the cite `(plane SPEC §10.5)` stays.
  - `templates/prompts/implement.md` and `plugin/agents/delivery-implementer.md`, the "Before you build" sentence:
    the parenthesis "(a count, a size, a list of sites, an "already" or "never happens" claim)" becomes "(one that
    sets scope: the sites the task edits, a figure a check holds)". The sentence after it is unchanged.
  - `tests/test_plugin.py`, `PREMISE_DOCS`: the skill's tokens lose "ccp tasks check` warns" and gain "sets scope";
    the brief's and the prompt's gain "sets scope". The test's comment says "a premise that sets scope".
- **No other SPEC text** holds the warning or the lead's re-measure. At `146cae57`, one line, §5.5's row: `grep -n -E 'states a number|re-measure' docs/spec/*.md`.

## Scope

- **In:** `ccp/tasklog.py` (`unmeasured_numbers` and the constants above removed, its call in `warnings`);
  `tests/test_tasklog.py`; `tests/test_tasklog_context_checks.py`; `tests/test_stale_context_audience.py`;
  `tests/test_plugin.py`; `plugin/skills/writing-tasks/SKILL.md`; `plugin/agents/delivery-implementer.md`;
  `templates/prompts/implement.md`; `docs/spec/01-model.md` (§5.5) and `docs/spec/03-quality.md` (§21.1), the
  passages below.
- **SPEC, signed before the claim (`sign_off: brief`):** two passages.

    CURRENT (`docs/spec/01-model.md` at `146cae57`), §5.5, the `Context (not checked)` row:
    > | `Context (not checked)` | task writer; the design seat when ruling (§17); on a claimed task, the implementer, writing a ruling the runner passes (§10.5) | background and constraints the verifier does not walk as checks. `Context (not verified)` is read as this heading. A count, size, site list or "already"/"never" claim in it names, on its line, the command that measured it and the commit it ran at; `ccp tasks check` warns, without refusing, about a line of it, in a task not yet done, that states a number with no backticked command on it, except a line of a quoted block (`> `), where a ruling written verbatim goes (§10.5) |

    PROPOSED:
    > | `Context (not checked)` | task writer; the design seat when ruling (§17); on a claimed task, the implementer, writing a ruling the runner passes (§10.5) | background and constraints the verifier does not walk as checks. `Context (not verified)` is read as this heading. A premise in it that sets the task's scope (the sites the task edits, a figure a check holds) names, on its line, the command that measured it and the commit it ran at; any other figure in it needs none |

    Retired: "A count, size, site list or "already"/"never" claim in it names …" (now only a premise that sets scope),
    and the whole clause on `ccp tasks check`'s warning, with its quoted-block exception.

    CURRENT (`docs/spec/03-quality.md` at `146cae57`), §21.1, in the paragraph that starts "It warns, without failing,
    when a task not yet done names a later task":
    > It also counts, in one warning, the tasks not yet done whose Context says ``Measured at `<sha>` `` when a commit since that sha changed one of the task's `paths`; `ccp tasks check --stale` names each such task with the commits, and the lead sees them at the spawn (§16.5) and the implementer in its prompt (§13.2).

    PROPOSED:
    > It also counts, in one warning, the tasks not yet done whose Context says ``Measured at `<sha>` `` when a commit since that sha changed one of the task's `paths`; `ccp tasks check --stale` names each such task with the commits, and the lead sees them at the spawn (§16.5) and the implementer in its prompt (§13.2). The lead re-measures a brief's premises before preferring it (§10.4) only when `--stale` names it.

    No sentence retired: one sentence added.
- **Out:** the stale-Context warning and `--stale` (unchanged); `Measured at` itself; the implementer's stop on a
  changed figure; any change to a done task's text.

## dod_checks

- id: `code-01`
  story: As a task writer, a number in Context with no command on its line raises no warning.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_tasklog.TaskLogTest.test_a_number_in_context_without_a_command_raises_no_warning`.
  expect: exit 0.
  dry run: n/a — the test is new.
- id: `cmd-01`
  story: As the lead, this repo's task check names no Context number.
  setup: A checkout of the PR head (any seat) and a scratch `QUEUE_ROOT` `<q>`.
  steps:
    1. Run `QUEUE_ROOT=<q> CCP_DEV=1 ./bin/ccp tasks check 2>&1 | grep -c 'Context states a number'`.
  expect: prints `0`.
  dry run (`146cae57`): printed `5`.
- id: `code-02`
  story: As a plane developer, the warning's code is gone, not left unused.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git show 146cae57:ccp/tasklog.py | grep -cwE 'unmeasured_numbers|CONTEXT_NUMBER_RE|NOT_MEASURED_RE|WORD_DATE_RE|QUOTED_RE'`.
    2. Run `git grep -nwP 'unmeasured_numbers|CONTEXT_NUMBER_RE|NOT_MEASURED_RE|WORD_DATE_RE|QUOTED_RE' -- ccp tests`.
  expect: step 1 prints a number above 0 (the pattern finds the code at the base); step 2 prints nothing.
  dry run (`146cae57`): step 1 printed `10`; step 2 printed 10 lines, all in `ccp/tasklog.py`.
- id: `doc-01`
  story: As a task writer, the skill and the implementer's briefs state the narrowed rule.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'sets scope' plugin/skills/writing-tasks/SKILL.md templates/prompts/implement.md plugin/agents/delivery-implementer.md`.
    2. Run `grep -c 'states a number with no backticked command' plugin/skills/writing-tasks/SKILL.md`.
    3. Run ``grep -c 'when `ccp tasks check --stale` names it' plugin/skills/writing-tasks/SKILL.md``.
  expect: step 1 prints a count of 1 or more for each of the three files; step 2 prints `0`; step 3 prints `1`.
  dry run (`146cae57`): step 1 printed 0 for each; step 2 printed `1`; step 3 printed `0`.
- id: `code-03`
  story: As a plane developer, the tests that hold the stale warning and the premise docs still pass.
  setup: As `code-01`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_tasklog tests.test_tasklog_context_checks tests.test_stale_context_audience tests.test_plugin.MeasuredPremises`.
  expect: exit 0.
  dry run (`146cae57`): exit 0 (the tests before the change).
- id: `spec-01`
  story: As the operator, §5.5 and §21.1 say what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0325`.
  expect: exit 0, both PROPOSED passages found.
  dry run (`146cae57`): exit 1, the PROPOSED passages missing.

## Implementation notes

## Verification notes
