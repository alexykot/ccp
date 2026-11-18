---
task_id: 0158-env-hooks-from-worktree-and-operator-step
title: A worktree can run its own env hooks, the runner doc names the operator gate class, and a check deferred past close is recorded
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S15", "S17"]
review_point: R10
paths: ["ccp/wt.py", "ccp/verify.py", "ccp/cli.py", "contracts/worktree.schema.json", "contracts/verification.schema.json", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "templates/prompts/verify.md", "plugin/agents/delivery-runner.md", "plugin/agents/delivery-verifier.md", "tests/test_wt.py", "tests/test_verify.py", "tests/test_verify_after_close.py", "tests/test_prompt*.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0158-env-hooks-from-worktree-and-operator-step
## Intent

A verifier judging a PR that changes the product's env hooks (plane.json `env`) or the scripts they
call can make its worktree with the PR's own hooks and exercise the change before it merges, instead
of deferring the check to an operator step after the merge. A runner opening a gate for an operator
step finds the gate class named in its doc. And a check that verify could not run before the merge
(`ran: false`) gets its result recorded against the done task through `ccp`, once it has run.

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
- A check deferred past close: §15.8 lets a task merge code-only with an operator step listed as a
  follow-up, and `ccp verify record` writes a whole verdict, so a later result has nowhere to go.
  `ccp tasks phase <id> operator` moves a live task's phase and records no check result; this task does
  not use it.
- §31.1: the §12.1, §12.2 and §15.8 sentences below describe this task's own features; no existing
  sentence changes meaning.

## Scope

- **In:**
  - `ccp/wt.py`: `ccp wt create … --own-hooks` (any kind; refused with `--baseline`, exit 2) records
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
  - `ccp/verify.py` and `ccp/cli.py`: `ccp verify after-close FILE|-` (new action), the input a JSON
    object `{task_id, dod_check_id, pass, evidence, produced_by, operator_step?}`. It refuses (exit 1,
    nothing written) unless the task is `done` in the task log, the task's verification record exists with
    verdict `approve`, that record's check `dod_check_id` has `ran: false`, `pass` is a boolean,
    `evidence` is non-empty, and `produced_by` passes the rule `producer_errors` holds `record` to (a
    `lead` or `runner` producer needs `operator_step` naming an approved `operator` gate of the task).
    It appends `{dod_check_id, pass, evidence, produced_by, operator_step?, at}` to the record's
    `after_close` list, leaves every other field as it was, stamps the record's `schema_version` with
    the writer's `RECORD_VERSION` (bumped by this task to 6), and prints the entry; exit 0. With
    `pass: false` it also prints to stderr that the lead files a follow-up task. No QUEUE_ROOT or bad
    JSON exits 2.
  - `contracts/verification.schema.json`: `after_close`, a list of those entries.
  - `docs/spec/02-delivery.md` §15.8, §31.1: after the bullet **Steps only the operator's machine can
    run.**'s sentence on a parked step, one sentence: once the task is done, the step's check result is
    recorded with `ccp verify after-close`; `docs/cli/02-delivery.md`: a row for it;
    `plugin/agents/delivery-runner.md` step 10: the same, one sentence.
  - Tests: `tests/test_wt.py` and `tests/test_verify_after_close.py` (new) for the checks below;
    `tests/test_verify.py` where it pins `RECORD_VERSION`; tests pinning the verify template text, if any.
- **Out:**
  - Reading hooks from the worktree by default, or from a sha other than the worktree's own head.
  - A new gate class, or any change to `scripts/team.sh` or `scripts/observability/team.py`.
  - Writing the after-close result into the task file's notes (it lives in the queue record).

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
- id: `after-01`
  story: As a runner, the operator's result for a check deferred past close is recorded on the done task.
  setup: a fenced scratch product and queue with a `done` task whose approve record has check `op-01` with `ran: false`, `pass: null`.
  steps:
    1. Run `ccp verify after-close <file>` with `{"task_id": <task>, "dod_check_id": "op-01", "pass": true, "evidence": "ran on the operator's machine: exit 0", "produced_by": "operator"}`.
  expect: exit 0; the record's `after_close` has that one entry with `at`; its `checks`, `verdict` and `head_sha` are as before; its `schema_version` is 6.
  dry run (`85d388b`): `ccp verify after-close x` is refused by argparse as an invalid choice.
- id: `after-02`
  story: As the plane, an after-close result is held to the record's rules.
  setup: the product of after-01.
  steps:
    1. Run `ccp verify after-close` with the same entry for a check the record shows `ran: true`.
    2. Run it for `op-01` with `"produced_by": "runner"` and no `operator_step`.
    3. Run it for `op-01` on a task that is still `pending`.
  expect: each exits 1 naming its reason (the check ran, a ruling seat's evidence, the task not done); the record is byte for byte unchanged.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
