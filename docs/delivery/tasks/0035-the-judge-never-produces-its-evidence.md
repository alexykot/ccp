---
task_id: 0035-the-judge-never-produces-its-evidence
title: The seat that rules never produces the evidence it rules on
status: pending
kind: feature
depends_on: []
spec_refs: ["S2", "S15"]
review_point: R3
paths: ["docs/spec/", "plugin/", "ccp/", "contracts/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0035-the-judge-never-produces-its-evidence

## Intent

Separation of duties becomes a plane rule: the seat that rules on a task (the lead, or a runner at a gate) never produces the evidence its verdict rests on, except an operator step the operator approved. The verify record names who produced each piece of evidence, and `ccp verify` refuses a record whose evidence came from the ruling seat.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §2 and §15.
- Any team with a ruling seat and an evidence-producing seat needs the judge kept apart from the evidence; today products keep this as prose.
- **SPEC change (§31):** this task changes a § rule — the seat duties in §2 and the verification record in §15. It needs the operator's approval at build: the PR carries the CURRENT → PROPOSED text and quotes the ruling.

## Scope

- **In:** §2 and §15 state the rule; the verification record schema gains a producer per evidence item; `ccp verify` rejects evidence produced by the ruling seat unless it is an approved operator step; the runner and verifier briefs state it.
- **Out:** seats beyond the existing ones.

## dod_checks

- id: `check-01`
  story: As a reviewer of the process, self-produced evidence is refused.
  setup: a verify record where the ruling seat produced an evidence item.
  steps:
    1. Record it with `ccp verify`.
  expect: it is refused, naming the item and the seat.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As an operator, my approved step counts.
  setup: evidence from an approved operator step.
  steps:
    1. Record it.
  expect: accepted.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): each `checks[]` item of the verify record gains `produced_by` (the seats of
  §2.1 plus `operator`: verifier, implementer, reviewer, architect, operator, runner, lead) and an
  optional `operator_step` (the approving gate's id, `<task_id>-<n>`). `ccp verify record` requires
  `produced_by` on every check, and refuses, naming the check and the seat, evidence produced by the
  lead or the runner unless `operator_step` names the task's gate file that is class `operator`,
  closed and approved (a standing approval writes such a file). A named `operator_step` that is not
  such a gate is refused whoever produced the evidence. `merge-ok` and `check` read records written
  before the field (E9) but refuse a ruling seat's evidence on the same terms. Gate runs carry no
  producer: §15.1 makes them the verifier's own. SPEC §2.3, §15.4 and §15.8 drafted for the operator's
  approval; the verifier and runner briefs state the rule. Tests: `tests/test_verify_producer.py`;
  existing fixtures recorded through `ccp verify record` now name `produced_by: verifier`.
- 2026-11-10 (implementer, fix round 1): the gate file an `operator_step` names must itself name
  this task (`task_id`) and this step (`escalation_id`), so a file under the task's directory that
  belongs to another gate is refused. SPEC §15.8 PROPOSED now says the lead or the runner runs a
  check only as an approved operator step, matching §2.3, §15.4 and the code (it said the lead never
  does). Review MINOR 3 (a check closed by a ruling with no underlying evidence) is left for the
  lead's ruling.
- 2026-11-10 (implementer, fix round 2): the lead ruled on review MINOR 3. A ruling is not evidence:
  a check the owner's ruling closed (`ran: false`, `rests_on` naming it, ADR-0035 D7) names in
  `produced_by` the seat whose evidence the ruling weighed, never `lead`, and names none when no
  evidence underlies the waiver. `ccp verify record` accepts a check with no `produced_by` only when
  it is `ran: false` with `rests_on`; a ruling seat named as producer is still refused, and a named
  `operator_step` is still checked. The schema keeps `produced_by` optional (records written before
  the field are read) and its description states the exception. SPEC §15.4 and the verifier brief
  say so. Merged origin/main (task 0036).

## Verification notes

*Append-only.*
