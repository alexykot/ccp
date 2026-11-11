---
task_id: 0055-merge-and-ruling-rounds
title: Merge-only and ruling rounds are rounds of their own
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S15"]
review_point: R4
paths: ["ccp/prompt.py", "ccp/runs.py", "templates/prompts/", "plugin/agents/delivery-runner.md", "docs/spec/02-delivery.md", "tests/test_prompt*.py", "tests/test_runs*.py"]
created: 2026-11-10
updated: 2026-11-11
---

# Task: 0055-merge-and-ruling-rounds

## Intent

The runner can launch a round that only merges the integration tip into a task branch, or only applies a lead's spec ruling, as a named round (`ccp prompt merge`, `ccp prompt ruling` or one `--kind`), so the run record and the prompt say what the round was instead of an `implement-N` run with a note file (§13, §15).

## Context (not checked)

- Today only `ccp prompt fix` counts as a fix round; tip merges and rulings ran as `implement-N` with `--note-file`, which mislabels the run and its prompt.
- §31: this task's SPEC text describes its own feature. If the operator's standing ruling for such text (given for R3, 2026-11-10) is not extended to R4, the merge waits on their approval.
- From later proposals: `ccp prompt fix` refuses when no review or verify report exists yet, so a lead ruling applied before review also runs as an implement round; and a pure merge-from-main catch-up still needs a review round before verify. Both belong to the round kinds this task adds.

## Scope

- **In:** the new round kind(s) with their own prompt template, run name and phase; the runner brief uses them; review and verify treat their heads like a fix round's; §13 lists them.
- **Out:** changing what a fix round is.

## dod_checks

- id: `check-01`
  story: As a runner, a tip merge is recorded as one.
  setup: a scratch product with a task in review.
  steps:
    1. Run the merge round prompt and record the run.
  expect: the run's kind is the merge round, not `implement`.
  dry run: on the merge base no such kind exists.
- id: `check-02`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-11 (implementer): two run phases, `merge` and `ruling` (`ccp prompt merge|ruling <id> --pr --head`),
  each with its own template (`templates/prompts/merge.md`, `ruling.md`), run id `<task>/merge[-n]` and
  `<task>/ruling[-n]`, the implementer's agent type and seat, and the task moved to `fixing`. A ruling round
  needs its ruling as `--note`/`--note-file` (exit 2 otherwise) and, unlike a fix, no prior review report.
  Their reports carry `PR:`, `Head:` and the declared verdicts, as a fix's. Review and verify treat their heads
  as a fix round's: the review and verify prompts list their reports; `runs.unreviewed_fix` counts them as
  fix rounds newer than the last review, except that rounds since that review that are all merge rounds
  pass when the head carries the reviewed change unchanged (same patch id, the existing integration-merge
  rule); `verify.skip_review` may prove them; `verify.repeat_round` counts them between verify rounds. The
  `behind_tip` refusal and the runner brief name `ccp prompt merge`. SPEC §11.1 (phase list) and §13.2/§13.4
  describe the kinds. Touched beyond the declared paths, as the change needs: `ccp/cli.py` (the phase
  choices), `ccp/report.py` (the report lines), `ccp/verify.py` (skip and repeat), the review template,
  README and `docs/cli/02-delivery.md`, and `tests/test_review_skip.py`, `tests/test_parallel_merging.py`.
- 2026-11-11 (implementer, fix round 1): SPEC §15.2 and §15.6 rule 4 now name merge and ruling rounds
  beside fix rounds (review MINOR 1). `reported_verdicts` breaks a same-second tie by when the run opened
  before phase and round, since round numbers are per phase (NIT 1). The close-time `behind_tip` refusal and
  the merge-conflict hint name `ccp prompt merge` (NIT 3). New tests: `ccp verify record` refused after a
  ruling round, and a merge round judged by real patch ids (MINOR 3). Known gap, left for a follow-up task
  (MINOR 2): `ccp/health.py`, `ccp/drill.py` and `ccp/estimate.py` count only implement, review, fix and
  verify, so merge and ruling rounds fall under "other" and out of `fix_rounds` and `rev_end`.

## Verification notes

*Append-only.*
