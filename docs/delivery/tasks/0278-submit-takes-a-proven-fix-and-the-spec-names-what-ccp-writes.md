---
task_id: 0278-submit-takes-a-proven-fix-and-the-spec-names-what-ccp-writes
title: Formal-submit takes a fix that verify.skip_review or a review prover proves after any review and runs the proof once per fix round, and the SPEC names submit's exit 3, the queue files ccp writes, the shared gate part and what ccp report computes
status: pending
kind: feature
depends_on: []
spec_refs: ["S11", "S13", "S15", "S23"]
review_point: R24
paths: ["ccp/submit.py", "ccp/verify.py", "ccp/prompt.py", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "docs/cli/02-delivery.md", "tests/test_formal_submit.py", "tests/test_review_skip.py", "tests/test_review_skip_provers.py", "tests/test_review_skip_clean.py", "tests/test_review_gate.py"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0278-submit-takes-a-proven-fix-and-the-spec-names-what-ccp-writes

## Intent

A product with `verify.skip_review` or a review prover no longer pays for an extra review after a
MAJOR one. Today `ccp prompt verify` would accept a fix the proof covers, but `ccp tasks submit`
refuses it. After this task, submit accepts what verify accepts, and the proof and provers run once
per fix round: submit records what it proved, and `ccp prompt verify` reuses it while the integration
tip has not moved. The SPEC says what the plane does: §15.1 names submit's exit 3 and its proof path,
§23.7 names `ccp` as the writer of `progress/` and `review/`, §13.2 names the shared before-push part,
and §11.1 no longer reads as if `follow_ups` were computed rather than taken from the report.

## Context (not checked)

Measured at `76f41dd` unless a line says otherwise.

Follow-ups covered (the lead's worker follow-up log):
`0258-the-plane-writes-the-pre-merge-phases/implement#1`, `…/review#2`, `…/fix#3`, `…/review-2#4`
(§23.7, §23.2); `…/fix#1`, `…/review-2#2` (§15.1 exit 3); `…/review#1`, `…/fix#2`, `…/review-2#1`,
`…/review-2#3` (submit and the proof); `…/fix-2#1` and `…/verify#1`, which restate the four
(every `…` is `0258-the-plane-writes-the-pre-merge-phases`);
`0223-a-follow-up-is-tracked-not-left-in-notes/review#1`,
`0223-a-follow-up-is-tracked-not-left-in-notes/verify#1` (§11.1);
`0257-one-gate-block-and-one-sentence-per-line/implement#1` (§13.2, moved here from 0276 because
naming `_gate.md` edits rule text: SPEC.md says the SPEC "states rules only", and
`git grep -n -i 'non-normative' -- docs/spec` at `76f41dd` finds no note form).

- **Submit after a MAJOR review.** `"def failures"` and `"def _review_gaps"` in `ccp/submit.py` fail
  `review_artifact_present` when the latest done review found a BLOCKER or MAJOR, or when the review
  record names an older review. `"def submit"` judges the head (`"def coverage"`, which calls
  `verify.skip_review`) only when there are no such gaps. So a fix after a MAJOR review that
  `verify.skip_review` or a review prover proves is refused. Yet §15.2 lets that fix "go straight to
  verify" whatever the review found ("a fix round opened since the last review that reported
  `done`"), and `"def review_gate"` in `ccp/prompt.py` opens it. The review record exists only for a
  clean review (§15.1; `"def submit"` in `ccp/report.py` calls `write_review_record` only on `clean`
  and `done`).
- **The proof runs twice.** On a proven fix of a clean review, submit's `coverage` runs
  `verify.skip_review` (the proof, then each review prover), and `ccp prompt verify`'s `review_gate`
  runs it again for the same head. `git grep -n 'verify.skip_review(cfg' -- ccp` at `76f41dd`: 2
  lines, `ccp/prompt.py` and `ccp/submit.py`. `test_a_proven_fix_of_a_clean_review_is_submitted`
  (`tests/test_formal_submit.py`) already logs each proof run.
- **SPEC text to change, measured.** §15.1 says submit passes only when "the review record's review
  covers the PR head (§15.2)", so accepting a proven fix after a MAJOR review changes rule text and
  stays here, not in 0277. §15.1 does not name the exit 3 that `"def phase_refusal"` raises
  (`git grep -n 'exit 3' -- docs/cli/02-delivery.md` at `76f41dd`: 2 lines, the `ccp tasks next` row's and the submit row's).
  §23.7's `progress/<id>.json` row says "the verifier packet | the runner", but
  `"def progress_event"` (`ccp/queue.py`) writes the task's phase moves from every `phase_move`,
  including a worker's `ccp report`. The `review/` row says "the reviewer subagent", but `ccp report`
  writes `review/<task_id>.json` on a clean review.
- **§23.2 needs no change, measured.** `git grep -n '"review", "recorded"' -- ccp/report.py` at `76f41dd`: 1 line, emitting `run_id`, `verdict` and `severity`, which is §23.2's row.
  0258's first fix round dropped the `record` key that review#2 was about.
- **§11.1.** After the field list, which ends with `follow_ups` ("the report's lines"), the next
  sentence starts "`ccp report` computes them when the round reports, never from the report's
  prose". "Them" meant `integration_merges` and `before_review` (0169 added the sentence).
- **Merged since**: `git log --oneline a80cee0..76f41dd -- <this task's paths> ccp/report.py ccp/queue.py` at `76f41dd`, 10 commits:
  0260, 0261, 0263-0266, 0268, 0269, 0272 and 0276. None does part of this task's work.
  0276 changed only the first line of `ccp/submit.py`'s docstring; the others changed other logic in
  `ccp/prompt.py`, `ccp/verify.py`, `ccp/report.py` and `ccp/queue.py`. The symbols this Context names
  (`"def failures"`, `"def _review_gaps"`, `"def coverage"`, `"def phase_refusal"`, `"def submit"`,
  `"def review_gate"`, `"def skip_review"`, `"def write_review_record"`, `"def progress_event"`) and
  `ccp/report.py`'s clean-and-done call of `write_review_record` read as above at `76f41dd`.
- **Other tasks.** 0275 (R23, pending) changes the third item of §13.2's list, and this task changes the first. 0270
  cites §15.2 but changes other sections' text (§19.6 in `docs/spec/03-quality.md`). 0273 adds refusals to `ccp prompt verify` in `ccp/prompt.py` and
  `ccp/verify.py` that have nothing to do with the review skip. That is different logic in each case: no clash.

### Rulings for the build (the lead's)

- **Submit's coverage.** `ccp tasks submit` calls the review proof at most once. When the task has a
  fix round since its latest done review, and `verify.skip_review` or a review prover proves the fix
  (the judgement `ccp prompt verify` makes, §15.2), `review_artifact_present` passes whatever that
  review found, with no review record, or one naming an older review or another PR. Submit's output then adds `review_skip`
  (what the verify run would record). Without such a proof, the items stay as they are, including
  `verify.skip_review_after_clean` for a clean review's minor fix.
- **One proof per fix round.** `ccp/verify.py` gets `review_proof(cfg, queue, task_id, head, pr)`, which
  returns what `skip_review` returns plus the integration tip whose plane.json it read.
  `skip_review` keeps its signature and calls it. When submit proves a fix and passes, it writes
  `review_proof: {"head": <head>, "tip": <tip>, "review_skip": <skip>}` on that fix round's run record;
  a submit that fails writes none.
  In `ccp prompt verify`, `review_gate` reads the latest rework run's `review_proof`. When its `head`
  is the `--head`, `origin/<integration branch>`, after one fetch, is still its `tip`, and the task's
  latest done review is still the one it judged (`review_skip`'s `reviewed`), it takes `review_skip` as
  the verify run's skip and runs neither `proof` nor a prover. Otherwise it judges as today.
- **Docs.** `docs/cli/02-delivery.md`'s `ccp tasks submit` row adds "a fix `verify.skip_review` or a
  review prover proves passes after any review (§15.2)".

## Scope

- **In:** `ccp/submit.py`, `ccp/verify.py` (`review_proof`), `ccp/prompt.py` (`review_gate`),
  `docs/cli/02-delivery.md` (the submit row), `tests/test_formal_submit.py`, and the review-skip and
  review-gate test modules in `paths` where `review_gate`'s change reaches them.
- **SPEC, signed before the claim (`sign_off: brief`):** four passages in `docs/spec/02-delivery.md`
  and two rows in `docs/spec/04-observability.md`, each CURRENT at `76f41dd`.

    CURRENT (`docs/spec/02-delivery.md` at `76f41dd`), §15.1, the paragraph that starts "The plane records two of these phases":
    > Formal-submit is `ccp tasks submit <id>`, which the runner runs before `ccp prompt verify`: it exits 4, naming each failed item and moving nothing, unless the task has a PR, the review record's review covers the PR head (§15.2), and no spec question or escalation listing the task is open; a pass moves the task to `submitted`.

    PROPOSED:
    > Formal-submit is `ccp tasks submit <id>`, which the runner runs before `ccp prompt verify`. It refuses a task that is not mid-flight or is past `submitted` (`verifying`, `merging`), exit 3, moving nothing. Otherwise it exits 4, naming each failed item and moving nothing, unless the task has a PR, the PR head is covered, and no spec question or escalation listing the task is open; a pass moves the task to `submitted`. The head is covered when the review record's review is the task's latest review that reported `done` and covers the head (§15.2), or when `verify.skip_review` or a review prover proves the fix since that review, whatever it found (§15.2).

    CURRENT (`docs/spec/02-delivery.md` at `76f41dd`), §15.2, the bullet "A declared prover of the review", its last sentence:
    > The verify run's `review_skip` then adds `prover` (its name) and `exit_code`, never the command text (§14.4).

    PROPOSED:
    > The verify run's `review_skip` then adds `prover` (its name) and `exit_code`, never the command text (§14.4). A fix round's proof runs once: when `ccp tasks submit` proves the fix (§15.1), it records `review_proof` on the fix round's run (the head, the integration tip whose plane.json it read, and the `review_skip` a verify run would record), and `ccp prompt verify` of that head takes that `review_skip`, running neither `proof` nor a prover, while `origin/<integration branch>` is still at that tip after its fetch and the task's latest review that reported `done` is still the one it judged (`reviewed`); otherwise it judges the fix again. Submit records `review_proof` only when it passes.

    CURRENT (`docs/spec/02-delivery.md` at `76f41dd`), §13.2, item 1:
    > **The plane template** `templates/prompts/<phase>.md` (with `templates/prompts/_common.md`): the rules that hold in every product,

    PROPOSED:
    > **The plane template** `templates/prompts/<phase>.md` (with `templates/prompts/_common.md`, and, for a phase that pushes, the before-push part `templates/prompts/_gate.md`): the rules that hold in every product,

    CURRENT (`docs/spec/02-delivery.md` at `76f41dd`), §11.1, the sentence after the field list:
    > `ccp report` computes them when the round reports, never from the report's prose:

    PROPOSED:
    > `ccp report` computes `integration_merges` and `before_review` when the round reports, never from the report's prose (`follow_ups` are the report's own lines, §13.4):

    CURRENT (`docs/spec/04-observability.md` at `76f41dd`), §23.7, the table's `progress/<id>.json` row:
    > | `progress/<id>.json`, the verifier packet | the runner |

    PROPOSED:
    > | `progress/<id>.json`, the task's phase moves (`contracts/progress.schema.json`) | `ccp`, at each phase move (§10.1), whichever seat's command makes it |

    CURRENT (`docs/spec/04-observability.md` at `76f41dd`), §23.7, the table's `review/` row:
    > | `review/` | the reviewer subagent |

    PROPOSED:
    > | `review/<id>.json`, the task's review record (§15.1) | the reviewer, through `ccp report`, when its review reports clean |
- **Out:** §23.2 (measured right); `verify.skip_review_after_clean`; the review record's shape;
  `plugin/agents/delivery-runner.md` (its "handle each item as the matching refusal of `ccp prompt verify`"
  becomes true as written); 0273's refusals.

## dod_checks

- id: `cmd-01`
  story: As the runner of a product with verify.skip_review, the proven fix of a MAJOR review is submitted, and an unproven one is not.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_formal_submit 2>&1 | grep -e major -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_formal_submit --mutant-file <file>`, the file's mutant making submit ignore the proof when the latest done review found a BLOCKER or MAJOR, as before.
  expect: step 1 prints, each `ok`, a test where a fix after a review with `MAJOR=1`, proven by the fixture's `verify.skip_review` proof, with no clean review ever reported (no `review/<id>.json` in the queue), makes `ccp tasks submit` exit 0 with `to` `submitted` and a `review_skip` in its output; one where a clean review was followed by a MAJOR review and a proven fix, and submit exits 0; and one where the proof exits 1 and submit exits 4 naming `review_artifact_present` and records no `review_proof` on the fix run; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the tests are new.
- id: `cmd-02`
  story: As a product with an expensive prover, a fix round's proof runs once, and again only after the tip moved.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_formal_submit 2>&1 | grep -e once -e moved -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_formal_submit --mutant-file <file>`, the file's mutant making `review_gate` ignore the run's `review_proof`.
    3. Run the same with a second mutant file, whose mutant drops the head and tip comparison from `review_gate`'s reuse condition.
  expect: step 1 prints, each `ok`, a test where, on a proven fix, `ccp tasks submit` then `ccp prompt verify` of the same head leave the proof's log with exactly one line and the verify run's `review_skip` equal to the `review_proof` submit recorded; one where a commit pushed to the integration branch between the two makes the log hold two lines; and one where `ccp prompt verify` of a different `--head` (a later fix round's) makes the log hold two lines; then `OK`. Steps 2 and 3 each print the mutant `killed`, step 3's by the tip-moved test.
  dry run: n/a — the tests are new.
- id: `cmd-03`
  story: As the runner, the review-skip paths of ccp prompt verify still behave as before.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_review_skip tests.test_review_skip_provers tests.test_review_skip_clean tests.test_review_gate 2>&1 | tail -1`.
  expect: prints `OK`.
  dry run (`76f41dd`): printed `OK` (all four modules).
- id: `spec-01`
  story: As the operator, §11.1, §13.2, §15.1, §15.2 and §23.7 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0278`.
  expect: exit 0, all six PROPOSED passages found.
  dry run (simulated at `76f41dd`: this task file committed, then the six passages applied, each CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0278 --base HEAD~1`): `"ok": true`, six passage(s) found, none missing.

## Implementation notes

## Verification notes
