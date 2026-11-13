---
task_id: 0075-spawn-dry-run-and-orientation-command
title: A lead can check a runner spawn without starting it, and see the orientation mid-session
status: done
kind: feature
depends_on: []
spec_refs: ["S9", "S16"]
review_point: R5
paths: ["scripts/observability/team.py", "scripts/team.sh", "ccp/cli.py", "plugin/orientation.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "tests/test_team*.py", "tests/test_orientation*.py"]
created: 2026-11-12
updated: 2026-11-13
---

# Task: 0075-spawn-dry-run-and-orientation-command

## Intent

A lead can see the Agent call a spawn would make, and its readiness checks, without writing anything (§16), and a session that adopted the product after it started can print the orientation it never received (§9).

## Context (not checked)

- Accepted plane proposal from an adoption trial: checking a spawn today is spawning, after which the idle hook acts on it; and every first adoption happens in a session the orientation never reached.
- Ruling round 1 (lead, on spec question sm-20261113T181606Z-478d, spec commit c92d947), verbatim:
  "The readiness checks are the ones a real spawn makes before writing (§10.2 step 1), reported
  instead of acted on. Every scope task exists in the task log, ccp tasks check is clean, and the
  runner worktree is a working tree or can be made; keep the task-log-readable check. Standing
  approvals are reported only to the extent a real spawn checks them mechanically; invent no new
  check. The exit code is 0 when every check passes and 1 when any fails, with the failing checks
  named, so the adoption checklist and scripts can use it. A dry run writes nothing. ccp orientation
  printing the hook's line is right. The SPEC text is accepted through this ruling (standing DoD item
  2: text from the task or a ruling): the §9.3 bullet and §16.5 paragraph, adjusted to the exit codes
  above, describing only the feature (§31.1). The docs/cli rows are accepted; list them as outside
  the declared paths. Record this ruling in 0075's Context with a ruling round, then review."

## Scope

- **In:** `team.sh runner spawn --dry-run` prints the spawn's actions and readiness checks and writes neither `work.json` nor the prompt audit; `ccp orientation` prints the plugin's orientation for the bound product; §9 and §16 name both.
- **Out:** changing the orientation's content.

## dod_checks

- id: `check-01`
  story: As a lead, a dry run writes nothing.
  setup: a scratch product ready to spawn.
  steps:
    1. Run `team.sh runner spawn --dry-run --scope <id>`.
    2. Compare `work.json` and `prompts/` before and after.
  expect: the output carries the spawn action; neither file changed.
  dry run: on the merge base the flag is refused.
- id: `check-02`
  story: As a lead adopting mid-session, I can read the orientation.
  setup: a scratch product with `plane.json`.
  steps:
    1. Run `ccp orientation`.
  expect: it prints the orientation text.
  dry run: on the merge base the command does not exist.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-13 — `team.sh runner spawn --dry-run` (`scripts/observability/team.py`, one runner and
  slots) runs every refusal the spawn runs, then returns before the worktree, the prompt audit, the
  ledger and `work.json`. It prints `outcome: dry_run`, `dry_run: true`, the actions the spawn would
  print (a live runner's `shutdown_teammate` first, `would_stop`; the spawn prompt is the real
  one), and `checks`: the §10.2 readiness a machine can answer (`scope_tasks_exist`, `tasks_check`,
  the one runner's `runner_worktree`, or `task_log` when the log does not read) with `ready`. Exit 0
  either way. Standing approvals are not checked: they live in plan prose (E6). `--dry-run` with
  another runner op is refused (exit 2). `ccp orientation` (`ccp/cli.py`) runs the plugin's
  SessionStart hook from `ccp`'s own checkout for this product root and prints its text, so the
  text and where it applies (the plane's own repo gets the one line) stay in one place. SPEC §9.3
  and §16.5 name both; `docs/cli` lists them; the orientation's header comment names the command,
  and its content is unchanged.
- 2026-11-13 — Ruling round 1: the dry run exits 0 when every readiness check passes and 1 when any
  fails (was 0 either way), so the adoption checklist and scripts can branch on it. A failing run
  names the failing checks in a `failed` list in its output and on stderr (`not ready: <checks>
  failed`); a refusal still exits as the spawn would (2). The checks themselves are unchanged (no
  standing-approval check: a real spawn checks none mechanically). SPEC §16.5's paragraph, the
  `docs/cli` row, `team.sh`'s usage and the flag's help say the exit codes. `docs/cli/01-model.md`
  and `docs/cli/02-delivery.md` are outside the declared paths; the ruling accepts their rows.

## Verification notes

- 2026-11-13 — verifier, PR #98 head `8a02dfb` (squash `a8db574`): APPROVE. Passed: check-01, check-02, check-03. Gate: `bash scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0075-spawn-dry-run-and-orientation-command.json.
