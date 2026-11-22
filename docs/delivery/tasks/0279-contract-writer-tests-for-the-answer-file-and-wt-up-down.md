---
task_id: 0279-contract-writer-tests-for-the-answer-file-and-wt-up-down
title: The answer file and the records ccp wt up and down write are checked against their contracts, and the two dead contracts are removed
status: pending
kind: refactor
depends_on: []
rule_refs: ["E9", "E12"]
review_point: R24
paths: ["contracts/question_answer.example.json", "contracts/architecture_review.schema.json", "contracts/result.schema.json", "contracts/CLAUDE.md", "tests/test_contract_writers.py"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0279-contract-writer-tests-for-the-answer-file-and-wt-up-down

## Intent

A change to the spec-maintainer answer file's contract, or to what `ccp wt up` and `ccp wt down` write
into a worktree record, fails a test when the record and its schema stop agreeing, as a change to the
question or to `ccp wt create` already does. `contracts/` holds no schema that nothing writes or reads.

## Context (not checked)

Measured at `254bb64` (origin/main). This task covers task 0263's open worker follow-ups
(`ccp tasks follow-ups --open`).

**Covered here:**

- `0263-…/review#1`, `0263-…/fix#1`, and the `question_answer` part of `review-2#2`, `fix-2#2` and
  `verify#3`: the answer file has no test. `git grep -c question_answer -- tests` at `254bb64`: no
  match (exit 1). The lead writes the file (SPEC §17.5; `plugin/skills/spec-maintainer/SKILL.md`,
  "## Answer file"); `scripts/observability/spec_maintainer.py` only reads it, through
  `"def validate_answer"` (docstring "Mirror of contracts/question_answer.schema.json"), and
  `ccp/verify.py` reads it too. The follow-ups call `spec_maintainer.py` its writer; it is the reader,
  so the test is the seat-written kind contracts/CLAUDE.md names: an example the reader accepts.
  A probe at `254bb64` (a `resolved` answer with `ruling`, `commit_sha`, `files_changed` and
  `written_by: "seat"`, run through `ccp.schema.schema_errors` and `validate_answer`): both returned
  `[]`, so an example both accept exists today.
- `0263-…/review-2#1`, `verify#1`, and the `wt up`/`down` part of `fix-2#2`: `"def up"` and
  `"def down"` in `ccp/wt.py` rewrite `state`, `up_at` and `urls`, and the only writer tests
  (`WorktreeContract` in `tests/test_contract_writers.py`) read records as `ccp wt create` leaves them.
  `git grep -n up_at -- tests` at `254bb64`: no match. A probe at `254bb64` (the `UpDownUrls` fixture's
  hooks, then `up`, `down`, and an `up` whose hook exits 4): each record validated against
  `contracts/worktree.schema.json` with no error; the same record with `up_at` set to `0` gave
  `record.up_at: 0 is not string`, so the test can bite.
- `0263-…/review#2` and the `architecture_review` part of `review-2#2`, `fix-2#2` and `verify#3`:
  E9 says a contract no code writes or reads is removed.
  `git grep -nP "(architecture_review|(?<!suite_)result)\.schema\.json" -- . ':!docs/delivery/tasks' ':!docs/delivery/reviews'` at `254bb64`: 2 lines, each the file's own `$id` (`contracts/architecture_review.schema.json:3`, `contracts/result.schema.json:3`). No code, test, SPEC page or doc names either. The architecture
  review schema's own description says "nothing writes it any more"; the architect's report has its own
  contract (`architect_report.schema.json`), a superset of its keys. `result.schema.json` was found by
  the same measurement: no code writes a record with its `outcome`/`completed_at` shape
  (`git grep -nw completed_at -- ccp scripts plugin templates docs/spec` at `254bb64`: no match). Done
  tasks and review records that name the two files are history and stay.
  `tests/test_contract_layout.py` globs `contracts/*.schema.json` and does not name either.

**The other live contracts are a further task, not this one.** `git grep -l schema_errors -- tests` at `254bb64`: 4 modules, and
`git grep -ho '[a-z_]*\.schema\.json' $(git grep -l schema_errors -- tests) | sort -u` at `254bb64`: 11 names, of which `project.schema.json` is only read for an enum (`tests/test_verify.py`,
`"def test_a_record_may_carry_every_access_mode_a_binding_declares"`). `ls contracts/*.schema.json | wc -l` at `254bb64`: 23, so (same commands) besides `question_answer` and the two removed here, 10 live contracts have no test
that runs a written record through the checker: `adr`, `architect_report`, `machine`,
`observability_event`, `plane_config`, `pr_record`, `project`, `prompt_audit`, `suite_result`,
`task_file` (0263 `implement#1`). Each has hand tests of the schema's keys or enums (for example
`tests/test_adr.py`, `tests/test_event_registry.py`, `tests/test_prompt_audit.py`), and each needs its
own writer fixture (`ccp init`, `ccp adr new`, the local PR host, the prompt audit, `scripts/gate_result.py`,
the ledger, a seat example for the architect report and the task file). Ten fixtures beside this task's
three items would pass six checks, so this task keeps to the answer file, `wt up`/`down` and the
removal, and leaves `implement#1` open for a task of its own.

**Out of scope, left open:**

- `0263-…/implement#2`: the run record (`runs/<task>/<run>.json`) and `runs/_suites.jsonl` have no
  contract by design; contracts/CLAUDE.md says their modules' tests check them.
- `0263-…/fix-2#1` and `verify#2`: whether `worktree.schema.json` sets `additionalProperties: false` is
  a contract decision for the architect, not a test gap.

**No SPEC change.** `git grep -nP "(architecture_review|(?<!suite_)result|question_answer|worktree)\.schema\.json" -- SPEC.md docs/spec` at `254bb64`: 2 lines, §12.1 (`worktree.schema.json`) and §17.5 (`question_answer.schema.json`), both
of which stay true; neither removed schema is named in the SPEC. No sign-off.

### Rulings for the build (the lead's)

- **The answer example.** `contracts/question_answer.example.json`: one `resolved` answer carrying
  `schema_version`, `question_id` (matching `^sm-`), `project_id`, `verdict`, `ruling`, `reasoning`,
  `commit_sha`, `files_changed`, `answered_by: "spec_maintainer"`, `answered_at` and
  `written_by: "seat"`. Neutral values only.
- **The answer test.** `Examples.test_the_question_answer_example_validates_and_the_spec_maintainer_accepts_it`
  in `tests/test_contract_writers.py`: the example has no `schema_errors` against
  `question_answer.schema.json`, and `validate_answer(rec, rec["question_id"])` from
  `scripts/observability/spec_maintainer.py` returns `[]`. Import the script the way
  `tests/test_plugin.py` imports `architecture_review` (the directory on `sys.path`).
- **The wt test.** `WorktreeContract.test_the_record_validates_after_ccp_wt_up_and_down` in the same
  module: with `env.up` and an `env.urls` hook that prints two URLs (as `UpDownUrls.URLS` does), create
  a `ver` worktree, run `ccp wt up` and validate the record (`state` `up`, `up_at` present, two `urls`),
  run `ccp wt down` and validate it (`state` `down`, `urls` `[]`); then create a second one whose
  `env.up` exits 4, run `ccp wt up` and validate that record too.
- **contracts/CLAUDE.md.** The sentence "Not yet checked: `question_answer`." becomes
  "Not yet checked by a written record: `adr`, `architect_report`, `machine`, `observability_event`,
  `plane_config`, `pr_record`, `project`, `prompt_audit`, `suite_result`, `task_file`."

## Scope

- **In:** `contracts/question_answer.example.json` (new), `contracts/architecture_review.schema.json`
  (removed), `contracts/result.schema.json` (removed), `contracts/CLAUDE.md` (the one sentence),
  `tests/test_contract_writers.py` (two tests).
- **Out:** `scripts/observability/spec_maintainer.py`, `ccp/wt.py` and the schemas' text (no code or
  contract change); writer tests for the 10 contracts listed in Context; the run record and
  `_suites.jsonl`; `additionalProperties` on `worktree.schema.json`; the SPEC.

## dod_checks

- id: `code-01`
  story: As a plane developer, an answer file the lead writes as the contract says is one the spec-maintainer accepts.
  setup: A checkout of the PR head, any seat.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_contract_writers`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.Examples.test_the_question_answer_example_validates_and_the_spec_maintainer_accepts_it --mutant 'scripts/observability/spec_maintainer.py:"supersedes", "written_by",=>"supersedes",'`.
  expect: step 1 exits 0 and lists `test_the_question_answer_example_validates_and_the_spec_maintainer_accepts_it` as `ok`; step 2 prints the mutant `killed`.
  dry run: n/a — the test and the example are new.
- id: `code-02`
  story: As a plane developer, a record `ccp wt up` or `ccp wt down` writes that breaks the worktree contract fails a test.
  setup: A checkout of the PR head, any seat.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_contract_writers.WorktreeContract`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.WorktreeContract.test_the_record_validates_after_ccp_wt_up_and_down --mutant 'ccp/wt.py:up_at=iso()=>up_at=0'`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.WorktreeContract.test_the_record_validates_after_ccp_wt_up_and_down --mutant-file <file>`, the file's mutant making the failed-up branch of `"def up"` write `state="stopped"` in place of `state="down"` (its old text the three lines from `st.update(state="down", urls=[])` to `raise QueueError(`, which occur once).
  expect: step 1 exits 0 and lists `test_the_record_validates_after_ccp_wt_up_and_down` as `ok`; steps 2 and 3 each print the mutant `killed`.
  dry run: n/a — the test is new. The premise probe is in Context.
- id: `data-01`
  story: As a plane developer, contracts/ holds no schema that nothing writes or reads.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nP "(architecture_review|(?<!suite_)result)\.schema\.json" 254bb64 -- . ':!docs/delivery/tasks' ':!docs/delivery/reviews'`.
    2. Run `git grep -nP "(architecture_review|(?<!suite_)result)\.schema\.json" -- . ':!docs/delivery/tasks' ':!docs/delivery/reviews'`.
    3. Run `ls contracts/architecture_review.schema.json contracts/result.schema.json`.
  expect: step 1 prints exactly two lines, `254bb64:contracts/architecture_review.schema.json:3` and `254bb64:contracts/result.schema.json:3` (the pattern finds the files); step 2 prints nothing (exit 1); step 3 exits non-zero, reporting both missing.
  dry run (`254bb64`): step 1 printed 2 lines (`254bb64:contracts/architecture_review.schema.json:3`, `254bb64:contracts/result.schema.json:3`); step 2 printed the same 2 lines without the ref prefix; step 3 listed both files, exit 0.
- id: `doc-01`
  story: As a plane developer, contracts/CLAUDE.md names the contracts still unchecked, and question_answer is not among them.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n question_answer -- contracts/CLAUDE.md`.
    2. Run `git grep -nw task_file -- contracts/CLAUDE.md`.
  expect: step 1 prints nothing (exit 1); step 2 prints one line.
  dry run (`254bb64`): step 1 printed 1 line (`contracts/CLAUDE.md:11`); step 2 printed nothing (exit 1).

## Implementation notes

- Built as the lead's rulings give: `contracts/question_answer.example.json` (new), the two tests in
  `tests/test_contract_writers.py` (`Examples` and `WorktreeContract`), the one sentence in
  `contracts/CLAUDE.md`, and `contracts/architecture_review.schema.json` and `contracts/result.schema.json` removed.
- The test module imports `spec_maintainer` at module level with the script directory put on `sys.path`, as
  `tests/test_plugin.py` does inside its tests.
- The second worktree (failed `up`) is created with `--name ver-0002-2`, since a `ver` worktree for the task
  already exists and `ccp wt create` would otherwise report it again.
- A `--mutant-file` mutant's old text is whole lines: the dod_check 3 file names the third line in full
  (`raise QueueError(f"env.up for ...", 1)`), as a text ending mid-line matches nowhere.
- Measured premises at `b4af31e8`: `git grep -c question_answer -- tests` no match; `git grep -n up_at -- tests` no
  match; the architecture_review/result grep printed the two `$id` lines; `completed_at` no match;
  `ls contracts/*.schema.json | wc -l` 23. All as the task states.

## Verification notes
