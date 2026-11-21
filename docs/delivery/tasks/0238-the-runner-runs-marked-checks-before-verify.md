---
task_id: 0238-the-runner-runs-marked-checks-before-verify
title: The runner runs each marked check at the head it hands the verifier, and verify does not launch without it
status: pending
kind: feature
depends_on: ["0224-checks-only-the-operator-s-machine-can-run", "0233-briefs-point-at-the-evidence-rules", "0234-one-check-parser-and-one-file-at-rev-reader", "0240-plane-workers-run-the-head"]
clashes_with: ["0212-full-role-runs-the-gate-lane-and-a-pregate-lane", "0213-a-green-tree-skips-the-lane-queue", "0221-workers-reach-the-pr-host-through-ccp-pr", "0223-a-follow-up-is-tracked-not-left-in-notes", "0228-report-sections-as-one-table"]
spec_refs: ["S10", "S13", "S14"]
adr_refs: ["0045 D2"]
review_point: R15
paths: ["ccp/prompt.py", "ccp/suite.py", "contracts/suite_result.schema.json", "templates/prompts/implement.md", "templates/prompts/verify.md", "plugin/agents/delivery-runner.md", "plugin/agents/delivery-implementer.md", "plugin/agents/delivery-verifier.md", "docs/spec/02-delivery.md", "docs/adr/0045-checks-only-the-operator-s-machine-can-run.md", "tests/test_marked_checks_loop.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0238-the-runner-runs-marked-checks-before-verify

## Intent

After 0224 a check only the operator's machine can run is marked. This task puts it in the runner's
loop: before each verify, at the head it hands the verifier, the runner runs each marked check in a
`--kind mac` worktree under the task's approved operator gate, as a recorded suite run that names
that head; a check only the operator can run by hand is run the same way by the operator. The
implement and verify prompts say those checks are not the worker's, and `ccp prompt verify` refuses
to launch while one has no passed run at the head, unless it rests on a carried verdict (§15.6 rule
3) or a ruling waives it. A step that is not a check (a rollout after the merge) keeps its place after
the merge.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0045 D2, accepted by the operator on 2026-11-20. D1 is 0224, D3 is 0237.
- **Shaped** by `sh-20261121T000350Z-5ef1`:
  - F01, the operator's: nothing binds an operator-machine run to a head, since a gate is approved once
    per task and suite rows record no commit. Recommended: the runner runs a marked check as `ccp
    suite run --lane <check_id> --task <task_id> -- <command>` in the mac worktree, the suite row
    records that worktree's HEAD, and `ccp prompt verify` refuses while a marked check has no passed
    run at the head, as `prompt.tip_gate` refuses today
    (`grep -c 'def tip_gate' ccp/prompt.py` at `8aefa59`: 1).
  This brief is written on the recommended answers; if the operator answers otherwise, it is
  revised and signed again.
  - F08's D2 half: the runner's brief runs the operator step from its own worktree after the merge
    (step 10, "Operator step"); §15.8 and D2 put a marked check in a `--kind mac` worktree before verify.
    The brief gets two places: a marked check before verify, a non-check step after the merge, and
    names the mac worktree's seat (`ccp/wt.py` `"mac": ("ver", "mac")`, the verifier's by default).
  - F09 (checks run the head's `ccp`) is covered by R16's 0240, which renders every `ccp` a worker
    prompt names as `{{ccp}}`; this task depends on it and writes its prompt text with `{{ccp}}`.
- **The exemptions (ADR-0045 D2).** A head that moved only by an integration merge, or a catch-up whose
  resolution review does not list the check in `Affected checks`, carries the earlier approve; the
  check is not run again there. A check a ruling waives is not run either. The launch refusal skips
  both, so a re-verify is never held for a run the ADR does not ask for.
- **One field, two questions.** 0213 records `tree` (`HEAD^{tree}`) to find a passing run of the same
  content; this task records `head` (`HEAD`) because a verdict, a carried `approve at <old>` and the
  launch refusal are keyed by the commit handed to the verifier. Both are recorded only when the
  checkout has nothing to commit, so the two never disagree; neither replaces the other, and the two
  tasks clash on the `started` row.
- **Clashes.** 0212, 0221 and 0223 edit `templates/prompts/implement.md`, whose instructions are one
  long line, or the runner's brief; each pair would conflict on the same lines.
- **The suite row's `head`** is contract text describing this task's feature (§31.1).

## Scope

- **In:** `ccp/prompt.py`, `ccp/suite.py`, `contracts/suite_result.schema.json`,
  `templates/prompts/implement.md`, `templates/prompts/verify.md`, `plugin/agents/delivery-runner.md`,
  `plugin/agents/delivery-implementer.md`, `plugin/agents/delivery-verifier.md`,
  `docs/spec/02-delivery.md`, `docs/adr/0045-checks-only-the-operator-s-machine-can-run.md`,
  `tests/test_marked_checks_loop.py` (new).
- **The suite row** records `head`, the worktree's HEAD, on a run whose checkout has nothing to commit
  (the condition 0213 uses for `tree`) (§31.1).
- **The prompts.** `ccp prompt implement` and `ccp prompt verify` list the marked checks (from
  `tasklog.checks`) as not the worker's to run; the verify prompt says their evidence is the runner's
  suite run, cited by `suite_id` with the gate's id. `ccp prompt verify` refuses (exit 1, naming the
  check and the command) while a marked check has no passed suite run of its lane, bound to the task,
  at the head, except a check that:
  - carries the task's latest approve at `<old>` (§15.6 rule 3): the PR's own patch id is unchanged
    from `<old>`, or the latest resolution review's `affected_checks` does not name it; or
  - is waived by a ruling given as `--waived <check_id>=<ruling id>`, which must pass the ruling form
    `rests_on` accepts (§15.4).
  The prompts name commands as `{{ccp}}` (0240).
- **The runner's brief** runs each marked check before `ccp prompt verify`, once per head it hands the
  verifier, after any catch-up, in `ccp wt create --kind mac` at that head, under the task's approved
  `operator` gate or a standing approval, through `ccp tasks checks <task> --json` and `ccp suite run
  --lane <check_id> --task <task_id> -- <the check's command>`; a check only the operator can run by
  hand is run by the operator with the same command in that worktree; a step that is not a check stays
  after the merge. The implementer's and verifier's briefs say the same from their side.
- ADR-0045 D2 recorded `built`.
- **Tests** in `tests/test_marked_checks_loop.py` (new): a suite row's `head`; both prompts listing a
  marked check; `ccp prompt verify` refusing with no run, with a failed run and with a run at another
  head, and launching with a passed run at the head, after an integration-merge-only move with no run
  at the new head, after a resolution review that does not list the check, and with `--waived` naming
  an approved ruling (refusing one that names none).

### SPEC changes (signed in the brief, §31)

**a. §10.2 step 2, the runner's loop.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> 2. **Run.** The runner loops: `ccp tasks next` (§10.3) → `ccp tasks claim` (§10.5) → `ccp prompt`
>    and the worker (implement, then the PR in the same worker) → review → fix and review again while
>    needed → verify (§15)

PROPOSED:
> 2. **Run.** The runner loops: `ccp tasks next` (§10.3) → `ccp tasks claim` (§10.5) → `ccp prompt`
>    and the worker (implement, then the PR in the same worker) → review → fix and review again while
>    needed → each `runs_on: operator-machine` check run at the head the runner hands the verifier,
>    after any catch-up, once per such head, as `ccp suite run --lane <check_id> --task <task_id> --
>    <the check's command>` in a `ccp wt create --kind mac` worktree at that head, by the runner or,
>    for a check only the operator can run by hand, by the operator; not for a check that carries an
>    earlier approve (§15.6 rule 3) or that a ruling waives (§15.8) → verify (§15)

**b. §13.2, the task part of a prompt.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> 3. **The task:** id, task file path, cited SPEC and ADR sections, the house rules (`rules_doc`), the
>    PR and head for review and verify, the verifier's fixed packet,

PROPOSED:
> 3. **The task:** id, task file path, cited SPEC and ADR sections, the house rules (`rules_doc`), the
>    PR and head for review and verify, the verifier's fixed packet, for implement and verify the
>    checks marked `runs_on: operator-machine` as not the worker's to run (`ccp prompt verify` refuses
>    while one has no passed suite run recorded at the head, unless it carries an earlier approve or a
>    ruling waives it, §15.8),

- **Out:** the refusals at `record` and `merge-ok` (0237), a new phase or stage, and a step that is not
  a check.

## dod_checks

- id: `ml-01`
  story: As a runner, verify does not launch until each marked check passed at its head.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_marked_checks_loop 2>&1 | tail -12`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `ml-02`
  story: As a plane developer, the launch refusal's head rule bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    refusal accepts a passed run at any head.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_marked_checks_loop`.
  expect: at least one failure (the run at another head).
  dry run: n/a — the module is new.

- id: `ml-05`
  story: As a runner, a re-verify after an integration merge launches without a new operator run.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    launch refusal ignores the carried-verdict exemption.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_marked_checks_loop`.
  expect: at least two failures (the integration-merge and the resolution-review cases).
  dry run: n/a — the module is new.

- id: `ml-03`
  story: As a worker, prompts for unmarked tasks read as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_prompt_pr_body tests.test_team_hosting 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

- id: `ml-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0238 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`8aefa59`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
