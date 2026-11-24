---
task_id: 0306-verify-record-refuses-a-head-that-is-not-the-verify-run-s-first-and-the-unused-re-verify-packet-goes
title: ccp verify record refuses, first and by name, a head_sha that is not its open verify run's head, and the re-verify packet contract nothing writes or reads goes with the brief line and refusal text that name it
status: pending
kind: feature
depends_on: []
spec_refs: ["S15"]
rule_refs: ["E13", "E9"]
review_refs: ["ar-20261122T162238Z-9098#F04", "ar-20261122T162238Z-9098#F07"]
review_point: R28
clashes_with: ["0191-the-grace-release-ends", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once", "0299-the-pre-gate-and-review-run-what-the-branch-touches-and-every-recorded-suite-run-keeps-a-log", "0308-module-docstrings-and-queue-docs-stop-restating-the-spec"]
paths: ["ccp/verify.py", "docs/spec/02-delivery.md", "contracts/reverify_packet.schema.json", "contracts/reverify_packet.example.json", "plugin/agents/delivery-verifier.md", "tests/test_verify.py", "tests/test_verify_record_head.py"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0306-verify-record-refuses-a-head-that-is-not-the-verify-run-s-first-and-the-unused-re-verify-packet-goes

## Intent

A verifier who types the wrong head into a verdict is told so, in one round: `ccp verify record` refuses
a record whose `head_sha` is not the head of the task's open verify run before any other refusal, naming
both heads, so a mistyped sha after a proven fix no longer reads as an unreviewed fix round. And the
verifier is no longer told to use a re-verify packet no one hands it: the contract, its example and the
test that only read each other go, the verifier brief stops naming them, and the merge judge's
"a push after the verdict needs a new verdict" refusal names the command that opens one.

## Context (not checked)

From architect pass `ar-20261122T162238Z-9098`, F07 (`incoherence`) and F04 (`holdover`); the record is in
`docs/delivery/reviews/`. Measured at `0f44fb3` (origin/main) unless a line says otherwise.

- **The order.** `ccp/verify.py` `"def main"`, the `record` action: `fill_gate`, then `cache_errors`, then `review_errors`, … No step compares the record's `head_sha` with the open verify run's `head` (the run `ccp prompt verify --head` opened, `ccp/prompt.py` `extra={"pr": a.pr or None, "head": a.head or None, …}`): `git grep -n 'latest_open' -- ccp/verify.py` at `0f44fb3`: 3 lines, in `review_errors`, `fill_reason` and `_note_run`, none comparing the run's `head` with the record's. `review_errors` calls `runs.unreviewed_fix` with the record's head; its `since` branch returns "fix round … is newer than the last review … run `ccp prompt review` first" before it compares heads, and the skip exemption (`heads_match(str(skipped.get("head") or ""), judged)`) fails on the mistyped head. Friction, 0298's verifier (15:08:23Z): "`verify record` refused first with a message about an unreviewed fix round when my record carried a mistyped head sha … The refusal text did not name the sha mismatch." `ccp health` gives 0298 2 verify rounds.
- **The packet.** `git grep -n -i -e 'reverify_packet' -e 're-verify packet' -- ccp plugin contracts tests templates docs/spec docs/cli` at `0f44fb3`: 10 lines in `ccp/verify.py` (1: `"(re-verify packet)"` in `merge_ok`'s head refusal), `contracts/reverify_packet.schema.json` (2), `plugin/agents/delivery-verifier.md` (2: the bullet "A re-verify after a fix-up, or after that head moved, uses `contracts/reverify_packet.schema.json` …") and `tests/test_verify.py` (5: the module docstring and `test_reverify_example_matches_the_schema_and_the_briefs_name_it`). `git ls-files contracts | grep -c reverify` at `0f44fb3`: 2. No code writes or reads a packet; the runner re-verifies with `ccp prompt verify --head <new> --note …` (`plugin/agents/delivery-runner.md`). House rule E9: "A contract no code writes or reads is removed, not kept." No SPEC text names it: `git grep -n -i 'reverify\|re-verify packet' -- docs/spec` at `0f44fb3`: no line.
- **Other tasks.** 0293 (claimed) edits `ccp/verify.py` for seat ids; 0308 (pending) cuts its module docstring;
  0299 (pending, signed) changes another passage of `docs/spec/02-delivery.md`; 0191 (pending) lists test globs. Different logic; recorded as clashes since the files meet.

### Rulings for the build (the lead's)

- `ccp/verify.py` gains `def head_errors(queue: Path, rec: dict[str, Any]) -> list[str]`: for a task id not
  starting `pr-`, with a `head_sha` given and an open verify run (`runs.latest_open(queue, tid, "verify")`)
  whose `head` is set, a `head_sha` that does not `heads_match` that head gives
  `head_sha <12 chars> is not <12 chars>, the head of the open verify run <run_id>: record the verdict of the head that run judges`;
  else `[]`. `main`'s `record` action runs it first, as the line
  `errs = head_errors(queue, rec) if isinstance(rec, dict) else []`, and `fill_gate` joins the chain after it
  (`errs = errs or (fill_gate(queue, rec) if isinstance(rec, dict) else [])`); a record it refuses reaches no other check.
- `merge_ok`'s refusal ends `"a push after the verdict needs a new verdict (`ccp prompt verify --head <new>`)"`
  instead of `"(re-verify packet)"`.
- `contracts/reverify_packet.schema.json` and `contracts/reverify_packet.example.json` are removed;
  `tests/test_verify.py` loses `test_reverify_example_matches_the_schema_and_the_briefs_name_it` and its module
  docstring's ", and the re-verify packet"; the verifier brief loses the three-line bullet.
- `tests/test_verify_record_head.py` (new) holds: an approve whose `head_sha` differs from the open verify
  run's head, on a task whose last round is a proven fix, is refused naming both heads and not naming `ccp
  prompt review`; a reject with such a head is refused the same way; a record at the run's head passes this
  check.

## Scope

- **In:** `ccp/verify.py` (`head_errors`, `main`'s `record` action, `merge_ok`'s head refusal),
  `contracts/reverify_packet.schema.json` (removed), `contracts/reverify_packet.example.json` (removed),
  `plugin/agents/delivery-verifier.md` (the packet bullet), `tests/test_verify.py`,
  `tests/test_verify_record_head.py` (new), `docs/spec/02-delivery.md`.
- **SPEC, signed before the claim (`sign_off: brief`):** one passage in `docs/spec/02-delivery.md`, CURRENT at
  `0f44fb3`.

    CURRENT (`docs/spec/02-delivery.md` at `0f44fb3`), §15.4, the first paragraph's list of refusals:
    > a check marked not run that has a `pass` or names no `rests_on`, and an `approve` that `merge-ok` would refuse (a failed check it ran, no `head_sha`, or no `gate` whose runs all exited 0).

    PROPOSED:
    > a check marked not run that has a `pass` or names no `rests_on`, an `approve` that `merge-ok` would refuse (a failed check it ran, no `head_sha`, or no `gate` whose runs all exited 0), and a `head_sha` that is not the head of the task's open verify run, which it refuses before anything else, naming both heads.
- **Out:** `review_errors` and `runs.unreviewed_fix` (their texts stay); `merge_ok`'s other refusals; the
  runner brief; `pr-<n>` verdicts.

## dod_checks

- id: `spec-01`
  story: As the operator, §15.4 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0306`.
  expect: exit 0, the one PROPOSED passage found.
  dry run (`0f44fb3`): n/a — the passage lands with the build; the CURRENT text is found once in `docs/spec/02-delivery.md` (whitespace-normalised, a `python3 -c` search at `0f44fb3`).
- id: `code-01`
  story: As a verifier, a mistyped head is refused as a head mismatch, naming both heads, before anything about review.
  setup: A checkout of the PR head, in your own worktree, with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_verify_record_head tests.test_verify`.
    2. Run `grep -e 'test_verify_record_head' -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_verify_record_head --mutant 'ccp/verify.py:errs = head_errors(queue, rec) if isinstance(rec, dict) else []=>errs = []'`.
  expect: step 1 exits 0; step 2 lists the module's three tests (the approve after a proven fix, the reject, the matching head), each `ok`, then `OK`; step 3 prints the mutant `killed`.
  dry run (`0f44fb3`): n/a — the module and `head_errors` are new.
- id: `code-02`
  story: As a plane developer, no file names the re-verify packet, and the merge refusal names the command.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n -i -e 'reverify_packet' -e 're-verify packet' -- ccp plugin contracts tests templates docs/spec docs/cli; git ls-files contracts | grep -c reverify`.
    2. Run `git grep -c 'needs a new verdict (`ccp prompt verify --head <new>`)' -- ccp/verify.py`.
  expect: step 1 prints only `0` (no grep line); step 2 prints `ccp/verify.py:1`.
  dry run (`0f44fb3`): step 1 printed 10 lines (Context's list), then `2`; step 2 printed nothing (exit 1).

## Implementation notes

- `head_errors` is built as the ruling gives it, run first in `record`; a `QueueError` reading the runs gives `[]`,
  as `review_errors` does. The §15.4 passage is the PROPOSED text, rewrapped.
- Three tests elsewhere recorded an approve of a head other than the open verify run's to reach `review_errors`
  through `record`, so the new check now refuses them first. They are updated so that `review_errors` still
  decides: `tests/test_review_gate.py`'s unreviewed-fix test and `tests/test_prompt_rounds.py`'s ruling-round
  test record at the run's head (`A`, with the fix or ruling to `B` after it), so the `since` refusal still
  fires. The head-the-review-did-not-judge test opens no verify run, the one way `record` reaches that refusal
  now. No expectation changed.
- The full gate showed four more of these. `tests/test_suite.py`'s earlier-round gate test now records at
  verify-2's head (`b`). `tests/test_sign_off.py`'s stale-sign-off test now opens its second verify round with
  `--supersede` and asserts that it opened; before, it was refused and the verdict went onto the first run.
  `tests/test_review_skip.py`'s proven-head test and `tests/test_review_skip_clean.py`'s run-head test hold an
  approve of another head. `record` now refuses that approve as a head mismatch, and both tests assert that
  refusal. They also call `verify.review_errors` on the same record, so its skip exemptions' head comparison is
  still tested.
- Premises re-measured at `bb102371`: the packet grep still printed 10 lines plus `2`, and `latest_open` still
  had 3 lines in `ccp/verify.py`.

## Verification notes
