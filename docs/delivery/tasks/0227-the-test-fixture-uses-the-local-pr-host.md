---
task_id: 0227-the-test-fixture-uses-the-local-pr-host
title: The shared test fixture runs on the local PR host, and the fake gh goes
status: done
kind: refactor
depends_on: ["0222-a-product-without-github-uses-the-local-pr-host"]
clashes_with: ["0241-gate-module-tests-wiring-only", "0242-retire-restructure-scaffolding-and-queue-markers"]
review_refs: ["sh-20261120T235116Z-eb9f#F04"]
rule_refs: ["E2", "E15"]
review_point: R15
paths: ["tests/test_toolkit.py", "tests/test_behind_tip_catch_up.py", "tests/helpers.py", "tests/CLAUDE.md", "docs/design/toolkit.md", "docs/ENGINEERING.md"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0227-the-test-fixture-uses-the-local-pr-host

## Intent

The fixture most of the suite builds on, `ToolkitFixture`, carries a fake `gh` written in test code
that clones origin, squash-merges the task branch and records the merge commit: a second copy of
what the local PR host (0222) now does for real. It runs as a fresh interpreter for every call. After
this task the fixture selects `pr_host.adapter: local`, the fake `gh` and its "head follows the branch"
variant are deleted, and the local adapter is tested end to end by every module that closes a task.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0040 (`sh-20261120T235116Z-eb9f`), F04.
- **The fake.** `tests/test_toolkit.py` `FAKE_GH` (`pr view` from a JSON file, `pr merge` clones,
  `merge --squash`, commits `Task NNNN: done (#n)`, pushes); `tests/test_behind_tip_catch_up.py`
  `FOLLOWING_GH` adds a head that follows `origin/<branch>`
  (`grep -n 'FOLLOWING_GH = FAKE_GH.replace' tests/test_behind_tip_catch_up.py` at `8aefa59`: one line).
- **Its reach.** `git grep -l ToolkitFixture -- tests` at `8aefa59`: 63 files, among them the slowest
  module, `tests.test_behind_tip_catch_up`.
- **House rule E2** says tests use no GitHub; the shape proposed adding "end-to-end tests use the local
  PR host". The triage deferred that clause to this task (finding E2, deferred), since it is true only
  once the fixture moves.
- **Clashes with R16's 0241 and 0242.** 0241 cuts `tests/test_behind_tip_catch_up.py`, `tests/helpers.py`
  and other gate modules down to wiring; 0242 edits `tests/test_toolkit.py`. This task rewrites the
  same fixture, so it does not run beside either.
- A refactor: the tests' expectations stay, except where a test read the fake's own files
  (`merge-called`, `pr.json`), which then read the local PR record.

## Scope

- **In:** `tests/test_toolkit.py`, `tests/test_behind_tip_catch_up.py`, `tests/helpers.py`,
  `tests/CLAUDE.md`, `docs/design/toolkit.md`, `docs/ENGINEERING.md`.
- `ToolkitFixture` writes `"pr_host": {"adapter": "local"}` in its product's plane.json and opens
  its PR with the local adapter's `open`; `FAKE_GH` and `FOLLOWING_GH` are deleted, and so is the
  fixture's `CCP_GH_BIN`. A test that pinned the fake's files reads the PR record
  (the local adapter's, 0222) instead.
- The GitHub adapter keeps its argv-recording stub only in its own tests (0226's and 0220's).
- `tests/CLAUDE.md` and `docs/design/toolkit.md` say the fixture uses the local PR host.
- House rule E2 gains "no forge (GitHub or other); end-to-end tests use the local PR host".
- **Out:** the GitHub adapter's own tests, and any test outside `ToolkitFixture`'s users.

## dod_checks

- id: `fx-01`
  story: As a plane developer, no test code re-implements a PR host.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -e FAKE_GH -e FOLLOWING_GH -- tests`.
  expect: prints nothing.
  dry run (`8aefa59`): prints the two definitions and their uses.

- id: `fx-02`
  story: As a runner, close still merges, confirms and reconciles on the fixture.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_toolkit tests.test_behind_tip_catch_up 2>&1 | tail -3`.
  expect: exit 0, `OK`, with as many tests as at the PR's base.
  dry run (`8aefa59`): `OK`.

- id: `fx-03`
  story: As a plane developer, the fixture really exercises the local adapter.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    local adapter's merge no longer pushes.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_toolkit`.
  expect: at least one failure.
  dry run: n/a — the local adapter is 0222's.

## Implementation notes

- `ToolkitFixture` writes `"pr_host": {"adapter": "local"}` in its plane.json and no longer builds a `gh`, a
  `ghstate` directory or `CCP_GH_BIN`. It gains `PR` (the number the local host gives its first PR, `"1"`),
  `open_pr()` (the host's `open` for the pushed task branch), `pr_record()` (the host's record) and
  `assert_pr_not_merged()`; `_push_task_work()` is the claim, commit, push and open that `_to_approved_pr()` builds on.
- Where a test read the fake's files, it reads the record: `merge-called` absent became "record open, no
  `merge_commit`"; `--match-head-commit X` became "record merged at head X"; the fake's `refuse-merge` file
  became a pre-receive hook on origin that refuses the merge's push to `main`. A merge by hand is
  `ccp pr merge`. Literal `--pr 7` on a real PR became `self.PR`.
- Where a test opened a review on a PR the fake answered for without a record (the fake's body read
  answered for any PR), the test now pushes the task branch and opens the PR first
  (`test_review_tip_gate`, `test_run_abandon`), else the body gate's warning is a second warning.
- `test_wt_outside` now sees close's merge checkout twice: the local host's squash runs in it.
  The test asserts the set of checkouts made is the sibling `merge-0002`.
- `test_tasks_close` keeps its "PR number as given" check with `01`, the local host's read of `1`.
- `test_prompt_pr_body` is a GitHub adapter test (a stub `gh`, its argv): it sets `pr_host.adapter: github`
  for its own class, and its stub's env var is renamed so `fx-01`'s grep is empty.
- `test_prhost_local` drops its `PLANE_JSON` override, now the fixture's default.
- `docs/ENGINEERING.md` E2, `tests/CLAUDE.md` and `docs/design/toolkit.md` say the fixture uses the local PR host.

## Verification notes
- 2026-11-21 — verifier, PR #281 head `4d6d5d3` (close's catch-up of the approved `4581044`, gate run st-20261121T182439Z-a95751) (squash `64efe0c`): APPROVE. Passed: fx-01, fx-02, fx-03. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0227-the-test-fixture-uses-the-local-pr-host.json.

