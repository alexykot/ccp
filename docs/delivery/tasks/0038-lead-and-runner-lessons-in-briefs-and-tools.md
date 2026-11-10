---
task_id: 0038-lead-and-runner-lessons-in-briefs-and-tools
title: Lead and runner lessons go into the plane's briefs and tools
status: done
kind: feature
depends_on: []
spec_refs: ["S2", "S13", "S16"]
review_point: R3
paths: ["plugin/", "scripts/team.sh", "scripts/observability/", "docs/spec/02-delivery.md", "tests/test_team*.py", "tests/test_plugin.py"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0038-lead-and-runner-lessons-in-briefs-and-tools

## Intent

Behaviours every product's lead and runner meet become plane rules and tool behaviour: subagents run long commands in the foreground (an agent waiting on a background command stalls); `team.sh` runner spawn shuts the old runner down first; the lead directs runners with `ccp tasks prefer`, never a message (a message races the claim); after an interrupted command, check git, the store and the ledger before reporting it did nothing.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §2 and §13 and §16.
- These are properties of the plane's team model and the agent harness, not of any product; today they live in one product's lead memory.

## Scope

- **In:** `scripts/team.sh` spawn stops a running runner before starting the new one; the runner, worker and orientation briefs state the foreground, prefer and interrupted-command rules; §16 notes the single-runner spawn.
- **Out:** a watchdog seat.

## dod_checks

- id: `check-01`
  story: As a lead, spawning a runner replaces the old one.
  setup: a fake team with a runner running.
  steps:
    1. Run `team.sh` runner spawn.
  expect: the old runner is stopped before the new one starts; only one is left.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a plane developer, the briefs state the rules.
  setup: the PR head.
  steps:
    1. Run the plugin tests.
  expect: each rule is found in its brief.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): single-runner `team.sh runner spawn` treats the runner as live when
  `work.json` `status` is `running` or `draining` and it was not rotated since its spawn (a rotation
  already printed its shutdown). Then it emits `runner`/`stop` (`reason: respawn`) before
  `runner`/`spawn`, puts a `shutdown_teammate` action for the bound name ahead of `spawn_teammate`,
  and returns `stopped: <name>`. `spawn --slot` (several runners) is unchanged: §16.5 already
  respawns no live slot on `--count`. §16.5 gains one descriptive sentence (§31.1, the task's own
  feature).
- 2026-11-10 (implementer): the foreground rule (with its reason) and the interrupted-command rule are
  in the orientation, the runner and the three worker briefs; the prefer rule's reason ("races the
  claim") is in the orientation and the runner brief, not the workers', which never direct a runner.
  §13.1 is not changed: the task gives no text for it.

## Verification notes

- 2026-11-10 — verifier, PR #37 head `cd04b9f` (squash `c986e3a`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0038-lead-and-runner-lessons-in-briefs-and-tools.json.
