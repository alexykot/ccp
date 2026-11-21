---
task_id: 0231-a-review-point-does-not-close-over-an-undecided-follow-up
title: A review point recorded closed while a follow-up is undecided fails the lead's checks
status: pending
kind: feature
depends_on: ["0230-the-lead-decides-each-follow-up"]
spec_refs: ["S21", "S22"]
adr_refs: ["0044 D3"]
review_point: R15
paths: ["ccp/followups.py", "ccp/cli.py", "scripts/observability/team.py", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "docs/adr/0044-a-follow-up-is-tracked-not-left-in.md", "tests/test_followups_closed_point.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0231-a-review-point-does-not-close-over-an-undecided-follow-up

## Intent

ADR-0044 lets a follow-up stay open while its review point runs, and refuses to let the point be
declared finished over one: the work it names is decided before the point closes. After this task
the lead's checks fail while the register records a point `closed` and a run of one of its tasks holds
a follow-up with no outcome, naming each one and the command that decides it. Workers' gates, which
cannot fix it, are not held by it.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0044 D3, accepted on 2026-11-20. Depends on 0230's `followups.undecided`.
- **Shaped** by `sh-20261120T235613Z-4fce`, F01, the operator's decision: `tasklog.check` is shared by
  `ccp docs check`, the reconcile, the review-point commands and every worker's gate
  (`git grep -n 'tasklog.check(cfg)' -- ccp scripts` at `8aefa59`: eleven lines), so a queue-state
  failure placed there would fail an unrelated task's verify whenever its shell had `QUEUE_ROOT`. This
  brief is written on the recommended answer: the check is its own function, run by `ccp tasks check
  --closed-points` and by the spawn's readiness check (`team.sh runner spawn [--dry-run]`, which
  ADR-0044 names), never by plain `tasks check`, `docs check` or a worker's gate. If the operator
  answers otherwise, the brief is revised and signed again.
- **The register's tasks.** `ccp/reviewpoints.py` `summary()` already maps tasks to points; the check
  reuses it.
- Without `QUEUE_ROOT` the check says nothing, so the fenced suite and CI stay quiet.
- §21.1's last failure bullet is also edited by 0224 (another bullet) and 0252 (the paragraph below);
  this task adds its text to §22.2 and a §21.1 sentence of its own, so the passages do not overlap.

## Scope

- **In:** `ccp/followups.py`, `ccp/cli.py`, `scripts/observability/team.py`,
  `docs/spec/03-quality.md`, `docs/cli/03-quality.md`,
  `docs/adr/0044-a-follow-up-is-tracked-not-left-in.md`, `tests/test_followups_closed_point.py` (new).
- **`followups.closed_point_errors(entries, point_tasks, runs) -> list[str]`**, on plain values: one
  error per undecided follow-up of a task of a `closed` point, naming the point, the follow-up and
  `ccp tasks follow-up <id> …`.
- **`ccp tasks check --closed-points`**: with `QUEUE_ROOT` set, the usual check plus these errors
  (exit 1 on any); without it, a note that it read no queue.
- **The spawn's readiness check** in `team.py` adds a `closed_points` check from the same function.
- ADR-0044 D3 recorded `built`; `docs/cli/03-quality.md` gains the flag.
- **Tests** in `tests/test_followups_closed_point.py` (new): the function on plain values (closed with
  an undecided follow-up, closed with all decided, open with an undecided one); `--closed-points` on a
  temp product and queue failing then passing once decided; plain `tasks check` unaffected.

### SPEC changes (signed in the brief, §31)

**a. §22.2, the register's checks.**

CURRENT (`docs/spec/03-quality.md` at `8aefa59`):
> - `ccp tasks check` and `ccp docs check` validate it.

PROPOSED:
> - `ccp tasks check` and `ccp docs check` validate it.
> - `ccp tasks check --closed-points`, with `QUEUE_ROOT` set, and the spawn's readiness check
>   (`team.sh runner spawn [--dry-run]`) also fail while the register records a point `closed` and a
>   run of one of its tasks holds a follow-up with no outcome (§13.4), naming each and the command that
>   decides it. Plain `ccp tasks check`, `ccp docs check` and a worker's gate do not run it, and closing
>   a task does not wait for one.

**b. §21.1, the warnings paragraph's last sentence.**

CURRENT (`docs/spec/03-quality.md` at `8aefa59`):
> the point has fewer than 2 tasks per depth on average. Inline `# comments` in frontmatter are ignored.

PROPOSED:
> the point has fewer than 2 tasks per depth on average. Inline `# comments` in frontmatter are ignored.
> With `--closed-points` it also fails on a closed review point holding an undecided follow-up (§22.2).

- **Out:** a refusal at `ccp tasks close`, a notice, and the follow-ups of the lead or the architect.

## dod_checks

- id: `cp-01`
  story: As a lead, I cannot record a point finished over an undecided follow-up.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_followups_closed_point 2>&1 | tail -12`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `cp-02`
  story: As a plane developer, the check bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `closed_point_errors` ignores the point's status.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_followups_closed_point`.
  expect: at least one failure (the open point).
  dry run: n/a — the module is new.

- id: `cp-03`
  story: As a worker, my gate's task check is not held by the lead's follow-ups.
  setup: a checkout of the PR head; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . tasks check 2>&1 | grep '^tasks:'`.
  expect: one line starting `tasks: clean`.
  dry run (`8aefa59`): `tasks: clean (209 tasks)` on `origin/main`.

- id: `cp-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0231 --base origin/main`.
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
