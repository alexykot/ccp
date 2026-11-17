---
task_id: 0147-signed-text-in-context-and-stale-sign-offs-wait
title: The signed-text check finds a passage that starts on an unchanged line, and next passes over a stale or malformed brief sign-off
status: pending
kind: feature
depends_on: ["0142-signed-text-checks"]
spec_refs: ["S3", "S10", "S15"]
review_point: R9
sign_off: brief
paths: ["ccp/verify.py", "ccp/selection.py", "ccp/cli.py", "ccp/lifecycle.py", "docs/spec/02-delivery.md", "tests/test_verify_spec_text.py", "tests/test_sign_off.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0147-signed-text-in-context-and-stale-sign-offs-wait
## Intent

A one-clause edit to a wrapped SPEC passage passes `ccp verify spec-text` when the PR carries the
signed words, even though the passage's first words sit on a line the PR did not touch; and
`ccp tasks next` never offers a task that `ccp tasks claim` will refuse for its brief sign-off, stale or
malformed as well as missing.

## Context (not checked)

- After task 0142, `ccp verify spec-text` reads each hunk's added lines as one text. A signed passage whose
  first words sit on an unchanged line before the added one is still not found. Measured at `921507e`:
  `git diff 7ff1abd^ 7ff1abd -- docs/spec` against task 0128's `signed_passages`: 4 of 12 not found, each of this kind.
  Implementers rewrap the SPEC to make the check pass (task 0130's fix round did), which churns the SPEC.
- §15.2 says the check looks "in the lines the branch adds", so reading unchanged lines too is a rule change.
- `selection.unsigned` (`"def unsigned"` in `ccp/selection.py`) passes over a task only when its brief
  sign-off is missing. `ccp tasks claim` also refuses a stale one (its head lacks the task file's last
  change, `_brief_stale` in `ccp/lifecycle.py`) and a malformed `sign_off:` value, so `next` offers a task
  the claim then refuses.
- §10.3 names only the missing case, so passing over the other two is a rule change too.
- Split from 0142, which carries the parts of the same proposals that need no new text.

## Scope

- **In:**
  - `ccp/verify.py` `spec_text`: for each hunk the branch's diff makes to a SPEC file, the text read is the
    hunk's lines in the head's file extended with the unchanged lines before and after it up to the
    nearest blank line on each side (the paragraph or list item), joined and whitespace-normalised. A
    passage is found when it lies within that text and covers at least one character of a line the hunk
    adds. A passage wholly inside unchanged lines is not found.
  - `ccp/selection.py` `unsigned` (and its callers in `ccp/cli.py`): a task is passed over when its brief
    sign-off is missing, stale (the test `ccp tasks claim` applies, read in the checkout `next` runs from)
    or its `sign_off:` value is malformed; the stderr line names which, with the command that fixes it.
    `ccp/lifecycle.py` keeps one implementation of the stale test, which both use.
  - `docs/spec/02-delivery.md` §15.2. CURRENT (at `921507e`): "and looks for it, whitespace-normalised, in the lines the branch adds to files under `task_log.spec_paths`" PROPOSED:
    > and looks for it, whitespace-normalised, in each hunk the branch's diff makes to files under `task_log.spec_paths`, read with the unchanged lines around it up to the nearest blank line on each side, where it covers at least one line the hunk adds
  - `docs/spec/02-delivery.md` §10.3. CURRENT (at `921507e`): "A task whose `brief` sign-off is due and not recorded (§3.5) is passed over the same way, and stderr names the missing sign-off, so the runner takes the next task it can claim." PROPOSED:
    > A task whose `brief` sign-off is due and not recorded, is stale, or whose `sign_off:` value is malformed (§3.5) is passed over the same way, and stderr names which, so the runner takes the next task it can claim.
  - Each PROPOSED passage goes in on lines of its own, unwrapped, the line holding its first word part
    of the diff.
- **Out:**
  - Matching across hunks that a blank line separates.
  - What claim refuses (unchanged).

## dod_checks

- id: `spec-01`
  story: As a reviewer, a passage whose head sits on an unchanged line is found.
  setup: a fixture repo (`tests/test_verify_spec_text.py`'s) whose SPEC paragraph wraps "Alpha one two" / "three four." over two lines; the task signs "Alpha one two three four five."; the branch changes only the second line to "three four five.".
  steps:
    1. Run `ccp verify spec-text 0001-signed --base <base>`.
  expect: exit 0.
  dry run: n/a.
- id: `spec-02`
  story: As a reviewer, unchanged text alone, or text across a blank line, is not found.
  setup: the fixture repo; case A: the signed passage already in the SPEC before the branch, the branch adding an unrelated line elsewhere; case B: the passage's halves in two paragraphs separated by a blank line, the branch adding the second.
  steps:
    1. Run `ccp verify spec-text 0001-signed --base <base>` for each case.
  expect: exit 1 in both, naming the passage.
  dry run: n/a.
- id: `next-01`
  story: As a runner, next does not offer a task its claim will refuse.
  setup: a scratch product with a queue and three pending tasks declaring `sign_off: brief`: one whose recorded sign-off covers a commit before the task file's last change, one whose `sign_off:` value is `breif`, and one with a current sign-off.
  steps:
    1. Run `ccp tasks next`.
  expect: it prints the task with the current sign-off; stderr names the other two, one as stale and one as malformed.
  dry run: n/a.
- id: `next-02`
  story: As a runner, a task next offers is one claim takes.
  setup: the product of next-01 with the current-sign-off task done.
  steps:
    1. Run `ccp tasks next`.
  expect: exit 3; nothing offered.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Run `ccp verify spec-text 0147-signed-text-in-context-and-stale-sign-offs-wait`, and compare the §15.2 and §10.3 edits with the PROPOSED text above.
  expect: exit 0, both match word for word, and no other § rule changes.
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

## Verification notes
