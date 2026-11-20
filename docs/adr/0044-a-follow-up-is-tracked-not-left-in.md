---
id: ADR-0044
title: "A follow-up is tracked, not left in notes"
status: accepted
date: "2026-11-20"
deciders: operator
spec_refs: [S9, S11, S13, S21, S22]
notes: |-
  Proposed from a product's plane proposal, accepted in triage with the direction of a structured
  follow-up field in worker reports. Triage suggested that close check it; this ADR enforces it at
  the review point instead (see Options). It changes SPEC rules (listed under Consequences), so the
  operator decides it.
  2026-11-20: status proposed → accepted: Operator: "accept 0044, 0045, 0046" (2026-11-20)
decisions:
  - "D1 not_built"
  - "D2 not_built"
  - "D3 not_built"
  - "D4 not_built"
---
# ADR-0044 — A follow-up is tracked, not left in notes

## Context

Workers find work they must not do: a finding the reviewer defers, a test gap out of the task's
scope, a step that has to wait for a later task. The SPEC says only where it goes, not how:

- §13.1 (`docs/spec/02-delivery.md:442`): workers "never create a task: a follow-up a worker finds
  goes to the lead".
- §3.5 (`docs/spec/01-model.md:214`) and the implementer's definition
  (`plugin/agents/delivery-implementer.md:39`): rule text the brief lacks goes to a plane proposal.
  That covers plane needs only (§31.4); most follow-ups are product work.

In practice a follow-up ends as a sentence in the task's Implementation or Verification notes, or in
a report's prose. Once the task closes nobody reads it again, and the work is lost. The plane cannot
look for it there: it never parses product text (`docs/ROADMAP.md:11`). The report format (§13.4,
`docs/spec/02-delivery.md:522`) already carries one free-text list the plane stores and counts but
does not interpret, `## Friction` (`docs/spec/02-delivery.md:542`). `ccp report` refuses a friction
line that looks like a secret (`ccp/report.py:499-500`).

## Options considered

1. **Parse the notes for follow-ups.** No change for workers. It breaks the rule that the plane never
   parses product prose, and a follow-up phrased another way is still lost. Rejected.
2. **A `follow_ups:` key in the task file**, written by the implementer in the PR. A claimed task's
   file changes only in its PR (§10.5), and the implementer cannot create the task or proposal a
   follow-up resolves to. The reviewer's and verifier's follow-ups would still need a way into the
   file. Rejected.
3. **Workers file proposals or tasks themselves.** Workers never create tasks (§13.1), and a plane
   proposal is for plane needs only (§31.4). Rejected.
4. **A `## Follow-ups` report section, decided by the lead.** The section is the same in each variant
   below; they differ in where an undecided follow-up is caught:
   - **4a. Close refuses.** The strongest, but any follow-up can hold a merge for the lead, on the
     task's critical path. Rejected.
   - **4b. Close warns.** Costs nothing, but a warning is no stronger than a note. Rejected.
   - **4c. Closing the review point refuses.** Follow-ups are decided before the work they belong to
     is declared finished, and no task's merge waits for the lead. A follow-up can stay open for as
     long as its review point runs. Chosen.

## Decision

### D1. A worker report may state follow-ups

A worker report (implement, fix, merge, ruling, review, verify) may carry `## Follow-ups`: one `- `
line per follow-up, or the single line `none`. A missing section reads as `none`. `ccp report`
refuses only a malformed one (a line that is not a `- ` item). A follow-up line that looks like a
secret is refused, as a friction line is. The line's text is the worker's, and the plane never
interprets it. The line is stored on the run record (`follow_ups`, each with an id
`<run_id>#<n>`). The worker definitions and prompts say that work found out of scope goes here, never
only in notes.

A corrected report (§13.4) replaces the run's follow-ups and numbers them afresh. An outcome already
recorded (D2) carries over to a line of the corrected report whose text is identical, and is
otherwise discarded; `ccp report` names each one it discards.

### D2. The lead decides each follow-up

`ccp tasks follow-up <run_id>#<n> --task <id> | --proposal <id> | --drop "<reason>"` records the
outcome beside the line on the run record. Only the lead runs it.

- `--task` names a task that exists in the task log at the integration tip, of any status: a new task
  the lead wrote, or an existing one the follow-up belongs to.
- `--proposal` names a row of `plane/proposals.jsonl` (§31.4).
- `--drop` states why the work is not worth doing. The reason is required.

The command refuses an id that does not resolve. Running it again replaces the outcome.

### D3. A review point does not close over an undecided follow-up

With `QUEUE_ROOT` set, `ccp tasks check` fails when the register (§22.2) records a point `closed`
while a follow-up from a run of one of its tasks is undecided. It names each one, with the command
that decides it. So the register edit that closes the point fails the check, and the lead's
readiness check before a scope (§10.2) and `team.sh runner spawn --dry-run` name it. Without a queue
the check says nothing, so fenced tests and CI stay quiet. Closing a task does not change.

### D4. The lead sees the open count

`ccp tasks follow-ups [--open] [--json]` lists follow-ups across tasks. Orientation (§9.3) shows the
number open, with that command, as its own line after the pending notices. It is not a §3.6 notice
trigger. The runner also tells the lead when a report carries follow-ups.

## Consequences

- The lead decides every follow-up a worker states before its review point closes. Nothing depends
  on anyone rereading notes.
- No task's merge waits on a follow-up. A follow-up can stay open until its review point ends.
- No extra worker runs; one lead decision per follow-up. The `--drop` outcome keeps that cheap for
  findings not worth doing.
- The run record gains `follow_ups`: the lines and their outcomes.
- **SPEC rules that change**, each through a task that carries its exact text for the operator's
  signature (§31):
  - §13.1: the worker's follow-up rule.
  - §13.4: the `## Follow-ups` report line, its secret refusal, and corrections.
  - §11.1: the run record's `follow_ups`, and `contracts/run.schema.json`.
  - §22.2 and §21.1: the closed point's check.
  - §9.3: orientation's open-count line.
  - The command reference gains `ccp tasks follow-up` and `ccp tasks follow-ups`.

## Notes

- Follow-ups the lead or the architect finds are out of scope. The lead writes tasks itself, and
  architect findings already go through review triage (§19.8).
- §15.8's code-only merge still lists its parked step as a follow-up in prose. This ADR gives the
  runner no way to record one. A later decision can add it if the need shows.
- Outcomes live on the run record, so the task's queue record (`contracts/task.schema.json`) does not
  change.
