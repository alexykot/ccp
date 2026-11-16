---
task_id: 0104-command-edge-fixes
title: suite affected, sign-off --at, wt exec and main_of handle their edge cases
status: pending
kind: fix
depends_on: []
spec_refs: ["S3", "S12", "S14"]
review_point: R6
paths: ["ccp/cli.py", "ccp/suite.py", "ccp/lifecycle.py", "ccp/wt.py", "ccp/refs.py", "docs/spec/01-model.md", "tests/test_suite_affected.py", "tests/test_sign_off.py", "tests/test_wt.py", "tests/test_merge_base.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0104-command-edge-fixes

## Intent

Commands that misread an input or crash on one now handle it. Each fix below has a test that fails
without it.

## Context (not checked)

- Accepted plane proposals (operator, 2026-11-16: all approved), the follow-ups of earlier tasks.
- `ccp suite affected`:
  - Git reads a `--since` that starts with a dash as an option.
  - The basename-only name match lists nearly every test for an extension-less path or a directory.
  - `--paths` is not normalised.
- `ccp tasks sign-off --at` compares a date-only value with the local date, but a time with an offset
  with UTC now.
- `ccp wt exec`:
  - A malformed `--timeout` gives a traceback.
  - A SIGTERM before the worktree exists exits with no result JSON.
  - Between `create` returning and its record being bound in `run_on_base` there is a small window
    where a worktree can leak.
- `main_of`, from a linked worktree of a repository with a separate git dir, returns the checkout
  itself.
- Lead ruling, spec question sm-20261116T211348Z-6642 (2026-11-16, verbatim):
  (1) Keep as built: a malformed `wt exec --timeout` exits 2; a base run's bad --timeout stays 125 per
  SPEC 12.1. No 12.1 edit.
  (2) Add to SPEC 14.7 in this PR, as description (section 31.1): "A path matches tests by name only
  when it has an extension and is not a directory; --paths are normalised relative to the root (./
  stripped, .. collapsed), and one outside the root is refused (exit 2)." Adjust the wording to what
  the code does. Make no other SPEC change beyond what the task already gave. Quote the replaced 14.7
  text (the text before your edit) in the PR body.
  (3) The SPEC 3.5 sentence you wrote is within intent (the task's Scope calls for it); no operator
  sign-off.

## Scope

- **In:**
  - `suite affected`:
    - pass `--since` after `--` (or as `--since=<ref>` resolved with `rev-parse --verify`);
    - match a test by name only for a path that has an extension and is not a directory;
    - normalise `--paths` (strip `./`, collapse `..`, relative to the root).
  - `sign-off --at`: one rule. A date-only value is a UTC date, compared with today's UTC date, and the
    SPEC §3.5 sentence says so.
  - `wt exec`:
    - a malformed `--timeout` refuses with exit 2 and a message;
    - a SIGTERM before the worktree exists emits the result JSON with `signal: 15` and no worktree;
    - the leak window in `run_on_base` is closed by binding the record before anything can be
      interrupted, or by cleaning up on the signal.
  - `main_of` returns the main checkout for a linked worktree of a separate-git-dir repository.
- **Out:**
  - New flags, or any rule beyond what Scope names.

## dod_checks

- id: `check-01`
  story: As a worker, `suite affected` lists the tests a change touches, and no more.
  setup: a throwaway product with tests named after modules, a `Makefile` at the root, and a
    directory `pkg/`.
  steps:
    1. Run `ccp suite affected --since -x`.
    2. Run it with `--paths Makefile`, `--paths pkg/`, and `--paths ./pkg/../pkg/mod.py`.
  expect: (1) refuses as an unknown ref, not as an option error. (2) The first two do not list every
    test whose name contains the basename. The third lists what `--paths pkg/mod.py` lists.
  dry run: n/a.
- id: `check-02`
  story: As a lead, `--at` means one thing.
  setup: a task with a sign-off due, and the local zone set to UTC-10 late in the day, so that the
    local date is behind the UTC date.
  steps:
    1. Record with `--at <today's UTC date>`.
  expect: accepted. A date after today's UTC date is refused.
  dry run: n/a.
- id: `check-03`
  story: As a runner, `wt exec` fails cleanly.
  setup: a throwaway product.
  steps:
    1. Run `ccp wt exec --timeout abc …`.
    2. Send SIGTERM to `ccp wt exec` before its worktree is made (a test hook or a slow `merge_base`).
  expect: (1) exit 2 with a message and no traceback. (2) Exit 143 and a result JSON with `signal:
    15`, with no worktree or record left.
  dry run: n/a.
- id: `check-04`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-16 (implementer):
  - `suite affected`: `cli.main` passes the word after `--since` as `--since=<word>`, so argparse takes a
    ref that starts with a dash. `changed_paths` resolves the ref with
    `git rev-parse --verify --quiet --end-of-options <ref>^{tree}` and diffs against the resolved sha,
    so git never reads the ref as an option. A ref it cannot resolve exits 2 and the message names the
    ref. `--paths` are normalised with `posixpath.normpath`, relative to the root; one that leaves the
    root exits 2. The name match keeps only names with an extension that are not a directory on disk.
    A directory passed as a path therefore matches by neither module nor name; it is not expanded into
    its files (Scope names no expansion).
  - `sign-off --at`: a date-only value is compared with `now().date()`, today's UTC date. The SPEC §3.5
    sentence and the `--at` help say it is a UTC date.
  - `wt exec`: `--timeout` is refused with exit 2, as on any kind other than base (§12.1). On a base
    run, a malformed `--timeout` still exits 125, its own refusal under §12.1. The check now accepts
    ASCII digits only, so a value such as `²` (which `isdigit()` accepts but `int()` rejects) no longer
    gives a traceback.
  - `run_on_base`: `create` takes a `bind` dict and puts the new worktree's record in it as the first
    thing in its guarded block. `run_on_base` passes its own record as that dict. A SIGTERM after the
    worktree exists, even one that arrives before `create` returns, therefore finds the record bound,
    and the cleanup removes the worktree. The cleanup removes only what is still there, so a worktree
    `create` already removed is not removed twice. A SIGTERM before the worktree exists now returns
    the result with `name: null`, `merge_base` (null if not yet known), `exit: 143`, `signal: 15` and
    `removed: true`, and `ccp` prints it as JSON.
  - `main_of`: git keeps no path from a separate git dir to its main checkout. For a linked worktree of
    such a repository, it looks for the directory whose `.git` file names the common dir. The search
    covers the ancestors and siblings of the checkout and of each linked worktree registered under
    `<common>/worktrees/*/gitdir`. When none is found it returns the checkout, as before.
- 2026-11-16 (implementer, ruling round 1):
  - Ruling (1) and (3) change nothing: the `wt exec --timeout` refusal (exit 2) and the §3.5 sentence
    stay as built.
  - Ruling (2): SPEC §14.7 now describes what `suite affected` does with `--paths` and the name match.
    The change bullet says `--paths` are normalised relative to the product root (`./` stripped, `..`
    collapsed, an absolute path made relative); the Python bullet says only a path that has an
    extension and is not a directory matches tests by name. The refusal of a path outside the root
    (exit 2) was already in §14.7's last bullet, so it is not repeated. No code or test change.
- 2026-11-16 (implementer, fix round 1):
  - Review MAJOR 1: a SIGTERM while `git worktree add` ran, or just after it returned, reached
    `run_on_base` before `create` had bound the record, so the worktree leaked and the result said
    nothing was left. `create`'s `add` now runs inside `_sigterm_held`: while a base run's handler
    (`_on_sigterm`) is installed, a SIGTERM is held until the make has finished and, when it
    succeeded, the record is bound; the held signal is raised then, and `run_on_base`'s cleanup removes
    the worktree. Holding it, not cleaning up after it, means `git worktree add` is never killed
    half-way (which would leave a locked, half-made entry). A failed `add` binds nothing, so a path
    another worker took is never removed as ours. Elsewhere (another kind, another thread)
    `_sigterm_held` changes nothing.
  - Review NIT 2: the §14.7 sentence says a dotfile such as `.gitignore` has no extension, so it
    matches no test by name. NIT 1 (a range as `--since` is refused) is accepted as the task's
    consequence; no change.

## Verification notes
