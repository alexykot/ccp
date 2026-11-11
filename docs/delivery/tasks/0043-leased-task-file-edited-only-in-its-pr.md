---
task_id: 0043-leased-task-file-edited-only-in-its-pr
title: A claimed task's file is edited only in its PR
status: pending
kind: feature
depends_on: []
spec_refs: ["S10", "S16"]
review_point: R3
paths: ["ccp/tasklog.py", "ccp/lifecycle.py", "docs/spec/02-delivery.md", "scripts/git-hooks/", "plugin/", "tests/test_lease*.py"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0043-leased-task-file-edited-only-in-its-pr

## Intent

Once a task is claimed, its file is not edited on the integration branch. A ruling or amendment on a claimed task goes to the runner and lands in the task's PR; `ccp` warns on or refuses an integration-branch commit touching a leased task's file.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §10 and §16.
- The implementer works from the brief on its branch and appends notes to the same file; an edit on the integration branch after the claim is unseen by the implementer and conflicts at merge.
- The operator ruled on 9 Nov 2026 to adopt this, reversing an earlier decline.
- **SPEC change (§31):** this task changes a § rule — the lease rules in §10. It needs the operator's approval at build: the PR carries the CURRENT → PROPOSED text and quotes the ruling.

## Scope

- **In:** §10 states the rule; a check (`ccp tasks check --lease`, used by the plane's commit hook template and the lead's tools) flags a commit on the integration branch that changes the file of a task with a live lease; the lead's orientation and the spec-maintainer skill route amendments to the runner.
- **Out:** forge-side branch protection.

## dod_checks

- id: `check-01`
  story: As a runner, an edit to my claimed task on the integration branch is caught.
  setup: a scratch product with task 0001 leased and a commit on the integration branch editing its file.
  steps:
    1. Run the check.
  expect: it fails, naming the task and the lease holder.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, unleased task files can be edited.
  setup: the same edit with no lease.
  steps:
    1. Run the check.
  expect: it passes.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 — implementer: `ccp tasks check --lease [--staged]` (`ccp/cli.py`, `ccp/lifecycle.py` `lease_edits`).
  It needs QUEUE_ROOT (exit 2 without it) and runs only the lease check. A lease is live when `lease_holder` is
  set and the queue status is neither done nor dropped. Without `--staged` it flags commits on the integration
  branch's first-parent history (local and `origin/<branch>`, no fetch) committed after `lease_since` (else
  `claimed_at`; with neither, the task is not judged) that change the task file. With `--staged` it judges the
  index, only while HEAD is on the integration branch. Not edits: the task's own squash merge
  (`Task NNNN: … (#N)`) and reconcile, and a change after which the file says `status: dropped` (the
  lead's drop, §10.4). Each failure names the task, the lease holder and the commit.
- The commit hook template is `scripts/git-hooks/pre-commit.template`, for any product. The plane's own
  `pre-commit` runs it after the main rule. It refuses only on exit 1 and warns on any other failure (an
  older `ccp`, no queue).
- §10.5 and §17.4 carry draft text (the task gave no PROPOSED text); it needs the operator's approval in
  the PR. The orientation, the spec-maintainer skill and the runner brief route an amendment on a claimed
  task to the runner. Tests: `tests/test_lease_edits.py`.

## Verification notes

*Append-only.*
