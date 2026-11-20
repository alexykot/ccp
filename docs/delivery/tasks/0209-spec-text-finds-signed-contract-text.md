---
task_id: 0209-spec-text-finds-signed-contract-text
title: ccp verify spec-text finds a signed passage that lands outside the SPEC, such as in a contract
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S15"]
review_point: R14
paths: ["ccp/verify.py", "docs/spec/02-delivery.md", "tests/test_verify_spec_text.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0209-spec-text-finds-signed-contract-text

## Intent

The operator signs "a SPEC CURRENT → PROPOSED, a contract" (§3.5), but `ccp verify spec-text` looks
for the signed passages only in the SPEC files. A task whose signed text includes a contract's
description therefore fails the check (exit 1) even though the text landed word for word. The
reviewer and verifier then have to argue around a red check. After this task, a passage not found
in the SPEC is looked for in the other files the branch changes, the task log aside, and the check
names where it found each one. §15.2 also gets the full list of what exits 2.

## Context (not checked)

Measured at `58cf1d0`.

- `ccp/verify.py` `spec_hunks` keeps a file's hunks only when `tasklog._names_spec(cur, spec_paths)`
  (`git grep -n '_names_spec' ccp/verify.py` at `58cf1d0`: one line), and `spec_text` searches only
  those.
- Probe: `ccp --root . verify spec-text 0197-usage-read-once-per-machine --base dda870a --head cac3a72`
  at `58cf1d0` fails: of its 12 passages, `missing` lists two (`verify spec-text`'s JSON, lines 467 and 482).
  Both are descriptions that landed in `contracts/allowance.schema.json` and
  `contracts/machine.schema.json`, each present there verbatim, as a search of each file for its
  passage's words shows (`grep -c 'is a failed read that says when to retry' contracts/allowance.schema.json` at `58cf1d0`: 1).
- `spec_text` exits 2 for: no passage, an unknown task, a `--head` that names no commit, and a diff
  that cannot be read, a base that does not resolve (`git grep -n 'return 2' ccp/verify.py` at `58cf1d0`, in `spec_text`: four returns).
  §15.2 names only the first. A plane proposal on task 0157 named the missing `--head` case. Task
  0204 left this sentence here, since this task rewrites the paragraph.
- No contract path is configured anywhere (`git grep -n 'contract_paths' ccp/` at `58cf1d0`: no
  line). Looking in every other changed file, the task log aside, needs no new key. The task log is
  left out because a task's own file quotes its passages.
- `tests/test_verify_spec_text.py` passes at the base
  (`python3 -B -m unittest -q tests.test_verify_spec_text` at `58cf1d0`: 24 tests).
- The SPEC text below describes only what this task builds, and states exit codes the code already
  returns (§31.1).

## Scope

- **In:** `ccp/verify.py`, `docs/spec/02-delivery.md`, `tests/test_verify_spec_text.py`.
- **`ccp/verify.py`:** the hunk reader takes a predicate on the path. `spec_hunks` keeps the SPEC
  files as today, and a new `other_hunks` keeps every other changed file, except those under the
  task log's directory (`cfg.tasks_dir`). Both read hunks the same way: unchanged lines up to the
  nearest blank line, and a passage must cover an added character.
  - `spec_text` looks for each passage in the SPEC hunks first. Only a passage not found there is
    looked for in `other_hunks`. `found_in` names the file or files it was found in.
  - The stderr line for a missing passage says "not found in the text <head> changes since <base>".
- **SPEC §15.2 (§31.1).** CURRENT (`docs/spec/02-delivery.md` at `58cf1d0`): "and nothing is
  fetched). It exits 0 when every passage is found, 1 naming each that is not, and 2 when the task
  carries no `PROPOSED:` block." PROPOSED: "and nothing is fetched). A passage not found there is
  looked for in the same way in the hunks the diff makes to every other file outside the task log's
  directory, such as a contract whose text the operator signed, and the result names the file each
  passage was found in. It exits 0 when every passage is found, 1 naming each that is not, and 2 when
  the task carries no `PROPOSED:` block, names no task, or gives a `--head` that names no commit or
  a base the diff cannot be read against."
- **Tests** in `tests/test_verify_spec_text.py`:
  - a passage that lands in a JSON contract's `description` on the branch is found (exit 0), and
    `found_in` names the contract;
  - a passage that the branch's diff adds only to the task file itself is not found (exit 1);
  - a passage that sits only in unchanged lines of a non-SPEC file is not found (exit 1);
  - a passage found in the SPEC is not also looked for elsewhere: `found_in` names the SPEC file
    alone, even when a changed contract holds the same text.
- **Out:** what the operator signs (§3.5), and the reviewer's and verifier's use of the result.

## dod_checks

- id: `st-01`
  story: As a verifier, a task whose signed text landed in contracts passes the check.
  setup: a checkout of the PR head, with history back to `dda870a`.
  steps:
    1. Run `ccp --root . verify spec-text 0197-usage-read-once-per-machine --base dda870a --head cac3a72 > <tmp>/st.json; echo rc=$?`.
    2. Run `python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['missing'], sorted({f for p in d['passages'] for f in p['found_in'] if f.startswith('contracts/')}))" <tmp>/st.json`.
  expect: `rc=0`; step 2 prints `[] ['contracts/allowance.schema.json', 'contracts/machine.schema.json']`.
  dry run (`58cf1d0`): `rc=1`, with lines 467 and 482 of the 0197 task file missing.

- id: `st-02`
  story: As a plane developer, the wider search is tested and the tests bite.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `other_hunks` returns `{}`.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_verify_spec_text 2>&1 | tail -30`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_verify_spec_text`.
  expect: step 1 exits 0 with the four Scope tests listed `ok`; step 2 fails, naming the contract
    test.
  dry run (`58cf1d0`): step 1 runs 24 tests, OK.

- id: `st-03`
  story: As the SPEC reader, §15.2 says where the check looks and every exit 2.
  setup: a checkout of the PR head.
  steps:
    1. Run `tr -s '[:space:]' ' ' < docs/spec/02-delivery.md | grep -c 'every other file outside the task log.s directory'`.
    2. Run `grep -c 'carries no .PROPOSED:. block\. For a task' docs/spec/02-delivery.md`.
  expect: step 1 prints 1; step 2 prints 0.
  dry run (`58cf1d0`): step 1 prints 0; step 2 prints 1.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
