---
task_id: 0302-submit-names-no-review-record-it-lacks-and-skip-tests-share-one-integration-commit-helper
title: ccp tasks submit names no review record when none exists, the CLI reference test proves a span's flags credit only that span's commands, and the skip tests commit to the integration branch through one SkipFlow helper
status: pending
kind: feature
depends_on: []
spec_refs: ["S15"]
rule_refs: ["E25", "E4"]
review_point: R26
paths: ["ccp/submit.py", "tests/test_formal_submit.py", "tests/test_cli_reference.py", "tests/review_flow.py", "tests/test_review_skip.py", "tests/test_review_skip_provers.py"]
clashes_with: ["0191-the-grace-release-ends", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0302-submit-names-no-review-record-it-lacks-and-skip-tests-share-one-integration-commit-helper

## Intent

Three leftovers of 0278 and 0298 close. `ccp tasks submit` never names a review record that does not
exist: a task submitted on a proven fix with no clean review prints `review_record: null`, as its
`review_run_id` already is, and a task with a record prints the record's path as today. The CLI
reference test (E25) has a test that fails when a joined row's span credits its flags to commands
outside the span, so the crediting side of `problems_of` is held as its checking side already is.
And the tests built on `SkipFlow` commit to the integration branch through one helper on it, not
through three copies (E4).

## Context (not checked)

Covers these follow-ups (`ccp --root . tasks follow-ups --open`):

- `0278-submit-takes-a-proven-fix-and-the-spec-names-what-ccp-writes/implement#1`: `on_main` belongs in `SkipFlow`.
- `0278-submit-takes-a-proven-fix-and-the-spec-names-what-ccp-writes/implement#2`: submit's `review_record` names a record that may not exist.
- `0298-the-cli-reference-reads-each-span-s-flags-and-tests-take-the-plane-root-and-git-env-from-helpers/verify#1`
  and `/verify-2#1`: no test holds the crediting side of `problems_of`.

Measured at `7a2993b` (origin/main).

- **Submit's output.** `"def submit"` in `ccp/submit.py` returns `"review_record": f"{report.REVIEW_DIR}/{tid}.json"` whatever
  `record` holds, beside `"review_run_id": record["review_run_id"] if record else None`
  (`git grep -n '"review_record": f"' -- ccp/submit.py` at `7a2993b`: 1 line, unconditional). Since 0278 a proven fix passes
  with no clean review, so no record exists (`test_a_proven_fix_of_a_major_review_with_no_clean_review_is_submitted` asserts
  the file is absent). No reader takes the key: `git grep -n review_record -- scripts plugin templates` at `7a2993b`: no line.
  No doc or contract gives submit's output shape: `git grep -n review_record -- docs/spec docs/cli contracts` at `7a2993b`: no line.
  So no SPEC, docs/cli or contract change.
- **The crediting side.** In `"def problems_of"` in `tests/test_cli_reference.py`, a span that names commands credits its flags
  (`fls`) to those commands only; the unit's flags (`flags`) are the union over its spans. A probe at `7a2993b` in a scratch
  worktree, replacing `update(fls)` with `update(flags)` in the branch commented "credits only them", then
  `python3 -B -m unittest -q tests.test_cli_reference`: `OK` (the mutant survives). A probe at `7a2993b` that drops each flag of each span
  in a row with two or more `ccp` spans and compares `problems_of` with the mutant's found two rows that tell them apart, both in
  `docs/cli/02-delivery.md`'s `ccp tasks wait` / `ccp tasks resume` row: dropping `[--detail …]` from the `ccp tasks resume` span gives
  `["docs/cli gives `ccp tasks resume` no `--detail`"]`, and the mutant gives `[]`, because the `ccp tasks wait` span's `--detail` is
  credited to `resume` too.
- **The copies.** `git grep -n 'def on_main' -- tests` at `7a2993b`: 1 line, `tests/test_review_skip.py` (`SkipReview`).
  `git grep -n '"worktree", "add", "-q", "--detach", str(other), "origin/main"' -- tests/test_review_skip.py tests/test_formal_submit.py tests/test_review_skip_provers.py` at `7a2993b`: 3 lines: `on_main` itself, `SubmitProvenFix.test_a_tip_moved_between_submit_and_verify_runs_the_proof_again` and
  `ReviewProvers.plane`, each a `SkipFlow` class doing the same steps (a detached worktree at `origin/main`, `self.commit(…, other)`,
  `git push origin HEAD:main`). `SkipReview.test_a_fix_that_edits_the_proofs_script_gets_the_integration_branchs_verdict` also reuses
  `on_main`'s worktree path for a second commit and push. The same steps in `ReviewFlow` classes (`tests/test_prompt_rounds.py`,
  `tests/test_review_gate.py`) use `ReviewFlow.commit`, whose arguments differ, and stay.
- **Other tasks.** 0293 (pending) changes how `ccp/submit.py` imports the whole-suite roles, not its output; 0191 (pending) lists
  test globs. Different logic; recorded as clashes since paths meet.

### Rulings for the build (the lead's)

- **Submit.** `"def submit"` returns `"review_record": f"{report.REVIEW_DIR}/{tid}.json" if record else None`; the key stays, so
  the output's shape does not change. In `tests/test_formal_submit.py`,
  `test_a_proven_fix_of_a_major_review_with_no_clean_review_is_submitted` also asserts
  `(body["review_record"], body["review_run_id"]) == (None, None)`, and
  `test_a_pass_with_no_suite_run_at_the_head_moves_the_task_to_submitted_and_says_so` asserts
  `body["review_record"] == "review/0002-second.json"`.
- **Crediting.** `tests/test_cli_reference.py` gains
  `test_a_flag_left_out_of_one_span_is_not_credited_from_its_siblings` in `CliReference`: `copy_with` replaces
  `` `ccp tasks resume <id> [--detail …]` `` with `` `ccp tasks resume <id>` `` and the test asserts
  `problems_of(d) == ["docs/cli gives `ccp tasks resume` no `--detail`"]`. `problems_of` does not change.
- **The helper.** `SkipFlow` in `tests/review_flow.py` gains
  `def on_main(self, files: dict[str, str]) -> None`, with a docstring saying it is another task's merge landing on the
  integration branch: it adds a detached worktree at `origin/main` in `Path(tempfile.mkdtemp(dir=self._tmp.name))`, commits each
  `rel: text` of `files` there in order with `self.commit(rel, text, other)`, and pushes once with `git push -q origin HEAD:main`.
  `SkipReview.on_main` goes; its four calls pass a one-entry dict, and the proof-script test's `on_main` plus second commit and push
  become one call with `{"tests/check.sh": "exit 1\n", "docs/delivery/plane.json": …}` in that order.
  `SubmitProvenFix`'s inline steps become `self.on_main({ToolkitFixture.PLANE_JSON["reconcile"]["log"]["path"]: "a merged task's entry\n"})`.
  `ReviewProvers.plane` calls `self.on_main` with its files (each `__` read as `/`) then `docs/delivery/plane.json`, and keeps its
  fetch and merge. Imports a module no longer uses go. If a test turns on where that worktree lives, stop and ask.

## Scope

- **In:** `ccp/submit.py` (the `review_record` value), `tests/test_formal_submit.py`, `tests/test_cli_reference.py`,
  `tests/review_flow.py`, `tests/test_review_skip.py`, `tests/test_review_skip_provers.py`.
- No SPEC change: no SPEC, docs/cli or contract text gives submit's output keys (Context's grep); the tests' helpers are named in
  no SPEC text (`git grep -n 'on_main\|SkipFlow\|problems_of' -- docs/spec` at `7a2993b`: no line).
- **Out:** `problems_of` itself; the `ReviewFlow` copies in `tests/test_prompt_rounds.py` and `tests/test_review_gate.py`;
  `tests/test_review_skip_clean.py` (it makes no integration commit); the review record (`ccp/report.py`).

## dod_checks

- id: `cmd-01`
  story: As the runner, submitting a proven fix with no clean review names no review record, and a clean review's record is named.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_formal_submit 2>&1 | grep -e no_clean_review_is_submitted -e no_suite_run_at_the_head -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_formal_submit --revert ccp/submit.py`.
  expect: step 1 lists `test_a_proven_fix_of_a_major_review_with_no_clean_review_is_submitted` `ok` and `test_a_pass_with_no_suite_run_at_the_head_moves_the_task_to_submitted_and_says_so` `ok`, then `OK`; step 2 prints the mutant `killed`.
  dry run (`7a2993b`): `git grep -n '"review_record": f"' -- ccp/submit.py` printed 1 line, the unconditional path; `python3 -B -m unittest -q tests.test_formal_submit` printed `OK`.
- id: `code-01`
  story: As a docs writer, a span that loses a flag its sibling span keeps is still told it lacks it.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_cli_reference 2>&1 | grep -e not_credited_from_its_siblings -e '^OK'`.
    2. Write a mutant file: first line `tests/test_cli_reference.py`, then `=== old`, the two lines `credits only them` (the end of the comment on the line `for p in ps:  # a span that names commands holds its flags to each of them, and credits only them`) and the next line `                    credited.setdefault(strip_action(root, p), set()).update(fls)`, then `=== new`, the same two lines with `update(flags)`. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_cli_reference --mutant-file <file>`.
  expect: step 1 lists `test_a_flag_left_out_of_one_span_is_not_credited_from_its_siblings` `ok`, then `OK`; step 2 prints the mutant `killed`.
  dry run (`7a2993b`): the same substitution in a scratch worktree, then `python3 -B -m unittest -q tests.test_cli_reference`, printed `OK` (it survives today); the probe of Context printed the one problem for the edited row, and `[]` for the mutant.
- id: `code-02`
  story: As a plane developer, every SkipFlow test that lands a commit on the integration branch does it through one helper.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n -e 'def on_main' -e '"worktree", "add", "-q", "--detach", str(other), "origin/main"' -- tests/review_flow.py tests/test_review_skip.py tests/test_formal_submit.py tests/test_review_skip_provers.py` (the `ReviewFlow` copies of Scope **Out** are not in it).
    2. Run `python3 -B -m unittest -q tests.test_review_skip tests.test_formal_submit tests.test_review_skip_provers 2>&1 | tail -1`.
  expect: step 1 prints exactly two lines, both in `tests/review_flow.py` (the `def on_main` line and its worktree line); step 2 prints `OK`.
  dry run (`7a2993b`): step 1 printed 4 lines (`tests/test_review_skip.py` twice, `tests/test_formal_submit.py`, `tests/test_review_skip_provers.py`); step 2 printed `OK`. A scratch worktree at `7a2993b` with this task's submit change and 0303's changes in it ran `GATE_COLD=1 scripts/gate.sh`: 222 modules, 3837 tests, all passed (no other module reads submit's `review_record`).

## Implementation notes

## Verification notes
