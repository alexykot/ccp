---
task_id: 0040-operator-notification-triggers
title: The plane defines when the operator is notified; a product setting names the channel
status: pending
kind: feature
depends_on: [0039-operator-sign-off-record]
spec_refs: ["S3", "S17"]
review_point: R3
paths: ["docs/spec/01-model.md", "docs/spec/02-delivery.md", "ccp/notify.py", "ccp/lifecycle.py", "plugin/", "tests/test_notify*.py"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0040-operator-notification-triggers

## Intent

The plane defines when the lead must notify the operator (a blocker, a decision needed, a review point done, an allowance checkpoint), and a product setting gives the channel (the interactive session by default; email, a chat message or another command when configured). The blanket rule that nothing emails is replaced by this.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §3 and §17.
- Every operator needs to hear about blockers and decisions; how depends on the operator's setup, not the plane.
- Today the SPEC says nothing emails (§1, §8, §17), so a product that wants another channel overrides a plane rule.
- **SPEC change (§31):** this task changes a § rule — the no-email statements in §1, §8 and §17 and the operator channel in §3. It needs the operator's approval at build: the PR carries the CURRENT → PROPOSED text and quotes the ruling.

## Scope

- **In:** §3 and §17 list the triggers; a `notify` block in the binding or `plane.json` names a channel command (default: the lead's session, as today); `ccp` calls it with the trigger and ids only on each trigger; the no-email statements in §1, §8 and §17 are rewritten.
- **Out:** shipping an email or chat client; message content beyond trigger, ids and a link.

## dod_checks

- id: `check-01`
  story: As an operator, a blocker reaches my channel.
  setup: a scratch product whose notify command appends to a file.
  steps:
    1. Raise a blocker.
  expect: the file gets one line naming the trigger and the task id.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As an operator with no channel set, nothing changes.
  setup: no notify block.
  steps:
    1. Raise a blocker.
  expect: it is raised in the lead's session as today; no command runs.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 — implementer. The channel is plane.json `notify` (`command`, a shell command, default
  null; `timeout_seconds`, default 30; `ccp/config.py`, `contracts/plane_config.schema.json`), beside
  the other product commands, not the binding. `ccp/notify.py` runs it in the product root on each
  trigger (`wt.run_cmd`: own process group, killed at the timeout), with the trigger and ids only in
  its environment: `CCP_NOTIFY_TRIGGER`, `CCP_PROJECT_ID`, `CCP_TASK_ID`, `CCP_NOTIFY_ID`,
  `CCP_NOTIFY_REASON` and all of them as one line, `CCP_NOTIFY_LINE`. No link: the plane has no
  stable URL to give. Best effort: a failure or timeout is a `notify:` warning on the step, never a
  refusal. The triggers and where they fire: `blocker`, `ccp tasks wait` on `reauth` or
  `operator_step`; `decision`, `ccp tasks wait` on `operator_decision`, `team.sh gate ask-operator`
  (`scripts/observability/team.py`) and a `needs_operator` answer the first time `process` applies it
  (`scripts/observability/spec_maintainer.py`); `review_point_done`, the `ccp tasks close` that
  reconciles the last open task carrying its review point (not a re-run); `allowance_checkpoint`, a
  claim refused at a weekly checkpoint (exit 5), once per refused claim. Other waits (quota, the
  lead's gates and questions) are not triggers. No event is recorded for a send. SPEC: a new §3.6 and
  edits to §2.2, §3.1, §8.1, §8.3, §9.3, §17.1 and §17.10; the text is the implementer's draft and
  needs the operator's approval (§31). Outside the declared paths: `ccp/config.py`, the contract,
  `scripts/observability/team.py` and `spec_maintainer.py`, `docs/cli/02-delivery.md`, `ccp/CLAUDE.md`.
  Tests: `tests/test_notify.py`.

## Verification notes

*Append-only.*
