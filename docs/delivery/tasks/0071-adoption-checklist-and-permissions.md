---
task_id: 0071-adoption-checklist-and-permissions
title: An adopting lead sees every plane.json feature it may need, and the operator gets a ready permission list
status: pending
kind: feature
depends_on: []
spec_refs: ["S4", "S8", "S18"]
review_point: R5
paths: ["README.md", "ccp/init.py", "ccp/cli.py", "templates/", "docs/spec/01-model.md", "tests/test_init*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0071-adoption-checklist-and-permissions

## Intent

A lead adopting the plane on a product learns, in one place, every `plane.json` feature a real product needs and when it needs it (§4.5, §8.1), and the operator gets the runner's and workers' permission allowlist ready to apply (§18.5), instead of discovering each by incident.

## Context (not checked)

- Accepted plane proposals from a managed product's adoption trial: the quick start goes from `ccp init` straight to tasks, so a fresh lead missed env hooks, the allowance checkpoint, auth probes and exclusive paths; and §18.5 makes a runner allowlist mandatory while each product reconstructs it from the briefs.
- Claude Code's auto mode refuses a lead's own edit to `.claude/settings.json` as self-modification, so the operator applies the permission list.

## Scope

- **In:** a one-screen adoption checklist in the README (each `plane.json` key a product may need: env hooks, telemetry and the allowance checkpoint, `auth_check` probes, `parallel.exclusive`, `merge.behind_tip_ignore`, `reconcile.log`, `notify`, starter rules, `architect.checks`, `verify.accept_cache`, `mutate.command`, `report.required_fields`: what it is for and when a product needs it); `ccp init --permissions` prints the runner and worker allowlist (`ccp`, `team.sh` and `spec-maintainer-ask.sh` by absolute path, git by verb, `gh pr`, the product's gate lane commands) and a deny list for destructive commands, as a JSON block for the operator to apply, writing nothing; the README says the operator applies it; §4.5 names both.
- **Out:** an interactive init; applying the permissions automatically.

## dod_checks

- id: `check-01`
  story: As an adopting lead, I find every feature a product needs.
  setup: a checkout of the PR head.
  steps:
    1. Read the README's adoption checklist.
  expect: it names each key listed in Scope, with its purpose and when a product needs it.
  dry run: on the merge base there is no such checklist.
- id: `check-02`
  story: As the operator, I get the permission list to apply.
  setup: a scratch product adopted with `ccp init`.
  steps:
    1. Run `ccp init --permissions`.
  expect: it prints a JSON `permissions` block with the allow and deny lists, using absolute plane paths and the product's gate lane commands, and changes no file.
  dry run: on the merge base the flag is refused.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12: The README has an adoption checklist under step 2, a table of the twelve Scope keys with what each is for and when a product needs it, and a Permissions part that says the operator applies the block. `ccp init --permissions` (`ccp/init.py` `permissions`, `print_permissions`) prints `{"permissions": {"allow": [...], "deny": [...]}}` and writes nothing. Allowed: `ccp` by name (§4.3: "the allowlist names `ccp`, not a path") and the plane's `team.sh` and `spec-maintainer-ask.sh` by absolute path, each also behind `QUEUE_ROOT=<the binding's queue>` because the seats run them that way; git by verb (`GIT_VERBS`); `gh pr`; the gate lane's argv, or each stage's `cmd`. Denied: `DENY` (force pushes, `reset --hard`, `clean`, `branch -D`, `stash`, `checkout --`, `restore`, `rm -rf`, `gh repo delete`). It refuses (exit 2) another init flag, a product whose `plane.json` is missing or does not load, and a product with no binding and queue. §4.5 names both. The `ccp init` usage line, the flag's help and the `docs/cli/01-model.md` reference row (outside `paths`) name the flag. Tests: `tests/test_init_permissions.py`.

## Verification notes

*Append-only.*
