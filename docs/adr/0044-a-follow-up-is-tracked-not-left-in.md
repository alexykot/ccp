---
id: ADR-0044
title: "A follow-up is tracked, not left in notes"
status: proposed
date: "2026-11-20"
deciders: operator
spec_refs: [S5, S9, S10, S13, S15]
notes: |-
  Proposed from a product's plane proposal, accepted in triage with the direction of a structured
  follow-up field in worker reports that close checks. It adds a close refusal and changes SPEC rules
  (listed under Consequences), so the operator decides it.
---
# ADR-0044 — A follow-up is tracked, not left in notes

## Context

Workers find work they must not do: a finding the reviewer defers, a test gap out of the task's
scope, a step that has to wait for a later task. The SPEC says only where it goes, not how:

- §13.1 (`docs/spec/02-delivery.md:442`): workers "never create a task: a follow-up a worker finds
  goes to the lead".
- §15.8 (`docs/spec/02-delivery.md:1095-1098`): a task may merge code-only, "the step listed as a
  follow-up". Nothing lists it anywhere the plane reads.
- §3.5 (`docs/spec/01-model.md:214`) and the implementer's definition
  (`plugin/agents/delivery-implementer.md:39`): rule text the brief lacks goes to a plane proposal.
  That covers plane needs only (§31.4); most follow-ups are product work.

In practice a follow-up ends as a sentence in the task's Implementation or Verification notes, or in
a report's prose. Once the task closes nobody reads it again, and the work is lost. The plane cannot
look for it there: it never parses product text (`docs/ROADMAP.md:11`). The report format (§13.4,
`docs/spec/02-delivery.md:522`) already carries one free-text list the plane stores and counts but
does not interpret, `## Friction` (`docs/spec/02-delivery.md:542`).

## Options considered

1. **Parse the notes for follow-ups.** No change for workers. It breaks the rule that the plane never
   parses product prose, and a follow-up phrased another way is still lost. Rejected.
2. **A `follow_ups:` key in the task file**, written by the implementer in the PR. The file is the
   durable home, but a claimed task's file changes only in its PR (§10.5), the implementer cannot
   create the task or proposal a follow-up resolves to, and the reviewer's and verifier's follow-ups
   would still need a path into the file. Rejected.
3. **Workers file proposals or tasks themselves.** Workers never create tasks (§13.1), and a plane
   proposal is for plane needs only (§31.4). Rejected.
4. **A `## Follow-ups` report section, resolved by the lead, checked by close.** Every worker states
   its follow-ups in the format it already fills in. The lead, who owns the task log, decides each,
   and close refuses while one is undecided. Costs one report section, one decision per follow-up,
   and a possible wait at close. Chosen.
5. **Option 4 with a warning at close instead of a refusal.** Cheaper, but a warning is no stronger
   than a note. Rejected.

## Decision

### D1. Every worker report states its follow-ups

Each worker report (implement, fix, merge, ruling, review, verify) carries `## Follow-ups`: one `- `
line per follow-up, or the single line `none`, as `## Friction` does. `ccp report` refuses a report
without the section. The line's text is the worker's, and the plane never interprets it. The plane
stores each line on the run (`follow_ups`, numbered `<run_id>#<n>`) and counts them. The worker
definitions and prompts say that work found out of scope goes here, never only in notes.

### D2. The lead resolves each follow-up to one of three outcomes

`ccp tasks follow-up <task_id> <run_id>#<n> --task <id> | --proposal <id> | --drop "<reason>"`
records the outcome on the task's queue record. Only the lead runs it.

- `--task` names a task that exists in the task log at the integration tip, of any status: a new task
  the lead wrote, or an existing one the follow-up belongs to.
- `--proposal` names a row of `plane/proposals.jsonl` (§31.4), filed with `--task <task_id>`.
- `--drop` states why the work is not worth doing. The reason is required.

The command refuses an id that does not resolve. Running it again replaces the outcome.

### D3. Close refuses an undecided follow-up

`ccp tasks close` refuses (exit 1) before it merges while any follow-up of the task's reported runs
has no outcome. It names each one with the resolve command, as it does for a missing sign-off (§10.5
step 1). On a re-run after a merge, the reconcile waits for it too. The reconcile writes one
Verification notes line listing the outcomes (`- follow-ups: <task id>, <proposal id>, dropped:
<reason>`), so the result is in git with the task.

### D4. The lead sees open follow-ups as they arrive

The runner tells the lead when a report carries follow-ups, not at close, so most are decided before
the verdict. `ccp tasks follow-ups [--open] [--json]` lists them across tasks, and orientation's
notice list (§9.3) shows the number open with that command.

## Consequences

- The lead decides every follow-up a worker finds before its task merges, and the decision is in
  the task log. Nothing depends on anyone rereading notes.
- **A new close refusal.** A task can wait at close for the lead. D4 keeps that rare: the lead
  usually hears of a follow-up while review or verify is still running.
- The lead takes on one small decision per follow-up. The `--drop` outcome keeps that cheap for
  findings not worth doing.
- The follow-up lines are stored on the run records, in the queue. Telemetry gains only a count per
  run.
- No extra model calls. Each report gains one section.
- §15.8's parked step, after a code-only merge, becomes a follow-up of its task.
- **SPEC rules that change**, each through a task that carries its exact text for the operator's
  signature (§31):
  - §13.1: the worker's follow-up rule.
  - §13.4: the `## Follow-ups` report line.
  - §10.5: close's refusal (step 1) and the reconcile's Verification notes line (step 2).
  - §5.5: the Verification notes row admits the follow-ups line.
  - §9.3: orientation shows the open count.
  - §15.8: the code-only merge's step is a follow-up of its task.
  - The command reference gains `ccp tasks follow-up` and `ccp tasks follow-ups`.

## Notes

- Follow-ups the lead or the architect finds are out of scope. The lead writes tasks itself, and
  architect findings already go through review triage (§19.8).
- The writing-tasks skill's advice to bundle small follow-ups by area (§27's small-tasks measure)
  applies to the tasks that `--task` names.
