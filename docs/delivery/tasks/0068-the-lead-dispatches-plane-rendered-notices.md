---
task_id: 0068-the-lead-dispatches-plane-rendered-notices
title: The lead dispatches the operator's notices, rendered and recorded by the plane, over a configured channel
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S8", "S17"]
review_point: R4
paths: ["ccp/notify.py", "ccp/cli.py", "docs/spec/01-model.md", "docs/adr/", "plugin/orientation.md", "plugin/skills/spec-maintainer/", "plugin/agents/delivery-runner.md", "contracts/", "docs/cli/", "tests/test_notify*.py"]
created: 2026-11-11
updated: 2026-11-11
---

# Task: 0068-the-lead-dispatches-plane-rendered-notices

## Intent

The operator hears from the lead when their attention is needed, over whatever channel their setup
has, and every notice looks the same and is on record: the plane owns the trigger, the content and
the record; the lead dispatches; the channel is configuration.

## Context (not checked)

- Today §3.6 lets only `ccp` send, through `notify.command`, a shell command; ADR-0037 D2 says no seat
  sends email itself. A channel that exists only as a tool in a Claude session (an MCP mail or chat
  server) cannot be called from a shell, so a product with one cannot use `notify.command`, and its
  lead had to override the plane to reach the operator.
- The rule that the design seat never emails dates from when the design seat only ruled spec
  questions; the lead is now the session leading delivery and the operator's only route.
- Operator ruling, 2026-11-11 (the lead session), on a managed product's proposal: "agree with
  proposed shape" for "the plane owns the trigger, the content and the record; the lead dispatches;
  the channel is configuration". Also: the four §3.6 triggers stay as they are, `review_point_done`
  included; repeated sends are left as they are for now; and "I do want the lead to be able to send
  messages if something unexpected shows up, so the option to send on its own judgment should stay."
- §31: this changes § rules (§3.6, §17) and amends ADR-0037 D2. The operator approved the shape above;
  the merge waits on their approval of the final text at the merge gate.

## Scope

- **In:**
  - `ccp notify render <trigger> [--task ID] [--id ID] [--reason R]` prints the notice for a §3.6
    trigger: a subject and a body built from the trigger, the project, the ids, the reason and a
    link-free summary line; never a brief, question text or file content. `--json` gives the same as
    an object.
  - `ccp notify sent <trigger> [--task ID] [--id ID] --via command|lead [--note TEXT]` records a sent
    notice in the ledger (`notify` `sent` event: trigger, ids, via, by). A notice the lead sends on
    its own judgment is recorded with trigger `other` and a one-line `--note` (no content beyond it).
  - plane.json `notify` gains `channels`: `command` (today's `notify.command`, run by `ccp`
    unattended, as now) and/or `lead` (the lead sends the rendered notice with a tool from its own
    session; `notify.lead.tool` names the tool and `notify.lead.to` the recipient, both strings the
    product sets). With no `lead` channel the lead does not send; with no channel at all, the lead's
    session is the route, as today. `ccp` records the `command` sends itself.
  - The runner raises each trigger to the lead (as today); with a `lead` channel the lead renders,
    sends and records it. The lead may also send on its own judgment, rendered with trigger `other`.
    The runner and workers never send.
  - §3.6 states this; §17.10 and §8.1 match; ADR-0037 D2 is amended (a new decision, or a superseding
    ADR) to "only the lead sends, a plane-rendered notice, over a configured channel"; the
    spec-maintainer skill's "Email anyone" line and the orientation's no-email lines match.
- **Out:** shipping any mail or chat client; changing the four triggers or how often they repeat.

## dod_checks

- id: `check-01`
  story: As the lead, I get the exact notice to send.
  setup: a scratch product with a `lead` channel in plane.json.
  steps:
    1. Run `ccp notify render decision --task 0001-x --id 0001-x-1`.
  expect: a subject and body naming the trigger, project, task and gate id; no brief or file content.
  dry run: n/a — the command does not exist yet.
- id: `check-02`
  story: As the operator, every notice is on record.
  setup: as check-01.
  steps:
    1. Run `ccp notify sent decision --task 0001-x --id 0001-x-1 --via lead`, then
       `ccp notify sent other --via lead --note "unexpected outage"`.
  expect: two `notify` `sent` events in the ledger with those fields; a `command` channel's send is
    recorded by `ccp` itself.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, the rule reads one way everywhere.
  setup: a checkout of the PR head.
  steps:
    1. `git grep -n -i 'email' -- docs/spec plugin docs/adr` and read each hit.
  expect: no passage says no seat or the lead never emails; each says the lead sends rendered notices
    over a configured channel, and the runner and workers never do.
  dry run: on the merge base, ADR-0037 D2 and the spec-maintainer skill say no seat emails.
- id: `check-04`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, `ccp adr check`, then
       `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
