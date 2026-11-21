---
task_id: 0244-tasks-check-runs-dry-runs
title: A dod_check's dry run is run and recorded by ccp, stale measured Context is flagged, and quoted rulings raise no number warning
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S10", "S21"]
review_refs: ["ar-20261120T234012Z-27eb#F12", "ar-20261120T234012Z-27eb#F13", "ar-20261120T234012Z-27eb#F14"]
review_point: R16
paths: ["ccp/dryrun.py", "ccp/tasklog.py", "ccp/cli.py", "ccp/config.py", "ccp/CLAUDE.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "templates/prompts/ruling.md", "plugin/agents/delivery-implementer.md", "templates/docs-delivery/standing-dod.md", "docs/delivery/standing-dod.md", "plugin/skills/writing-tasks/SKILL.md", "tests/test_tasks_dry_run.py", "tests/test_tasklog_context_checks.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0244-tasks-check-runs-dry-runs

## Intent

A task writer no longer types a dod_check's dry run: `ccp tasks dry-run` runs each check's command at
the integration tip and writes what it printed, so a check whose command does not exist, takes a
wrong argument or errors as written is caught before any worker sees it. A pending task whose
measured Context has gone stale (commits since its "Measured at" sha changed the files it declares)
is flagged by `ccp tasks check`, so the lead re-reads the brief before a runner spends a round on it.
And a ruling written verbatim into Context, as §10.5 requires, no longer raises an unmeasured-number
warning that nobody is allowed to clear.

## Context (not checked)

From architect pass `ar-20261120T234012Z-27eb`, findings F12, F13 and F14, triaged by the lead on
2026-11-21. Measured at `8aefa59`.

- **F12, typed dry runs.** §5 makes the dry run the writer's typed line, and §21.1 checks only that
  the line is there, "not that it is true". Friction notes on tasks 0120 to 0193 (in the architect
  report) name checks that called a nonexistent flag or command, or passed a str to `config.load`,
  each reaching the implementer, reviewer and verifier. Probe at `8aefa59`:
  `python3 -B -c "from ccp import config; print(config.load('.').project_id)"` raised
  `TypeError: unsupported operand type(s) for /: 'str' and 'str'`; `ccp tasks dry-run 0242` was refused
  as an invalid choice (no such subcommand).
- **The ruling on the mechanism.** A new subcommand, `ccp tasks dry-run <id> [--write]`, in a new
  module `ccp/dryrun.py`. It never runs inside `ccp tasks check` (which the gate and `ccp docs check`
  run). It makes a temporary worktree detached at `origin/<integration_branch>` and removes it when
  done; runs each numbered step that is one backticked command and nothing else (`N. Run \`…\`.`)
  with `bash -c`, in that worktree, each with a time limit (a constant in code); prints, per check id,
  each command's exit code, its output's line count and first line, and lists every other step as not
  run. `--write` writes each check's ``dry run (`<tip sha>`): …`` line from that output, replacing
  one already there, and changes nothing else in the file; a check with no step run keeps its line.
  It refuses a task that is `done` or `dropped`, or claimed (a claimed task's file is edited only in
  its PR, §10.5). `config.load` accepts a str as well as a `Path`.
- **F13, stale Context.** Tasks are written in batches with Context "Measured at `<sha>`" (e.g. task
  0203); nothing compares that sha with later commits. Ruling: for a task not yet done or dropped,
  `ccp tasks check` reads the first ``Measured at `<sha>` `` in Context and warns, without failing,
  when `git log <sha>..HEAD -- <the task's paths>` lists commits, naming them (at most a few, then a
  count). An unknown sha or a checkout without git gives no warning.
- **F14, rulings.** `ccp/tasklog.py` `"def unmeasured_numbers"` skips fenced blocks, code spans and
  a growing list of exception words (`NOT_MEASURED_RE`). A ruling passed verbatim (§10.5) keeps its §
  numbers, round ordinals and exit codes, so it warns with no allowed fix. Ruling: a ruling goes into
  Context as a quoted block (each line beginning `> `), and the warning skips quoted lines; no
  exception word is added. The implementer brief, the ruling prompt and the standing DoD say "as a
  quoted block". Count at `8aefa59`: `CCP_DEV=1 QUEUE_ROOT=<empty dir> ./bin/ccp tasks check 2>&1 | grep -c 'states a number'` printed 13.

## Scope

- **In:**
  - `ccp/dryrun.py` (new), `ccp/cli.py` (the subcommand), `ccp/config.py` (`load` accepts a str),
    `ccp/tasklog.py` (stale Context warning; quoted lines skipped), `ccp/CLAUDE.md` (layout).
  - `docs/cli/03-quality.md` (the subcommand's row).
  - `templates/prompts/ruling.md`, `plugin/agents/delivery-implementer.md`,
    `templates/docs-delivery/standing-dod.md`, `docs/delivery/standing-dod.md`,
    `plugin/skills/writing-tasks/SKILL.md`: a ruling is written as a quoted block; the writer runs
    `ccp tasks dry-run --write` instead of typing dry runs.
  - `tests/test_tasks_dry_run.py` (new), `tests/test_tasklog_context_checks.py` (new).
  - SPEC, signed before the claim (`sign_off: brief`):
  - `docs/spec/01-model.md` §5.5, the `dod_checks` row: CURRENT (at `8aefa59`): "a check whose steps run a command carries `dry run (<commit>): …` or `dry run: n/a — <reason>` where dry runs are required (§21.1)." PROPOSED:
    > a check whose steps run a command carries `dry run (<commit>): …`, written by `ccp tasks dry-run` (§21.1), or `dry run: n/a — <reason>` where dry runs are required (§21.1).
  - `docs/spec/01-model.md` §5.5, the `Context (not checked)` row: CURRENT (at `8aefa59`): "`ccp tasks check` warns, without refusing, about a line of it, in a task not yet done, that states a number with no backticked command on it" PROPOSED:
    > `ccp tasks check` warns, without refusing, about a line of it, in a task not yet done, that states a number with no backticked command on it, except a line of a quoted block (`> `), where a ruling written verbatim goes (§10.5)
  - `docs/spec/02-delivery.md` §10.5: CURRENT (at `8aefa59`): "the implementer writes it into the task file's `Context (not checked)` section on the task branch, besides its Implementation notes, so it lands in the task's PR (§17.4)." PROPOSED:
    > the implementer writes it, as a quoted block (each line beginning `> `), into the task file's `Context (not checked)` section on the task branch, besides its Implementation notes, so it lands in the task's PR (§17.4).
  - `docs/spec/03-quality.md` §21.1, the warnings paragraph: CURRENT (at `8aefa59`): "It warns, without failing, when a task not yet done names a later task as a prerequisite in prose: the prerequisite goes in `depends_on` instead." PROPOSED:
    > It warns, without failing, when a task not yet done names a later task as a prerequisite in prose: the prerequisite goes in `depends_on` instead. It also warns about a task not yet done whose Context says ``Measured at `<sha>` `` when a commit since that sha changed one of the task's `paths`, naming the commits.
  - `docs/spec/03-quality.md` §21.1: CURRENT (at `8aefa59`): none; a new paragraph goes at the end of §21.1, after the paragraph ending "Inline `# comments` in frontmatter are ignored." and before the `### 21.2` heading. PROPOSED:
    > **`ccp tasks dry-run <id> [--write]`** runs, in a temporary worktree detached at `origin/<integration_branch>` and removed afterwards, each `dod_check` step that is one backticked command and nothing else, and prints, per check, each command's exit code, its output's line count and its first line; any other step is listed as not run. With `--write` it writes each check's ``dry run (`<tip sha>`): …`` line from that output, replacing one already there, and changes nothing else in the file. It refuses a task that is `done`, `dropped` or claimed (§10.5).
- **Out:**
  - Turning `task_log.dry_run` on for the plane (the lead's call, separately).
  - Running dry runs inside `ccp tasks check`, the gate or `ccp docs check`.

## dod_checks

- id: `dry-01`
  story: As a task writer, `ccp tasks dry-run --write` runs my checks' commands at the tip and writes what they printed, and the test bites.
  setup: a checkout of the PR head; then a separate copy where `--write` leaves the task file unchanged.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_tasks_dry_run`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_tasks_dry_run`.
  expect: step 1 exits 0; step 2 exits non-zero.
  dry run: n/a — `tests/test_tasks_dry_run.py` is new.
- id: `dry-02`
  story: As the lead, a dry run leaves my checkout as it was and refuses a claimed task.
  setup: a checkout of the PR head. The fixture is in `tests/test_tasks_dry_run.py`: a temp product with a bare origin and a clone, whose task log holds one pending task with two checks (one whose only step runs `echo one`, one whose step is prose) and one claimed task.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_tasks_dry_run -k checkout -k claimed`.
  expect: exits 0, running at least two tests: one asserting that after `ccp tasks dry-run <pending task>` the clone's `git worktree list` has as many lines as before and `git status --porcelain` is empty, and that the output names both check ids, the second as not run; one asserting that `ccp tasks dry-run <claimed task>` exits non-zero and writes nothing.
  dry run: n/a — `tests/test_tasks_dry_run.py` is new; at `8aefa59` `ccp tasks dry-run` is refused as an invalid choice.
- id: `dry-03`
  story: As a check writer, `config.load` takes a str.
  setup: a checkout of the PR head, run from its root.
  steps:
    1. Run `python3 -B -c "from ccp import config; print(config.load('.').project_id)"`.
  expect: prints `control-plane`.
  dry run (`8aefa59`): raised `TypeError: unsupported operand type(s) for /: 'str' and 'str'`.
- id: `dry-04`
  story: As the lead, a pending task whose measured Context went stale is flagged, and one still current is not.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_tasklog_context_checks`.
  expect: exits 0, with tests covering: a commit after the Context's sha changing a declared path warns, naming the commit; a commit changing only an undeclared path does not; an unknown sha does not; a done task does not.
  dry run: n/a — `tests/test_tasklog_context_checks.py` is new.
- id: `dry-05`
  story: As an implementer, a ruling I write as a quoted block raises no number warning, and nothing else is exempted.
  setup: a checkout of the PR head with `origin/main` fetched.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_tasklog_context_checks`.
    2. Run `git show origin/main:ccp/tasklog.py > /tmp/tasklog_main.py && python3 -B -c "import importlib.util as u, sys; sys.path.insert(0, '.'); s=u.spec_from_file_location('m', '/tmp/tasklog_main.py'); m=u.module_from_spec(s); s.loader.exec_module(m); from ccp import tasklog; print(m.NOT_MEASURED_RE.pattern == tasklog.NOT_MEASURED_RE.pattern)"`.
  expect: step 1 exits 0, with a test that a Context line beginning `> ` holding `§10.5`, `round 2` and `42` warns nothing while the same line unquoted warns; step 2 prints `True`.
  dry run: n/a — the test module is new; step 2 printed `True` at `8aefa59` (head equal to `origin/main`).

## Implementation notes

## Verification notes
