---
task_id: 0327-init-keeps-an-empty-task-log-in-git-and-checks-build-scratch-products-with-sandbox-create
title: ccp init keeps an empty task log in git, so a fresh clone of a new product passes tasks check and docs check; the writing-tasks skill has a check that needs a scratch product build it with ccp sandbox create in the step that uses it
status: done
kind: feature
depends_on: []
spec_refs: ["S4", "S21"]
review_refs: ["ar-20261124T205520Z-4ce8#F01"]
review_point: R34
paths: ["ccp/init.py", "tests/test_init.py", "docs/spec/01-model.md", "plugin/skills/writing-tasks/SKILL.md"]
clashes_with: ["0191-the-grace-release-ends"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0327-init-keeps-an-empty-task-log-in-git-and-checks-build-scratch-products-with-sandbox-create

## Intent

A product adopted with `ccp init` and committed can be cloned and checked at once: init leaves a file in its empty
task log directory, so git carries the directory and a fresh clone passes `ccp tasks check` and `ccp docs check`
instead of failing with `docs/delivery/tasks: missing`. And a task writer whose check needs a scratch product builds
it in the step that uses it with `ccp sandbox create`, so `ccp tasks dry-run` and every seat run that check whole,
instead of each reviewer and verifier hand-building a scratch repo from a prose `setup:` with `<checkout>`,
`<product>` and `<q>` placeholders.

## Context (not checked)

Finding F01 of architect pass `ar-20261124T205520Z-4ce8` (`docs/delivery/reviews/ar-20261124T205520Z-4ce8.md`) and
the lead's friction note T99 (a new product adopted on 24 Nov, flagged STALE by `release.sh`).

Measured at `cd3a6bf5`:

- **T99.** `ccp/init.py` makes the task log with `"(root / "docs" / "delivery" / "tasks").mkdir(parents=True,
  exist_ok=True)"` and writes no file in it; git tracks no empty directory. In a sandbox
  (`CCP_DEV=1 ./bin/ccp sandbox create "$D"`, which commits what init wrote), `git -C "$D/product" ls-files
  docs/delivery/tasks` printed nothing; a clone of `"$D/product"` gave `tasks check` `docs/delivery/tasks: missing —
  the task log lives here`, exit 1, and `docs check` the same line, exit 1. The same clone with an empty
  `docs/delivery/tasks/.gitkeep` committed printed `tasks: clean (0 tasks)`, exit 0, and `docs: clean`, exit 0. Two
  test fixtures already write that file (`git grep -n gitkeep -- tests` at `cd3a6bf5`: `tests/test_run_checkout_upgrade.py`
  and `tests/test_sync_on_release.py`, the second commented "git keeps no empty task log").
- **F01.** `git grep -n sandbox -- plugin/skills/writing-tasks/SKILL.md` at `cd3a6bf5`: nothing. `ccp sandbox create
  DIR` takes a new or empty directory (so `mktemp -d` serves), commits what init wrote and prints the `env` lines
  (SPEC §29.3). Run with `--root "$D/product"` from the checkout, a command inside the sandbox is sealed to its binding
  and queue; with `QUEUE_ROOT` exported to a path outside it, it refuses: `ccp: QUEUE_ROOT=… names a path outside the
  sandbox …; unset it` (exit 2, measured at `cd3a6bf5`), which the fence intends, so the step unsets it.
- **Ruled.**
  - `"def init"` (`ccp/init.py`, where it makes the task log) writes an empty `docs/delivery/tasks/.gitkeep`
    when the task log directory holds no file, and lists it as written; with a file there (a task, or a `.gitkeep`) it
    writes nothing more there. A rerun on such a product changes nothing, as init's other files. The tests are
    `test_an_empty_task_log_gets_a_gitkeep` and `test_a_task_log_holding_a_file_gets_none` in `tests/test_init.py`
    (class `Adopt`).
  - `plugin/skills/writing-tasks/SKILL.md`, *Commands and searches in checks*, gains this bullet, after the bullet
    on a check of a `ccp` command:

    > - **A check that needs a scratch product** builds it in the step that uses it, with `ccp sandbox create` on a
    >   new temporary directory, and runs `ccp` there with `--root`, so `ccp tasks dry-run` runs the step whole:
    >   ``D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && env -u QUEUE_ROOT -u
    >   PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$D/product" tasks check`` (the plane's own repo). A setting the
    >   check needs is written into `"$D/product"` in the same step. A sandbox refuses an exported `QUEUE_ROOT` or
    >   `PROJECT_YAML` outside it (plane SPEC §29.3), so the step unsets them. No step names a `<…>` placeholder but
    >   the verifier's `<your run>`.

  - House rule E21 states the same rule; this triage applied it.
- **§31.1.** The §4.5 bullet only describes this task's fix (`git grep -n gitkeep -- docs/spec` at `cd3a6bf5`:
  nothing).

## Scope

- **In:** `ccp/init.py`; `tests/test_init.py`; `plugin/skills/writing-tasks/SKILL.md` (the bullet above, word for
  word); `docs/spec/01-model.md`, §4.5, §31.1:

  CURRENT (`docs/spec/01-model.md` at `cd3a6bf5`), §4.5, the bullet after "A product is adopted by running `ccp init`
  in its repository. It writes:" that names the adoption point:
  > - in a `plane.json` it writes, the architect's adoption point (`architect.shape_from_task`, the next task number, §19.11), and the starter house rules unless the product has a rules doc (§20.5);

  That bullet stays as it is; a new bullet follows it.

  PROPOSED:
  > - an empty `docs/delivery/tasks/.gitkeep` when the task log directory holds no file, so a clone of the product has its task log;

- **Out:** `ccp tasks check` or `ccp docs check` accepting an absent task log; `ccp sandbox` itself; rewriting
  existing tasks' checks; the reviewer's and verifier's briefs.

## dod_checks

- id: `cmd-01`
  story: As an operator adopting a product, a fresh clone of it passes tasks check and docs check.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && git clone -q "$D/product" "$D/clone" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$D/clone" tasks check; echo "exit $?"`.
    2. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && git clone -q "$D/product" "$D/clone" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$D/clone" docs check >/dev/null 2>&1; echo "exit $?"`.
  expect: step 1 prints `tasks: clean (0 tasks)` and `exit 0`; step 2 prints `exit 0`.
  dry run (`cd3a6bf5`): step 1 printed `tasks: 1 failure(s)`, `docs/delivery/tasks: missing — the task log lives here`, `exit 1`; step 2 printed `exit 1`.
- id: `code-01`
  story: As an operator, init writes the task log's .gitkeep only when the log holds no file.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_init.Adopt.test_an_empty_task_log_gets_a_gitkeep tests.test_init.Adopt.test_a_task_log_holding_a_file_gets_none tests.test_init`.
  expect: exit 0.
  dry run (`cd3a6bf5`): exit 1 (the named tests do not exist yet: `AttributeError: type object 'Adopt' has no attribute 'test_an_empty_task_log_gets_a_gitkeep'`).
- id: `doc-01`
  story: As a task writer, the writing-tasks skill shows me a step that builds a scratch product with ccp sandbox create and unsets the queue it refuses.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'env -u QUEUE_ROOT' plugin/skills/writing-tasks/SKILL.md`.
  expect: prints a number of at least `1`.
  dry run (`cd3a6bf5`): printed `0`, exit 1.
- id: `spec-01`
  story: As the operator, §4.5 says init keeps an empty task log in git.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0327`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`cd3a6bf5`, with this brief): exit 1, the PROPOSED passage missing (`not found in the SPEC`).

## Implementation notes

- Premises re-measured at `c9774ca5`: `ccp/init.py` still makes the task log with a bare `mkdir`; `git grep -n
  gitkeep -- tests` gives the same two fixtures, and `-- docs/spec` nothing; `git grep -n sandbox --
  plugin/skills/writing-tasks/SKILL.md` nothing. 1706f4b1 touched only `tests/test_init.py`'s imports and fixture
  helpers, not the class this task adds to.
- `ccp/init.py`: after the task log directory is made, an empty `.gitkeep` is written and listed in `written` when
  no file sits directly in the directory. "Holds no file" is read literally: a file directly in it, not one in a
  subdirectory. When a file is there nothing is written and nothing listed (not in `kept` either: the file may be
  the product's own task, not init's). The path is the one the `mkdir` makes, `docs/delivery/tasks`, not
  `task_log.dir` from a kept plane.json, as before this task.
- `--force` does not rewrite an existing `.gitkeep`: the ruling writes nothing more once a file is there.
- SPEC §4.5 gains the PROPOSED bullet after the adoption-point bullet; the writing-tasks skill gains the ruled bullet
  word for word after the bullet on a check of a `ccp` command.
- Fix round 1 (review MINOR 1): `Adopt` gains a case for a task log holding only an empty subdirectory, which git
  drops: init writes and lists `.gitkeep`. It pins the "a file directly in it" reading, which no test pinned
  before; a mutant that counts any entry survived `Adopt` and is now killed.

## Verification notes
- 2026-11-24 — verifier, PR #401 head `f1e92ed` (squash `162d9cd`): APPROVE. Passed: cmd-01, code-01, doc-01, spec-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0327-init-keeps-an-empty-task-log-in-git-and-checks-build-scratch-products-with-sandbox-create.json.

