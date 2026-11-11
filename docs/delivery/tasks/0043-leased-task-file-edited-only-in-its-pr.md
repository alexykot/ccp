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
- 2026-11-11, lead's ruling on this task's spec question: (a) record the reversal as ADR-0038 ("A claimed task's file is edited only in its PR"), superseding ADR-0035 D5, accepted, deciders operator; the operator's approval at this task's merge gate is the approval. (b) A lead ruling or amendment on a claimed task reaches the runner, which passes it verbatim in the next implementer prompt; the implementer writes it into this section on the task branch, besides Implementation notes. Standing DoD item 3 (the plane's copy and its template) allows exactly that, and §10.5 says it. (c) §17.4: on a claimed task, a resolved ruling's `commit_sha` names the task-branch commit that carries it, or, if given before that commit exists, the integration tip it was ruled against. The paths outside `paths:` (`ccp/cli.py`, `docs/cli/02-delivery.md`, `scripts/CLAUDE.md`, the pre-commit template) are accepted.

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
- 2026-11-11 — implementer, applying the lead's ruling (Context): ADR-0038 (accepted, deciders operator,
  D1–D3 built) supersedes ADR-0035 D5 through `ccp adr supersede --decisions D5 --by D1`. §10.5 says the
  runner passes a ruling or amendment on a claimed task verbatim and the implementer writes it into
  Context on the task branch; §17.4 says which commit `commit_sha` names. Standing DoD item 3 (the
  plane's copy and `templates/docs-delivery/standing-dod.md`), the implementer and runner briefs and
  the spec-maintainer skill say the same. A product's existing standing DoD copy is not rewritten.
- 2026-11-11 — implementer, fix round 1 (review MINOR-1, -3, -4 and three NITs): the Context rows of the
  §4.2 and §5.5 tables, §15.6 item 6 and the §17.4 first bullet now name the implementer, writing a ruling
  the runner passes on a claimed task (§10.5), so the SPEC says one thing about who writes Context. §10.5
  says the own squash merge and reconcile are known by their §10.7 rule 1 and 2 subjects, that a lease
  with no `lease_since` is timed from `claimed_at`, and one with neither is not judged. Two tests pin the
  untested paths: a `--no-ff` merge of a `task/0002-…` branch is not an edit, and the `claimed_at`
  fallback and the no-stamp skip. ADR-0038 D2 cites §10.5; the spec-maintainer skill bullet is rewrapped
  and names drop and sync. MINOR-2 is left to the lead.

## Verification notes

*Append-only.*
