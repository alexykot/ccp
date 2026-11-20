---
task_id: 0198-architect-runs-in-its-own-worktree
title: The architect runs in its own worktree at the head it names, and one call shapes every ADR due
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S19"]
review_point: R14
paths: ["ccp/architect.py", "ccp/cli.py", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "tests/test_architect.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0198-architect-runs-in-its-own-worktree

## Intent

An architect pass records the head it reviews, but it runs in the caller's checkout. When that
checkout is a runner's worktree, it moves while the pass is running, so the pass can read files from
a different commit than the one it names. Shaping is slow in another way: a lead with several ADRs
due must start one shape pass per ADR, one call at a time. After this task, every pass runs in a
worktree of its own, detached at the head it records and removed when the pass ends. A single call,
`ccp architect run --mode shape --adr due`, shapes every ADR that `ccp architect due` lists, one
after another.

## Context (not checked)

Measured at `58cf1d0`.

- The pass's cwd is the product root. `ccp/architect.py` `cmd_run` sets `pr = str(cfg.root)`, takes
  `head` as `git rev-parse HEAD` there and launches the headless call with `subprocess.run(argv,
  cwd=pr, …)` (`git grep -n 'cwd=pr' ccp/architect.py` at `58cf1d0`: one line). `_spawn`, the
  detached start, also runs with `cwd=cfg.root`.
- `--adr` takes one id: `cmd_run` reads `adr_id(a.adr, cfg)`, and a shape run without it exits with
  "give --adr <id>" (`git grep -n 'give --adr' ccp/architect.py` at `58cf1d0`: one line).
  `shape_due(cfg, tasks)` already lists every ADR a pending task cites with no shaping record, and
  `ccp architect due` prints it as `shape_due`.
- One pass holds `architect.lock` (`ar.lock_take(q, actor, rid, …)`), and §19.6 rule 5 refuses a
  shape run while another pass is running. That is why the passes of one call run one after another,
  never at once. Running them at once would change that rule, so it is out of scope.
- `merge-<nnnn>` is the model to follow (§12.1). It is close's own worktree, made under the worktree
  directory (`wt.base_dir`, default `.plane-runtime`), not a `ccp wt` kind and not recorded.
- The proposals this answers were accepted at triage. The SPEC text below describes only the feature
  this task builds (§31.1).
- `tests/test_architect.py` uses a stub `claude` (`STUB`) that writes its argv beside the report.
  It passes 30 tests at the base (`python3 -B -m unittest -q tests.test_architect` at `58cf1d0`).

## Scope

- **In:** `ccp/architect.py`, `ccp/cli.py`, `docs/spec/02-delivery.md`, `docs/spec/03-quality.md`,
  `docs/cli/03-quality.md`, `tests/test_architect.py`.
- **The pass's own worktree.** `cmd_run`, once it holds the lock and has recorded `head`, makes a
  worktree `arch-<review id>` under `wt.base_dir(cfg)` with `git worktree add --detach <path> <head>`,
  run in the main checkout. Every later step of the pass runs there: the prompt audit's
  `--worktree`, and the headless call's `cwd`. The worktree's path goes into the pass's record as
  `worktree`.
  - The `finally` that releases the lock first removes the worktree (`git worktree remove --force`,
    then `git worktree prune`), whatever the pass's outcome.
  - When `_reap` marks a dead `running` pass `failed`, it also removes that pass's recorded worktree
    if it is still there.
  - `head` and `dirty` are still read in the product root, as today. The pass reads only committed
    files, which the prompt already implies by naming `head`.
  - A worktree that cannot be made fails the pass (`failed`, the git error as its `error`), nothing
    launched.
- **`--adr` takes several ADRs.** `--adr` accepts a comma-separated list of ids, or the word `due`.
  `due` means every ADR in `shape_due`, read when the call starts. It is refused with any mode but
  `shape`.
  - The call runs one shape pass per ADR, in the order given (`due`: `shape_due`'s order), each
    with its own `sh-` id, each taking and releasing the lock as a single pass does today.
  - Plain `run` prints one JSON object, `{"runs": [<each pass's result as today>]}`. It exits 0
    when every pass reported, else 1.
  - With `--detach`, one detached process runs the passes in turn. The call returns once the first
    pass is recorded running, printing `outcome: started` and `review_ids`, every id assigned up
    front.
  - `--adr due` with nothing due exits 3 with `outcome: not_due` and launches nothing.
  - A single id behaves exactly as today, output included.
- **`cli.py`:** the `--adr` help says "shape: the ADR(s) to shape, comma-separated, or `due` for
  every ADR `ccp architect due` lists", and the usage line in the module docstring follows.
- **`docs/cli/03-quality.md`:** the `ccp architect` row shows `[--adr ID[,ID…]|due]`.
- **SPEC (§31.1, describing this task's own feature):**
  - §19.7 step 2. CURRENT (`docs/spec/03-quality.md` at `58cf1d0`): "then run a fresh
    `claude -p "/architect …"` from the product root:". PROPOSED: "then run a fresh
    `claude -p "/architect …"` in the pass's own worktree, `arch-<review id>` under the worktree
    directory (§12.1), made detached at `head` and removed when the run ends, so a checkout that moves
    during the pass changes nothing the pass reads:".
  - §19.5, the `shape` bullet, gains a last sentence: "`--adr` takes several ADR ids, comma-separated,
    or `due`, every ADR `ccp architect due` lists in `shape_due`; one call then runs a shape for
    each, one after another."
  - §12.1, after the `merge-<nnnn>` bullet, a new bullet: "`arch-<review id>` is an architect pass's
    own worktree (§19.7), not a `ccp wt` kind and not recorded: the pass makes it detached at the head
    it reviews and removes it when it ends, as does the check that marks a dead pass `failed`."
- **Tests** in `tests/test_architect.py`. The stub also writes its working directory beside its
  argv.
  - A pass's headless call ran in `<worktrees dir>/arch-<review id>`, at the recorded `head`.
  - That directory is gone afterwards, after a pass that reported and after one that failed.
  - A commit made in the product root while the pass runs does not change what the pass read. The
    stub reads a file at its start, sleeps, and reads it again, while the test commits a change to
    the file in the product root.
  - `--adr due` with two ADRs due makes two `sh-` reports in `shape_due` order. With none due, it
    exits 3. The test's name contains `due`.
  - `--adr 31,32` makes two reports in that order. The test's name contains `comma`.
- **Out:** running shape passes at once (a §19.6 change), the triage of shape reports, and the
  architect's lenses and prompt.

## dod_checks

- id: `ar-01`
  story: As a lead, a pass reads the commit it names, whatever its caller's checkout does meanwhile.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_architect 2>&1 | tail -60`.
  expect: exit 0. The output lists the Scope's tests by name: the cwd test, the removal test after a
    reported pass and after a failed one, and the moving-checkout test, each `ok`.
  dry run (`58cf1d0`): 30 tests, OK; none of the new tests exists yet.

- id: `ar-02`
  story: As a plane developer, the worktree tests bite.
  setup: a copy of the PR head (`git worktree add --detach <tmp> HEAD`) in which `cmd_run`'s
    headless call runs with `cwd=str(cfg.root)` again.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_architect`.
  expect: at least one failure, naming the cwd test or the moving-checkout test.
  dry run: n/a — the tests are new.

- id: `ar-03`
  story: As a lead, one call shapes every ADR due.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_architect 2>&1 | grep -i 'due\|comma'`.
    2. Run `ccp --root . architect run --help`.
  expect: step 1 shows the `--adr due` test (two reports, then exit 3 with nothing due) and the
    comma-list test as `ok`. Step 2's `--adr` help names `due` and comma-separated ids.
  dry run (`58cf1d0`): step 2 prints `--adr ADR  shape: the ADR to shape`.

- id: `ar-04`
  story: As the SPEC reader, the pass's worktree and the multi-ADR call are described.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -c 'from the product root' docs/spec/03-quality.md`.
    2. Run `tr -s '[:space:]' ' ' < docs/spec/02-delivery.md | grep -c 'is an architect pass.s own worktree (§19.7), not a .ccp wt. kind'`.
    3. Run `tr -s '[:space:]' ' ' < docs/spec/03-quality.md | grep -c 'in the pass.s own worktree, .arch-<review id>. under the worktree directory'`.
  expect: step 1 prints 0; steps 2 and 3 each print 1.
  dry run (`58cf1d0`): 1, 0 and 0.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
