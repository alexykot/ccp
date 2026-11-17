---
task_id: 0107-check-not-as-written
title: The verification record gives a check that cannot hold as written its own state, and close shows it
status: pending
kind: feature
depends_on: []
spec_refs: ["S15"]
review_point: R6
sign_off: build
paths: ["contracts/verification.schema.json", "contracts/verification.example.json", "ccp/verify.py", "ccp/lifecycle.py", "templates/prompts/verify.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-runner.md", "docs/spec/02-delivery.md", "tests/test_verify*.py", "tests/test_tasks_close*.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0107-check-not-as-written

## Intent

A verifier can meet a dod_check that cannot hold as written: its expectation names something the
product cannot do, or a step that no longer exists. Today it records that check as a pass with the
caveat in `findings`. It should be able to record the check as not as written: what it checked in its
place, and the ruling that let it. The closing runner should see each one, so the lead learns of it
from the tooling, not from a relayed finding.

## Context (not checked)

- An accepted product proposal (operator, 2026-11-16: all approved; gated). It is generic: any product
  whose verifier meets a check that cannot hold as written needs to record that distinctly from a
  pass. Today the verifier puts the caveat in findings, and the runner relays it to the lead.
- This changes the verification record's contract and §15.4's rules, so the final §15.4 text needs
  the operator's sign-off after verify (`sign_off: build`). The PR body quotes each changed passage
  with its CURRENT and PROPOSED text.
- §15.4 already lets an older reader pass over a newer record's unknown keys. Task 0099 tells the
  verifier to record such a change with the head's own `ccp`.
- Ruling (spec question sm-20261117T013234Z-3736, lead's answer, commit 4d46bf63bdf4429d2def60cd73c49dde5289e01b):
  Keep exit 1 as built. Read 0107's check-01 as expecting exit 1 for each refused record copy; the
  verifier judges it so. Append an Implementation note to docs/delivery/tasks/0107-check-not-as-written.md
  citing this ruling (the check text itself is left as written, per SPEC §10.5 for a claimed task). No
  SPEC change, no code change.

## Scope

- **In:**
  - A check in the record may carry `as_written: false` (the default is true) with:
    - `held_instead`: what the verifier checked in its place (required, non-empty);
    - `ruling`: the spec question or gate ids that let it, in the ruling form `rests_on` already
      accepts (required; each id exists, each gate is closed and approved, each question is resolved).
    The check itself is still ran and passed (`ran: true`, `pass: true`), or it is a failure. "Not as
    written" is never a third pass value.
  - The record's schema version rises, and the contract and example carry the fields.
  - `ccp verify record` refuses `as_written: false` without `held_instead` or a valid `ruling`, naming
    the check. It also refuses one on a `ran: false` check.
  - `ccp tasks close` prints each not-as-written check (id, `held_instead`, `ruling`) before it merges,
    and the runner brief tells the runner to pass that list to the lead with the close result. Close
    does not refuse on it: the ruling is already the owner's decision.
  - The verify template and the verifier agent say when to use it, and that the caveat no longer goes
    only in findings.
  - SPEC §15.4, PROPOSED (final wording at build): "A check the verifier ran whose expectation cannot
    hold as written is recorded `as_written: false`, with `held_instead`, what it checked in its
    place, and `ruling`, the spec question or gate ids that let it, in the ruling form above. It is
    still a pass or a fail. `ccp verify record` refuses one without both, or on a check not run.
    `ccp tasks close` lists each one when it merges."
- **Out:**
  - Rewriting the task's dod_check text. That stays the lead's, through the usual amendment.

## dod_checks

- id: `check-01`
  story: As a verifier, I can record a check that held only in another form.
  setup: a throwaway product with a task, an approved gate `<task_id>-1`, and a verdict whose check-01
    is `as_written: false` with `held_instead` and `ruling: <task_id>-1`.
  steps:
    1. Run `ccp verify record` on it, then on copies with `held_instead` removed, with `ruling` naming a
       gate that does not exist, and with the check `ran: false`.
  expect: the first is written, and `ccp verify merge-ok` accepts it. Each copy is refused (exit 2),
    naming the check and what is missing.
  dry run: n/a.
- id: `check-02`
  story: As a runner, close shows me what to pass on.
  setup: as check-01, the record written and the PR mergeable (a throwaway remote, or close's existing
    test seam).
  steps:
    1. Run `ccp tasks close <id> --pr <n>`.
  expect: the output lists check-01 with its `held_instead` and `ruling` before the merge, and the
    merge proceeds.
  dry run: n/a.
- id: `check-03`
  story: As an older reader, a newer record still reads.
  setup: a record with `as_written: false`, read by `merge-ok` with `RECORD_VERSION` patched to the
    previous value.
  steps:
    1. Run `ccp verify merge-ok`.
  expect: it passes over the new keys (§15.4) and accepts it.
  dry run: n/a.
- id: `check-04`
  story: As the operator, I sign the text I approve.
  setup: the PR body.
  steps:
    1. Read the body's §31 section.
  expect: each changed SPEC and contract passage is quoted with its CURRENT and PROPOSED text.
  dry run: n/a.
- id: `check-05`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 — implementer: a check may carry `as_written: false` with `held_instead` and `ruling`
  (contract and example, record version 3 → 4). `ccp verify record` refuses one on a check not run,
  without `held_instead`, without `ruling`, or with a ruling not in the form `rests_on` accepts
  (`verify.as_written_errors`, the write path only, as `rests_on_errors` is), naming the check; the pass
  rules are unchanged, so it is still a pass or a fail. `ccp tasks close` prints the list on stderr just
  before `_merge` (`verify.not_as_written`, `lifecycle._print_not_as_written`) and never refuses on it; a
  re-run of close after the merge prints nothing, as it merges nothing. §15.4 gains the paragraph from
  Scope; the verify template, the verifier and the runner brief say when to use it and to pass the list on.
- Open: check-01 expects the refused copies to exit 2; `ccp verify record` refuses every record with exit 1
  (§10.6: 1 is check failures), and these refusals keep that. Flagged to the runner.
- Not built (beyond Scope): a refusal of `held_instead` or `ruling` on a check that is not `as_written: false`.
- 2026-11-17 — implementer, ruling round 1: the open point above is settled by spec question
  sm-20261117T013234Z-3736 (lead's answer, commit 4d46bf63bdf4429d2def60cd73c49dde5289e01b): exit 1 stays
  as built, and check-01's "refused (exit 2)" is read as exit 1 for each refused record copy; the verifier
  judges it so. The check text is left as written (SPEC §10.5, a claimed task). No SPEC, code or test change.

## Verification notes
