---
task_id: 0077-adr-the-pr-host-is-an-adapter
title: ADR: the PR host is an adapter; until then a GitHub origin is stated as required
status: pending
kind: docs
depends_on: []
spec_refs: ["S10", "S29"]
review_point: R5
paths: ["docs/adr/", "README.md", "ccp/init.py", "tests/test_init*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0077-adr-the-pr-host-is-an-adapter

## Intent

The plane's dependence on GitHub for pull requests is stated up front now, and the design for working with any git remote is written down as a proposed ADR for the operator to decide (§10.5, §29).

## Context (not checked)

- Accepted plane proposal, as a design item: claim, worktrees and the reconcile push need only an origin, but `merge-ok`, the default merge, close's merge confirmation and the implementer's PR are GitHub-only, and nothing says so. The acceptance says an ADR the operator approves comes first, then tasks.
- §31: this task adds or changes a § rule beyond describing its own feature, so its merge waits on the operator's approval of the final text at its merge gate (§31.1). The ADR is accepted only by the operator's approval at that gate.

## Scope

- **In:** a proposed ADR (status `proposed`, deciders operator) describing the PR host as an adapter: GitHub (today's), a local mode in which the plane keeps the PR record (branch, head, review state) and merges with git, and GitLab/Gitea later; which commands each adapter serves; how a product selects one; what stays forge-independent; the README's prerequisites and `ccp init` state now that a GitHub origin and a logged-in `gh` are required, and `ccp init` warns when the origin is not on GitHub.
- **Out:** building any adapter (later tasks, once the ADR is accepted).

## dod_checks

- id: `check-01`
  story: As an adopting lead, I learn GitHub is required before I start.
  setup: a scratch product whose origin is a local bare repository.
  steps:
    1. Run `ccp init`.
  expect: it warns that pull requests need a GitHub origin and names the commands affected.
  dry run: on the merge base it says nothing.
- id: `check-02`
  story: As the operator, the adapter design is written for me to decide.
  setup: a checkout of the PR head.
  steps:
    1. Read the new ADR and run `ccp adr check`.
  expect: the ADR is `proposed`, names the three adapters and the commands each serves; `ccp adr check` passes.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12 (implementer): ADR-0040 "The PR host is an adapter" is written `proposed`, deciders
  operator: D1 the interface (open, view, diff, merge pinned to a head, confirm, through `ccp pr`),
  D2 GitHub (today's), D3 local (the plane keeps the PR record in the queue and merges with git),
  D4 GitLab and Gitea later, D5 selection by `plane.json` `pr_host.adapter` (default `github`), D6
  what stays forge-independent, D7 the GitHub requirement stated until then. `ccp init` warns on
  stderr and in its result's `warnings` when `origin` is missing, local or on a host that is not
  `github.com` or a subdomain of it, naming `ccp verify merge-ok`, `ccp tasks close` and the
  workers' `gh pr` steps; only the host is printed, never the URL. The README's prerequisites state
  the requirement. SPEC §4.5 is not changed: the task gives no SPEC text and its paths exclude
  `docs/spec/` (flagged in the report). A GitHub Enterprise host is warned about as not GitHub.

## Verification notes

*Append-only.*
