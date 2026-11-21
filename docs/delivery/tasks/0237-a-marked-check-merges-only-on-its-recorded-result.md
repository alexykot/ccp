---
task_id: 0237-a-marked-check-merges-only-on-its-recorded-result
title: verify record and merge-ok refuse an approve whose marked check has no recorded pass at its head
status: pending
kind: feature
depends_on: ["0234-one-check-parser-and-one-file-at-rev-reader", "0235-one-approval-judge-for-merge-ok-and-verify-check", "0238-the-runner-runs-marked-checks-before-verify"]
clashes_with: ["0217-a-deferred-check-is-recorded-after-close"]
spec_refs: ["S15"]
adr_refs: ["0045 D3"]
review_point: R15
paths: ["ccp/verify.py", "ccp/runs.py", "contracts/verification.schema.json", "contracts/verification.example.json", "docs/spec/02-delivery.md", "docs/adr/0045-checks-only-the-operator-s-machine-can-run.md", "tests/test_marked_checks_record.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0237-a-marked-check-merges-only-on-its-recorded-result

## Intent

ADR-0045 closes three gaps that let a task merge without its operator-machine check: a `ran: false`
check resting on free-text operator evidence is accepted, any evidence under an approved gate passes
whatever head it came from, and §15.8 lets such a task merge code-only. After this task `ccp verify
record` and `ccp verify merge-ok` refuse an approve whose marked check is missing, rests on free text,
cites no passed suite run at the head, or carries a verdict it may not carry, and §15.8 lets only a
step that is not a check merge code-only.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0045 D3, accepted by the operator on 2026-11-20. It needs the suite row's `head`
  (0238), 0235's one judge, and 0234's parser and file-at-rev reader.
- **Shaped** by `sh-20261121T000350Z-5ef1`. Two decisions are the operator's:
  - F01: how a marked check's result is bound to its head. Recommended: the check's record entry cites
    the `suite_id` of the runner's passed run (0238), whose row names the head.
  - F02: the queue keeps one verdict per task, overwritten by each `record`, so a carry of a carry
    cannot be judged. Recommended: a carried pass counts when the earlier verdict held it as a pass on
    these terms or itself carried it (transitive), and each verify run keeps its verdict's per-check
    facts (id, ran, pass, `produced_by`, `operator_step`, `suite_id`: ids and booleans, house rule E5).
  This brief is written on the recommended answers; if the operator answers otherwise, it is
  revised and signed again.
- **The judge.** `merge-ok` and `ccp verify check` share 0235's `judge`, so the refusal lands once.
- **The example contract** carries the sample this task forbids for a marked check
  (`grep -c "operator's live run" contracts/verification.example.json` at `8aefa59`: 1); after 0233 it
  is the only copy, and it stays valid for an unmarked check.
- **Exemptions (ADR-0045 D2, D3).** A marked check may rest on a carried verdict (`approve at <old>`,
  §15.6 rule 3: a head moved only by an integration merge, or a catch-up whose resolution review does
  not list it in `Affected checks`), and a check waived by a ruling is handled as today. Neither needs
  a run at the record's head.
- **Clash with 0217**, which lets a check recorded `ran: false` on a ruling be run after close
  (`ccp verify later`): that is the waiver case, which this task leaves as it is, and §15.8 below says
  so. The two texts agree in either merge order.

## Scope

- **In:** `ccp/verify.py`, `ccp/runs.py`, `contracts/verification.schema.json`,
  `contracts/verification.example.json`, `docs/spec/02-delivery.md`,
  `docs/adr/0045-checks-only-the-operator-s-machine-can-run.md`, `tests/test_marked_checks_record.py` (new).
- **A check's `suite_id`** (optional in the contract) names the run its evidence came from.
- **The refusals**, in `judge` on plain values and so in `record` (on an approve), `merge-ok` and
  `verify check`, each naming the check, for a marked check that: is missing from the record; was run
  and its evidence names no approved `operator_step`, whoever produced it; was run and names no
  `suite_id` of a passed run of that lane, bound to the task, whose `head` is the record's head; is
  `ran: false` on free-text operator evidence; or carries `approve at <old>` where the run at `<old>`
  kept no qualifying facts for that check. A marked check carrying a qualifying verdict needs no run at
  the new head, and a check waived by a ruling (`ran: false`, `rests_on` naming the ruling) is handled
  as today. `merge-ok` takes the marked
  checks from the task file at the head (`tasklog.text_at`), never the checkout's.
- **The verify run** keeps the per-check facts of the verdict recorded on it (`runs.py`).
- `contracts/verification.example.json`'s operator sample names an unmarked check.
- ADR-0045 D3 recorded `built`.
- **Tests** in `tests/test_marked_checks_record.py` (new): each refusal on plain values; an approve
  with a passed run at the head accepted; a carry accepted from a qualifying verdict and from a
  qualifying carry, refused from a free-text one; a carried marked check accepted after an
  integration-merge-only move and after a resolution review that does not list it, with no run at the
  new head; a marked check waived by a ruling accepted; `merge-ok` reading the task file at the
  head.

### SPEC changes (signed in the brief, §31)

**a. §15.4, the `rests_on` forms.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> where `<sha>` resolves to a commit; or evidence the operator produced, `produced_by: operator` with
> free text.

PROPOSED:
> where `<sha>` resolves to a commit; or evidence the operator produced, `produced_by: operator` with
> free text, never for a check marked `runs_on: operator-machine`. On an approve it refuses a marked
> check that is missing from the record; that was run with evidence naming no approved `operator_step`
> (whoever produced it, `operator` included) or no `suite_id` of a passed run recorded at the record's
> head; that is `ran: false` on free-text operator evidence; or that carries a verdict it may not
> carry (§15.6 rule 3). A marked check resting on a verdict it may carry needs no run at the new head,
> and one waived by a ruling is handled as any other. `ccp verify merge-ok` reads the marked checks
> from the task file at the head it is given and refuses on the same terms.

**b. §15.6 rule 3, a carried verdict.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
>    in full. A new head needs a new verdict, except a catch-up close made itself (§16.5 rule 4).

PROPOSED:
>    in full. A new head needs a new verdict, except a catch-up close made itself (§16.5 rule 4). A
>    check marked `runs_on: operator-machine` rests on `approve at <old>` only when the verdict at
>    `<old>` held it as a pass with an approved `operator_step` and a passed run at `<old>`, or itself
>    carried it on these terms; each verify run keeps its verdict's per-check facts (id, ran, pass,
>    producer, `operator_step`, `suite_id`) for that judgement. Otherwise it is run again at the new
>    head (§15.8).

**c. §15.8, steps only the operator's machine can run.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
>   The task may merge code-only, the step listed as a follow-up. A parked step, and any check needing

PROPOSED:
>   A step that is not a dod_check (a rollout after the merge) may merge code-only, the step listed as
>   a follow-up. A dod_check that needs that machine is marked `runs_on: operator-machine` (§5.5): the
>   runner runs it, under the task's approved `operator` gate or a standing approval (§17.9), at each
>   head it hands the verifier (§10.2), and the task never merges without its result, a verdict it
>   carries (§15.6 rule 3) or a ruling that waives it (§15.4). A parked step, and any check needing

- **Out:** records written before this task (not re-judged), the runner's loop (0238), and a step that
  is not a check.

## dod_checks

- id: `mr-01`
  story: As a lead, a check only my machine can run cannot be approved on a promise.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_marked_checks_record 2>&1 | tail -15`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `mr-02`
  story: As a plane developer, the free-text refusal bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `judge` accepts free-text operator evidence for a marked check again.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_marked_checks_record`.
  expect: at least one failure (the `ran: false` free-text test).
  dry run: n/a — the module is new.

- id: `mr-05`
  story: As a runner, a re-verify after an integration merge is not held for a run the check does not need.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `judge` asks every marked check for a passed run at the record's head, carried or not.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_marked_checks_record`.
  expect: at least two failures (the integration-merge and the resolution-review carries).
  dry run: n/a — the module is new.

- id: `mr-03`
  story: As a runner, the producer and verify rules I already rely on hold unchanged.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_verify_producer tests.test_verify_as_written tests.test_verify 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

- id: `mr-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0237 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`8aefa59`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
