---
task_id: 0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope
title: Stale-Context warnings reach the lead at the spawn and the implementer in its prompt, not every seat's task check, and a same-point respawn keeps the tasks the lead added
status: pending
kind: feature
depends_on: ["0257-one-gate-block-and-one-sentence-per-line"]
clashes_with: ["0259-a-check-failure-already-on-the-integration-branch-is-reported"]
spec_refs: ["S13", "S16", "S21", "S22"]
review_refs: ["ar-20261121T223646Z-f0a7#F05", "ar-20261120T234012Z-27eb#F13"]
review_point: R23
paths: ["ccp/tasklog.py", "ccp/cli.py", "ccp/prompt.py", "templates/prompts/implement.md", "scripts/observability/team.py", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/cli/02-delivery.md", "docs/cli/03-quality.md", "tests/test_tasklog_context_checks.py", "tests/test_team_dry_run.py", "tests/test_review_points.py", "tests/test_stale_context_audience.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope

## Intent

A brief measured before later commits changed its paths is flagged to the two seats that can act on
it: the lead, when it spawns a runner on a scope holding it, and the implementer, in the prompt of
that very task, so it re-measures the Context at its base before building. Every other seat's
`ccp tasks check` (the gate, a reviewer, a verifier) prints one count line instead of a warning per
pending task, and `ccp tasks check --stale` names them all. A lead who respawns a runner on the same
review point keeps the tasks it added to the scope by hand; today they are dropped.

## Context (not checked)

Measured at `8020446` unless a line says otherwise. Provenance: architect pass
`ar-20261121T223646Z-f0a7`, F05 (`process-cost`; it revisits `ar-20261120T234012Z-27eb` F13, built
by 0244), and one item of the lead's follow-up log (the respawn scope), folded here because both
change what `team.sh runner spawn` does with its scope. The SPEC passages are the operator's to sign
(the triage's third question).

- **The noise.** `CCP_DEV=1 ./bin/ccp tasks check 2>&1 | grep -c 'Measured at'` at `8020446`: 14 warning lines, one per pending task whose paths changed since its `Measured at`. `"def warnings"` in `ccp/tasklog.py` adds `stale_context` for every task. Every implementer, the gate and every verifier runs `ccp tasks check`; only the lead can edit an unclaimed brief, and only the implementer re-measures a claimed one.
- **The lead does not see them at the spawn.** `"def readiness"` in `scripts/observability/team.py`:
  the `tasks_check` check's `ok` is `not errs` (`tasklog.check`); warnings are not read.
- **False premises reached implementers.** 0232's `paths` named `ccp/cli.py` for code its dependency
  0229 had put in `ccp/notify.py`; the friction notes of 0224, 0230 and 0232 say the warning cost a
  re-read each time or the premise was wrong (the queue's notes; data only the queue holds).
- **The respawn.** `"def review_point_scope"` in `team.py`: with `--review-point` and no `--scope`,
  `scope = tagged_open(tasks, args.review_point)`, which drops the pending tasks `team.sh runner scope --add` put in `work.json`'s scope without the tag. §22.5 says so ("takes the open tasks tagged R, plus the waiting refactors on top"). `"def refactor_scope"` already keeps the point's refactors on a respawn of the same point.
- **Tests this changes.** `tests/test_tasklog_context_checks.py` (the per-task warning; `git grep -n 'Measured at' -- tests/test_tasklog_context_checks.py` at `8020446` finds its cases), `tests/test_team_dry_run.py` (the dry run's body), `tests/test_review_points.py` (the spawn's scope).
- **0259 clash.** 0259 (R18, signed) changes how `ccp tasks check` reports in `ccp/cli.py`, as this
  task's count line and `--stale` do, so the two must not run together. The clash is recorded on this
  task only: editing 0259's file would stale its brief sign-off, and `clashes_with` holds for both
  tasks from either side.
- **Other tasks on these files.** 0264 (`ccp/tasklog.py`'s signed-block parser), 0260 (`ccp/prompt.py`'s review tools), 0272 (`team.py`'s `LEAD` constant): other
  logic. 0257 rewraps `templates/prompts/implement.md` first.

### Rulings for the build (the lead's)

- **`ccp tasks check`.** Without `--stale`, the per-task stale-Context lines become one warning:
  "`<n>` task(s) not yet done were measured before commits that changed their paths: `ccp tasks check
  --stale` names them (§21.1)", printed only when `n` is at least one. `--stale` prints each task's
  line as today (`stale_warning`, unchanged) and nothing else of the warnings; it goes with no other
  flag (exit 2 otherwise). The exit code is unchanged: warnings never fail.
- **The implement prompt.** `ccp prompt implement` renders, when the task's own `stale_context` gives a
  line, a `{{#stale_context}}` block in `templates/prompts/implement.md`: the line itself, then
  "Re-run the Context's measurements at your base before you build; a figure that changed materially
  is a scope question in your report." Fix, merge and ruling rounds do not render it.
- **The spawn.** `team.sh runner spawn` and its `--dry-run` compute `stale_context` for each scope task
  (after the refactors are added). The spawn prints each line on stderr as `warning: …`; the dry run
  adds `"stale": [<line>, …]` to its body (`[]` when none) and prints the same lines on stderr. No
  readiness check fails for them and `ready` is unchanged.
- **The respawn.** With `--review-point R`, no `--scope`, and R equal to `work.json`'s
  `review_point`, the scope is the tagged open tasks, then `work.json`'s scope tasks that are still
  pending and not among them, in `work.json`'s order. A new review point (R differs) is unchanged.

## Scope

- **In:** `ccp/tasklog.py` (`"def warnings"`, a `stale` reader), `ccp/cli.py` (`tasks check --stale`),
  `ccp/prompt.py` and `templates/prompts/implement.md` (the block), `scripts/observability/team.py`
  (`"def review_point_scope"`, the spawn and dry-run outputs), `docs/cli/03-quality.md` (the
  `ccp tasks check` row), `docs/cli/02-delivery.md` (the dry-run row), `tests/test_stale_context_audience.py`
  (new), and the test modules named in Context.
- **SPEC, signed before the claim (`sign_off: brief`):** four passages, each CURRENT at `8020446`.

    CURRENT (`docs/spec/03-quality.md` at `8020446`, §21.1, the paragraph that starts "It warns, without failing"):
    > It also warns about a task not yet done whose Context says ``Measured at `<sha>` `` when a commit since that sha changed one of the task's `paths`, naming the commits.

    PROPOSED:
    > It also counts, in one warning, the tasks not yet done whose Context says ``Measured at `<sha>` `` when a commit since that sha changed one of the task's `paths`; `ccp tasks check --stale` names each such task with the commits, and the lead sees them at the spawn (§16.5) and the implementer in its prompt (§13.2).

    CURRENT (`docs/spec/02-delivery.md` at `8020446`, §13.2, item 3, The task):
    > the PR and head for review and verify, the verifier's fixed packet,

    PROPOSED:
    > the PR and head for review and verify, the verifier's fixed packet, for implement the task's own stale-Context warning when it has one (§21.1),

    CURRENT (`docs/spec/02-delivery.md` at `8020446`, §16.5, the `--dry-run` paragraph):
    > It exits 0 with `ready: true` when every check passes, and 1 with `ready: false` when any fails, naming the failing checks in `failed` and on stderr; a refusal exits as the spawn would.

    PROPOSED:
    > The spawn and its dry run print, on stderr, each scope task's stale-Context warning (§21.1), and the dry run lists them in `stale`; neither fails a check for them. It exits 0 with `ready: true` when every check passes, and 1 with `ready: false` when any fails, naming the failing checks in `failed` and on stderr; a refusal exits as the spawn would.

    CURRENT (`docs/spec/03-quality.md` at `8020446`, §22.5):
    > With a register, `team.sh runner spawn --review-point R` without `--scope` takes the open tasks tagged R, plus the waiting refactors on top (§20.4).

    PROPOSED:
    > With a register, `team.sh runner spawn --review-point R` without `--scope` takes the open tasks tagged R, plus the waiting refactors on top (§20.4); when R is `work.json`'s review point, it also keeps `work.json`'s scope tasks that are still pending, so a respawn keeps the tasks the lead added (`team.sh runner scope --add`).
- **Out:** what makes a Context stale (`stale_context`, unchanged); the other warnings; review, verify,
  fix, merge and ruling prompts; a readiness check that fails on staleness; `--remove`d tasks.

## dod_checks

- id: `cmd-01`
  story: As a verifier running the gate, `ccp tasks check` gives one count line for stale briefs, and `--stale` names them.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_stale_context_audience`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_stale_context_audience --mutant-file <file>`, the file's mutant making `"def warnings"` add each task's stale line again.
  expect: step 1 exits 0 and lists, each `ok`, a test where a temp product with two pending tasks measured at a commit before a change to their paths gets one warning line naming `2` and `--stale` from `ccp tasks check`, no per-task line, exit 0; and one where `ccp tasks check --stale` prints both tasks' lines and no other warning. Step 2 prints the mutant `killed`.
  dry run: n/a — the module and the flag are new.
- id: `cmd-02`
  story: As an implementer, my prompt says my brief was measured before later commits changed its paths.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_stale_context_audience`.
  expect: exits 0 and lists, `ok`, a test where `ccp prompt implement` for a stale task renders the task's stale line and `Re-run the Context's measurements`, and the same task's fix prompt and a fresh task's implement prompt render neither.
  dry run: n/a — the module is new.
- id: `cmd-03`
  story: As the lead, the spawn and its dry run show me which scope tasks are stale, without refusing.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_team_dry_run 2>&1 | tail -3`.
    2. Run `python3 -B -m unittest -v tests.test_stale_context_audience`.
  expect: step 1 ends `OK`; step 2 lists, `ok`, a test where `team.sh runner spawn --dry-run` on a scope holding one stale task exits 0 with `ready: true` and `stale` holding that task's line, and one where the spawn prints it on stderr as `warning:`.
  dry run (`8020446`): step 1 ended `OK`; step 2 n/a — the module is new.
- id: `cmd-04`
  story: As the lead, respawning on the same review point keeps the tasks I added to the scope.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_stale_context_audience`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_stale_context_audience --mutant-file <file>`, the file's mutant making `"def review_point_scope"` return the tagged tasks alone again.
  expect: step 1 lists, `ok`, a test where `work.json` records review point `R1` and a scope holding an untagged pending task added with `runner scope --add`, and `team.sh runner spawn --review-point R1 --dry-run` lists that task in its scope; and one where `--review-point R2` (a new point) does not. Step 2 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `spec-01`
  story: As the operator, §13.2, §16.5, §21.1 and §22.5 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0275`.
  expect: exit 0, all four PROPOSED passages found.
  dry run (simulated at `8020446`: this task file committed, then the four passages applied, each CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0275 --base HEAD~2`): `"ok": true`, four passage(s) found, none missing.

## Implementation notes

## Verification notes
