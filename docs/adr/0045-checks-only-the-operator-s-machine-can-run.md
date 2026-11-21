---
id: ADR-0045
title: "Checks only the operator's machine can run"
status: accepted
date: "2026-11-20"
deciders: operator
spec_refs: [S2, S5, S10, S13, S15, S21]
notes: |-
  Proposed from a product's plane proposal that asked for a new stage beside review and verify,
  with a close refusal, a health measure and a rehearsal hook. This ADR weighs it against extending
  the existing operator step and recommends the smaller change. It changes SPEC rules (listed under
  Consequences), so the operator decides it.
  2026-11-20: status proposed → accepted: Operator: "accept 0044, 0045, 0046" (2026-11-20)
decisions: ["D1 built", "D2 built", "D3 built"]
---
# ADR-0045 — Checks only the operator's machine can run

## Context

Some dod_checks are a step the workers cannot take (§15.8's words): a live check on the operator's
machine, a round trip to a real receiver or service, or a step that needs credentials only that
machine holds. The lead and the runner run on that machine; workers cannot reach what it holds.

The plane already has most of the mechanism:

- **The wait.** `waiting_on=operator_step` is "a step only the operator's machine can run" (§10.1,
  `docs/spec/02-delivery.md:31`).
- **Where it runs.** A parked step, and any check that needs that machine, runs in a worktree of its
  own at the PR head, `ccp wt create --kind mac` (§15.8, `docs/spec/02-delivery.md:1095-1100`).
  The runner runs approved operator steps (`docs/spec/01-model.md:52`).
- **The evidence.** The seat that rules never produces its evidence, except an operator step the
  operator approved (§2.3, `docs/spec/01-model.md:83-86`). The verify record names each check's
  producer and, for the lead or the runner, the approved gate in `operator_step` (§15.4,
  `docs/spec/02-delivery.md:995-1013`; `ccp/verify.py:247-268`).

Three gaps remain:

1. Nothing in the task says which check needs that machine. The verifier finds out at verify time.
2. A check the verifier did not run may be recorded `ran: false`, resting on evidence "the operator
   produced, `produced_by: operator` with free text" (§15.4, `docs/spec/02-delivery.md:1006-1007`).
   So such a check can be approved on a promise instead of a result.
3. A task may "merge code-only, the step listed as a follow-up" (§15.8,
   `docs/spec/02-delivery.md:1098`). For a dod_check, that means merging unchecked.

## Options considered

1. **A new stage beside review and verify** (the proposal): its own phase and state, a close
   refusal, a health measure and a rehearsal hook. It is explicit, but it duplicates what exists:
   the wait, the worktree kind, the gate class and the evidence rule. It adds a phase to every
   runner's loop, to the lifecycle (§10.1) and to the board.
2. **Require an approved `operator_step` for all `produced_by: operator` evidence, with no marker.**
   No grammar change, and it closes gap 2 for every check. But gap 1 stays: nothing says in advance
   which check needs the machine, so a check left out of the record or recorded on a promise is not
   caught. It would also change how every existing operator-produced check is recorded. Rejected.
3. **Mark the check and tighten the existing operator step.** One line on the check, a fixed place in
   the runner's loop, and refusals in `ccp verify record` that close inherits through
   `ccp verify merge-ok`. It closes all three gaps with no new phase. Chosen.
4. **Guidance only**: tell task writers and verifiers to use operator steps. No code, but gap 2
   stays open. Rejected.

## Decision

### D1. A check names where it runs

A dod_check may carry the line `runs_on: operator-machine` after its `setup:` line: it is a step the
workers cannot take, run on the operator's machine. A check without the line is the workers' to run,
as today. `ccp tasks check` refuses any other value. The check's `dry run` line may read
`dry run: n/a — runs on the operator's machine`.

### D2. The runner runs it at the head the verifier gets

The runner runs each `runs_on: operator-machine` check at the head it hands to the verifier, after
any catch-up with the integration tip (§15.6 rule 2), just before it launches the verifier. It runs
the check in a `--kind mac` worktree, under the task's approved `operator` gate or a standing approval
(§17.9), and hands the result to the verifier. A check that only the operator can run by hand (a
credential the runner may not use) is run by the operator under the same gate.

Each new head handed to the verifier gets a new run of the check. A fix round always produces a new
head. The only exceptions are a head that moved only by an integration merge, or a catch-up whose
resolution review does not list the check in `Affected checks`; there the check rests on the earlier
approve (D3). The implement and verify prompts list such checks as not the worker's to
run.

### D3. Its evidence must be a result, not a promise

The verifier records a `runs_on: operator-machine` check with the evidence it was handed, naming the
approved gate in `operator_step`, whoever produced it (`runner`, `lead` or `operator`). It may instead
rest on a carried verdict (`approve at <old>`, §15.6 rule 3), but only when the record at `<old>` held
the check as a pass meeting these terms. After a resolution review, the check is run again when the
review lists it in `Affected checks`, as §15.6 rule 3 already requires.

New refusals, by `ccp verify record` on an approve, naming the check, when a marked check:

- is missing from the record;
- has evidence with no approved `operator_step`, even when `produced_by: operator` (today that seat
  needs none);
- is `ran: false` resting on free-text operator evidence; or
- carries a verdict from a record that did not hold it as such a pass.

A failed check, or a `ran: false` check resting on a ruling that waives it, is handled as today.
`ccp verify merge-ok` reads the marked checks from the task file at the head it is given and refuses
on the same terms, and so `ccp tasks close` does too. §15.8's code-only merge no longer covers a
dod_check; it stays for a step that is not one, such as a rollout after the merge.

## Consequences

- A task says when it is written which checks need the operator's machine. It cannot merge until
  each has a recorded result, a carried one, or a recorded waiver.
- **Refusals tightened, not a new stage.** An approve that today rests on free-text operator evidence
  for such a check is refused.
- A task with such a check waits for the operator's gate unless a standing approval covers it. The
  lead can write that approval when it starts the scope (§10.2).
- No extra worker runs. The check runs once per head handed to the verifier, on the operator's
  machine, as an operator step does today.
- No new stage, health measure or rehearsal hook. The wait is the existing `operator_step` wait,
  recorded in the ledger. A rehearsal is the check's `dry run` line plus the product's env hooks
  (§12), which already prepare a `--kind mac` worktree.
- **SPEC rules and definitions that change**, each through a task that carries its exact text for the
  operator's signature (§31):
  - §5.5 and §5.6: the check grammar's `runs_on` line.
  - §21.1: `ccp tasks check` refuses another value.
  - §10.2 step 2: where in the runner's loop such a check runs, and its rerun per head.
  - §13.2: the implement and verify prompts list such checks as not the worker's.
  - §15.4: the new refusals in `ccp verify record`, and `merge-ok` reading the marked checks at the
    head.
  - §15.6 rule 3: a carried verdict for a marked check.
  - §15.8: the code-only merge does not cover a dod_check.
  - `plugin/agents/*`: the runner's, implementer's and verifier's definitions.

## Notes

- Under ADR-0044, a follow-up is recorded through worker reports. The two ADRs are independent: each
  holds without the other.
- If the operator later wants the wait measured, it fits as one line in §27's sign-off wait measure.
  This ADR does not add it.
