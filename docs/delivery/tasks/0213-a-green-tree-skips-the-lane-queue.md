---
task_id: 0213-a-green-tree-skips-the-lane-queue
title: Confirming a head whose gate is already recorded green does not queue for the exclusive lane
status: pending
kind: feature
depends_on: ["0199-suite-wait-auto"]
spec_refs: ["S14", "S15", "S16"]
review_point: R15
paths: ["ccp/suite.py", "docs/spec/02-delivery.md", "tests/test_parallel_lanes.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0213-a-green-tree-skips-the-lane-queue

## Intent

An exclusive lane runs one run at a time, because a full run is heavy. But a run of a tree that has
already passed that lane is mostly answered by the product's test cache, and it still waits behind
whatever holds the lock, sometimes past the worker's shell limit. The verifier confirming a head the
implementer already ran green is the usual case. After this task, a run whose clean checkout has the
same tree as a passing run of the same lane already recorded in the queue runs at once, without
taking the lock, and the record says so. The verifier still runs the gate itself.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: an accepted plane proposal (triage item T7b).
- **The lock comes first.** `ccp/suite.py` `run`: when `_exclusive(cfg, a.lane)`, it calls
  `take_lane(q, mine)` before anything runs, and on a held lane exits 75 or waits up to `--wait`
  (`git grep -n 'lane_fd, holder = take_lane(q, mine)' -- ccp/suite.py` at `1b734dd`: two lines, the
  first try and the wait loop). Nothing about the tree is consulted.
- **No tree is recorded.** The `started` row holds `suite_id`, `at`, `lane`, `cmd`, `argc`, `output`
  and the bound run's fields (`git grep -n '"op": "started"' -- ccp/suite.py` at `1b734dd`: one line);
  `git grep -n '"tree"' -- ccp/suite.py` at `1b734dd` finds no line. The `ended` row has `exit_code`,
  `tests` and `interrupted`, which tell a passing run.
- **ADR-0010** has the verifier run the gate itself. The proposal also asked that a confirmation be
  answered from the recorded result alone; that would replace the verifier's run and is not done
  here. This task changes only whether the run queues: it still runs, at the head, recorded against
  the verify run, and the product's test cache (§15.3) decides what it re-executes.
- **A cold gate.** A task whose gate is cold (§15.3, `verify.cold_gate(cfg, meta)`) asks for a run with
  nothing cached, which is as heavy as any; it keeps the lock.
- **Depends on 0199**, which changed the same §16.6 paragraph and the same lock code in `run` (`--wait
  auto`); it merged at `9cec44f`. The CURRENT below quotes a sentence 0199 did not change, verbatim at
  `8aefa59` too.
- `tests/test_parallel_lanes.py` holds the exclusive-lane tests (`python3 -B -m unittest tests.test_parallel_lanes`: 8 tests at `1b734dd`, 14 at
  `8aefa59` after 0199).

## Scope

- **In:** `ccp/suite.py`, `docs/spec/02-delivery.md`, `tests/test_parallel_lanes.py`.
- **The tree on the row.** A recording run whose working directory is in a git checkout with nothing
  to commit (`git status --porcelain` prints nothing, untracked files included) adds
  `tree: <HEAD^{tree}>` to its `started` row. Any other run records no `tree`. A git call that fails
  records no `tree` and never blocks the run.
- **A green tree skips the queue.** Before `take_lane`, a run of an exclusive lane that has a `tree`
  looks in `runs/_suites.jsonl` for an earlier run with:
  - a `started` row of the same `lane`, `tree`, `cmd` and `argc`; and
  - an `ended` row with `exit_code` 0, a `tests` count above 0 and no `interrupted`.

  With one found, and unless the run is bound to a task whose gate is cold (`verify.cold_gate`), it
  runs at once without the lock. Its `started` row records `lane_skipped: "green_tree"` and
  `green_from: <that suite id>`. Stderr says `lane <lane>: a passing run of this tree is recorded
  (<suite id>): running without the lock`. A held lock is neither waited on nor counted busy.
- Any failure reading the suites file leaves the run on the lock as today.
- **Tests** in `tests/test_parallel_lanes.py`:
  - with the lane held and a passing run of the same tree recorded, a second run exits with the
    command's own code (not 75), its `started` row has `lane_skipped` and `green_from`;
  - with the recorded run failed (exit 1), or of another tree, or of another lane, the held lane
    exits 75 as today;
  - a checkout with an uncommitted change records no `tree` and queues;
  - a run bound to a cold-gate task queues.

### SPEC changes (signed in the brief, §31)

**a. §16.6, after the lock's takeover sentence.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> A lock whose holder process is gone is
> taken over with a warning.

PROPOSED:
> A lock whose holder process is gone is
> taken over with a warning. A run whose clean checkout (nothing to commit, untracked files included)
> has the tree of a passing run of the same lane and command already recorded in the queue does not
> take the lock: it runs at once, recorded `lane_skipped: "green_tree"` with that run's `green_from`,
> since the product's test cache answers most of it; a run bound to a task whose gate is cold (§15.3)
> takes the lock as any other. The verifier still runs its gate (§15.3).

**b. §14.4, the `started` row.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> A staged
> lane's `started` row has `cmd` `stages` and its stage count as `argc`.

PROPOSED:
> A staged
> lane's `started` row has `cmd` `stages` and its stage count as `argc`. A run from a git checkout with
> nothing to commit adds `tree`, the `HEAD^{tree}` it ran (§16.6), and a run that skipped an exclusive
> lane's lock adds `lane_skipped` and `green_from`.

- **Out:** answering a run from a recorded result without running it (ADR-0010), the lock for
  non-exclusive lanes, and `--wait`.

## dod_checks

- id: `gt-01`
  story: As a verifier, confirming a head already run green does not wait behind the lock.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_parallel_lanes 2>&1 | tail -30`.
  expect: exit 0, with the Scope's four tests listed `ok`.
  dry run (`8aefa59`): 14 tests, OK; the new tests do not exist yet.

- id: `gt-02`
  story: As a plane developer, the skip is tested and the tests bite.
  setup: a checkout of the PR head; then two copies (`git worktree add --detach <tmp> HEAD`): in copy
    A the `exit_code` 0 condition on the recorded run is removed; in copy B the `tree` comparison is
    removed.
  steps:
    1. In copy A, run `python3 -B -m unittest -q tests.test_parallel_lanes`.
    2. In copy B, run the same.
  expect: each step has at least one failure.
  dry run: n/a — the tests are new.

- id: `gt-03`
  story: As a lead, a clean run records the tree it ran.
  setup: a checkout of the PR head with nothing to commit; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . suite run --lane quick -- true`.
    2. Run `python3 -c "import json,os; rows=[json.loads(l) for l in open(os.environ['QUEUE_ROOT']+'/runs/_suites.jsonl')]; print([r.get('tree') == os.popen('git rev-parse HEAD^{tree}').read().strip() for r in rows if r['op']=='started'])"`.
  expect: step 1 exits 0; step 2 prints `[True]`.
  dry run (`1b734dd`): step 1 exits 0; step 2 prints `[False]`.

- id: `gt-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0213 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`1b734dd`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
