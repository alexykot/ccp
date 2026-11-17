---
task_id: 0122-unsigned-tasks-wait-and-signed-text-check
title: tasks next passes over a task awaiting its brief sign-off, and a command checks the PR's SPEC text against the signed words
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S10", "S15"]
review_point: R8
sign_off: brief
paths: ["ccp/selection.py", "ccp/lifecycle.py", "ccp/verify.py", "ccp/cli.py", "templates/prompts/review.md", "templates/prompts/verify.md", "docs/spec/02-delivery.md", "tests/test_next*.py", "tests/test_sign_off.py", "tests/test_verify_spec_text.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0122-unsigned-tasks-wait-and-signed-text-check
## Intent

A runner never idles on a task it cannot claim for want of the operator's signature while other
ready tasks wait, and the reviewer and verifier confirm a PR's SPEC edits are the signed words with
one command instead of a hand comparison.

## Context (not checked)

- `ccp tasks next` named a task whose brief sign-off was missing; `ccp tasks claim` then refused it
  and the slot idled until the lead reordered the queue with `ccp tasks prefer` (two runners, one
  review point of the plane, 2026-11-17).
- Signed passages sit in a task's Scope as a `PROPOSED:` marker followed by `> ` blockquote lines.
- §31.1 for the command: it is this task's own feature, described in §15.

## Scope

- **In:**
  - `ccp/selection.py` / `ccp/lifecycle.py`: `ccp tasks next` passes over a task whose `brief`
    sign-off is due and unrecorded, naming it and the missing sign-off on stderr, as it does a held task.
  - `docs/spec/02-delivery.md` §10.3. CURRENT (at `b4de6ad`): none; a new sentence before "A held task (§10.4) is passed over, a held refactor and a held preference alike, and stderr says so;". PROPOSED:
    > A task whose `brief` sign-off is due and not recorded (§3.5) is passed over the same way, and stderr names the missing sign-off, so the runner takes the next task it can claim.
  - `ccp verify spec-text <task_id> [--base REF]` (new): reads each `PROPOSED:` blockquote in the
    task's Scope and looks for it, whitespace-normalised, in the lines the branch adds under
    `task_log.spec_paths` (`git diff <base>...HEAD`, base default the integration branch on the remote); exit 0 when
    all are found, 1 naming each passage not found, 2 when the task has no `PROPOSED:` block.
  - `templates/prompts/review.md`, `templates/prompts/verify.md`: for a task with `sign_off: brief`,
    run `ccp verify spec-text` and report its result.
  - `docs/spec/02-delivery.md` §15: one paragraph describing the command (§31.1).
- **Out:**
  - Judging text the PR adds beyond the signed passages (the `spec_beyond_intent` report does that).

## dod_checks

- id: `cmd-01`
  story: As a runner, an unsigned task does not block the queue.
  setup: a scratch task log with pending 0001 (`sign_off: brief`, unsigned) and 0002 (no sign-off), both ready.
  steps:
    1. Run `ccp tasks next`.
  expect: prints 0002; stderr names 0001 and its missing `brief` sign-off.
  dry run: n/a.
- id: `cmd-02`
  story: As a runner, a signed task is picked as usual.
  setup: the log of cmd-01 after `ccp tasks sign-off 0001 --stage brief` is recorded.
  steps:
    1. Run `ccp tasks next`.
  expect: prints 0001.
  dry run: n/a.
- id: `cmd-03`
  story: As a verifier, matching text passes.
  setup: a scratch repo whose task carries one `PROPOSED:` blockquote, and a branch adding that passage to `docs/spec/x.md` with different line wrapping.
  steps:
    1. Run `ccp verify spec-text <task> --base main`.
  expect: exit 0.
  dry run: n/a.
- id: `cmd-04`
  story: As a verifier, a changed word is caught.
  setup: the repo of cmd-03 with one word of the added passage changed.
  steps:
    1. Run `ccp verify spec-text <task> --base main`.
  expect: exit 1, naming the passage; a task with no `PROPOSED:` block exits 2.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Run `ccp verify spec-text 0122-unsigned-tasks-wait-and-signed-text-check` at the PR head.
  expect: exit 0, and the §15 paragraph only describes the command.
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

- 2026-11-17 (implementer): `selection.pick` passes over, beside the holds, each ready task that declares
  `sign_off: brief` with no `brief` sign-off in the ledger (`selection.unsigned`), unless the queue holds a
  lease on it (its claim resumes it with no sign-off check); `ccp tasks next` names each on stderr, the
  preference note and `--explain` mark it, and the board's ready queue (the same `pick`) agrees. A stale
  brief sign-off or a malformed `sign_off:` is not passed over: the signed sentence names only one "not
  recorded", and claim still refuses those.
- `ccp verify spec-text` (`verify.signed_passages`, `added_spec_lines`, `spec_text`): a passage is the
  `> ` lines straight after a Scope line holding `PROPOSED:`; each SPEC file's added lines (`git diff
  --unified=0 <base>...HEAD`, files under `task_log.spec_paths` as `tasklog._names_spec` reads them) are
  joined into one whitespace-normalised text and the passage is a substring of it. It needs no
  QUEUE_ROOT; the default base is `origin/<integration branch>` (the binding's with QUEUE_ROOT, else
  `main`), nothing fetched. Output is JSON on stdout (each passage with its task-file line and the files
  it was found in, `missing`), the passages not found named on stderr.
- The review and verify prompts render the step only for a `brief` task: a new prompt value,
  `brief_sign_off` (`ccp/prompt.py`, outside the declared paths), and a row in `docs/cli/02-delivery.md`.

## Verification notes
