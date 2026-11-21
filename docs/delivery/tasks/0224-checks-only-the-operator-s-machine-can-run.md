---
task_id: 0224-checks-only-the-operator-s-machine-can-run
title: A dod_check the workers cannot take is marked runs_on operator-machine, and the task check reads the mark
status: pending
kind: feature
depends_on: ["0234-one-check-parser-and-one-file-at-rev-reader", "0244-tasks-check-runs-dry-runs"]
clashes_with: ["0244-tasks-check-runs-dry-runs"]
spec_refs: ["S5", "S21"]
adr_refs: ["0045 D1"]
review_point: R15
paths: ["ccp/tasklog.py", "ccp/dryrun.py", "ccp/cli.py", "plugin/skills/writing-tasks/SKILL.md", "templates/docs-delivery/TEMPLATE-task.md", "docs/spec/01-model.md", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "docs/adr/0045-checks-only-the-operator-s-machine-can-run.md", "tests/test_runs_on.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0224-checks-only-the-operator-s-machine-can-run

## Intent

A check that only the operator's machine can run (a real device, a signed build, a live account) is
today marked, if at all, in its `setup` prose, often beside steps the workers can take, so nothing
can tell the runner, the prompts or the verifier which checks are not the workers'. After this task
such a check carries `runs_on: operator-machine` on the line after `setup:`, holds only the steps that
machine runs, `ccp tasks check` refuses a misspelt or misplaced mark, and `ccp tasks checks <task>
--json` lists a task's marked checks for the runner. ADR-0045's loop (0238) and refusals (0237) read
this mark.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0045 D1, accepted by the operator on 2026-11-20. D2 is 0238, D3 is 0237.
- **Shaped** by `sh-20261121T000350Z-5ef1`:
  - F04: the mark is read through 0234's one parser, `tasklog.checks`, and the runner gets it as JSON
    from `ccp`, not by parsing prose (house rules E6, E13).
  - F08's D1 half: the writing-tasks skill tells writers to mark such a step "in its `setup`"
    (`grep -n "operator's machine" plugin/skills/writing-tasks/SKILL.md` at `8aefa59`: one line), and
    written tasks put one such step inside a check whose other steps are the workers'. D1 marks whole
    checks, so the skill and the template say a marked check holds only that machine's steps, and a
    mixed check is split in two.
  - F06 of ADR-0046's shape (`sh-20261121T001225Z-7dbe`) and F09/F10 of this one: the same skill says a
    check of a `ccp` command runs the head's `bin/ccp`, and signed SPEC text is checked with `ccp
    verify spec-text`, as house rule E21 says.
- **A line read nowhere today.** `git grep -n 'runs_on' -- ccp` at `8aefa59` prints nothing.
- **R16's 0244** adds `ccp tasks dry-run`, which runs a check's one-command steps in a temporary
  worktree and, with `--write`, rewrites its dry-run line. Unchanged, it would run a marked check on a
  worker's machine and overwrite its `n/a — runs on the operator's machine` line. This task depends on
  it and makes `ccp/dryrun.py` skip marked checks (listed as not run, their line kept); 0234 has already
  routed dry-run through `tasklog.checks`. 0244 also edits the §5.5 row and §21.1, hence the clash; the
  passages below are only the sentences this task adds, so either merge order keeps both.

## Scope

- **In:** `ccp/tasklog.py`, `ccp/dryrun.py`, `ccp/cli.py`, `plugin/skills/writing-tasks/SKILL.md`,
  `templates/docs-delivery/TEMPLATE-task.md`, `docs/spec/01-model.md`, `docs/spec/03-quality.md`,
  `docs/cli/03-quality.md`, `docs/adr/0045-checks-only-the-operator-s-machine-can-run.md`,
  `tests/test_runs_on.py` (new).
- **The grammar.** `tasklog.checks` gives each check's `runs_on`; `ccp tasks check` fails on a
  `runs_on:` line with another value, or not right after `setup:`, naming the task and the check.
  `dry run: n/a — runs on the operator's machine` is an accepted dry-run line.
- **Dry run.** `ccp tasks dry-run` lists a marked check as not run, and `--write` leaves its dry-run
  line as it is.
- **`ccp tasks checks <task_id> [--json]`**: the task's checks at the checkout, each id with its
  `runs_on` (null when unmarked); exit 2 on an unknown task. `docs/cli/03-quality.md` gains the row.
- **The skill and the template** show one marked check, say it holds only the steps the operator's
  machine runs (a mixed check is split), and cite §5.5; the skill's line on marking a step "in its
  `setup`" goes. The skill says a check of a `ccp` command runs the head's `bin/ccp` and signed SPEC
  text is checked with `bin/ccp verify spec-text <task>`.
- ADR-0045 D1 recorded `built`.
- **Tests** in `tests/test_runs_on.py` (new): the mark read; another value, and the mark after
  `steps:`, refused with the check's id; the n/a dry-run line accepted; `ccp tasks checks --json`;
  `ccp tasks dry-run --write` on a task with a marked check runs only the other checks and leaves the
  marked check's line unchanged.

### SPEC changes (signed in the brief, §31)

**a. §5.5, the dod_checks row (the end of its dry-run sentence).**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
> where dry runs are required (§21.1).

PROPOSED: (same line, after it)
> A check the workers cannot take carries `runs_on: operator-machine` on the line after `setup:`
> (§15.8); `ccp tasks dry-run` does not run it and leaves its dry-run line as it is.

**b. §21.1, a failure after the check-count bullet.**

CURRENT (`docs/spec/03-quality.md` at `8aefa59`):
> - other than 1..6 unique `` - id: `kind-NN` `` checks, or soft language inside
>   `## dod_checks` (dry-run lines are left out of that scan, since they quote output);

PROPOSED: (new lines after it)
> - a `runs_on:` line with a value other than `operator-machine`, or not right after the check's
>   `setup:` line (§5.5);

- **Out:** the runner's loop and the prompts (0238), the refusals at `record` and `merge-ok` (0237),
  and re-marking tasks already written (their writer's follow-up).

## dod_checks

- id: `ro-01`
  story: As a task writer, the mark is read and a wrong one is refused.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_runs_on 2>&1 | tail -10`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `ro-02`
  story: As a task writer, a misspelt marker is caught when the task is checked.
  setup: a checkout of the PR head; a copy (`git worktree add --detach <tmp> HEAD`) in which one
    pending task's first check gains `runs_on: operator-box` after its `setup:` line; QUEUE_ROOT a
    fresh temp directory.
  steps:
    1. Run `<tmp>/bin/ccp --root <tmp> tasks check 2>&1 | grep -c 'runs_on'`.
  expect: prints 1 or more, and `<tmp>/bin/ccp --root <tmp> tasks check` exits non-zero.
  dry run (`8aefa59`): prints 0; the line is not read.

- id: `ro-03`
  story: As a runner, I get a task's marked checks from ccp.
  setup: a checkout of the PR head; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . tasks checks 0224 --json; echo rc=$?`.
  expect: a JSON list of this task's check ids, each with `"runs_on": null`, and `rc=0`.
  dry run (`8aefa59`): `rc=2`, argparse refusing `checks`.

- id: `ro-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0224 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`8aefa59`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- 2026-11-21 (implementer): `tasklog.Check.runs_on` gives a check's `runs_on:` value as written (None when
  unmarked) and `on_operator_machine` whether it is the one valid mark; `tasklog.runs_on_errors` names a
  wrong value, or a `runs_on:` line that is not the key right after `setup:`, and `tasks check` reports
  each with the task's file and the check's id, for a task of any status.
- "Right after `setup:`" is read as the next key line at the check's key indent: `setup:`'s wrapped
  lines (deeper in) may come between, and a `runs_on:` line deeper in than the keys (read as a wrapped
  line, so never as the mark) is refused too.
- `ccp tasks dry-run` skips only a check marked exactly `runs_on: operator-machine` (a misspelt mark is
  run, and `tasks check` refuses it); it prints the check as not run and `--write` leaves its line.
- `ccp tasks checks <task> [--json]` reads the task file in the checkout through `queue.task_meta` (no
  queue needed); an unknown task exits 2. Text output is one `id<TAB>runs_on` line per check, `-` when
  unmarked.
- The skill's line about a check of a `ccp` command scopes `bin/ccp` to a head that carries one (the
  plane's own repo) and names `ccp verify spec-text` for a product's checkout, since the skill is
  generic.

## Verification notes
