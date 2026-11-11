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
  - **Firing.** When a §3.6 trigger fires, `ccp` writes a `notify` `pending` event to the ledger
    (trigger, project, task, id, reason) and prints the rendered notice on stderr with the channel to
    use. The runner's message to the lead names the trigger, as today. `ccp notify pending` lists
    every pending notice with no matching `sent` event, so a trigger that fired while the lead was idle
    is still found.
  - **Content.** `ccp notify render <trigger> [--task ID] [--id ID] [--reason R] [--json]`, with
    `<trigger>` one of the four §3.6 triggers or `other`, prints a subject
    (`[<project_id>] <trigger>: <task or id>`) and a body (one line each for project, trigger, task,
    id and reason, those given), and nothing else: never a brief, question text or file content.
  - **Record.** `ccp notify sent <trigger> [--task ID] [--id ID] --via command|lead [--note TEXT]`
    writes a `notify` `sent` event (trigger, ids, via, `by`: the seat that ran it, `ok`). A `command`
    send is recorded by `ccp` itself with `ok: true` or `ok: false` (failed or timed out), and a
    failure stays a warning on the step. A notice the lead sends on its own judgment is trigger
    `other` with a one-line `--note` (ids and a short reason, no content). The ledger event schema in
    `contracts/` gains the two events.
  - **Channels.** plane.json `notify.command` and `notify.timeout_seconds` stay as they are (the
    unattended channel `ccp` runs). A new optional `notify.lead` object, with `tool` and `to` (both
    non-empty strings the product sets), declares that the lead sends with that tool from its own
    session. Config validation refuses `notify.lead` without both keys, or with other keys. With
    neither, the lead's session is the route, as today. Existing plane.json files are unchanged.
  - **Seats.** With a `lead` channel the lead renders, sends and records each pending notice; it may
    also send on its own judgment (trigger `other`). The runner and workers never send: their briefs
    say so, and `ccp notify sent --via lead` records the seat it was run as (`by`).
  - **Text.** §3.6 states this; §17.10 and §8.1 match; ADR-0037 D2 is amended (a new decision, or a
    superseding ADR) to "only the lead sends, a plane-rendered notice, over a configured channel"; the
    spec-maintainer skill's "Email anyone" line, the orientation's no-email lines and the runner brief
    match.
- **Out:** shipping any mail or chat client; changing the four triggers or how often they repeat.

## dod_checks

- id: `check-01`
  story: As the lead, I get the exact notice to send.
  setup: a scratch product with a `lead` channel in plane.json.
  steps:
    1. Run `ccp notify render decision --task 0001-x --id 0001-x-1`.
  expect: the subject is `[<project_id>] decision: 0001-x`; the body has one line each for project,
    trigger, task and id; `--json` gives the same keys; nothing else is printed.
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
- id: `check-05`
  story: As the lead, a trigger that fired while I was idle is not lost.
  setup: a scratch product with a `lead` channel; a task waiting on `operator_decision` (fires
    `decision`).
  steps:
    1. Run `ccp notify pending`.
    2. Run `ccp notify sent decision --task <id> --via lead`, then `ccp notify pending` again.
  expect: the first lists the `decision` notice; after the send it lists none.
  dry run: n/a.
- id: `check-06`
  story: As a product, a malformed lead channel is refused.
  setup: plane.json with `notify.lead: {"tool": "x"}` (no `to`), then with an unknown key.
  steps:
    1. Run `ccp tasks check` under each.
  expect: each is refused, naming `notify.lead`; plane.json with only `notify.command` still loads.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, the rule reads one way everywhere.
  setup: a checkout of the PR head.
  steps:
    1. Read ADR-0037 D2, §3.6, §8.1, §17.10, the spec-maintainer skill's "What you never do" list,
       `plugin/orientation.md` and the runner brief.
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
