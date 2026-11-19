---
task_id: 0193-leak-check-finds-its-denylist
title: The leak check finds the installation's denylist when CCP_LEAK_DENYLIST is unset, so the gate checks for real
status: pending
kind: feature
depends_on: ["0175-one-binding-reader"]
spec_refs: ["S8"]
rule_refs: ["E3"]
review_point: R12
paths: ["scripts/leak-check.sh", "tests/test_leak_check.py", "tests/test_self_hosting.py", "docs/ENGINEERING.md"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0193-leak-check-finds-its-denylist

## Intent

House rule E3's check, `scripts/leak-check.sh` (the `leak-check` entry in `docs.checks`), reads its
patterns from a local denylist named by `CCP_LEAK_DENYLIST`. When that variable is unset, it prints
"nothing checked" and passes. Workers and the gate run without the variable, so every task's leak
check has passed without looking. A product name inside an identifier and a local absolute path both
reached `main` that way, and a later fix removed them. With this task, the check finds the
installation's denylist on its own, so the gate checks for real. It still passes without a denylist
on an installation that keeps none, such as a fresh clone of the open-source repo.

## Context (not checked)

- The denylist is local and untracked, because it names what must not appear. It sits beside the
  installation's bindings as `leak-denylist.txt`, in the bindings directory (§8.3,
  `scripts/observability/lib.py` `bindings_dir()`, which `CCP_BINDINGS_DIR` overrides).
- A worker runs in a worktree, whose own `projects/` does not exist. The installation's bindings
  directory is the one beside the binding that `ccp where` (from PATH) resolves. It prints `binding`
  and `plane`.
- Tests are fenced (`tests/__init__.py`): they set `CCP_BINDINGS_DIR` to a temp dir and never read the
  real installation.

## Scope

- `scripts/leak-check.sh` looks for the denylist in this order:
  1. `CCP_LEAK_DENYLIST`, as today. When it is set but names a missing file, the check exits 2, as
     today.
  2. When `CCP_BINDINGS_DIR` is set, it is authoritative: `leak-denylist.txt` in it, or no
     denylist. Step 3 does not run. This keeps tests fenced, because `tests/__init__.py` sets it.
  3. Otherwise, `ccp where --root <the repo being checked>`, run from PATH. Its JSON names
     `binding`, and the denylist is `leak-denylist.txt` in that binding's directory. When there is
     no `binding`, it is `<plane>/projects/leak-denylist.txt`. If `ccp` is missing, exits non-zero
     or prints output that doesn't parse, the step falls through quietly, which matters under
     `set -euo pipefail`.
- The first file found is used. Stdout names its source, never its path:
  `leak-check: denylist found (CCP_LEAK_DENYLIST)` or `leak-check: denylist found (bindings dir)`. A
  local absolute path never reaches gate output, verifier notes or PR bodies.
- The script's header comment describes the lookup.
- When none is found, it prints `leak-check: no denylist found (CCP_LEAK_DENYLIST, the bindings
  directory): nothing checked` and passes, as today.
- E3's check line in `docs/ENGINEERING.md` names the fallback.
- New `tests/test_leak_check.py`:
  - a denylist in a temp `CCP_BINDINGS_DIR` is found and a match fails the check;
  - `CCP_LEAK_DENYLIST` wins over it;
  - a `CCP_BINDINGS_DIR` with no denylist means "nothing checked", even when a stub `ccp` on PATH
    would name one;
  - with `CCP_BINDINGS_DIR` unset, a stub `ccp` whose `where` names a temp binding finds the
    denylist beside it (lookup step 3, the path workers take);
  - with neither, the check passes with the "nothing checked" line.

  Every test runs the script against a temp git repo with `ccp` hidden from PATH, or replaced by a
  stub, and never reads the real installation. `tests/test_self_hosting.py`'s existing leak-check
  test keeps passing, or moves into the new module.

Out of scope: the patterns themselves (local), and any other docs check.

## dod_checks

- id: `lk-01`
  story: As the plane, a worker's gate checks for leaks with no variable set.
  setup: a checkout of the PR head, on this installation, where the bindings directory holds
    `leak-denylist.txt`.
  steps:
    1. Run `env -u CCP_LEAK_DENYLIST -u CCP_BINDINGS_DIR scripts/leak-check.sh; echo rc=$?`.
  expect: the output contains `leak-check: denylist found (bindings dir)`, and either
    `leak-check: clean` with `rc=0` or a match list with `rc=1`. It contains no `nothing checked`
    and no absolute path. Record only the rc and the first line in the verification notes.
  dry run (`9d36e52`): `leak-check: no denylist (CCP_LEAK_DENYLIST unset): nothing checked`, rc=0,
    so the expect fails today.
- id: `lk-02`
  story: As a plane developer, the lookup order is tested and the tests bite.
  setup: a checkout of the PR head; then a copy in which step 2 of the lookup (the
    `CCP_BINDINGS_DIR` file) is deleted from `scripts/leak-check.sh`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_leak_check`.
    2. In the copy, run the same.
  expect: step 1 passes; step 2 fails with at least one failure.
  dry run (`9d36e52`): `tests/test_leak_check.py` does not exist.
- id: `lk-03`
  story: As someone with a fresh clone and no denylist, the check still passes.
  setup: a checkout of the PR head.
  steps:
    1. Run `env -u CCP_LEAK_DENYLIST CCP_BINDINGS_DIR=$(mktemp -d) PATH=/usr/bin:/bin
       scripts/leak-check.sh; echo rc=$?`.
  expect: the output contains `nothing checked` and `rc=0`.
  dry run (`9d36e52`): `nothing checked`, rc=0 (a regression guard: this case must not change).
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, then
       `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
