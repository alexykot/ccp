---
task_id: 0346-verify-spec-text-reads-the-working-tree-plane-built-takes-a-task-number-and-the-observability-scripts-and-release-are-tidied
title: ccp verify spec-text with no --head reads the working tree, so an uncommitted SPEC edit counts, with its signed §15.2 passage; ccp plane built takes a task's number; the observability doc stops inventorying ccp/lib.py and restating E7, and the doclang doc E18, and team.py puts the plane on sys.path once; release.sh fast-forwards from a fetched ref, not FETCH_HEAD
status: pending
kind: feature
depends_on: []
spec_refs: ["S15", "S29"]
review_refs: ["ar-20261125T094654Z-c8a0#F06", "ar-20261125T094654Z-c8a0#F07"]
review_point: R37
paths: ["ccp/verify.py", "ccp/upgrade.py", "docs/spec/02-delivery.md", "scripts/observability/CLAUDE.md", "ccp/doclang/CLAUDE.md", "scripts/observability/team.py", "scripts/release.sh", "tests/test_verify_spec_text.py", "tests/test_plane_built.py"]
clashes_with: ["0191-the-grace-release-ends"]
sign_off: brief
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0346-verify-spec-text-reads-the-working-tree-plane-built-takes-a-task-number-and-the-observability-scripts-and-release-are-tidied

## Intent

An implementer who has edited the SPEC for a signed-text task learns from `ccp verify spec-text` whether the
passages are there before committing, instead of spending a run to find the command read only committed text. The
plane session closes a proposal as built with the task's number, as every other task argument takes it. The
observability scripts' doc says what lives there and leaves `ccp/lib.py`'s map and house rule E7 to their own
homes, and `team.py` puts the plane root on `sys.path` once. A release run while runners fetch no longer fails on
git's fetch record.

## Context (not checked)

Findings F06 and F07 of architect pass `ar-20261125T094654Z-c8a0` (`docs/delivery/reviews/ar-20261125T094654Z-c8a0.md`),
and three follow-ups the lead passed to that pass: `ccp plane built --task` refusing a bare number, `team.py`'s
repeated `sys.path` lines (0331), and `scripts/release.sh`'s `git pull --ff-only`, which failed once with "Cannot
fast-forward to multiple branches" while runners fetched (git's `FETCH_HEAD` held several branches).

Measured at `704ca8de`:

- **F06.** `"head = head or \"HEAD\""` (`ccp/verify.py`, `"def spec_text"`) and `spec_hunks(cfg, base, head)` diff
  `base...HEAD`, so a SPEC edit not yet committed is reported missing. 0333's and 0338's implementers each spent a run
  on it.
- **F07.** `grep -c -e 'write_atomic' -e 'LEGACY_EVENT_TYPES' -e 'imports nothing from' scripts/observability/CLAUDE.md`:
  3; its first paragraph lists `ccp/lib.py`'s exports and restates E7's clause, which E26 forbids, and `ccp/CLAUDE.md`
  maps `lib.py` already. The triage widened E26's check grep (`imports nothing from`, `language-neutral`), which also
  finds `ccp/doclang/CLAUDE.md`'s "core code stays language-neutral (E18)", a restatement of E18; its "a
  language-neutral core" (line 3) names §21.5's design, not a rule, and stays.
- **team.py.** `grep -c 'sys.path.insert' scripts/observability/team.py`: 11. Two at module level (`HERE` and the
  plane root, `HERE.parents[1]`), which run on every import, including the tests' `spec_from_file_location` loads;
  nine inside functions re-insert the plane root.
- **plane built.** `"def merged_task(task_id: str)"` (`ccp/upgrade.py`) compares the whole id, so `--task 0340` is
  refused (`no merged plane task by that id`); `docs/cli/02-delivery.md` says "A task argument takes the full id or its
  number".
- **release.sh.** `grep -c 'pull -q --ff-only' scripts/release.sh`: 1 (`git -C "$MAIN" pull -q --ff-only`).

**Ruled.**

- **F06.** With no `--head`, `spec_text` diffs from the merge base of the base and `HEAD` to the working tree, reading
  each SPEC file (and a passage's named file) as it is on disk; with `--head`, as now. `named_hunks` follows the same
  rule. The body's `head` is `"working tree"` when none is given. A file git does not track is not read. New tests
  `tests.test_verify_spec_text.SpecText.test_with_no_head_an_uncommitted_spec_edit_is_found` and
  `tests.test_verify_spec_text.SpecText.test_with_head_given_an_uncommitted_spec_edit_is_not_read`.
- **F07.** `scripts/observability/CLAUDE.md`'s first paragraph, up to "is `ccp/architecture_review.py`.", becomes: "The
  scripts here are built on `ccp/lib.py`, which `ccp/CLAUDE.md` maps (house rule E7). `team.py` runs the runner
  teammate's lifecycle and the gate ledger, `spec_maintainer.py` spec questions to the lead (the open-question rule is
  `ccp/queue.py`'s, the headless launch `ccp/headless.py`'s). The review kit the architect seat runs on (§19) is
  `ccp/architecture_review.py`." The rest of the paragraph and the doc stay. In `ccp/doclang/CLAUDE.md`, "core code
  stays language-neutral (E18)" becomes "house rule E18".
- **team.py.** Keep the two module-level inserts; remove the nine in functions (and their `if … not in sys.path`
  guards). `tests.test_team_hosting` and `tests.test_parallel_by_default`, which load the file by path, still pass.
- **plane built.** `merged_task` takes the full id or its number: a value of `ids.task.width` digits matches the done
  task whose id starts with it and a hyphen. `built` records and prints the full id as `built_task`. New test
  `tests.test_plane_built.Built.test_a_bare_task_number_names_the_merged_task`.
- **release.sh.** `git -C "$MAIN" pull -q --ff-only` becomes `git -C "$MAIN" fetch -q origin && git -C "$MAIN" merge
  -q --ff-only "origin/$(git -C "$MAIN" symbolic-ref --short HEAD)"`; its comment's "the pull below" becomes "the
  update below".
- No other test expectation changes.

## Scope

- **In:** `ccp/verify.py` (`spec_text`, `spec_hunks`, `named_hunks`); `ccp/upgrade.py` (`merged_task`);
  `scripts/observability/CLAUDE.md`; `ccp/doclang/CLAUDE.md` (the one clause); `scripts/observability/team.py`; `scripts/release.sh`;
  `tests/test_verify_spec_text.py`; `tests/test_plane_built.py`; the SPEC, signed:

  CURRENT (`docs/spec/02-delivery.md` at `704ca8de`), §15.2, the signed-text bullet:
  > (`git diff <base>...<head>`, each SPEC file read as it is at `<head>`, which defaults to `HEAD`; the base defaults to `origin/<integration branch>`,

  PROPOSED:
  > (`git diff <base>...<head>`, each SPEC file read as it is at `<head>`; with no `--head`, the diff runs from the
  > merge base of `<base>` and `HEAD` to the working tree, each file read as it is there, so an edit not yet committed
  > counts; the base defaults to `origin/<integration branch>`,

  Retired: "which defaults to `HEAD`".
- **Out:** `docs/cli/05-operations.md` (the `plane built` row names a plane task id, which a number now resolves to);
  the rest of `scripts/observability/`; `scripts/run-checkout.sh`.

## dod_checks

- id: `code-01`
  story: As an implementer, spec-text finds a signed passage I have written but not committed.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_verify_spec_text.SpecText.test_with_no_head_an_uncommitted_spec_edit_is_found tests.test_verify_spec_text.SpecText.test_with_head_given_an_uncommitted_spec_edit_is_not_read tests.test_verify_spec_text`.
  expect: exit 0.
  dry run (`704ca8de`): exit 1 (`AttributeError: type object 'SpecText' has no attribute 'test_with_no_head_an_uncommitted_spec_edit_is_found'`).
- id: `spec-01`
  story: As the operator, §15.2 says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0346`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`704ca8de`, with this brief): exit 1, the PROPOSED passage missing.
- id: `doc-01`
  story: As a maintainer, the package docs leave lib.py's map and the house rules' text to their homes.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c -e 'write_atomic' -e 'LEGACY_EVENT_TYPES' -e 'imports nothing from' scripts/observability/CLAUDE.md`.
    2. Run `grep -c 'stays language-neutral' ccp/doclang/CLAUDE.md`.
  expect: step 1 prints `0` and step 2 prints `0` (each grep's exit 1, no match).
  dry run (`704ca8de`): step 1 printed `3`, exit 0; step 2 printed `1`, exit 0.
- id: `code-02`
  story: As a maintainer, team.py puts the plane root on sys.path once, at import.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'sys.path.insert' scripts/observability/team.py`.
  expect: prints `2`.
  dry run (`704ca8de`): printed `11`.
- id: `code-03`
  story: As the plane session, I close a proposal as built with the task's number.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_plane_built.Built.test_a_bare_task_number_names_the_merged_task tests.test_plane_built`.
  expect: exit 0.
  dry run (`704ca8de`): exit 1 (`AttributeError: type object 'Built' has no attribute 'test_a_bare_task_number_names_the_merged_task'`).
- id: `code-04`
  story: As the operator, a release fast-forwards the dev checkout from a fetched ref, whatever runners fetch meanwhile.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'pull -q --ff-only' scripts/release.sh`.
    2. Run `grep -c 'merge -q --ff-only' scripts/release.sh`.
  expect: step 1 prints `0` (grep's exit 1, no match); step 2 prints `1`.
  dry run (`704ca8de`): step 1 printed `1`; step 2 printed `0`, exit 1.

## Implementation notes

## Verification notes
