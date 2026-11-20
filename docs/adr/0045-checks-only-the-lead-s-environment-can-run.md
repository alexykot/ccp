---
id: ADR-0045
title: "Checks only the lead's environment can run"
status: proposed
date: "2026-11-20"
deciders: operator
spec_refs: [S2, S5, S10, S13, S15]
notes: |-
  Proposed from a product's plane proposal that asked for a new stage beside review and verify,
  with a close refusal, a health measure and a rehearsal hook. This ADR weighs it against extending
  the existing operator step and recommends the smaller change. It changes SPEC rules (listed under
  Consequences), so the operator decides it.
---
# ADR-0045 — Checks only the lead's environment can run

## Context

Some dod_checks cannot run in a worker's sandbox: a live check on the operator's machine, a
round trip to a real receiver or service, or a step that needs credentials only that machine holds.
Here "the lead's environment" means the operator's machine, where the lead and the runner run and
the workers' sandboxes do not reach.

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
2. **Mark the check and tighten the existing operator step.** One line on the check, a fixed place in
   the runner's loop, and a refusal in `ccp verify record` that close inherits through
   `ccp verify merge-ok`. It closes all three gaps with no new phase. Chosen.
3. **Guidance only**: tell task writers and verifiers to use operator steps. No code, but gap 2
   stays open. Rejected.

## Decision

### D1. A check names where it runs

A dod_check may carry the line `runs_on: operator` after its `setup:` line: it runs on the operator's
machine, not in a worker's sandbox. A check without the line runs in the sandbox, as today.
`ccp tasks check` refuses any other value. The check's `dry run` line may read
`dry run: n/a — runs on the operator's machine`.

### D2. The runner runs it as an approved operator step

After the last clean review and before it launches the verifier, the runner runs each `runs_on:
operator` check at the reviewed head. It runs it in a `--kind mac` worktree, under the task's
approved `operator` gate or a standing approval (§17.9), and hands the result to the verifier. A
check that only the operator can run by hand (a credential the runner may not use) is run by the
operator under the same gate. The implement and verify prompts list such checks as not the worker's
to run.

### D3. Its evidence must be a result, not a promise

The verifier records a `runs_on: operator` check with the evidence it was handed: `produced_by`
`runner`, `lead` or `operator`, and `operator_step` naming the approved gate, whoever produced it.
`ccp verify record` refuses an approve, naming the check, when a marked check:

- is missing from the record;
- failed;
- has no approved `operator_step`; or
- is `ran: false`, unless it rests on a ruling (a gate, spec question or lead ruling that waives it).

Free-text operator evidence does not hold for a marked check. `ccp verify merge-ok`, and so
`ccp tasks close`, refuses on the same terms. §15.8's code-only merge no longer covers a dod_check;
it stays for a step that is not one, such as a rollout after the merge.

### D4. No new stage, health measure or rehearsal hook

- The wait is the existing `operator_step` wait, recorded in the ledger like every other wait.
- A rehearsal is the check's `dry run` line, plus the product's env hooks (§12), which already
  prepare a `--kind mac` worktree.

## Consequences

- A task states when it is written which checks need the operator's machine. It cannot merge until
  each has a recorded result or a recorded waiver.
- **A refusal tightened, not a new one.** An approve that today rests on free-text operator evidence
  for such a check is refused.
- A task with such a check waits for the operator's gate unless a standing approval covers it. The
  lead can write that approval when it starts the scope (§10.2).
- No extra model calls. The check runs once, on the operator's machine, as an operator step does
  today.
- **SPEC rules that change**, each through a task that carries its exact text for the operator's
  signature (§31):
  - §5.5 and §5.6: the check grammar's `runs_on` line.
  - §10.2 step 2: where in the runner's loop such a check runs.
  - §13.2: the implement and verify prompts list such checks as not the worker's.
  - §15.4: the refusals in `ccp verify record` and `merge-ok`.
  - §15.8: the code-only merge does not cover a dod_check.

## Notes

- Under ADR-0044, a step that §15.8's code-only merge parks becomes a follow-up of its task. The two
  ADRs are independent: each holds without the other.
- If the operator later wants the wait measured, it fits as one line in §27's sign-off wait measure.
  This ADR does not add it.
