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
- 2026-11-10 — implementer, fix round 1 (review of PR #43). The command now reads an empty stdin
  (`wt.run_cmd(..., no_stdin=True)`, a new keyword; other callers unchanged): a channel such as `mail`
  that reads its body from stdin would otherwise wait on `ccp`'s own stdin until the timeout and the
  notice would be lost. A close also sends `review_point_done` on the retry that records the task
  done after a close that crashed between its reconcile commit and the queue's record (`reconciled`
  but the queue's status not yet `done`); a re-run that finds both done still sends nothing. §3.6
  now says the command runs with an empty stdin in the checkout the call came from, as reconcile
  hooks do (the binding's product root for a gate or a spec question), not "the product root"; and
  that each trigger sends once per call, so a repeated wait, `gate ask-operator` or refused claim
  sends again. A test pins that a claim refused at the checkpoint with no channel runs nothing and
  its refusal carries no `notify:` warning. Left for the lead: §19, `plugin/orientation.md`,
  ADR-0004 D5 and ADR-0034 still say nothing emails (review MINOR-4).
- 2026-11-10 — implementer, fix round 2 (lead's direction on the review and verify of PR #43). The
  leftover "nothing emails" statements now point to §3.6 (the plane's triggers, the product's
  channel): §19 in `docs/spec/03-quality.md`, the §9.3 orientation bullet in `docs/spec/01-model.md`,
  `plugin/orientation.md`, and a code comment in `scripts/observability/architecture_review.py` and
  `tests/test_architect.py`. A new ADR-0037 (status proposed; the approval of this task's PR accepts
  it) records the change: its D2 supersedes ADR-0004 D5 (`ccp adr supersede 0004 0037 --decisions D5
  --by D2`, so D5 is retired) and amends ADR-0034 D13, whose body now notes it. The worker prompt's
  "No email" (`templates/prompts/_common.md`) is a worker's rule, not the operator's channel, and
  stays. Two guards are now pinned: a `ccp tasks resume` named for an operator wait sends nothing
  (`action == "set"`), and a `process` that reaches a `needs_operator` answer its event log already
  holds sends no second decision (`not already`). Outside the declared paths: `docs/adr/`,
  `docs/spec/03-quality.md`, `scripts/observability/architecture_review.py`, `tests/test_architect.py`.

## Verification notes

*Append-only.*
