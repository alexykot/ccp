---
task_id: 0263-writers-are-checked-against-their-contracts
title: One schema checker, and a test per live contract that validates what its writer writes or its reader reads
status: pending
kind: refactor
depends_on: ["0258-the-plane-writes-the-pre-merge-phases"]
clashes_with: ["0234-one-check-parser-and-one-file-at-rev-reader", "0240-plane-workers-run-the-head", "0253-one-wait-reason-table"]
review_refs: ["ar-20261121T111633Z-4e26#F06", "ar-20261121T020523Z-1d5f#F08"]
rule_refs: ["E9", "E12"]
review_point: R19
paths: ["ccp/schema.py", "ccp/verify.py", "ccp/CLAUDE.md", "contracts/worktree.schema.json", "contracts/question.schema.json", "contracts/escalation.schema.json", "contracts/allowance.schema.json", "contracts/architecture_review_triage.schema.json", "contracts/escalation.example.json", "contracts/allowance.example.json", "contracts/architecture_review_triage.example.json", "contracts/CLAUDE.md", "docs/ROADMAP.md", "tests/test_contract_writers.py", "tests/test_task_state_contract.py", "tests/test_phase_contracts.py", "tests/test_verify.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0263-writers-are-checked-against-their-contracts

## Intent

`contracts/CLAUDE.md` says tests check that code and schema agree, and after this task they do for
every live contract: one schema checker in its own module, and a test per contract that validates a
record its writer writes, or, where a seat or a machine command writes it, an example record that its
reader accepts. Drift like the ten keys task 0236 found between claim and `task.schema.json` is then
caught by the gate, not by chance.

## Context (not checked)

Measured at `1aa5e3f`.

- From architect pass `ar-20261121T111633Z-4e26`, F06, which takes up the deferred
  `ar-20261121T020523Z-1d5f#F08` (`docs/ROADMAP.md`): the deferral waited on a validator choice,
  and `"def schema_errors"` in `ccp/verify.py` is a stdlib one that knows the keywords the plane's
  contracts use (`git grep -n 'def schema_errors' -- ccp` at `1aa5e3f`: `ccp/verify.py:161`).
  `tests/test_task_state_contract.py` already uses it; 0258 adds `tests/test_phase_contracts.py`
  (progress and review), which is why this task depends on 0258.
- **Unchecked contracts.** `for n in worktree question escalation allowance architecture_review_triage; do git grep -l "$n.schema" -- ccp scripts tests plugin | wc -l; done` at `1aa5e3f`: 0 for each of the five.
- **Their writers and readers.**
  - worktree: written by `ccp wt create` (`QUEUE_ROOT/worktrees/<name>.json`); its `kind` enum
    lists `impl`, `rev`, `ver`, `mut`, `mac`, `base`, which `"KINDS: dict"` in `ccp/wt.py` also holds.
  - question: written by `scripts/observability/spec_maintainer.py` (`QUEUE_ROOT/questions/`).
  - escalation: written by a seat by hand (`QUEUE_ROOT/escalations/<task_id>/<n>.json`); read by
    `ccp/verify.py`'s gate read and `ccp/board.py`.
  - allowance: printed by the machine's `allowance_cmd`; read by `"def reading"` in `ccp/usage.py`.
  - architecture_review_triage: written by the lead; read by `validate_triage` in
    `scripts/observability/architecture_review.py`, called from `ccp architect triage`.
- **Rulings for the build** (the lead's):
  - `schema_errors` moves to `ccp/schema.py` (new), unchanged; `ccp/verify.py` and the tests import
    it from there, with no alias left in `verify`.
  - `tests/test_contract_writers.py` (new): for worktree and question, a record written by the real
    writer in a fixture queue validates with no errors, and the worktree `kind` enum equals
    `wt.KINDS`' keys. For escalation, allowance and the triage, `contracts/<name>.example.json`
    (new) validates against its schema and is accepted by its reader (an approved gate escalation
    the verify read finds; a reading `usage.reading` parses with its windows; a triage
    `validate_triage` returns no errors for).
  - Where a writer's record does not validate, the schema is corrected to what the writer writes
    today (E9: readers accept every live value), never the writer; each correction is listed in the
    Implementation notes.
  - `contracts/CLAUDE.md` names the queue records that have no contract (run records
    `runs/<task>/<run>.json` and `runs/_suites.jsonl`, checked by their own modules' tests) instead
    of claiming one schema per record. `docs/ROADMAP.md`'s F08 deferral line is removed.
- A refactor: behaviour is unchanged; a schema changes only to describe what is already written.
- **Lead's ruling `0263-writers-are-checked-against-their-contracts-r1`** (on `sm-20261122T030237Z-98ff`;
  the answer's `ruling` field, shortened): (1) A: extend the checker with the keywords the live contracts
  use; don't rewrite the three schemas. (2) (a): enforcing proof_urls' schema-valued additionalProperties
  is ruled in, with a test that verify record refuses a non-string proof_urls value, named in Implementation
  notes. Its reasoning: a per-contract exemption would be the kind of special case the task removes.

## Scope

- **In:** `ccp/schema.py` (new), `ccp/verify.py`, `ccp/CLAUDE.md` (the module list), the five
  schemas (only as corrected), `contracts/escalation.example.json` (new),
  `contracts/allowance.example.json` (new), `contracts/architecture_review_triage.example.json` (new),
  `contracts/CLAUDE.md`, `docs/ROADMAP.md`, `tests/test_contract_writers.py` (new),
  `tests/test_task_state_contract.py`, `tests/test_phase_contracts.py`, `tests/test_verify.py` (their
  imports).
- **Out:** new schemas for run records or suite rows; the readers' and writers' code; the progress
  and review contracts (0258); `observability_now` (0253).

## dod_checks

- id: `ct-01`
  story: As a plane developer, one module holds the schema checker.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'def schema_errors' -- ccp`.
    2. Run `git grep -n 'verify.schema_errors' -- ccp tests scripts | wc -l`.
  expect: step 1 prints one line, in `ccp/schema.py`; step 2 prints `0`.
  dry run (`1aa5e3f`): step 1 printed `ccp/verify.py:161:def schema_errors(…)`; step 2 printed `2`.
- id: `ct-02`
  story: As a plane developer, every live contract is named by a test that checks it.
  setup: A checkout of the PR head.
  steps:
    1. Run `for n in worktree question escalation allowance architecture_review_triage task; do git grep -l "$n.schema" -- tests | wc -l; done`.
  expect: six lines, each `1` or more (the last, `task`, is the known positive).
  dry run (`1aa5e3f`): printed `0 0 0 0 0 1`.
- id: `ct-03`
  story: As a plane developer, the writers' records and the example records validate and their readers accept them, and the tests bite.
  setup: A checkout of the PR head; then a separate copy of it with `"required"` in `contracts/worktree.schema.json` given one more key, `"no_such_key"`.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_contract_writers 2>&1 | tail -9`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_contract_writers`.
  expect: step 1 exits 0, listing as `ok` tests for: a worktree record from `ccp wt create` validates; its kind enum equals `wt.KINDS`; a question from the spec-maintainer writer validates; the escalation, allowance and triage examples validate and their readers accept them. Step 2 exits non-zero, naming `no_such_key`.
  dry run: n/a — the module is new.
- id: `ct-04`
  story: As a plane developer, the contracts doc says which records have no contract.
  setup: A checkout of the PR head.
  steps:
    1. Run `grep -c '_suites.jsonl' contracts/CLAUDE.md`.
    2. Run `grep -c 'F08' docs/ROADMAP.md`.
  expect: step 1 prints `1` or more; step 2 prints `0`.
  dry run (triage branch): step 1 printed `0`; step 2 printed `1`.

## Implementation notes

- Re-measured at `a80cee0`: `git grep -n 'def schema_errors' -- ccp` printed one line (`ccp/verify.py:104`, moved from 161); the five contracts named by no test printed `0` each, as stated; `git grep -n 'verify.schema_errors' -- ccp tests scripts | wc -l` printed `4`, not `2`, because 0258's `tests/test_phase_contracts.py` (which this task depends on) holds two. Nothing material moved.
- `schema_errors` moved to `ccp/schema.py` with `is_type` (was `_is`) and `parse_dt` (was `_parse_dt`), which it needs and `ccp/verify.py` still uses; `verify` calls `schema.schema_errors`, and the tests import `schema_errors` from `ccp.schema`. No alias is left in `verify`.
- **The checker had to learn keywords.** The task says it "knows the keywords the plane's contracts use"; it knew those of the verification, task, progress and review contracts only. `question.schema.json` uses `allOf`/`if`/`then`/`const`, `allowance.schema.json` uses `oneOf`/`not`/`anyOf`/`maxProperties` and a schema-valued `additionalProperties`, and `architecture_review_triage.schema.json` uses `const`; the checker refuses a schema with a keyword it does not know, so none of the three could validate. The choice was to add those keywords to the checker (`const`, `allOf`, `anyOf`, `oneOf`, `not`, `if`/`then`, `maxProperties`, `additionalProperties` as a schema) rather than to rewrite the schemas to the old subset, which would lose what they say (the allowance's three shapes, the question's `sm-` conditional). One existing contract's verdict changes, as the lead ruled (r1, above): `contracts/verification.schema.json` gives `proof_urls.local` and `proof_urls.verifier` a schema-valued `additionalProperties` (`{"type": "string"}`) that the old checker passed over, and the checker now enforces it, so `ccp verify record` refuses a verdict with a non-string value there, and the merge gate refuses a stored record that has one (no stored record does: 958 scanned in review). The task, progress and review schemas use none of the new keywords. A sub-schema with a keyword still unknown is reported as unchecked, never read as a branch that did not match. The lead ruled the extension in (r1): nothing the checker already checked is loosened.
- `tests/test_verify.py`'s fail-closed test used `oneOf` as its unknown keyword, which is now known; it uses `dependentRequired` and asserts the same thing (an unknown keyword is an error naming it).
- **Schema corrections: none.** Every record the writers write validated against its schema as it stood (worktrees of every kind `ccp wt create` makes, a shallow one and the baseline included, and the `base` one read from inside its command, since it is removed with it; a question as raised and as sent to the lead; a gate as `team.sh gate open` and `gate decide` write it).
- Beyond the task's examples, the escalation contract is also checked against the real writer: `escalation` is written by `team.sh gate open` and `gate decide` today, not only by hand, so `tests/test_contract_writers.py` validates both of its records.
- The three examples are `contracts/escalation.example.json` (an approved, closed `operator` gate, which `verify._operator_step_refusal` accepts), `contracts/allowance.example.json` (the generic form with a null window and `retry_after_s`; `usage._run` reads it from a command that prints it) and `contracts/architecture_review_triage.example.json` (`validate_triage` returns no errors).
- `contracts/CLAUDE.md` names the records with no contract (run records and `runs/_suites.jsonl`); the F08 deferral line is out of `docs/ROADMAP.md`; `ccp/CLAUDE.md` lists `schema.py`.
- Fix round 1 (lead's ruling r1 and the review's findings): a test in `tests/test_verify.py` (`Record`) that `ccp verify record` refuses a non-string `proof_urls.local` and `proof_urls.verifier` value; `not` and `if` are judged with `newer=False`, because a key skipped there would make the sub-schema match more; `const` compares JSON types (`1.0` against `const: 1` holds, a string or a boolean does not); `contracts/CLAUDE.md` says "Some queue records have no schema, among them ..." and scopes the per-contract test claim to the contracts the tests name, listing `question_answer` as not yet checked (a follow-up in the fix report, not built here).
- Fix round 2: `WorktreeContract.test_the_base_record_validates_while_its_command_runs` validates the `kind: base` record (made by `wt.run_on_base`, with its extra `head` key), which round 1's loop did not cover; the ruling quote in Context is the answer's `ruling` field, shortened, instead of a "verbatim" text that was not it; `contracts/CLAUDE.md` also names `tests/test_task_state_contract.py`.

## Verification notes
