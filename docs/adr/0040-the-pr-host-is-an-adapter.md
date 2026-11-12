---
id: ADR-0040
title: "The PR host is an adapter"
status: accepted
date: "2026-11-12"
deciders: operator
spec_refs: [S10, S15, S29]
notes: |-
  Proposed with task 0077, from an accepted plane proposal taken as a design item: the operator
  decides it; the tasks that build its adapters follow its acceptance.
  2026-11-12: status proposed → accepted: Accepted by the operator at gate 0077-adr-the-pr-host-is-an-adapter-1 (2026-11-12, in the lead session: 'approve ADR-0040 and 0077's section 4.5 change'). Its decisions stay not_built until the adapter tasks build them.
decisions:
  - "D1 not_built"
  - "D2 not_built"
  - "D3 not_built"
  - "D4 not_built"
  - "D5 not_built"
  - "D6 not_built"
  - "D7 not_built"
---
# ADR-0040 — The PR host is an adapter

## Context

The plane delivers every task as a pull request, and today only GitHub hosts one. Claim, the
worktrees and the reconcile push need nothing but a git `origin` (SPEC §10.5, §12). Four steps go
through the GitHub CLI, `gh`:

- the implementer opens its PR with `gh pr create`, and the reviewer and verifier read it with
  `gh pr diff` and `gh pr view`;
- `ccp verify merge-ok` reads the PR's state and head with `gh pr view` (§15.5);
- the default merge of `ccp tasks close` is `gh pr merge --squash --match-head-commit` (§15.5);
- close confirms the merge, and finds the merge commit, with `gh pr view` (§10.5, §15.5).

ADR-0029 D3's repository settings (`ccp repo check|apply`) would read a hosting service's API too.
Nothing said so up front: a product whose origin is a bare repository, a GitLab or a Gitea server
would adopt cleanly and fail at its first close. `merge.command` (§15.5) replaces the merge but not
`merge-ok`, the confirmation or the workers' `gh` steps, so it does not lift the dependency.

## Decision

### D1. One PR-host interface

The plane reaches the PR host only through one interface with five operations: **open** a PR for a
pushed task branch, **view** it (number, state, head, merge commit), **diff** it against its base,
**merge** it pinned to a head, and **confirm** a merge. The plane's commands and the worker prompts
call it through `ccp pr open|view|diff|merge`, never a forge's CLI directly, so a prompt reads the
same whatever the host. `merge-ok` (view), close's merge (merge) and its confirmation (confirm),
review (diff), verify (view) and the implementer's PR (open) are its callers.

### D2. The GitHub adapter

The GitHub adapter is today's behaviour behind the interface: open is `gh pr create`, view and
confirm are `gh pr view`, diff is `gh pr diff`, merge is `gh pr merge --squash
--match-head-commit <head>`. It serves ADR-0029 D3's repository settings too. It needs a GitHub
origin and a logged-in `gh`, and it is the default.

### D3. The local adapter

In the local adapter the plane keeps the PR record itself, in the queue: a number the plane gives,
the branch, its base, the head it last saw, its state, the review state (the verification and
review records already bound to a head, §15) and, once merged, the merge commit. Open records the
pushed branch; view reads the head from `origin/<branch>`; diff is `git diff
origin/<base>...<head>`; merge squashes the branch onto the integration tip in close's merge
worktree, refusing a branch whose head is not the verified one, commits it with the subject
`Task <NNNN>: <title> (#<n>)` (§10.7 rule 1) and pushes it; confirm finds that commit on
`origin/<base>`. It needs only a git origin the plane can push to, a bare repository included, and
it serves no repository settings.

### D4. GitLab and Gitea later

GitLab and Gitea adapters come later, each serving the five operations through its own API or CLI:
its merge request or pull request number as the PR number, its merge call pinned to the head sha,
and its repository settings where ADR-0029 D3 asks for them. Neither is built with the interface.

### D5. A product selects its adapter

A product names its adapter in `plane.json` as `pr_host.adapter`: `github` (the default, so a
product that names none keeps today's behaviour), `local`, and later `gitlab` or `gitea`.
`merge.command` stays an override of the merge operation under any adapter. `ccp init` warns when
the origin does not suit the adapter, naming the commands affected; a probe for the adapter's login
belongs in `auth_check.probes` (§30.1).

### D6. What stays forge-independent

The task lifecycle (§10), claim and the lease, the worktrees (§12), the branches and their push, the
reconcile and its push, the verification records and their head binding (§15), the merge and verify
rules (§15.6), sign-offs, gates, the ledger and the board never call the host: they see a PR only as
its number and head, which the interface gives them.

### D7. Until then, a GitHub origin is required and stated

Until an adapter other than GitHub is built, the README's prerequisites state that a GitHub origin
and a logged-in `gh` are required, and `ccp init` warns when the product's origin is missing or not
on GitHub, naming the commands that need it. The warning does not stop the adoption.

## Consequences

- A product without GitHub can run the whole loop once the local adapter is built, and a forge
  adapter is added without touching the lifecycle.
- The worker prompts and the runner's brief change once, from `gh pr` to `ccp pr`; that is a change
  to the runner's contract, so its release is followed by a runner rotation (§29.3).
- §10.5 and §15.5 name the interface's operations instead of `gh`; `ccp init --permissions` allows
  `ccp pr` and, for the GitHub adapter, keeps `gh pr`.
- In local mode nothing outside the plane shows the PR: its record lives only in the product's queue,
  and its review happens in the plane's records, not on a web page.
- Until D2 to D6 are built, adopting a product needs GitHub, and the plane says so before the first
  task rather than at the first close.
