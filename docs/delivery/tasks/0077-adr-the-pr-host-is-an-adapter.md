---
task_id: 0077-adr-the-pr-host-is-an-adapter
title: ADR: the PR host is an adapter; until then a GitHub origin is stated as required
status: done
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
- Ruling sm-20261112T124326Z-da68 (lead): add a sentence to SPEC 4.5 (Adopting a product,
  docs/spec/01-model.md) in this PR: ccp init warns when the product has no origin or its origin is
  not GitHub, since review, merge and close need a GitHub origin until ADR-0040's adapter exists.
  This is a section 31.1 text change describing the task's own feature, so no operator approval.
  Quote the new sentence in the PR body (and say it adds text, replacing none).
- Ruling, gate 0077-adr-the-pr-host-is-an-adapter-1 (operator, in the lead session, 2026-11-12:
  'approve ADR-0040 and 0077's section 4.5 change'): set ADR-0040 to accepted with
  `ccp adr status 40 accepted`, deciders staying operator, its decisions left not_built (no
  `ccp adr decide`); regenerate the ADR index; change nothing else. Update the PR body's line on the
  ADR status from proposed to accepted.

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
- 2026-11-12 (implementer, ruling round 1): per the lead's ruling sm-20261112T124326Z-da68, SPEC
  §4.5 gains one sentence after the paragraph on what init keeps and refuses: init warns, on stderr
  and in its result's `warnings`, when the product has no `origin` or its origin is not on GitHub,
  and adopts it all the same, because review, merge and close need a GitHub origin until ADR-0040's
  adapter exists. It adds text and replaces none (§31.1: it describes this task's own feature). The
  frontmatter `paths` is left as written (it does not list `docs/spec/`); code and tests are
  unchanged, as the ruling asks only for the SPEC text.
- 2026-11-12 (implementer, ruling round 2): the operator approved ADR-0040 and the §4.5 sentence
  at gate 0077-adr-the-pr-host-is-an-adapter-1, so ADR-0040 is set `accepted` with
  `ccp adr status` (the note cites the gate), deciders operator. The command wrote its decisions
  D1-D7 as `not_built` and updated the ADR index; none is decided, as nothing is built yet.
  check-02's "the ADR is `proposed`" described the PR before the gate; the ruling supersedes it
  (flagged in the report). Code, tests and SPEC are unchanged.

## Verification notes

- 2026-11-12 — verifier, PR #81 head `560bfc4` (squash `5a09f42`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0077-adr-the-pr-host-is-an-adapter.json.
