---
task_id: 0062-producer-rule-follow-ups
title: The producer rule pins its operator-step branch and names what a ruling is
status: pending
kind: feature
depends_on: []
spec_refs: ["S15"]
review_point: R4
paths: ["ccp/verify.py", "contracts/", "docs/spec/02-delivery.md", "tests/test_verify*.py"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0062-producer-rule-follow-ups

## Intent

The §15.4 producer rule is pinned by tests on every branch, and a check closed by a ruling cites a ruling the plane can find (a spec question id or a gate id), so `rests_on` is not free text.

## Context (not checked)

- From task 0035's review: a named `operator_step` on a check with no `produced_by` is validated, but deleting that branch keeps the suite green.
- Any `rests_on` text counts as a ruling today.
- `produced_by` is self-declared, and a runner can open a standing operator gate itself, so the operator-step exception is only as strong as the gate ledger. That is a known limit, recorded here, not fixed by this task.
- §31.1: §15.4 gains a requirement, so the merge waits on the operator's approval.
- Lead ruling, fix round 1 (option b, bounded; the lead's words): "A rule that adding produced_by bypasses is not worth the operator's approval. One fix round: 1. Check rests_on on every ran:false check. Accept exactly three forms and refuse anything else, naming the check: (i) a ruling: every spec-question id or gate id it names exists, and a gate must be closed and approved (no unknown id beside a known one); (ii) a carried verdict, 'approve at <sha>' (15.6 rule 3), where <sha> resolves to a commit; (iii) evidence the operator produced: produced_by: operator with free text. 2. Reword the PROPOSED 15.4 text to state those three forms, replacing the task's verbatim sentence, and quote both versions (the task's and the reworded) in the PR body. It is a gated section change, so the operator approves the final text. 3. Fix plugin/agents/delivery-verifier.md:49 to match, and list it as outside the declared paths. 4. Test each form and each refusal."
- Lead ruling, fix round 2, on review 2's MINOR 3 (the lead's words): "an unanswered spec question isn't a ruling. Make it symmetric with gates: a named spec-question id counts only when its answer file exists with verdict `resolved`, and the §15.4 text says so."

## Scope

- **In:** a test for the operator-step branch on a check with no `produced_by`; `ccp verify record` accepts `rests_on` only when it names a spec question id (`sm-…`) or a gate id (`<task_id>-<n>`) that exists, and names it otherwise. §15.4, CURRENT: "a check the owner's ruling closed is `ran: false` with `rests_on` naming the ruling (ADR-0035 D7)". PROPOSED: "a check the owner's ruling closed is `ran: false` with `rests_on` naming the ruling by its spec question id or gate id, which `ccp verify record` checks exists (ADR-0035 D7)".
- **Out:** how producers are authenticated.

## dod_checks

- id: `check-01`
  story: As a verifier, a waiver must cite a real ruling.
  setup: a scratch task with a check `ran: false`, first with a free-text `rests_on`, then with an existing gate id.
  steps:
    1. Run `ccp verify record` with each.
  expect: the first is refused, naming `rests_on`; the second is recorded.
  dry run: on the merge base both are recorded.
- id: `check-02`
  story: As a plane developer, the operator-step branch is pinned.
  setup: the PR head with the operator-step check for a check without `produced_by` deleted from `ccp/verify.py`.
  steps:
    1. Run `tests.test_verify`.
  expect: a test fails.
  dry run: on the merge base the suite stays green with that branch deleted.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12 (implementer): `producer_errors` (record only, `require`) now refuses a check that names
  no `produced_by` and is `ran: false` with a `rests_on` that names no ruling the queue holds: a gate
  id `<task_id>-<n>` whose `escalations/<task_id>/<n>.json` exists, or a spec question id `sm-…`
  whose `questions/<id>.json` exists. The id may sit inside prose; one that exists is enough. The
  refusal names the check and `rests_on`. A check that names a `produced_by` keeps a free `rests_on`
  (whose claim it rests on, §15.4; `approve at <old>`, §15.6 rule 3), so the rule applies only to the
  check the plane can tell a ruling closed. `merge-ok` and `check` do not apply it, so a record
  written earlier is still read. Any task's gate counts, and existence is all that is checked (not
  the gate's state). The operator-step branch on a check with no `produced_by` is pinned in
  `tests/test_verify.py`. §15.4 carries the task's PROPOSED text; the schema's `rests_on` and
  `produced_by` descriptions say the same.

- 2026-11-12 (implementer, fix round 1, per the lead's ruling in Context): the `rests_on` check
  moved out of `producer_errors` into `rests_on_errors`, which `ccp verify record` runs on every
  `ran: false` check whatever its `produced_by`. It accepts a ruling (at least one gate or spec
  question id, every one named existing, every gate closed and approved), a carried verdict (exactly
  `approve at <sha>`, the sha resolving with `git rev-parse` in the product checkout), or any text
  with `produced_by: operator`, and refuses anything else naming the check and `rests_on`. A check
  with no `produced_by` may rest on a ruling or a carried verdict, as the ruling lists them. The §15.4 sentence
  now states the three forms, replacing the task's PROPOSED wording; the schema descriptions and the
  verifier brief (outside the declared `paths`, per the ruling) say the same. The round-1 test that
  let a check with a producer rest on any text was replaced; no other existing test contradicted
  the ruling.

- 2026-11-12 (implementer, fix round 2): the sentences that still said a check not run names "whose
  claim it rests on" (§15.4's first paragraph, the verifier brief's not-run bullet and the schema's
  `ran` and `rests_on` descriptions) now point at the three forms, so §15.4 no longer contradicts
  itself. A date beside a ruling's id reads as a gate id (`<digits>-<slug>-<digits>`) that is not in
  the queue, and is refused as an unknown id beside a known one: a test records that decision, and
  another pins the token boundaries of both id patterns. Known asymmetry, left for the lead: a gate
  cited as a ruling must be closed and approved, but a spec question only has to exist
  (`questions/<id>.json`), so an unanswered question passes as a ruling. The code follows the
  ruling's "exists"; requiring `status: answered` would be the lead's call.

- 2026-11-12 (implementer, fix round 2, per the lead's second ruling in Context): the asymmetry
  above is closed. A spec question cited as a ruling now counts only when its answer file
  `questions/<id>.answer.json` exists with verdict `resolved` (§17.5), as a gate counts only closed
  and approved; an unanswered question, or one answered `needs_operator` or `not_a_spec_question`,
  is refused, alone or beside a ruled id. §15.4, the schema's `rests_on` description and the verifier
  brief say so.

## Verification notes

*Append-only.*
