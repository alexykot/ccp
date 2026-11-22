---
task_id: 0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes
title: Seats run one dod_check or house-rule check exactly as the plane does, the plane declares its pre-gate lane, lane text names only declared lanes, and the SPEC states the operator-gate waiver limit and the one-gate-lane example
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S15", "S16", "S20", "S21"]
review_refs: ["ar-20261122T055103Z-11aa#F07", "ar-20261122T055103Z-11aa#F09"]
review_point: R25
paths: ["ccp/dryrun.py", "ccp/cli.py", "ccp/rules.py", "ccp/suite.py", "ccp/prompt.py", "ccp/tasklog.py", "docs/delivery/plane.json", "docs/cli/03-quality.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "tests/test_tasks_dry_run.py", "tests/test_docs_check_only.py", "tests/test_suite_lane_default.py", "tests/test_prompt_lanes.py", "tests/test_signed_blocks_check.py"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes

## Intent

A worker or reviewer runs one of its task's dod_checks, at its own head, exactly as the dry run does
(each step through `bash -c`, whatever its tool shell), and runs one house-rule check by id exactly as
`ccp docs check` does. The plane's own pre-gate is a declared lane, so a docs-rule or budget failure
shows in seconds rather than in the full lane. No message or prompt line points a worker at a lane the
product does not declare, nor offers a mutation check through a lane that takes module names. `ccp tasks
check` warns on an unreadable `PROPOSED:` wherever `ccp verify spec-text` would read one. The SPEC's
§16.2 example matches the one gate lane, and §15.4 states the rule the code already holds: an operator
gate never waives a check.

## Context (not checked)

From architect pass `ar-20261122T055103Z-11aa`, F07 (`process-cost`) and F09 (`process-cost`); the record
is in `docs/delivery/reviews/`. Worker follow-ups covered (`ccp tasks follow-ups --open`), every `…` being
`0265-one-gate-lane-and-worker-runs-wait-for-it`: `…/implement#2`, `…/ruling#1`, `…/review#3`, `…/fix#3`,
`…/verify#3` (§16.2's example); `…/review#2`, `…/fix#2`, `…/verify#2` (`resolve_stages`' example);
`0261-a-declared-part-lane-runs-the-affected-modules/fix#1` (the verify prompt's mutation-check wording);
`0264-one-parser-for-signed-blocks-and-task-id-patterns/review#2`, `…/fix#2`, `…/verify#2` (section
extents, `…` there being `0264-one-parser-for-signed-blocks-and-task-id-patterns`). Also the lead's deferred
question four of `ar-20261121T223646Z-f0a7` (§15.4), asked again in this triage.

Measured at `245528c`.

- **F07.** `python3 -B -c "import json;print(sorted(json.load(open('docs/delivery/plane.json'))['suite']['lanes']))"` at `245528c`:
  `['gate', 'part']`. `ccp/prompt.py` renders the declared `pregate` lane in place of the `architect.checks`
  commands (`"pregate = isinstance(lanes, dict) and PREGATE_LANE in lanes"`), and `ccp docs check`
  (`"def cmd_docs_check"`) runs the task-log check, the house rules' shape and line budget and every
  `architect.checks` entry, so one argv covers them. The roadmap's `ar-20261121T020523Z-1d5f` F12 entry
  made this a lead adopt step; this task takes it and the entry goes (this triage edits the roadmap).
- **F09.** `ccp/dryrun.py`'s `"def run_step"` runs `["bash", "-c", cmd]`; workers paste the same commands
  into their tool shell (zsh: `2>&1 >/dev/null` and an unquoted `$VAR` behave differently, per two 0261
  reviewer notes). `ccp tasks dry-run` refuses a claimed task (`"def refusal"`), so a worker cannot run its
  own task's check through it. House-rule checks run with `shell=True` in `ccp/rules.py` (`"def run_check_runs"`),
  and `ccp docs check` takes no check id. `git grep -n -i 'zsh\|bash -c' -- plugin/skills/writing-tasks templates/prompts plugin/agents docs/spec` at `245528c`: no lines.
- **The no-lane refusal.** `ccp/suite.py` `"def resolve_stages"`: "give the command after `--` (ccp suite
  run --lane full -- scripts/gate.sh), …". After 0265 this repo declares no `full` lane, and `full` is not in
  `exclusive_lanes`, so a run that follows the example skips the exclusive lock. `config.lane_for(cfg, "full")`
  at `245528c`: `gate`. `git grep -n 'lane full' -- ccp templates` at `245528c`: 1 line, this one; the
  prompts render each role's lane through `lane_for` (`"def suite_lanes"`), so 0265's `ruling#2`,
  `fix#1`, `review#1` and `verify#1` need no code (see the review record).
- **The verify part line.** `ccp/prompt.py` `SUITE_LANES["verify"]`: "{part}{part_for}a subset such as a
  mutation check{part_as}"; with this repo's declared part argv it renders `scripts/gate.sh <modules>`,
  which takes module names, not a mutation check, which runs through `ccp mutate`.
  `git grep -n 'such as a mutation check' -- tests` at `245528c`: no lines.
- **Section extents.** `ccp/tasklog.py` `"def unreadable_proposed"` finds the signed sections in the text
  with fences and code spans blanked, while `"def signed_blocks"` (what `ccp verify spec-text` reads)
  finds them in the raw text. A fenced line starting `## ` inside the Scope ends the section for
  `signed_blocks` only, so a quoted-inline `PROPOSED:` after it raises no warning.
- **§15.4.** `ccp/verify.py` `"def _waiver_texts"`: "An operator gate approves running a step, never skipping it, so
  a text whose only ids are operator gates waives nothing." §15.4 says a ruling may name "gate ids" with
  "every gate closed and approved", with no class limit. ADR-0045 D3 reads as the code does.
- **SPEC text measured.** `git grep -n 'exclusive_lanes": \["gate", "full"\]' -- docs/spec` at `245528c`: 1 line (§16.2);
  `docs/spec/01-model.md`'s `"suite": { "lanes": { "full": ["scripts/test.sh"]` example (§8) is a
  product's own lane name and stays.
- **Other tasks.** 0276 (R24) edits `ccp/suite.py` and `ccp/prompt.py` docstrings and template text; 0269
  (R21) changes `ccp verify`'s flags in `ccp/cli.py`; 0275 (R23, signed) changes `ccp tasks check`'s stale
  warnings in `ccp/tasklog.py`. Each is different logic from this task's. No clash.

### Rulings for the build (the lead's)

- `docs/delivery/plane.json` `suite.lanes.pregate` is `["bin/ccp", "docs", "check"]`, not exclusive.
- `ccp tasks dry-run <id> --check <check-id>` runs only that check; an id the task does not have exits 2
  naming its check ids. `--here` runs in the current checkout at HEAD, writes nothing, refuses `--write`
  (exit 2), refuses a `done` or `dropped` task and accepts a claimed one. Each step still runs through
  `run_step`, with its timeout.
- `ccp docs check --only <id>` runs that one `architect.checks` or `docs.checks` entry through the same
  runner and judging as `ccp docs check`, and nothing else; an unknown id exits 2 naming the known ids.
- `resolve_stages`' no-lane refusal names `ccp suite run --lane <lane_for(cfg, "full")>` and that lane's
  declared argv, or says to give the command after `--` where that lane declares none.
- `SUITE_LANES["verify"]`'s part item reads "a subset of the tests (a mutation check runs through `ccp mutate`)".
- `unreadable_proposed` takes its sections from `_signed_sections(text)`, the raw text as `signed_blocks`
  reads it, and still skips a `PROPOSED:` that sits in a code span or fenced block.
- `docs/cli/03-quality.md`'s `ccp tasks dry-run` and `ccp docs check` rows name the new flags.

## Scope

- **In:** `ccp/dryrun.py`, `ccp/cli.py` (the two parsers), `ccp/rules.py` (if the runner needs a filter),
  `ccp/suite.py` (`resolve_stages`), `ccp/prompt.py` (`SUITE_LANES`), `ccp/tasklog.py`
  (`unreadable_proposed`), `docs/delivery/plane.json` (`suite.lanes.pregate`), `docs/cli/03-quality.md`,
  `tests/test_tasks_dry_run.py`, `tests/test_docs_check_only.py` (new), `tests/test_suite_lane_default.py`,
  `tests/test_prompt_lanes.py` (new), `tests/test_signed_blocks_check.py`.
- **SPEC, signed before the claim (`sign_off: brief`):** two passages in `docs/spec/02-delivery.md` and
  two in `docs/spec/03-quality.md`, each CURRENT at `245528c`.

    CURRENT (`docs/spec/02-delivery.md` at `245528c`), §16.2, the second line of the knob's example:
    > "suite": { "exclusive_lanes": ["gate", "full"] },

    PROPOSED:
    > "suite": { "exclusive_lanes": ["gate"] },

    CURRENT (`docs/spec/02-delivery.md` at `245528c`), §15.4, the sentence that starts "A marked check resting on a verdict":
    > A marked check resting on a verdict it may carry needs no run at the new head, and one waived by a ruling is handled as any other.

    PROPOSED:
    > A marked check resting on a verdict it may carry needs no run at the new head, and one waived by a ruling is handled as any other, save that the ruling must name at least one id that is not a gate of class `operator`: an operator gate approves running a step, never skipping it.

    CURRENT (`docs/spec/03-quality.md` at `245528c`), §21.1, the paragraph on `ccp tasks dry-run`:
    > **`ccp tasks dry-run <id> [--write]`** runs, in a temporary worktree detached at `origin/<integration_branch>` and removed afterwards, each `dod_check` step that is one backticked command and nothing else, and prints, per check, each command's exit code, its output's line count and its first line; any other step is listed as not run. With `--write` it writes each check's ``dry run (`<tip sha>`): …`` line from that output, replacing one already there, and changes nothing else in the file. It refuses a task that is `done`, `dropped` or claimed (§10.5).

    PROPOSED:
    > **`ccp tasks dry-run <id> [--write] [--check <check-id>] [--here]`** runs, in a temporary worktree detached at `origin/<integration_branch>` and removed afterwards, each `dod_check` step that is one backticked command and nothing else, through `bash -c`, and prints, per check, each command's exit code, its output's line count and its first line; any other step is listed as not run. `--check` runs only the named check. With `--write` it writes each check's ``dry run (`<tip sha>`): …`` line from that output, replacing one already there, and changes nothing else in the file. It refuses a task that is `done`, `dropped` or, without `--here`, claimed (§10.5). With `--here` it runs the steps in the checkout it is run in, at its HEAD, and writes nothing (it refuses `--write`), so a worker runs its own task's check as the dry run does.

    CURRENT (`docs/spec/03-quality.md` at `245528c`), §20.1, the `command` bullet's last clause:
    > exit 0 = pass, run inside `ccp docs check` so the verifier gates on it (§21.2);

    PROPOSED:
    > exit 0 = pass, run inside `ccp docs check` so the verifier gates on it (§21.2), and alone by `ccp docs check --only <id>`, which runs that one `architect.checks` or `docs.checks` entry as `ccp docs check` does and nothing else;
- **Out:** an explicit `--lane full` where no full lane is declared (ruling `0265-…-r2` keeps the refusal);
  a render-only `ccp prompt` (F08, deferred); recording a check's run through `ccp suite run`.

## dod_checks

- id: `cfg-01`
  story: As a worker on the plane, my pre-gate is the declared lane and it passes on a clean head.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -c "import json;print(json.load(open('docs/delivery/plane.json'))['suite']['lanes'].get('pregate'))"`.
    2. Run `CCP_DEV=1 ./bin/ccp docs check >/dev/null 2>&1; echo "exit=$?"`.
  expect: step 1 prints `['bin/ccp', 'docs', 'check']`; step 2 prints `exit=0`.
  dry run (`245528c`): step 1 printed `None`; step 2 printed `exit=0`.
- id: `cmd-01`
  story: As a worker, I run one of my claimed task's checks at my head exactly as the dry run would.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_tasks_dry_run 2>&1 | grep -e here -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_tasks_dry_run --mutant-file <file>`, the file's mutant making `--here` run in the temporary worktree at the tip.
  expect: step 1 prints, each `ok`, a test where a claimed task's check whose step is `` `echo a 2>&1 >/dev/null; echo "$0"` `` run with `--check <id> --here` prints that check alone, its first line `bash`, from a commit only the current checkout holds, and leaves the task file unchanged; one where `--here --write` exits 2; and one where `--check` with an id the task lacks exits 2 naming its ids; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the tests are new.
- id: `cmd-02`
  story: As a reviewer, I run one house-rule check by id as ccp docs check runs it.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp docs check --only E22; echo "exit=$?"`.
    2. Run `CCP_DEV=1 ./bin/ccp docs check --only E99 2>&1 >/dev/null | head -1; python3 -B -m unittest -q tests.test_docs_check_only 2>&1 | tail -1`.
  expect: step 1 ends `exit=0` and names E22 and no other check; step 2's first line names `E99` and the known ids, then `OK`.
  dry run (`245528c`): step 1 printed argparse's unrecognized-arguments error and `exit=2`; step 2: n/a (the test module is new).
- id: `cmd-03`
  story: As a worker, no refusal or prompt line points me at a lane the product does not declare or at a mutation check through module names.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n -e 'lane full' -e 'such as a mutation check' -- ccp templates; echo "exit=$?"`.
    2. Run `python3 -B -m unittest -q tests.test_suite_lane_default tests.test_prompt_lanes 2>&1 | tail -1`.
  expect: step 1 prints only `exit=1`; step 2 prints `OK`, with `tests.test_prompt_lanes` holding a test that the no-lane refusal in a product declaring only `gate` and `part` names `--lane gate`, and one that the rendered verify prompt's part item names `ccp mutate`.
  dry run (`245528c`): step 1 printed 2 lines (`ccp/suite.py`, `ccp/prompt.py`) and `exit=0`; step 2: n/a (`tests.test_prompt_lanes` is new).
- id: `cmd-04`
  story: As a task writer, ccp tasks check warns on an unreadable PROPOSED wherever spec-text reads the section.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_signed_blocks_check 2>&1 | grep -e fence -e '^OK'`.
  expect: prints, `ok`, a test where a Scope holding a fenced block with a `## ` line, then `PROPOSED: > quoted inline`, warns with that line's number; then `OK`.
  dry run: n/a — the test is new.
- id: `spec-01`
  story: As the operator, §15.4, §16.2, §20.1 and §21.1 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0285`.
  expect: exit 0, all four PROPOSED passages found.
  dry run (simulated at `245528c`: this task file committed, then the 4 passages applied, each CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0285 --base HEAD~1`): `"ok": true`, 4 passage(s) found, none missing.

## Implementation notes

## Verification notes
