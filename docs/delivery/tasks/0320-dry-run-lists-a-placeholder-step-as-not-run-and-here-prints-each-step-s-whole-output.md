---
task_id: 0320-dry-run-lists-a-placeholder-step-as-not-run-and-here-prints-each-step-s-whole-output
title: ccp tasks dry-run lists a step whose command holds a placeholder as not run, naming it, and with --here prints each step's whole output; the worker prompt and the runner brief name the command they mean
status: pending
kind: feature
depends_on: []
spec_refs: ["S21", "S13", "S15"]
review_refs: ["ar-20261124T034246Z-e089#F01"]
review_point: R33
paths: ["ccp/dryrun.py", "tests/test_tasks_dry_run.py", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "templates/prompts/_common.md", "plugin/agents/delivery-runner.md"]
clashes_with: ["0191-the-grace-release-ends", "0322-a-house-check-program-lives-in-a-tracked-script-and-mutate-files-unbuilt-only-on-the-mutant-s-own-files"]
sign_off: brief
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0320-dry-run-lists-a-placeholder-step-as-not-run-and-here-prints-each-step-s-whole-output

## Intent

A seat that walks one of its task's dod_checks with `ccp tasks dry-run <id> --check <check id> --here`, as every
prompt tells it to, sees what each step really did. A step whose command still holds a placeholder (`<your run>`,
`<the log step 1 names>`, `<checkout>`) is listed as not run, naming the placeholder, instead of being handed to bash
and reported as a syntax error. With `--here`, each step's whole output is printed, not only its first line, so the
seat does not rerun the step by hand to read it. The worker prompt's mutation-worktree bullet names the
`ccp suite run` command it means, and the runner brief says which refusal `ccp verify record` gives first.

## Context (not checked)

Finding F01 of architect pass `ar-20261124T034246Z-e089` (`docs/delivery/reviews/ar-20261124T034246Z-e089.md`), the
lead's friction notes T94 and T95 (dry-run on placeholder steps), and these open follow-ups
(`QUEUE_ROOT=<queue> ccp --root . tasks follow-ups --open`):

- `0306-…/review#2`, `/verify#2`: `plugin/agents/delivery-runner.md` describes `verify record`'s refusal of an approve of
  a head the review did not judge; with an open verify run, the head check of §15.4 now refuses that case first.
- `0307-…/review#1`: whether "the command above" in `templates/prompts/_common.md` names `{{ccp}} suite run`. 0307's fix
  round named it in the evidence bullet; the mutation-worktree bullet after it still says "through the command above",
  and the nearest command above it is now the dry-run and docs-check bullet.

Measured at `9691fd9c` (origin/main after 0317's reconcile):

- **The placeholders.** `"def check_steps"` in `ccp/tasklog.py` takes a step as runnable when it is one backticked
  command and nothing else; nothing looks for a placeholder. A probe over every task file's checks (the steps
  `tasklog.check_steps` gives a command), with the pattern `<[A-Za-z][^<>\n]*>`:
  `python3 -B -c 'import re,pathlib,ccp.tasklog as t; P=re.compile(r"<[A-Za-z][^<>\n]*>"); c=[s for f in sorted(pathlib.Path("docs/delivery/tasks").glob("0*.md")) if int(f.name[:4])>=290 for _,s in t.check_steps(t._section(f.read_text(),"dod_checks") or "") if s]; print(len(c), sum(bool(P.search(s)) for s in c))'`
  printed `228 65`: 65 of the 228 runnable steps of tasks 0290 to 0319 hold one. Over all task files the matches are
  all placeholders (`<your run>`, `<task>`, `<the log step 1 names>`, `<tmp>`, `<n>` and so on); none is a shell
  redirection, since the pattern needs a letter right after `<` and a `>` before any other `<`, `>` or line break.
- **What the seat sees now.** A scratch product whose task `0001-a` has the check below (the `setup` of `cmd-01`):
  `QUEUE_ROOT=<q> CCP_DEV=1 ./bin/ccp --root <product> tasks dry-run 0001-a --check cmd-01 --here` printed
  `step 1 exited 2, 2 lines, first: ``bash: -c: line 0: syntax error near unexpected token `newline'``` and
  `step 2 exited 0, 3 lines, first: `one``, exit 0.
- **The first line.** `"def outcome"` in `ccp/dryrun.py` keeps `lines[0]`, cut at `FIRST_LINE_CAP` (160); `"def _here"`
  prints the same printout as the worktree mode, though it writes no record.
- **Ruled.**
  - A step's command is a placeholder step when it matches `<[A-Za-z][^<>\n]*>` (one module constant in
    `ccp/dryrun.py`, `PLACEHOLDER_RE`). It is not run, with or without `--here`, and its printout line is
    `step <n>: not run (holds the placeholder <the first match, as a code span>)`. With `--write`, its check's record
    is written from the steps that ran, as for any other step not run.
  - With `--here`, each step that ran prints its line as today, then every line of its output, each indented six
    spaces, with no cap. Without `--here` nothing changes: the printout and the record keep the first line.
  - No `--run` option: a placeholder is never filled in.
  - The test is `test_a_step_holding_a_placeholder_is_not_run_and_names_it` in `tests/test_tasks_dry_run.py` (class
    `StepsAndRecords`), on plain values (`plan` and `printout`), for `<your run>` and `<the log step 1 names>`, and
    showing that `printf 'a\n' > out` (a redirection) and `grep -c x < in` still run, and that `sort <in >out` and
    `cat <<EOF >f` are listed as not run (safe: nothing runs).
- **The prompt bullet.** `templates/prompts/_common.md`, the bullet that starts "Where the product declares no
  `mutate.command`", says "run the test there through the command above with `--lane {{part_lane}}`"
  (`grep -c 'through the command above' templates/prompts/_common.md` at `9691fd9c`: 1). It becomes
  "run the test there through `{{ccp}} suite run` with `--lane {{part_lane}}`".
- **The runner brief.** `plugin/agents/delivery-runner.md`, in the fix-round paragraph: "and `ccp verify record` refuses
  the approve, unless the product's `verify.skip_review`". It becomes "and `ccp verify record` refuses the approve (it
  refuses first a verdict whose head is not the open verify run's, SPEC §15.4), unless the product's
  `verify.skip_review`" (`grep -c "not the open verify run's" plugin/agents/delivery-runner.md` at `9691fd9c`: 0).
- **Not changed.** The pairing of a mutation check with `suite run` in `_common.md`'s first bullet and evidence bullet
  stays: §13.1 and §13.2 give both routes, and the `suite run` route is the one a product with no per-test runner
  has (the triage drops 0317's follow-ups on it).

## Scope

- **In:** `ccp/dryrun.py` (`PLACEHOLDER_RE`, `plan` or `printout`, `outcome`, `_here`); `tests/test_tasks_dry_run.py`;
  `docs/spec/03-quality.md` (§21.1, the passage below); `docs/cli/03-quality.md` (the `ccp tasks dry-run` row, §31.1:
  it follows the passage); `templates/prompts/_common.md` (the mutation-worktree bullet); `plugin/agents/delivery-runner.md`
  (the fix-round sentence).
- **SPEC, signed before the claim (`sign_off: brief`):** one passage in `docs/spec/03-quality.md`, §21.1.

    CURRENT (`docs/spec/03-quality.md` at `9691fd9c`), §21.1, the paragraph on `ccp tasks dry-run`:
    > **`ccp tasks dry-run <id> [--write] [--check <check-id>] [--here]`** runs, in a temporary worktree detached at `origin/<integration_branch>` and removed afterwards, each `dod_check` step that is one backticked command and nothing else, through `bash -c`, and prints, per check, each command's exit code, its output's line count and its first line; any other step is listed as not run. `--check` runs only the named check. With `--write` it writes each check's ``dry run (`<tip sha>`): …`` line from that output, replacing one already there, and changes nothing else in the file. It refuses a task that is `done`, `dropped` or, without `--here`, claimed (§10.5). With `--here` it runs the steps in the checkout it is run in, at its HEAD, and writes nothing (it refuses `--write`), so a worker runs its own task's check as the dry run does.

    PROPOSED:
    > **`ccp tasks dry-run <id> [--write] [--check <check-id>] [--here]`** runs, in a temporary worktree detached at `origin/<integration_branch>` and removed afterwards, each `dod_check` step that is one backticked command and nothing else, through `bash -c`, and prints, per check, each command's exit code, its output's line count and its first line. A step whose command holds a placeholder (a `<`, a letter, then text up to the next `>` with no `<`, `>` or line break in it, as `<your run>`) is listed as not run, naming the placeholder; so is a step that is not one backticked command. `--check` runs only the named check. With `--write` it writes each check's ``dry run (`<tip sha>`): …`` line from that output, replacing one already there, and changes nothing else in the file. It refuses a task that is `done`, `dropped` or, without `--here`, claimed (§10.5). With `--here` it runs the steps in the checkout it is run in, at its HEAD, prints each command's whole output after its line, and writes nothing (it refuses `--write`), so a worker runs its own task's check as the dry run does.

  Retired: "any other step is listed as not run" (now "so is a step that is not one backticked command").
- **Out:** filling a placeholder in; the worktree mode's printout and records; `_common.md`'s other bullets; the
  verifier's and reviewer's briefs.

## dod_checks

- id: `cmd-01`
  story: As a worker, a check step that still holds a placeholder is listed as not run, naming it, and the next step still runs.
  setup: A checkout of the PR head at `<checkout>` (any seat). A scratch git repo `<product>` outside it (`git init`, one commit) holding `docs/delivery/plane.json` = `{"project_id": "p", "language": "python", "suite": {"lanes": {"gate": ["true"]}}}` and `docs/delivery/tasks/0001-a.md`, a pending task (frontmatter `task_id: 0001-a`, `title`, `status: pending`, `depends_on: []`, `spec_refs: ["S1"]`, `created`, `updated`; the six sections) whose one check `cmd-01` has two steps, ``1. Run `grep -c x <your run>`.`` and ``2. Run `printf 'one\ntwo\nthree\n'`.``; and a scratch `QUEUE_ROOT` `<q>`.
  steps:
    1. Run `cd <product> && QUEUE_ROOT=<q> CCP_DEV=1 <checkout>/bin/ccp --root <product> tasks dry-run 0001-a --check cmd-01 --here; echo "exit $?"`.
  expect: the step 1 line holds `not run` and `<your run>`; no line holds `syntax error`; the step 2 line holds `exited 0`; the last line is `exit 0`.
  dry run (`9691fd9c`): printed `step 1 exited 2, 2 lines, first: ``bash: -c: line 0: syntax error near unexpected token `newline'``` and `step 2 exited 0, 3 lines, first: `one``, then `exit 0`.
- id: `cmd-02`
  story: As a worker, `--here` shows me each step's whole output.
  setup: As `cmd-01`.
  steps:
    1. Run `cd <product> && QUEUE_ROOT=<q> CCP_DEV=1 <checkout>/bin/ccp --root <product> tasks dry-run 0001-a --check cmd-01 --here | grep -cE '^ +(two|three)$'`.
  expect: prints `2`.
  dry run (`9691fd9c`): printed `0` (exit 1).
- id: `code-01`
  story: As a plane developer, the placeholder rule is tested on plain values and a redirection still runs.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_tasks_dry_run.StepsAndRecords.test_a_step_holding_a_placeholder_is_not_run_and_names_it`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_tasks_dry_run`.
  expect: both exit 0.
  dry run: n/a — the test is new.
- id: `doc-01`
  story: As a worker without a per-test runner, the mutation-worktree bullet names the command it means.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'through the command above' templates/prompts/_common.md`.
    2. Run ``grep -c 'there through `{{ccp}} suite run` with' templates/prompts/_common.md``.
  expect: step 1 prints `0`; step 2 prints `1`.
  dry run (`9691fd9c`): step 1 printed `1`; step 2 printed `0`.
- id: `doc-02`
  story: As a runner, the brief says which refusal verify record gives first.
  setup: As `doc-01`.
  steps:
    1. Run `grep -c "not the open verify run's" plugin/agents/delivery-runner.md`.
  expect: prints `1`.
  dry run (`9691fd9c`): printed `0`.
- id: `spec-01`
  story: As the operator, §21.1 says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0320`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`9691fd9c`): exit 1, the PROPOSED passage missing; the CURRENT paragraph is found once in `docs/spec/03-quality.md` (`grep -c 'any other step is listed as not run' docs/spec/03-quality.md`: 1).

## Implementation notes

- `ccp/dryrun.py`: `PLACEHOLDER_RE` and `placeholder(cmd)` (the first match); `runnable(steps)` gives the steps both
  modes run (one backticked command holding no placeholder), so `plan` keeps each command and `printout` names the
  placeholder: `step <n>: not run (holds the placeholder <span>)`. `Ran` carries the step's whole output's lines;
  `printout(..., whole=True)`, which only `_here` passes, prints them under the step's line, indented six spaces
  (`HERE_INDENT`), uncapped. The worktree mode's printout and `--write` records are unchanged; a placeholder step
  is left out of its check's record like any step not run.
- Tests: `test_a_step_holding_a_placeholder_is_not_run_and_names_it` and
  `test_here_prints_each_step_s_whole_output_and_without_it_only_the_first_line` on plain values; the shared
  `CHECKS` fixture's `cmd-01` gains a placeholder step (the worktree mode and its `--write` record end to end), and
  the `--here` end-to-end test a step `touch ran # <your run>`, which bash would run, so a clean status shows it did
  not; its line indexes move by the whole output now printed.
- Docs: §21.1's passage as signed, the `ccp tasks dry-run` row in `docs/cli/03-quality.md`, `_common.md`'s
  mutation-worktree bullet and the runner brief's fix-round sentence as the Context gives them.

## Verification notes
