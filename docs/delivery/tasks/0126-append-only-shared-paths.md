---
task_id: 0126-append-only-shared-paths
title: Paths that tasks only append lines to do not keep two runners apart, and close merges them as a line union
status: pending
kind: feature
depends_on: []
spec_refs: ["S16"]
review_point: R8
sign_off: brief
paths: ["ccp/parallel.py", "ccp/lifecycle.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/02-delivery.md", "tests/test_parallel*.py", "tests/test_tasks_close.py"]
adopt: "plane.json parallel.shared listing the paths tasks only append lines to, such as a package doc's file map"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0126-append-only-shared-paths
## Intent

Two runners can hold two tasks that each add a line to the same index file (a package doc's file
map, a changelog), and the second to close merges both lines without a fix round, while a real
conflict in such a file still stops close.

## Context (not checked)

- A product's tasks nearly all add one line to the file map of the package doc they touch, so the path rule
  (§16.3) kept most pairs of its tasks apart and its second runner idled (a product's report,
  2026-11-17).
- Close's catch-up today needs a clean merge and a tip that changes no file the task changes, so
  even two appended lines in one file send the task back to its implementer.
- A union is safe only when both sides only added lines: a hunk that changes or removes an existing
  line is a real conflict.

## Scope

- **In:**
  - `ccp/config.py`, `contracts/plane_config.schema.json`: `parallel.shared`, a list of paths and globs
    (default empty), validated like `parallel.exclusive`; a path in both is refused (exit 2).
  - `ccp/parallel.py`: rule 3 ignores a meeting of two paths both covered by `parallel.shared`.
  - `ccp/lifecycle.py`: close's catch-up merge resolves a conflict confined to `parallel.shared` paths,
    where each side's hunks only add lines, as the tip's lines followed by the task's; any other
    conflict refuses as today, naming the file.
  - `docs/spec/02-delivery.md` §16.3, rule 3. CURRENT (at `b4de6ad`): "3. No path of C meets a path of a task in A (equal, one a directory holding the other, or a glob or bare name of one matching the other)." PROPOSED:
    > 3. No path of C meets a path of a task in A (equal, one a directory holding the other, or a glob or bare name of one matching the other), unless both are covered by a `parallel.shared` entry.
  - `docs/spec/02-delivery.md` §16.3, after the sentence on `exclusive`. CURRENT (at `b4de6ad`): none (new sentence). PROPOSED:
    > `shared` (empty by default) lists paths and globs that tasks only append lines to, such as a package doc's file map; two tasks may hold one at once (rule 3), and close merges them as §16.5 rule 4 says. A path may not be both `shared` and `exclusive`.
  - `docs/spec/02-delivery.md` §16.5 rule 4. CURRENT (at `b4de6ad`): "When the merge with the tip is clean, the tip's new commits change no file the task's own diff or declared paths change, and no build sign-off is due on the task (§3.5), close merges the tip into the verified head itself," PROPOSED:
    > When the merge with the tip is clean, or its only conflicts are in `parallel.shared` paths where both sides only added lines (resolved as the tip's lines, then the task's), the tip's new commits change no file the task's own diff or declared paths change other than a `parallel.shared` path, and no build sign-off is due on the task (§3.5), close merges the tip into the verified head itself,
  - `docs/spec/02-delivery.md` §16.3's plane.json example: `"shared": []` in the `parallel` block (§31.1).
- **Out:**
  - Shared paths in the single-runner flow beyond the catch-up merge.
  - Ordering the appended lines (the tip's come first).

## dod_checks

- id: `cmd-01`
  story: As a second runner, I claim a task that only shares an append-only file.
  setup: a scratch product with `parallel.max_in_flight` 2 and `parallel.shared` `["docs/*/README.md"]`; task A in flight with paths `["src/a.py", "docs/a/README.md"]`; pending task B with `["src/b.py", "docs/a/README.md"]`.
  steps:
    1. Run `ccp tasks claim B`.
  expect: exit 0; with `parallel.shared` empty the same claim exits 7 naming rule 3.
  dry run: n/a.
- id: `cmd-02`
  story: As close, I merge two appended lines myself.
  setup: a scratch repo where the tip and the verified task head each append a different line to `docs/a/README.md` from the same base, the file covered by `parallel.shared`, and a gate lane that passes.
  steps:
    1. Run `ccp tasks close <task>`.
  expect: the task merges; the file holds the tip's line, then the task's; the verification record names the catch-up.
  dry run: n/a.
- id: `cmd-03`
  story: As close, a changed line in a shared file still stops me.
  setup: the repo of cmd-02, but the tip changes an existing line of the file that the task also changes.
  steps:
    1. Run `ccp tasks close <task>`.
  expect: exit non-zero, naming `docs/a/README.md`; nothing merges.
  dry run: n/a.
- id: `cmd-04`
  story: As a product, a contradictory config is refused.
  setup: a scratch product listing `docs/x.md` in both `parallel.shared` and `parallel.exclusive`.
  steps:
    1. Run `ccp tasks next`.
  expect: exit 2, naming `docs/x.md`.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §16.3 and §16.5 edits with the PROPOSED text above.
  expect: they match word for word, and no other § rule changes.
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

- 2026-11-17 (implementer): `parallel.shared` is in `PARALLEL_DEFAULTS` and the plane_config schema; config
  loading refuses a non-list and an entry listed in both `shared` and `exclusive` (compared as written, a
  leading `./` and a trailing `/` aside), naming it. `parallel.covered(p, entries)` says a path lies wholly
  within a shared entry: equal, under a directory entry, matched by a glob entry, or ending in a bare-name
  entry; a glob or directory path is covered only by an equal entry or a directory holding it. Rule 3
  skips a meeting when both paths are covered.
- Close's catch-up: `_catch_up_commit` reads `git merge-tree -z` stages; when every conflicted path is
  covered and each side only adds lines to the base (every base line kept, in order), `_union` writes the
  file as the base lines with, at each place, the tip's added lines then the task's, and `_tree_with`
  swaps it into the merge tree through a scratch index. Any other conflict refuses as before, naming the
  files. The overlap check leaves out shared paths. The record's `catch_up.merge_tree` is `union` when a
  union was made (the verification contract's enum gains the value; no new key, no record version bump).
- The §16.2 edits sit in §16.2 (the knob), where the `exclusive` sentence and the plane.json example are;
  the task called that place §16.3. README's knob table gains a `parallel.shared` row. The catch-up tests
  live in `tests/test_behind_tip_catch_up.py`, beside its fixture.

## Verification notes
