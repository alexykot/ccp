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
paths: ["ccp/baseline.py", "ccp/cli.py", "ccp/rules.py", "ccp/CLAUDE.md", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "templates/docs-delivery/standing-dod.md", "docs/delivery/standing-dod.md", "tests/test_preexisting_failures.py", "tests/test_preexisting_checks.py"]
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
- **Today** (at `b2b9846`): `"def cmd_docs_check"` in `ccp/cli.py` fails on any line of
  `pkgdocs.check`, `tasklog.check`, `rules.check` (the `architect.checks` commands, through
  `"def run_checks"` in `ccp/rules.py`), `rules.starter_check`, `adr.check` and `docs.checks`;
  `scripts/leak-check.sh` greps the whole tree. The reconcile already excuses what failed before it
  (`git grep -n "already failed on the branch" -- ccp` at `b2b9846`: 1 line, `ccp/lifecycle.py`),
  comparing `tasklog.check` lines as strings.
- **Rulings for the build** (the lead's):
  - **When.** Only when the run at `HEAD` fails. The base is `git merge-base HEAD
    origin/<integration>` (the binding's branch with QUEUE_ROOT, else `main`), as it is in the checkout,
    nothing fetched. No base (no such ref), a base equal to `HEAD` (the integration tip itself), or a
    base that cannot be checked out: every failure counts, as today.
  - **How.** The same checks run at the base in a temporary detached worktree outside the product
    root, removed afterwards, whatever happens. `ccp docs check` and `ccp tasks check` share one
    function, in a new module `ccp/baseline.py`, with the decision on plain values.
  - **Which failures are pre-existing.** A failure line (a doc rule, a task-log rule, the ADR check)
    whose text the base prints too. A failing command check (`architect.checks` or `docs.checks`, by
    id) that fails at the base as well, unless its kept output at `HEAD` names a path the branch
    changes (`git diff --name-only <base>...HEAD`, matched as a whole path at a line start or after
    whitespace or a colon). Anything else fails as before.
  - **Output.** Pre-existing failures print after the others, under the heading
    `pre-existing on <integration> at <base sha7>, not this change's: report it under Friction`, and
    leave the exit code alone. Workers' Friction lines reach the lead through the health notes, the
    channel the two friction notes behind F01 took; no prompt changes.
  - **Leak hits** are judged like any command check: a hit in a file the branch changes still fails.
- **Rule text.** Both § changes and the standing DoD line below are signed in the brief (§31). The
  reconcile's own comparison stays as it is (Out).

## Scope

- **In:**
  - `ccp/baseline.py` (new): the base, the run at the base and the decision; `ccp/cli.py`
    (`ccp docs check` and `ccp tasks check` call it); `ccp/rules.py` (run results that keep each
    check's id and output for the decision); `ccp/CLAUDE.md` (the module list).
  - `docs/cli/03-quality.md` (the two commands' output).
  - `tests/test_preexisting_failures.py` (new, plain values), `tests/test_preexisting_checks.py`
    (new, a fixture repo).
  - Signed before the claim (`sign_off: brief`):
  - `docs/spec/03-quality.md` §21.2, a paragraph added after the one that ends "runs it as its last
    stage, `plane-docs` (§14.2).":

    CURRENT (`docs/spec/03-quality.md` at `b2b9846`): none, a new paragraph.

    PROPOSED:
    > **Failures already on the integration branch.** When `ccp docs check` or `ccp tasks check` fails
    > on a branch whose merge base with `origin/<integration>` is not `HEAD`, it runs the same checks
    > at that merge base, in a temporary worktree it removes afterwards. A failure line the base prints
    > too is pre-existing, and so is a check command (`architect.checks`, `docs.checks`) that fails at
    > the base as well, unless its output at `HEAD` names a file the branch changes. Pre-existing
    > failures are printed under `pre-existing on <integration> at <sha>, not this change's: report it
    > under Friction` and do not fail the command; every other failure fails it as before. With no
    > such base, on the integration tip itself, or when the base cannot be checked out, every failure
    > counts. The verifier's gate therefore rejects only on failures new against the integration tip
    > the PR head last merged.
  - `docs/spec/03-quality.md` §21.8, the Verifier row; its last sentence replaced:

    CURRENT (`docs/spec/03-quality.md` at `b2b9846`):
    > | Verifier | `ccp tasks check && ccp docs check` in the submitted checkout before walking a task's `dod_checks`, recorded in its verdict's `gate` (§15). A failure is a reject with its output |

    PROPOSED:
    > | Verifier | `ccp tasks check && ccp docs check` in the submitted checkout before walking a task's `dod_checks`, recorded in its verdict's `gate` (§15). A failure is a reject with its output; a pre-existing one (§21.2) passes the commands and is no reject |
  - `templates/docs-delivery/standing-dod.md` item 1, replaced; `docs/delivery/standing-dod.md` item 1
    takes the same text:

    CURRENT (`templates/docs-delivery/standing-dod.md` at `b2b9846`):
    > 1. **`ccp docs check` is clean**, which includes `ccp tasks check`.

    PROPOSED:
    > 1. **`ccp docs check` is clean**, which includes `ccp tasks check`; a failure already on the
    >    integration branch, outside the task's diff, is reported, not the task's (plane SPEC §21.2).
- **Out:** the reconcile's own before/after comparison (`ccp/lifecycle.py`, unchanged); the leak
  check's script and denylist; `ccp health` and the board (no new report); the prompt templates.

## dod_checks

- id: `pe-01`
  story: As a plane developer, the decision of which failures are pre-existing is tested on plain values, and the tests bite.
  setup: a checkout of the PR head; then a separate copy of it with the "names a path the branch changes" condition in `ccp/baseline.py` removed.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_preexisting_failures 2>&1 | tail -10`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_preexisting_failures`.
  expect: step 1 exits 0, listing as `ok` tests for: a line printed at both is pre-existing; a line only at `HEAD` fails; a command check failing at both is pre-existing; one failing at both whose `HEAD` output names a changed path fails; a base equal to `HEAD`, or none, leaves every failure failing. Step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `pe-02`
  story: As an implementer, a hit already on the integration branch no longer fails my docs check, a hit in my own diff does, and the lead's run on the integration branch still fails.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_preexisting_checks 2>&1 | tail -10`.
  expect: exit 0, listing as `ok` tests in a fixture repo whose integration branch carries a hit of an `architect.checks` grep command: on a task branch that does not touch the file, `ccp docs check` exits 0 and prints the `pre-existing on main at` heading naming the check; on a branch that adds a hit in a file it changes, it exits 1; on the integration branch itself it exits 1; and the temporary worktree is gone after each run (`git worktree list` shows only the fixture's own).
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
  dry run (`b2b9846`): step 1 n/a (the passages land with the task); step 2 printed nothing.

## Implementation notes

## Verification notes
