---
task_id: 0240-plane-workers-run-the-head
title: The plane's own workers run the head they change, and briefs name commands rather than restating their conditions
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S15", "S29"]
review_refs: ["ar-20261120T234012Z-27eb#F01", "ar-20261120T234012Z-27eb#F15"]
review_point: R16
paths: ["ccp/prompt.py", "ccp/wt.py", "ccp/cli.py", "ccp/verify.py", "templates/prompts/", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-runner.md", "plugin/skills/writing-tasks/SKILL.md", "docs/spec/02-delivery.md", "docs/spec/05-operations.md", "tests/test_plane_workers_run_head.py", "tests/test_plugin.py", "tests/test_prompt_end.py", "tests/test_prompt_note_env.py", "tests/test_verify.py", "tests/test_wt.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0240-plane-workers-run-the-head

## Intent

When the plane develops itself, every `ccp` command a worker's prompt names runs the code of the head
that worker is changing, not the released plane on PATH. A worker checking a new subcommand or a
tightened plane.json rule sees the head's behaviour, and the hand workarounds in the reviewer and
verifier briefs go. `ccp wt exec`, which those commands go through, no longer prints the §29.2
checkout warning in its child, so real warnings are no longer buried. The runner brief, the
writing-tasks skill and the verify prompt name commands and their § instead of restating the
commands' refusal conditions and constants.

## Context (not checked)

From architect pass `ar-20261120T234012Z-27eb`, findings F01 and F15, triaged by the lead on
2026-11-21. Measured at `8aefa59`.

- **How `ccp` renders today.** `ccp/prompt.py` `"def ccp_command"` returns `"ccp"` when `ccp` is on
  PATH and the product carries no managed agent copies. For the plane that is the run checkout's
  released code. Probe at `8aefa59`: a temp product with plane.json `{"project_id": "demo", "language": "none"}`
  printed `ccp` from `prompt.ccp_command(config.load(...))`, with and without a `bin/ccp` file.
- **The ruling on the mechanism.** A product whose root holds `bin/ccp` (only the plane does) renders
  `{{ccp}}` as `ccp wt exec --`. With no NAME, `ccp wt exec` runs the `bin/ccp` of the checkout it
  runs in (`--root`, else `$CCP_ROOT`, else the working directory's git toplevel, §12.1). Every
  worker runs in its own worktree, so this is the head it changes. Templates keep saying `{{ccp}}`;
  §29.4's "say `ccp`" still holds. The runner itself keeps `ccp` on PATH for claim, close and merge.
- **Literal `ccp` in the templates.** `git grep -nE 'ccp [a-z]' -- templates/prompts` at `8aefa59`: 21 lines (`git grep -cE 'ccp [a-z]' -- templates/prompts`: 7 in `_common.md`, 6 in `verify.md`, 3 in `review.md`, 2 in `merge.md`, 1 each in `fix.md`,
  `implement.md` and `ruling.md`) name `ccp` literally instead of `{{ccp}}`. Ruling (the lead, on the
  triage review): every one becomes `{{ccp}}`, so §12.1's "every `ccp` a worker prompt names" holds.
- **The warning.** `ccp/cli.py` `"def checkout_warning"` warns when the checkout `ccp` runs from is
  off `main`, silenced only by `CCP_DEV=1`. `ccp/wt.py` `"def exec_ccp"` runs the child with the
  caller's environment unchanged. Ruling: `exec_ccp` sets one variable for the child through
  `envvars.for_child` (named by the implementer, `CCP_*`), and `checkout_warning` returns nothing
  when it is set. A plain run off `main` still warns. Dry run at `8aefa59`, from a worktree on a
  branch: `env -u CCP_DEV QUEUE_ROOT=<empty dir> ./bin/ccp wt exec -- tasks list --status nothing`
  printed the "not main" warning twice (parent and child).
- **Hand workarounds to remove.** `git grep -n 'wt exec' -- templates/prompts plugin/agents` at `8aefa59`: 6 lines, in `templates/prompts/verify.md`, `plugin/agents/delivery-reviewer.md` and
  `plugin/agents/delivery-verifier.md`. The verify prompt's paragraph on a task that changes the
  record's contract exists only because the prompt's `ccp` was the released one. Ruling: the
  workaround paragraphs go, and `verify.md` and `review.md` keep one rendered rule for checks by
  hand: "run a check's `ccp` command as `{{ccp}} <args>`". The reviewer's and verifier's agent
  definitions say to run a check's `ccp` command as the prompt's `{{ccp}}` renders it.
  `ccp/verify.py`'s module docstring and its refusal of a key the contract does not know name
  `ccp wt exec` (`git grep -n 'wt exec' -- ccp/verify.py` at `8aefa59`: 2 lines); they point at the
  prompt's rendered `ccp` instead.
- **Restated conditions (F15, house rule E13).** `git grep -nE '4000 characters|120-second|Exit 3 means one of' -- plugin/agents/delivery-runner.md` at `8aefa59`: 3 lines (the note limit, the supersede grace, the three meanings of exit 3 of
  `ccp prompt`). The writing-tasks skill's `adopt` row restates two `ccp tasks check` warnings
  (`git grep -n '^| .adopt. |.*ccp tasks check' -- plugin/skills/writing-tasks/SKILL.md` at `8aefa59`: 1 line). Each is cut to the command and its §. Each command's own refusal already names the
  failed condition (§10.6); where one does not, the implementer fixes the message rather than
  keeping the brief's copy.
- **Risk accepted.** A head whose `bin/ccp` does not start also stops its own worker's `ccp report`.
  Such a head fails its own gate anyway, and the implementer is in that worktree to fix it.
- Tests that read the briefs or the rendered verify prompt (`git grep -ln 'wt exec\|ccp_command\|4000 char\|120-second\|checkout_warning' -- tests` at `8aefa59`: 5 modules) are in `paths`.

## Scope

- **In:**
  - `ccp/prompt.py` (`ccp_command`), `ccp/wt.py` (`exec_ccp`), `ccp/cli.py` (`checkout_warning`).
  - `templates/prompts/`: every literal `ccp` command becomes `{{ccp}}`; `verify.md` and
    `review.md` keep the rendered by-hand rule; the `wt exec` workaround paragraphs removed.
  - `plugin/agents/delivery-reviewer.md`, `plugin/agents/delivery-verifier.md`: the workarounds
    replaced by "run a check's `ccp` command as the prompt's `{{ccp}}` renders it".
  - `ccp/verify.py`: the docstring and the refusal message point at the rendered `ccp`.
  - `plugin/agents/delivery-runner.md`, `plugin/skills/writing-tasks/SKILL.md`: restated conditions
    and constants cut to the command and its §.
  - `tests/test_plane_workers_run_head.py` (new); the test modules in `paths` that pin removed text.
  - SPEC, signed before the claim (`sign_off: brief`):
  - `docs/spec/05-operations.md` §29.2: CURRENT (at `8aefa59`): "`ccp` warns on stderr when the run checkout has local changes, is not on `main`, or is behind `origin/main`." PROPOSED:
    > `ccp` warns on stderr when the run checkout has local changes, is not on `main`, or is behind `origin/main`; a `ccp wt exec` child, which runs a worktree's head on purpose (§12.1), gives no such warning.
  - `docs/spec/02-delivery.md` §12.1: CURRENT (at `8aefa59`): "It loads no plane.json, so a reviewer or verifier can run the change under review's own `ccp`, new subcommands included; `ccp` on PATH stays the released one." PROPOSED:
    > It loads no plane.json, so a reviewer or verifier can run the change under review's own `ccp`, new subcommands included; `ccp` on PATH stays the released one. For a product whose checkout carries its own `bin/ccp` (the plane itself), every `ccp` a worker prompt names renders as `ccp wt exec --`, so a worker's commands run the head it is changing.
  - `docs/spec/02-delivery.md` §15.4: CURRENT (at `8aefa59`): "The verify prompt and the verifier's definition say so: when the task's own diff changes the record's contract (`contracts/verification.schema.json`, or the record's version), the verifier records with the head's own `ccp`, `ccp wt exec <its worktree> -- verify record <file>` (§12.1)." PROPOSED:
    > Only the plane changes that contract, and there a worker prompt's `ccp` already runs the head (§12.1), so the verifier records with the head's own `ccp`.
- **Out:**
  - The runner's own commands (claim, close, merge, reconcile): they stay on `ccp` on PATH.
  - Products other than the plane: no `bin/ccp`, no change.

## dod_checks

- id: `head-01`
  story: As the plane's lead, my workers' prompts name a `ccp` that runs their head.
  setup: a checkout of the PR head; a temp dir `D` with `docs/delivery/plane.json` holding `{"project_id": "demo", "language": "none"}`; `CCP_BINDINGS_DIR` pointed at an empty temp dir; `ccp` on PATH.
  steps:
    1. Run `python3 -B -c "from pathlib import Path; from ccp import prompt, config; print(prompt.ccp_command(config.load(Path('D'))))"` with `D` replaced by the temp dir.
    2. Create an empty file `D/bin/ccp` and run step 1 again.
  expect: step 1 prints `ccp`; step 2 prints `ccp wt exec --`.
  dry run (`8aefa59`): both steps printed `ccp`.
- id: `head-02`
  story: As a worker, a `ccp wt exec` child gives no checkout warning, and a plain run off main still does.
  setup: a worktree of the PR head on a branch other than `main`; `QUEUE_ROOT` an empty temp dir; `CCP_DEV` unset.
  steps:
    1. In the worktree, run `env -u CCP_DEV ./bin/ccp wt exec -- tasks list --status nothing 2>&1 | grep -c 'not main'`.
    2. Run `env -u CCP_DEV ./bin/ccp tasks list --status nothing 2>&1 | grep -c 'not main'`.
  expect: step 1 prints `1` (the parent's own warning only); step 2 prints `1`.
  dry run (`8aefa59`): step 1 printed `2`, step 2 printed `1`.
- id: `head-03`
  story: As a reviewer or verifier, my brief carries no hand workaround for the released `ccp`, and keeps one rendered rule for checks by hand.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE 'wt exec|does not know the new contract|released plane' -- templates/prompts plugin/agents ccp/verify.py`.
    2. Run `grep -cF '{{ccp}} <args>' templates/prompts/verify.md templates/prompts/review.md`.
  expect: step 1 prints nothing; step 2 prints a count of at least 1 for each file.
  dry run (`8aefa59`): step 1 printed 10 lines; step 2 printed 0 for each file.
- id: `head-04`
  story: As a runner or task writer, my brief names commands and their § rather than restating their conditions.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE '4000 characters|120-second|Exit 3 means one of' -- plugin/agents/delivery-runner.md`.
    2. Run `git grep -n '^| .adopt. |.*ccp tasks check' -- plugin/skills/writing-tasks/SKILL.md`.
  expect: both print nothing.
  dry run (`8aefa59`): step 1 printed 3 lines, step 2 printed 1 line.
- id: `head-05`
  story: As a plane developer, the rendering and the warning rule are held by tests that bite.
  setup: a checkout of the PR head; then a separate copy where `ccp_command` ignores `bin/ccp`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_plane_workers_run_head tests.test_wt tests.test_verify`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_plane_workers_run_head`.
  expect: step 1 exits 0; step 2 exits non-zero.
  dry run: n/a — `tests/test_plane_workers_run_head.py` is new.
- id: `head-06`
  story: As a worker, every `ccp` command my prompt names is the rendered one.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE 'ccp [a-z]' -- templates/prompts`.
  expect: it prints nothing.
  dry run (`8aefa59`): 21 lines.

## Implementation notes

## Verification notes
