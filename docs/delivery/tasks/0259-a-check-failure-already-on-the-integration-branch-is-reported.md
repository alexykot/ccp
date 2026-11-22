---
task_id: 0259-a-check-failure-already-on-the-integration-branch-is-reported
title: A docs or tasks check failure already on the integration branch is reported, not blocking, in a task's checks and the verifier's gate
status: pending
kind: feature
depends_on: ["0244-tasks-check-runs-dry-runs", "0252-the-task-check-reports-a-decision-built-before-its-prerequisite"]
clashes_with: ["0224-checks-only-the-operator-s-machine-can-run", "0230-the-lead-decides-each-follow-up", "0234-one-check-parser-and-one-file-at-rev-reader"]
spec_refs: ["S15", "S21"]
review_refs: ["ar-20261121T020523Z-1d5f#F01", "sh-20261121T001225Z-7dbe#F05"]
review_point: R18
paths: ["ccp/baseline.py", "ccp/cli.py", "scripts/observability/lib.py", "ccp/rules.py", "ccp/CLAUDE.md", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "templates/docs-delivery/standing-dod.md", "docs/delivery/standing-dod.md", "tests/test_preexisting_failures.py", "tests/test_preexisting_checks.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0259-a-check-failure-already-on-the-integration-branch-is-reported

## Intent

A task is failed only by what its own branch brings in. When `ccp docs check` or `ccp tasks check`
fails on a task branch because of something already on the integration branch (a hit in a file the
task never touched, a denylist pattern added mid-task, a task file merged from main), the failure is
printed as pre-existing, with a pointer to report it, and does not fail the command. So neither the
implementer's standing DoD nor the verifier's gate holds a task on a failure its implementer cannot
clear, while a failure the branch causes fails exactly as before.

## Context (not checked)

- **The rulings** (the operator, 2026-11-21, in the lead session):
  - Architect pass `ar-20261121T020523Z-1d5f`, F01: "(a)", that is, a house-rule check that also
    fails at the task's merge base is reported as pre-existing on the integration branch and the lead
    is told, while a hit in the task's own diff still fails (a § change to §21 and the standing DoD).
  - Shape `sh-20261121T001225Z-7dbe` (ADR-0046), F05: "accept the shape recommendations", that is,
    the verifier's gate judges whole-log and whole-tree checks (docs check, tasks check, the leak
    check) against the integration tip's failures, rejecting only on new ones, as its own task after R15.
  - Both are recorded in their review records under `docs/delivery/reviews/`.
- **One mechanism.** The verifier's gate is `ccp tasks check && ccp docs check` at the PR head
  (§21.8), so when those two commands judge failures against the merge base, the gate does too: the
  merge base of the PR head and `origin/<integration>` is the latest tip the head has merged, and a
  failure there is not the branch's doing. Hence one task, with both § changes signed together.
  `depends_on` 0252 because the shape asked for this after R15, whose ADR-0046 D3 adds a whole-log
  failure under `adr.strict`; and 0244 because it changes the standing DoD files and `tasklog.py`.
- **Today** (at `58e9220`): `"def cmd_docs_check"` in `ccp/cli.py` fails on any line of
  `pkgdocs.check`, `tasklog.check`, `rules.check` (the `architect.checks` commands, through
  `"def run_checks"` in `ccp/rules.py`), `rules.starter_check`, `adr.check` and `docs.checks`;
  `scripts/leak-check.sh` greps the whole tree. The reconcile already excuses what failed before it
  (`git grep -n "already failed on the branch" -- ccp` at `58e9220`: 1 line, `ccp/lifecycle.py`),
  comparing `tasklog.check` lines as strings.
- **Rulings for the build** (the lead's):
  - **When.** Only when the run at `HEAD` fails. The base is `git merge-base HEAD
    origin/<integration>` (the binding's branch with QUEUE_ROOT, else `main`), as it is in the checkout,
    nothing fetched. No base (no such ref), a base equal to `HEAD` (the integration tip itself), or a
    base that cannot be checked out: every failure counts, as today.
  - **How.** The base run is the same command at the base, in a temporary detached worktree outside the
    product root, removed afterwards whatever happens. It is the running `ccp` with the base worktree as
    its root, so it reads its config (plane.json, the rules doc, the task log) from the base, and it runs
    with QUEUE_ROOT unset. (A change to the checker code makes every failure count, below, so the
    running `ccp` judges both sides alike.)
  - **Inputs outside git resolve the same at both.** The base run's environment carries
    `CCP_BINDINGS_DIR` set to the bindings directory the `HEAD` run resolved (the variable the leak
    check and `lib`'s bindings lookup already read), and `CCP_LEAK_DENYLIST` unchanged when set, so a
    check whose input lives outside git, such as E3's denylist, reads the same input at the base.
    `ccp where` resolves the binding from `CCP_BINDINGS_DIR` when it is set; where it does not today,
    this task makes it.
    `ccp docs check` and `ccp tasks check` share one function, in a new module `ccp/baseline.py`, with
    the decision on plain values.
  - **Checker code changed: no comparison.** When the branch changes the checker itself, every failure
    counts: the repository's own `ccp` (a path under `bin/` or `ccp/` in
    `git diff --name-only <base>...HEAD`, where the repository holds the `ccp` package), and, for one command
    check, any file its command line names that the branch changes (that check's failure counts).
  - **Which failures are pre-existing.** The branch's changed paths are
    `git diff --name-only <base>...HEAD`; a line names one when the path appears in it as a whole path
    (at the line start or after whitespace, a colon or a backtick).
    - A rule-failure line (a doc rule, a task-log rule, the ADR check, an unknown key) is pre-existing
      when the base run prints the same line and it names no changed path.
    - A failing command check (`architect.checks` or `docs.checks`, by id) is pre-existing only when it
      fails at the base too, its output at `HEAD` is not empty, and every line of that output also
      appears in the base's output, after the base worktree's root path is replaced by the product
      root's in the base output. Its whole output is compared: an output at either side that reached
      the kept-output cap (`OUTPUT_CAP` in `ccp/rules.py`, §21.5) counts as new.
    - Anything else fails as before. A leak hit is a command check like any other: a new hit line, in
      a changed file or not, fails.
  - **Output.** Pre-existing failures print after the others, under the heading
    `pre-existing on <integration> at <base sha7>, not this change's: report it under Friction`, and
    leave the exit code alone. Workers' Friction lines reach the lead through the health notes, the
    channel the two friction notes behind F01 took; no prompt changes.
- **Rule text.** Both § changes and the standing DoD line below are signed in the brief (§31). The
  reconcile's own comparison stays as it is (Out).

## Scope

- **In:**
  - `ccp/baseline.py` (new): the base, the run at the base and the decision; `ccp/cli.py`
    (`ccp docs check` and `ccp tasks check` call it; `ccp where` honours `CCP_BINDINGS_DIR` if it
    does not already); `scripts/observability/lib.py` only if the bindings lookup needs it;
    `ccp/rules.py` (run results that keep each check's id and output for the decision);
    `ccp/CLAUDE.md` (the module list).
  - `docs/cli/03-quality.md` (the two commands' output).
  - `tests/test_preexisting_failures.py` (new, plain values), `tests/test_preexisting_checks.py`
    (new, a fixture repo).
  - Signed before the claim (`sign_off: brief`):
  - `docs/spec/03-quality.md` §21.2, a paragraph added after the one that ends "runs it as its last
    stage, `plane-docs` (§14.2).":

    CURRENT (`docs/spec/03-quality.md` at `58e9220`): none, a new paragraph.

    PROPOSED:
    > **Failures already on the integration branch.** When `ccp docs check` or `ccp tasks check` fails
    > on a branch whose merge base with `origin/<integration>` is not `HEAD`, it runs the same command
    > at that merge base, in a temporary worktree it removes afterwards: the running `ccp` with the
    > base as its root and the base's own config, QUEUE_ROOT unset, and `CCP_BINDINGS_DIR` set to the
    > bindings directory the `HEAD` run resolved, so an input outside git, such as a denylist, is the
    > same at both. A rule-failure line is pre-existing when the base prints it too and it names no
    > file the branch changes. A check command (`architect.checks`, `docs.checks`) is pre-existing
    > only when it fails at the base too, its output at `HEAD` is not empty, and every line of that
    > output, with the worktree root normalised, also appears in the base's; an output that reached
    > the kept-output cap counts as new. When the branch changes the checker (the repository's own
    > `ccp`, or a file a check's command names), its failures all count. Pre-existing failures are
    > printed under `pre-existing on <integration> at <sha>, not this change's: report it under
    > Friction` and do not fail the command; every other failure fails it as before. With no such
    > base, on the integration tip itself, or when the base cannot be checked out, every failure
    > counts. The verifier's gate therefore rejects only on failures new against the integration tip
    > the PR head last merged.
  - `docs/spec/03-quality.md` §21.8, the Verifier row; its last sentence replaced:

    CURRENT (`docs/spec/03-quality.md` at `58e9220`):
    > | Verifier | `ccp tasks check && ccp docs check` in the submitted checkout before walking a task's `dod_checks`, recorded in its verdict's `gate` (§15). A failure is a reject with its output |

    PROPOSED:
    > | Verifier | `ccp tasks check && ccp docs check` in the submitted checkout before walking a task's `dod_checks`, recorded in its verdict's `gate` (§15). A failure is a reject with its output; a pre-existing one (§21.2) passes the commands and is no reject |
  - `templates/docs-delivery/standing-dod.md` item 1, replaced; `docs/delivery/standing-dod.md` item 1
    takes the same text:

    CURRENT (`templates/docs-delivery/standing-dod.md` at `58e9220`):
    > 1. **`ccp docs check` is clean**, which includes `ccp tasks check`.

    PROPOSED:
    > 1. **`ccp docs check` is clean**, which includes `ccp tasks check`; a failure already on the
    >    integration branch, outside the task's diff, is reported, not the task's (plane SPEC §21.2).
- **Out:** the reconcile's own before/after comparison (`ccp/lifecycle.py`, unchanged); the leak
  check's script and denylist; `ccp health` and the board (no new report); the prompt templates.

## dod_checks

- id: `pe-01`
  story: As a plane developer, the decision of which failures are pre-existing is tested on plain values, and the tests bite.
  setup: a checkout of the PR head; then a separate copy of it with the "every line also appears in the base's output" condition in `ccp/baseline.py` removed.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_preexisting_failures 2>&1 | tail -10`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_preexisting_failures`.
  expect: step 1 exits 0, listing as `ok` tests for: a rule line printed at both is pre-existing; one printed at both that names a changed path fails; a line only at `HEAD` fails; a command check failing at both whose `HEAD` lines all appear in the base output (worktree root normalised) is pre-existing; one with a `HEAD` line the base lacks fails; one with empty `HEAD` output fails; one whose output reached the cap fails; a changed checker path (`ccp/`, `bin/`, or a file the check's command names) makes the failure count; a base equal to `HEAD`, or none, leaves every failure failing. Step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `pe-02`
  story: As an implementer, a hit already on the integration branch no longer fails my docs check, a hit in my own diff does, and the lead's run on the integration branch still fails.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_preexisting_checks 2>&1 | tail -10`.
  expect: exit 0, listing as `ok` tests in a fixture repo whose integration branch carries a hit of an `architect.checks` grep command: on a task branch that does not touch the file, `ccp docs check` exits 0 and prints the `pre-existing on main at` heading naming the check; on a branch that adds a hit in a file it changes, it exits 1; on the integration branch itself it exits 1; the base run reads the base's plane.json (a check the branch adds is not run at the base) and sees no QUEUE_ROOT; a leak-style check whose pattern list lives outside git (in the bindings directory) and whose hit is already on main is excused on a branch that does not touch the hit file, the base run having read the same list through `CCP_BINDINGS_DIR`; and the temporary worktree is gone after each run (`git worktree list` shows only the fixture's own).
  dry run: n/a — the module is new.
- id: `pe-03`
  story: As a verifier, a task-log failure merged from the integration branch does not fail `ccp tasks check` on the task's head, and one the branch makes does.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_preexisting_checks 2>&1 | grep -i 'tasks'`.
  expect: at least two lines ending `ok`: one where a task-file failure present at the merge base leaves `ccp tasks check` at exit 0 with the heading, and one where a failure in a task file the branch adds exits 1.
  dry run: n/a — the module is new.
- id: `pe-04`
  story: As the operator, the SPEC and the standing DoD read as I signed them.
  setup: a checkout of the PR head; the brief sign-off recorded.
  steps:
    1. Run `./bin/ccp verify spec-text 0259`.
    2. Run `diff <(sed -n '/^1\. /,/^2\. /p' templates/docs-delivery/standing-dod.md) <(sed -n '/^1\. /,/^2\. /p' docs/delivery/standing-dod.md)`.
  expect: step 1 exits 0 with the three PROPOSED passages found (two in `docs/spec/03-quality.md`, one in `templates/docs-delivery/standing-dod.md`); step 2 prints nothing.
  dry run (`58e9220`): step 1 n/a (the passages land with the task); step 2 printed nothing.

## Implementation notes

- 2026-11-22 (implementer): `ccp/baseline.py` holds the decision on plain values (`split`, `comparable`,
  `checker_changed`, `names`) and the wiring (`judge`, `run_at_base`, `emit`). `ccp docs check` and `ccp tasks
  check` build a list of `Failure`s (rule lines, and command checks with their key, command and whole kept
  output) and print through `cli._print_judged`. `ccp/rules.py` keeps each check command's run (`CheckRun`,
  `run_check_runs`, `house_checks`); `run_checks`, `check_failures` and `check` return the same lines as before.
- The run at the base is `bin/ccp --root <tmp worktree> <same argv>` with `CCP_BASE_RUN` naming a file it writes
  its failures to as JSON (it then compares nothing itself), QUEUE_ROOT and CCP_ROOT dropped,
  `CCP_NO_BINDING_QUEUE=1` (else `ccp` derives QUEUE_ROOT from the binding, since the base worktree's main
  checkout is the product's) and `CCP_BINDINGS_DIR` set to `lib.bindings_dir()`. The worktree is made with
  `wt.add_unrecorded` (the `worktrees.links` paths linked, as `tasks dry-run` does) in a `mkdtemp` directory and
  removed in a `finally`. A base run that exits other than 0 or 1, or writes nothing readable, counts as no base.
- `ccp where` already resolves the binding through `lib.bindings_dir()`, which honours `CCP_BINDINGS_DIR`: no
  change to `cmd_where` or `scripts/observability/lib.py`.
- Narrowest readings, flagged in the report: a check command that timed out at either side is never
  pre-existing (its output is not whole); a command line names a path also after a quote, a parenthesis or
  `=`, and either kind of line names `./<path>`; "the repository holds the `ccp` package" is
  `ccp/__init__.py` in the product root; the changed paths are `git diff --name-only <base>...HEAD`, so an
  uncommitted edit is not among them.

## Verification notes
