---
id: ADR-0038
title: "A claimed task's file is edited only in its PR"
status: accepted
date: "2026-11-11"
deciders: operator
spec_refs: [S10, S17]
supersedes: ["ADR-0035 D5"]
decisions: ["D1 built — task 0043", "D2 built — task 0043", "D3 built — task 0043"]
notes: "2026-11-11: status proposed → accepted: the operator's approval of task 0043's PR at its merge gate (SPEC §31)"
---
# ADR-0038 — A claimed task's file is edited only in its PR

## Context

ADR-0035 D5 declined to lock a leased task file: the task-log owner could amend it at any time. But
the implementer works from the task file on its branch and appends its notes to the same file. An
edit on the integration branch after the claim is unseen by the implementer and conflicts at merge.
The operator reversed the earlier decline on 2026-11-09. Task 0043 builds the rule; the operator's
approval of task 0043's PR at its merge gate (SPEC §31) is the approval of this ADR.

## Decision

### D1. A claimed task's file changes on the integration branch only by its own merge

From the claim until the lease clears, the task's file changes on the integration branch only by the
task's own squash merge and reconcile, and by the lead marking it `dropped`. `ccp tasks check
--lease` names any other edit, with the task and its lease holder, and the plane's commit hook
template refuses one (SPEC §10.5).

### D2. A ruling or clarification on a claimed task lands in its PR

A lead ruling or clarification on a claimed task reaches the runner holding it. The runner passes
it, verbatim, in the next implementer prompt, and the implementer writes it into the task file's
`Context (not checked)` section on the task branch, besides its Implementation notes. The standing
definition of done allows the implementer exactly that edit (SPEC §10.5).

### D3. Its commit is the task-branch commit, or the tip it was ruled against

On a claimed task, a resolved ruling's `commit_sha` names the task-branch commit that carries it, or,
if the ruling is given before that commit exists, the integration tip it was ruled against
(SPEC §17.4).

## Consequences

- ADR-0035 D5 (the owner may amend a task file at any time) is superseded by D1. The owner still
  amends an unclaimed task at any time, and a claimed one through the runner.
- A ruling on a claimed task reaches the integration branch with the task's squash merge, not before.
  SPEC and PROJECT wording a ruling needs still lands on the integration branch at once.
- A product gets the refusal only if it installs the commit hook template; without it, `ccp tasks
  check --lease` is the lead's check before a push.
