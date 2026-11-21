---
task_id: 0217-a-deferred-check-is-recorded-after-close
title: A check that verify deferred can be run and recorded after its task closed
status: pending
kind: feature
depends_on: []
clashes_with: ["0237-a-marked-check-merges-only-on-its-recorded-result"]
spec_refs: ["S15", "S23"]
review_point: R15
paths: ["ccp/verify.py", "ccp/cli.py", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "docs/cli/02-delivery.md", "tests/test_verify_later.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0217-a-deferred-check-is-recorded-after-close

## Intent

Some dod_checks cannot run before the merge: a step on the live system, or one that needs the merged
code deployed. The verifier records such a check `ran: false`, resting on a ruling or on the
operator's word, and the task closes. When the check is finally run, there is nowhere to put the
result: only `ccp verify record` writes the verdict, and it is the verifier's, at the PR head, before
close. So the outcome lives in a chat message. After this task, the lead or the runner records the
result of a deferred check after its task closed, with its evidence and producer held to the same
rules as a verdict's, and `ccp verify deferred` lists the closed tasks' checks still waiting for one.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: an accepted plane proposal, cut from R10 because it changes a § rule (triage item T18).
  Task 0158's Context left it for a signed task:
  `grep -n 'deferred check after close' docs/delivery/tasks/0158-*.md` at `1b734dd`: one line.
- **Only `record` writes.** `ccp verify` takes `record`, `merge-ok`, `check` and `spec-text`
  (`git grep -n 'choices=("record", "merge-ok", "check", "spec-text")' -- ccp/cli.py` at `1b734dd`: one
  line), and §15.4 says the verifier writes `verification/<task_id>.json` only through
  `ccp verify record`. §23.7's writer table names the verifier subagent as that file's only writer.
- **What a deferred check looks like.** In a record, `ran: false`, `pass: null`, and `rests_on` in one
  of three forms (§15.4): a ruling, a carried verdict `approve at <sha>`, or `produced_by: operator`
  with free text. A carried verdict was run at an earlier head, so it is not deferred.
  `verify.carried_from(rests_on)` tells the carried form apart
  (`git grep -n 'def carried_from' -- ccp/verify.py` at `1b734dd`).
- **The producer rule to reuse.** `verify.producer_errors` and `_operator_step_refusal` refuse
  evidence a ruling seat (`lead`, `runner`) produced unless `operator_step` names the task's approved
  `operator` gate. A deferred check run after close is usually run by the runner or the lead on the
  operator's machine, so the same rule applies.
- **Clash with 0237**, which changes how a `ran: false` check on operator evidence is judged in
  `ccp verify record` (§15.4) for checks marked `runs_on: operator-machine`; both change the handling
  of checks not run at verify, so they do not run together.
- No R14 task edits this logic. Task 0209 edits `ccp/verify.py`'s `spec_text` and §15.2.

## Scope

- **In:** `ccp/verify.py`, `ccp/cli.py`, `docs/spec/02-delivery.md`, `docs/spec/04-observability.md`,
  `docs/cli/02-delivery.md`, `tests/test_verify_later.py` (new).
- **`ccp verify later <task_id> --check <id> (--pass | --fail) --evidence "<text>" --produced-by <seat>
  [--operator-step <gate id>]`**, needs `QUEUE_ROOT`. It appends one row to
  `QUEUE_ROOT/verification/<task_id>.later.jsonl`: `{task_id, dod_check_id, pass, evidence,
  produced_by, operator_step, at, by}` (`by`: the seat it was run as). It refuses, exit 2 and nothing
  written, naming why:
  - a task that is not `done` in the queue, or has no verification record;
  - a check the record does not hold, or holds other than `ran: false`, or holds resting on a carried
    verdict (`approve at <sha>`);
  - evidence that is empty, longer than 500 characters, holds a line break, or looks like a secret
    (the check `ccp prompt --note` uses);
  - a producer the verdict record would refuse (§15.4: `lead` or `runner` without an approved
    `operator` gate of the task in `operator_step`, or an `operator_step` that is not one), reusing
    `_operator_step_refusal`.

  A check may be recorded again: the latest row is its result.
- **`ccp verify deferred [--task <id>] [--json]`** lists, for each `done` task with a verification
  record, each check recorded `ran: false` and not resting on a carried verdict, as `open` (no
  `later` row), `passed` or `failed` (its latest row). Text: one line each,
  `<task_id> <check id> <state>`, and a last line `<n> open, <m> failed`. Exit 0 whatever it finds.
- The verdict record and its contract are unchanged; `merge-ok`, `check` and close never read the
  `later` rows.
- `docs/cli/02-delivery.md` gains both commands' rows (who: lead, runner).
- **Tests** in `tests/test_verify_later.py` (new), on a temp queue with a closed task whose record
  holds a check on a ruling, one carried, and one run:
  - recording a pass on the ruled check writes one row, and `deferred` shows it `passed` and the
    carried and run checks not at all;
  - each refusal in the list above, nothing written;
  - a `failed` row is listed as failed and counted;
  - `--produced-by runner` with an approved operator gate is accepted, without one refused.

### SPEC changes (signed in the brief, §31)

**a. §15.4, a paragraph after the `as_written` paragraph.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> without both, or on a check not run, naming the check. `ccp tasks close` lists each one (its id,
> `held_instead` and `ruling`) before it merges, and does not refuse on it.

PROPOSED:
> without both, or on a check not run, naming the check. `ccp tasks close` lists each one (its id,
> `held_instead` and `ruling`) before it merges, and does not refuse on it.
>
> A check recorded `ran: false` that does not rest on a carried verdict may be run after its task
> closed: the lead or the runner records the result with `ccp verify later <task_id> --check <id>
> --pass|--fail --evidence "<one line>" --produced-by <seat> [--operator-step <gate>]`, appended to
> `verification/<task_id>.later.jsonl`, never to the verdict record. It refuses a task not done, a
> check not recorded so, evidence that is empty, over 500 characters, on more than one line or looks
> like a secret, and a producer the verdict record would refuse (a ruling seat without an approved
> operator step). `ccp verify deferred` lists each such check of a done task as open, passed or
> failed. A failed result reopens nothing: the lead tasks the fix.

**b. §23.7, the writers table.**

CURRENT (`docs/spec/04-observability.md` at `8aefa59`):
> | `verification/<id>.json` | the verifier subagent, through `ccp verify record` |

PROPOSED:
> | `verification/<id>.json` | the verifier subagent, through `ccp verify record` |
> | `verification/<id>.later.jsonl` | the lead or the runner, through `ccp verify later`, after the task closed (§15.4) |

- **Out:** a ledger event for the result, a notice on a failed result, and any change to the verdict
  record, `merge-ok` or close.

## dod_checks

- id: `dl-01`
  story: As a lead, I record the result of a check that could only run after the merge.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_verify_later 2>&1 | tail -25`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `dl-02`
  story: As a plane developer, the producer rule bites here too.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `ccp verify later` no longer calls `_operator_step_refusal`.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_verify_later`.
  expect: at least one failure (the runner without an approved gate).
  dry run: n/a — the module is new.

- id: `dl-03`
  story: As a lead, the list of open deferred checks runs on a real queue.
  setup: a checkout of the PR head; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . verify deferred --json; echo rc=$?`.
  expect: prints a JSON list (empty) and `rc=0`.
  dry run (`1b734dd`): exit 2, argparse refusing `deferred` as an action.

- id: `dl-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0217 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`1b734dd`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
