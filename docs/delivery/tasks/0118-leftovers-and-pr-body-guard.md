---
task_id: 0118-leftovers-and-pr-body-guard
title: SPEC and test leftovers from R6 are closed, and a PR whose body names another task is caught before review
status: pending
kind: feature
depends_on: ["0116-prompt-and-verify-fixes"]
spec_refs: ["S12", "S13", "S14", "S15"]
review_point: R7
sign_off: brief
paths: ["ccp/prompt.py", "ccp/wt.py", "ccp/suite.py", "plugin/agents/delivery-runner.md", "templates/prompts/_common.md", "docs/spec/02-delivery.md", "docs/design/toolkit.md", "tests/test_prompt*.py", "tests/test_suite_affected.py", "tests/test_merge_base.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0118-leftovers-and-pr-body-guard
## Intent

The small leftovers R6's reviews recorded are closed, and a pull request whose body was overwritten
with another task's is caught before a reviewer reads it.

## Context (not checked)

- From an accepted plane proposal listing R6 leftovers.
- During a parallel run a PR's body was once overwritten with another task's PR body; the cause is unknown. Two guards close it: workers always pass the PR number to `gh pr edit`, and the review prompt refuses a PR whose body does not name its task.
- Two changes are § rules and are quoted below for sign-off before the claim (§3.5): `--since` taking a range (§14.7), and the review prompt refusing a PR body that does not name its task (§15.2). The rest describe the accepted follow-ups (§31.1). The runner brief's line about repairing the body is guidance, not a § rule.

## Scope

- **In:**
  - §13.2 and `docs/design/toolkit.md`: the parenthesis on prompt rendering lists only examples, and says so; the three SPEC passages task 0101 re-wrapped badly are re-wrapped (text unchanged).
  - `ccp/wt.py`: the SIGTERM hold across `git worktree add` is bounded (30 s), after which the signal is acted on and the partial worktree removed.
  - `ccp suite affected --since`: a range (`A..B`) is accepted and means the files changed in it. A test pins the §14.7 dotfile rule.
  - `docs/spec/02-delivery.md` §14.7. CURRENT (at `7094dfe`): "else the files `git diff <ref>` names against the working tree (a rename as both its paths) plus the untracked files git does not ignore; `--since` defaults to `HEAD`, the uncommitted change." PROPOSED:
    > else the files `git diff <ref>` names against the working tree (a rename as both its paths) plus the untracked files git does not ignore; `--since` defaults to `HEAD`, the uncommitted change. A range `<a>..<b>` given to `--since` is the files `git diff <a>..<b>` names, without the working tree.
  - `templates/prompts/_common.md`: `gh pr edit` and `gh pr view` always take the PR number.
  - `ccp prompt review` (`ccp/prompt.py`): refuses (exit 2) when the PR's body does not contain the task id, naming both; the runner brief says to repair the body before review.
  - `docs/spec/02-delivery.md` §15.2. CURRENT (at `7094dfe`): "**Review starts on a settled head.** The runner opens a review (`ccp prompt review --head`) only once the task's open spec questions are answered and their rulings are on the PR." PROPOSED:
    > **Review starts on a settled head.** The runner opens a review (`ccp prompt review --head`) only once the task's open spec questions are answered and their rulings are on the PR. `ccp prompt review` refuses (exit 2), naming the task and the PR, a PR whose body does not contain the task id; the runner repairs the body first.
- **Out:**
  - Finding the cause of the overwrite.

## dod_checks

- id: `cmd-01`
  story: As a runner, a PR body naming another task is caught.
  setup: a scratch task T whose PR body (stubbed `gh`) names task U only; then one naming T.
  steps:
    1. Run `ccp prompt review T` in each case.
  expect: (1) exit 2 naming T and the PR. (2) renders the prompt.
  dry run: n/a.
- id: `cmd-02`
  story: As a worker, `--since` takes a range.
  setup: a scratch repository with commits A, B, C, where B..C changes one module.
  steps:
    1. Run `ccp suite affected --since B..C`.
  expect: lists the tests for that module only; exit 0.
  dry run: n/a.
- id: `code-01`
  story: As a runner, a hung worktree add cannot hold a signal forever.
  setup: a test whose `git worktree add` is stubbed to hang, with a SIGTERM sent during it.
  steps:
    1. Run the test through `ccp suite run`.
  expect: the process exits 143 within 40 s and no worktree is left registered.
  dry run: n/a.
- id: `check-02`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §14.7 and §15.2 edits with the PROPOSED text above.
  expect: they match word for word.
  dry run: n/a.
- id: `check-01`
  story: As a reader, the other leftovers are fixed without new rules.
  setup: the PR diff.
  steps:
    1. Read every changed SPEC line.
  expect: apart from the two signed passages, each one describes behaviour this task builds or re-wraps text unchanged; the verdict's `spec_beyond_intent` is empty.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 — implementer: `ccp/wt.py` bounds the SIGTERM hold across a base run's worktree make at
  `SIGTERM_HOLD_SECONDS` (30): the first SIGTERM starts a SIGALRM timer, and a make still going then is
  cut short by the signal there (the git child killed by `subprocess.run`) and what it made removed
  (`_discard`: `git worktree remove --force --force`, as git keeps a worktree being added locked, then
  the directory, then `git worktree prune`). The run then exits 143 with no worktree named. The bound
  is not in the SPEC (no signed text for it); the module docstrings carry it.
- `ccp suite affected --since <a>..<b>` takes the files `git diff` names between the two ends' trees,
  without the working tree or untracked files; both ends must be given and resolve (`a...b`, `a..`
  and a dash-led end are refused, exit 2, as an unknown ref). The CLI help and `docs/cli/02-delivery.md`
  name the form.
- `ccp prompt review` reads the PR body with `gh pr view <pr> --json body` (`CCP_GH_BIN`, else `gh`),
  before anything is opened, and refuses (exit 2) a body that does not contain the full task id,
  naming the task and the PR. A body `gh` cannot read (not installed, non-zero exit, no body, a 60 s
  timeout) is a warning recorded on the run, and the review opens. `tests/__init__.py` points
  `CCP_GH_BIN` at a nonexistent guard so no test calls the real `gh`; `tests/test_toolkit.py`'s fake
  `gh` answers the body request with the fixture's open task.
- SPEC: §14.7 and §15.2 carry the signed text (§15.2's new sentence wrapped so `ccp prompt review`
  stays on one line); the four passages the 0101 review and verify reports named as badly wrapped
  (§12.1 `--shallow`, §13.4 `report.required_fields`, §14.2 `{head}`, §16.5 dry run) are re-wrapped
  with their words unchanged (`git diff --word-diff`); §13.2 and `docs/design/toolkit.md` say
  "such as" before the filled-in fields.

## Verification notes
