---
task_id: 0299-the-pre-gate-and-review-run-what-the-branch-touches-and-every-recorded-suite-run-keeps-a-log
title: ccp suite affected reads a branch's own change from its merge base, ccp suite run --affected runs what it lists, a --full run keeps a log, and report.fill_suite's branches are tested on plain rows
status: pending
kind: feature
depends_on: ["0292-the-review-prompt-asks-for-a-cold-run-where-review-takes-no-cache-hits"]
spec_refs: ["S13", "S14"]
rule_refs: ["E15", "E21"]
review_refs: ["ar-20261122T141424Z-e148#F01", "ar-20261122T141424Z-e148#F05", "ar-20261122T141424Z-e148#F06", "ar-20261122T141424Z-e148#F07"]
review_point: R27
paths: ["ccp/suite.py", "ccp/cli.py", "ccp/report.py", "templates/prompts/_gate.md", "templates/prompts/review.md", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_suite_affected.py", "tests/test_suite.py", "tests/test_prompt_gate_block.py", "tests/test_prompt_tools.py", "tests/test_worker_efficiency.py", "tests/test_full_lane_prompt.py", "tests/test_suite_run_affected.py", "tests/test_suite_full_log.py", "tests/test_fill_suite.py"]
clashes_with: ["0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0299-the-pre-gate-and-review-run-what-the-branch-touches-and-every-recorded-suite-run-keeps-a-log

## Intent

A worker's pre-gate and a reviewer's run take the tests the branch's own change touches, even when the
integration branch has moved on since the branch was cut, and they get them from one command instead of
copying a module list from one command's stderr into the next. Every recorded suite run keeps a log, so a
test name a worker cites from a `--full` run can be checked later. The report's suite-line fill is decided
by a plain function over the folded runs, its branches tested on plain rows.

## Context (not checked)

From the triage of architect pass `ar-20261122T141424Z-e148` (F01, F05, F06, F07; the record is in
`docs/delivery/reviews/`). The SPEC passages are the operator's to sign (that record's second question).
Measured at `3368264`.

- **F01, the tip-relative diff.** `"def changed_paths"` in `ccp/suite.py`: with one ref,
  `tree = _commit_tree(root, ref, ref)` then `git diff --name-only … <tree> --`, the tip's tree against the
  working tree, so a branch behind the tip also lists every file the tip gained since the branch was cut.
  Both prompts run it against the tip (`git grep -n 'suite affected --since origin/' -- templates` at `3368264`: 2 lines,
  in `templates/prompts/_gate.md` and `templates/prompts/review.md`). Probe at `3368264`, from a checkout of
  the tip: `CCP_DEV=1 ./bin/ccp --root . suite affected --since 097a6560 | wc -l` printed 81 (one merge, 0273,
  behind). `--since origin/main...` is refused today ("git knows no such ref", exit 2), so the three-dot form
  is free.
- **F06, the hand-off.** `"def affected_hint"` prints `ccp suite run --lane <part> -- <argv> <modules>` on
  stderr for the worker to paste; `CCP_DEV=1 ./bin/ccp --root . suite run --affected` at `3368264`:
  "unrecognized arguments: --affected". Workers' notes of 0273, 0288 and 0291 (queue data) describe zsh
  passing an unquoted module list as one word.
- **F07, no log for `--full`.** `"def run"`'s log is opened only under `if mode == "summary":`; §14.2's
  `--full` bullet names no log, and §14.4's `ended` row carries "summary mode's `log` path".
- **F05, fill_suite.** `ccp/report.py` `"def fill_suite"` calls `suite.fold(q)` and then decides; `git grep -ln
  'fill_suite' -- tests` at `3368264`: nothing. Its branches are tested only through `ReportCrossCheck` in
  `tests/test_suite.py` (`awk '/^class ReportCrossCheck/{f=1;next} /^class /{f=0} f && /def test_/' tests/test_suite.py | wc -l` at `3368264`: 14 tests,
  on `SuiteFixture`, a git product).
- **0292 first.** 0292 (signed) changes the same line of `templates/prompts/review.md`, adding
  `{{^review_cache}} --cold{{/review_cache}}` after `--lane {{part_lane}}`; this task keeps that section on
  the new command. 0293 renames `ccp/report.py`'s `AUTO_ROLES`, the default of `fill_suite`'s `auto_lanes`
  (the clash).
- **Tests that pin today's prompt words**, in `tests/test_prompt_gate_block.py`, `tests/test_prompt_tools.py`,
  `tests/test_worker_efficiency.py` and `tests/test_full_lane_prompt.py` (`git grep -c 'suite affected --since' -- tests` at `3368264`: 1, 3, 3 and 1 lines).

### Rulings for the build (the lead's)

- **The merge-base form.** `--since <ref>...` (three dots, nothing after) is the files
  `git diff <merge base of <ref> and HEAD>` names against the working tree, plus the untracked files git does
  not ignore, as the one-ref form adds them. A `<ref>` with no merge base with `HEAD` exits 2 naming it. `<a>..<b>`
  and the one-ref form are unchanged; `<a>...<b>` stays refused.
- **`ccp suite run --affected [--since <ref>]`.** It works out the modules exactly as `ccp suite affected` does
  (same `--since`, default `HEAD`) and runs the command `"def affected_hint"`'s line names: the part role's lane
  with the modules, or the full role's lane when the line says to run it instead. That run is recorded as any
  run, every other option (`--cold`, `--task`/`--run`/`--phase`, `--summary`/`--full`, `--log`, `--wait`)
  applying. With no module touched it prints `ccp suite run --affected: no test module touched` on stderr,
  runs and records nothing, and exits 0. With modules but no line (no declared part lane and no language test
  command) it exits 2 naming why. `--affected` with `--lane` or a command after `--`, and `--since` without
  `--affected`, exit 2 with nothing run. `ccp suite affected` itself is unchanged.
- **The prompts.** `templates/prompts/_gate.md` gives the pre-gate's affected run as
  `` `{{ccp}} suite run --affected --since origin/{{integration}}...` `` (it picks the part or full lane itself),
  and `templates/prompts/review.md` gives the reviewer's run as
  `` `{{ccp}} suite run --affected --since origin/{{integration}}...` `` from the checkout of the head, 0292's
  `{{^review_cache}} --cold{{/review_cache}}` section kept on it. The tests in Context follow the new words.
- **The `--full` log.** A `--full` run that is recorded opens its log as summary mode does (`--log`, else beside
  the run's record, else `runs/_suite-logs/`, else a temp file) and copies to it everything it copies through,
  both streams in the order `ccp` reads them; what reaches the terminal is unchanged, with no line of `ccp`'s
  added. The `ended` row records `log` in both modes, and `ccp suite list` shows it. A log
  that cannot be opened is a warning and the run streams with none, as in summary mode. Pruning (§14.4) already
  matches these paths.
- **fill_suite.** A plain function `judge_suite(rows, run_id, phase, parsed, accept_cache, auto_lanes)` in
  `ccp/report.py` reads and writes nothing and returns `(errors, warnings, update)`; `fill_suite` folds, calls it
  and applies `update` to `parsed`. A new `tests/test_fill_suite.py` tests each outcome on plain rows: a hand-written
  line stays; an unparsed line warns; `from` an unknown run, another run's, one not ended or with no count, and,
  in verify with `accept_cache`, one with no cache counts, each refused; `from` a good run fills its numbers with
  `suite_filled: from` and `suite_passed`; with no line, no matching run fills nothing, a failed latest run warns
  and fills nothing, a passed one fills `auto`, and in verify with `accept_cache` one with no cache counts fills
  nothing and warns nothing. In `ReportCrossCheck`, `test_suite_from_takes_the_recorded_numbers`,
  `test_suite_from_an_all_cached_gate_takes_zero_tests_ran`, `test_a_failed_latest_run_fills_nothing_and_warns`,
  `test_an_unparsed_suite_line_warns_and_is_not_filled_over`, `test_no_suite_line_and_no_full_run_fills_nothing`
  and `test_a_hand_written_line_stays` go (E15); the other eight stay.

## Scope

- **In:** `ccp/suite.py` (`"def changed_paths"`, `"def run"`'s log), `ccp/cli.py` (`suite run --affected`,
  `--since`), `ccp/report.py` (`"def fill_suite"`), `templates/prompts/_gate.md`, `templates/prompts/review.md`,
  `docs/cli/02-delivery.md` (the `ccp suite run` and `ccp suite affected` rows), `tests/test_suite_run_affected.py`
  (new), `tests/test_suite_full_log.py` (new), `tests/test_fill_suite.py` (new), and the test modules named in
  Context.
- **SPEC, signed before the claim (`sign_off: brief`):** seven passages in `docs/spec/02-delivery.md`, each CURRENT
  at `3368264`.

    CURRENT (`docs/spec/02-delivery.md` at `3368264`), §13, the **Fail fast** item:
    > and the run `ccp suite affected` prints on stderr (§14.7), through `ccp suite run`: the part lane, or, when it says the change reaches most of the suite, no pre-gate and the full lane.

    PROPOSED:
    > and `ccp suite run --affected --since origin/<integration>...` (§14.7), which runs the part lane on the modules the branch's own change touches or, when that change reaches most of the suite, the full lane in place of the pre-gate.

    CURRENT (`docs/spec/02-delivery.md` at `3368264`), §14.2, the `--full` item:
    > is the default with a terminal on stdin: the output is copied through unchanged as it arrives; when stdout and stderr are the same file the command gets one pipe for both.

    PROPOSED:
    > is the default with a terminal on stdin: the output is copied through unchanged as it arrives, and a recorded run also copies it to a log named as in summary mode, whose path its `ended` row records (§14.4); a log that cannot be opened is a warning, and the run streams with none. When stdout and stderr are the same file the command gets one pipe for both.

    CURRENT (`docs/spec/02-delivery.md` at `3368264`), §14.2, **Summary mode**, after its list:
    > A log that cannot be opened is a warning, and the run streams as `--full` does.

    PROPOSED:
    > A log that cannot be opened is a warning, and the run's output streams through unchanged, with no log.

    CURRENT (`docs/spec/02-delivery.md` at `3368264`), §14.4, the `ended` row's fields:
    > `counts_from`, summary mode's `log` path, `cold` (§14.6)

    PROPOSED:
    > `counts_from`, the run's `log` path, `cold` (§14.6)

    CURRENT (`docs/spec/02-delivery.md` at `3368264`), §14.4, **Logs are pruned**:
    > A recording `ccp suite run` removes summary-mode logs

    PROPOSED:
    > A recording `ccp suite run` removes suite-run logs

    CURRENT (`docs/spec/02-delivery.md` at `3368264`), §14.7, the opening paragraph:
    > guessing. It runs nothing and records nothing.

    PROPOSED:
    > guessing. It runs nothing and records nothing. `ccp suite run --affected [--since <ref>]` takes the same change and runs, recorded as any run (§14.4), what the stderr line below names: the part lane with the modules, or the full lane when the line says so. With no module touched it runs and records nothing, says so on stderr and exits 0; with no line to run it exits 2. It takes no `--lane` and no command after `--`, and `--since` without `--affected` exits 2, nothing run.

    CURRENT (`docs/spec/02-delivery.md` at `3368264`), §14.7, **The change**:
    > A range `<a>..<b>` given to `--since` is the files `git diff <a>..<b>` names, without the working tree.

    PROPOSED:
    > A range `<a>..<b>` given to `--since` is the files `git diff <a>..<b>` names, without the working tree. `<ref>...` (three dots, nothing after) is the change since the merge base of `<ref>` and `HEAD`: the files `git diff <merge base>` names against the working tree, plus the untracked files git does not ignore, so a branch behind `<ref>` lists only its own changes; a `<ref>` with no merge base with `HEAD` exits 2.
- **Out:** `ccp/prompt.py`'s `SUITE_LANES` and `"def suite_lanes"` (their part-lane wording "as `ccp suite affected`
  prints it" stays true, since that command and its stderr line are unchanged, and 0285 edits them); the one-ref and `<a>..<b>` forms; `ccp suite affected`'s output; `plugin/agents/delivery-implementer.md`'s
  `--since <ref>` for what a merge brought in (correct as it is); the verifier's gate; `suite.affected_map`.

## dod_checks

- id: `spec-01`
  story: As the operator, §13 and §14 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0299`.
  expect: exit 0, all seven PROPOSED passages found.
  dry run (simulated at `d17505a`: this task file committed, then each passage applied, its CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0299 --base HEAD~1`): `"ok": true`, every passage found.
- id: `cmd-01`
  story: As a worker on a branch the integration branch has moved past, the affected list holds only my own change.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_suite_affected`.
    2. Run `grep -e merge_base -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_suite_affected --mutant-file <file>`, the file's mutant making `changed_paths` diff the three-dot form's working tree against `<ref>`'s own tree instead of the merge base's.
  expect: step 1 exits 0; step 2 lists, `ok`, a test whose name holds `merge_base` where, in a repository whose `main` gained a commit changing `a.py` after the branch was cut and whose branch changed `b.py`, `--since main...` lists the tests of `b.py` and not those of `a.py`, and a ref with no merge base exits 2; then `OK`. Step 3 prints the mutant `killed`.
  dry run (`3368264`): step 1 ran and passed; step 2 printed only `OK` (no test names `merge_base` yet).
- id: `cmd-02`
  story: As a worker, one command runs the tests my change touches, with no list to copy.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_suite_run_affected`.
    2. Run `grep -e affected -e '^OK' <the log step 1 names>`.
    3. Run `git grep -n 'suite affected --since\|suite run --affected --since origin/{{integration}}\.\.\.' -- templates/prompts`.
  expect: step 1 exits 0; step 2 lists, each `ok`, tests whose names hold `affected` showing that `ccp suite run --affected` runs the part lane with exactly the modules `ccp suite affected` lists and records one run; that with nothing touched it records nothing, prints `no test module touched` and exits 0; and that `--affected` with `--lane`, with a command after `--`, and `--since` alone each exit 2 with no run recorded; then `OK`. Step 3 prints exactly two lines, one in `templates/prompts/_gate.md` and one in `templates/prompts/review.md`, each holding `suite run --affected --since origin/{{integration}}...`, and none holding `suite affected --since`.
  dry run (`3368264`): step 1: n/a — the module is new; step 3 printed 2 lines, both `suite affected --since origin/{{integration}}`.
- id: `cmd-03`
  story: As a reader checking a worker's cited test, a `--full` run has a log I can open.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_suite_full_log`.
    2. Run `grep -e full -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_suite_full_log --mutant-file <file>`, the file's mutant opening the log only when the mode is `summary`, as at `3368264`.
  expect: step 1 exits 0; step 2 lists, `ok`, a test whose name holds `full` where a recorded `--full` run of a command printing `alpha` on stdout and `beta` on stderr still prints both, its log holds both, its `ended` row's `log` names that file, and what the run printed is exactly the command's output, no line added; then `OK`. Step 3 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `code-01`
  story: As a plane developer, the report's suite-line fill is decided on plain rows and its branches are tested there.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_fill_suite`.
    2. Run `grep -c ' ok$' <the log step 1 names>`.
    3. Run `awk '/^class ReportCrossCheck/{f=1;next} /^class /{f=0} f && /def test_/' tests/test_suite.py | wc -l`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_fill_suite --mutant-file <file>`, the file's mutant making `judge_suite` fill `auto` from the latest run whatever its state.
  expect: step 1 exits 0; step 2 prints at least 11, one per outcome the rulings list; step 3 prints 8; step 4 prints the mutant `killed`.
  dry run (`3368264`): step 1: n/a — the module is new; step 3 printed 14.

## Implementation notes

- `ccp/suite.py`: `changed_paths` takes `<ref>...` (nothing after the dots) as the diff from `_merge_base(<ref>, HEAD)`
  against the working tree plus untracked files; an unknown ref or no merge base exits 2 naming the `--since`.
  `affected_plan` is the one decision of what runs the modules (lane, argv or None for the lane's own, the text the
  line prints); `affected_hint` formats its line from it, unchanged, and `ccp suite run --affected` runs it.
  `affected_modules` is what both commands work from. `main_run` refuses `--since` without `--affected`, and
  `--affected` with `--lane` or a command, before loading anything (`affected_usage`); then `affected_run` works out
  the lane and command, and the run goes on as any run.
- Choices the rulings leave open, the narrowest: `ccp suite run --affected` runs from the product root (the modules are
  named from it, as a named lane runs there), resolving a relative `--log` from the caller's directory first; before
  the run it prints one stderr line naming the `ccp suite run --lane …` it runs. The leading-dash `--since` rewrite in
  `cli.main` now applies to `suite run` too, so `--since -x` is an unknown ref, not an option.
- The `--full` log is opened only for a recorded run (a queue and a `started` row), as the ruling says; an unrecorded
  `--full` run keeps none, `--log` or not. Both streams are copied to it by the pumps under one lock, chunk by chunk;
  staged lanes' stage marks stay on stderr (they are `ccp`'s lines, not copied output). The log is not read back and
  no summary is printed in `--full`.
- `ccp/report.py`: `judge_suite` holds every branch of the old `fill_suite`; `fill_suite` folds, calls it and applies
  its update. Six `ReportCrossCheck` tests went (E15); `tests/test_fill_suite.py` holds 13 tests on plain rows.
- `tests/test_suite.py` `Counting.test_a_real_unittest_run_is_counted` asserted a `--full` run's `ended` row has
  `log: None`; the ruling changes that, so it now reads the log.

## Verification notes
