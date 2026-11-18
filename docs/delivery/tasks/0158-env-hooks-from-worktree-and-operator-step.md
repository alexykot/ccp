---
task_id: 0158-env-hooks-from-worktree-and-operator-step
title: A worktree can run its own env hooks, and the runner doc names the operator gate class
status: done
kind: feature
depends_on: []
spec_refs: ["S12", "S15", "S17"]
review_point: R10
paths: ["ccp/wt.py", "ccp/cli.py", "contracts/worktree.schema.json", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "templates/prompts/verify.md", "plugin/agents/delivery-runner.md", "plugin/agents/delivery-verifier.md", "tests/test_wt.py", "tests/test_prompt*.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0158-env-hooks-from-worktree-and-operator-step
## Intent

A verifier judging a PR that changes the product's env hooks (plane.json `env`) or the scripts they
call can make its worktree with the PR's own hooks and exercise the change before it merges, instead
of deferring the check to an operator step after the merge. A runner opening a gate for an operator
step finds the gate class named in its doc.

## Context (not checked)

- Hooks come from the caller's plane.json: `hook` in `ccp/wt.py` reads `cfg.env`, `cfg` loaded from the
  checkout `ccp` runs in (`--root`, else the working directory), and runs the command with the
  worktree as its working directory. A hook that names its script through `{main_checkout}`, or a
  caller in another checkout, runs a script that is not the PR's. Seen in an adopting product: a PR
  changed its env script and the hook's flags together; the verifier's `ccp wt create --kind ver`
  failed with the older script refusing the new flag, and the check was deferred past the merge.
- Making it the default to read each worktree's own plane.json would change every existing product's
  hooks and break the fenced tests that set hooks in the main checkout's plane.json without committing
  it (`git grep -n 'self.plane(env=' -- tests/test_wt.py` at `85d388b`: 9 sites, besides the `made` helper's own call). So it is opt-in per
  worktree: `--own-hooks`.
- Running the PR's own hooks runs PR code; the verifier already runs PR code (the gate, its checks),
  in the same worktree, so the flag adds no new trust. It is the verifier's choice per PR, not a default.
- Gate class: `team.sh gate open` takes `operator` (`GATE_CLASSES` in `scripts/observability/team.py`;
  SPEC §17.9 lists the same classes). `operator_step` is a wait reason (`ccp tasks wait`, §2) and the
  verdict field naming the approved gate (§15.4), never a gate class. The runner doc's **Operator step.** item says
  "open a gate" and its Gates section gives `--class …`, naming no class: the docs, not the code, are
  short. The least change is the runner doc naming `--class operator`; `team.sh` is unchanged.
- A path to record a deferred check after close changes §15.4 (only `ccp verify record` writes the
  record) and is left to a signed task.
- §31.1: the §12.2 sentence below describes this task's own feature; no existing
  sentence changes meaning.

## Scope

- **In:**
  - `ccp/wt.py` and `ccp/cli.py` (the flag): `ccp wt create … --own-hooks` (any kind; refused with `--baseline`, exit 2) records
    `own_hooks: true`. For such a worktree every hook (`setup`, `teardown`, `up`, `down`, `urls`) and
    `env.timeout_seconds` come from the plane.json in the worktree itself (`docs/delivery/plane.json`
    under its path, loaded as `config.load` does), not the caller's. On `create`, a worktree plane.json
    that does not load fails the create like a failed setup (the worktree removed, exit 1, the load
    error shown). On `teardown` and `down`, one that does not load is a warning and the hook is skipped.
  - `contracts/worktree.schema.json`: `own_hooks` (boolean).
  - `docs/spec/02-delivery.md` §12.2, §31.1: one sentence: a worktree made with `--own-hooks` takes its
    hooks and their timeout from its own plane.json, so a hook naming its scripts relative to the
    worktree runs the head's own; `docs/cli/02-delivery.md`: the `ccp wt create` row gains
    `[--own-hooks]`.
  - `templates/prompts/verify.md` (the own-worktree sentence) and `plugin/agents/delivery-verifier.md`:
    one clause: when the PR changes plane.json `env` or a script its hooks call, add `--own-hooks`.
  - `plugin/agents/delivery-runner.md`: step 10 says the operator step's gate is
    `team.sh gate open --class operator`; the Gates section's command names `--class operator` for an
    operator step beside the other classes.
- **Out:**
  - Reading hooks from the worktree by default, or from a sha other than the worktree's own head.
  - A new gate class, or any change to `scripts/team.sh` or `scripts/observability/team.py`.

## dod_checks

- id: `hook-01`
  story: As a verifier, my worktree runs the PR's own setup hook.
  setup: a fenced scratch product whose main checkout's plane.json sets `env.setup` to `echo main > hook.txt`, and a commit on another branch whose plane.json sets it to `echo head > hook.txt`.
  steps:
    1. Run `ccp wt create --kind ver --task <task> --sha <that commit> --own-hooks`.
    2. Run `ccp wt create --kind rev --task <task> --sha <that commit>`.
  expect: both exit 0; the `ver` worktree's `hook.txt` reads `head` and its record has `own_hooks: true`; the `rev` worktree's reads `main`.
  dry run (`85d388b`): `ccp wt create --help` names no `--own-hooks`.
- id: `hook-02`
  story: As a verifier, a PR whose plane.json does not load fails my create cleanly.
  setup: the product of hook-01 and a commit whose plane.json is not JSON.
  steps:
    1. Run `ccp wt create --kind ver --task <task> --sha <that commit> --own-hooks`.
  expect: exit 1; stderr names the worktree's plane.json; no worktree directory and no record remain.
  dry run: n/a.
- id: `gate-01`
  story: As a runner, my doc names the gate class an operator step takes.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -- '--class operator' -- plugin/agents/delivery-runner.md`.
  expect: at least two lines, one in step 10 and one in the Gates section.
  dry run (`85d388b`): no line (exit 1), as expected before the change.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-18 (implementer): `ccp wt create --own-hooks` records `own_hooks: true`; `wt.hook_env` gives
  such a worktree's hooks and `env.timeout_seconds` from its own `docs/delivery/plane.json`
  (`config.load` on the worktree path), and every hook (`setup`, `teardown`, `up`, `down`, `urls`) goes
  through it. The hook's template fields (`{main_checkout}` included) are still the caller's: only the
  `env` block moves. A base run passes the flag through, so its hooks are the merge base's own; a base
  run's default command timeout stays the caller's `env.timeout_seconds` (it is not a hook's).
- Choices the task leaves open, made narrowly: `--own-hooks` on any action but `create` is refused
  (exit 2), as `--shallow` is; reusing a recorded worktree whose `own_hooks` differs from the call's is
  refused (exit 3), as a depth mismatch is, so a worktree set up by the other hooks never stands in;
  on `up` and `urls` an own plane.json that does not load fails the command (exit 1, the file named),
  as a failed hook does there; a recorded `own_hooks` worktree whose path is gone always warns that
  its `down` and `teardown` were not run (its hooks cannot be read any more).
- The runner doc names `--class operator` in step 10 and in the Gates section; `team.sh` is unchanged.

## Verification notes
- 2026-11-18 — verifier, PR #171 head `4a13afb` (squash `55f7c51`): APPROVE. Passed: hook-01, hook-02, gate-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0158-env-hooks-from-worktree-and-operator-step.json.

