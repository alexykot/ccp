---
task_id: 0073-init-polish-and-writing-guide
title: ccp init writes a tidy adoption, and the writing guide states the rules tasks check enforces
status: done
kind: chore
depends_on: []
spec_refs: ["S4", "S5", "S8"]
review_point: R5
paths: ["ccp/init.py", "ccp/tasklog.py", "plugin/skills/writing-tasks/", "CLAUDE.md", "tests/test_init*.py", "tests/test_tasklog*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0073-init-polish-and-writing-guide

## Intent

Every product runs `ccp init` once and `ccp tasks check` constantly; small frictions in both are removed, and the rules a task writer meets as check failures are written in the guide first (§4.5, §5, §8.3).

## Context (not checked)

- Accepted plane proposals from an adoption trial and a delivered task's review.
- Ruling sm-20261112T113121Z-f073 (lead, commit 11381a4): Build the Scope item. tasks check and
  tasks index do not print the estimates note while estimate.auto is off. Correct SPEC 26.3
  (docs/spec/04-observability.md) to say 'with estimate.auto on, they name the tasks that need an
  estimate': a section 31.1 correction of text the change makes false, so no gate. Edit
  ccp/estimator.py (notice returns nothing when estimate.auto is off) and update the pin in
  tests/test_estimator.py (test_auto_is_off_by_default_and_only_notes) to the new behaviour, with a
  test for both auto on and auto off. Both files are outside the task's declared paths: list
  ccp/estimator.py, tests/test_estimator.py (and docs/spec/04-observability.md, and ccp/cli.py if
  you touch it) in the PR body as outside the declared paths.

## Scope

- **In:** `ccp init`'s `CLAUDE.md` line is preceded by a blank line; it writes `production_branch` as §8.3's example shows; `ccp tasks check` and `ccp tasks index` stop printing the estimates note while `estimate.auto` is off; the plane's `CLAUDE.md` says how `ccp init` writing the binding into the run checkout's projects folder squares with never editing the clones; the writing-tasks skill states that `spec_refs` is required even beside `rule_refs`, how the `new` and `(removed)` path markings work, and that a task-file edit after signing makes a `brief` sign-off stale only for a task that declares one.
- **Out:** other init features.

## dod_checks

- id: `check-01`
  story: As an adopting lead, init's writes are tidy.
  setup: a scratch product whose `CLAUDE.md` ends without a blank line.
  steps:
    1. Run `ccp init`.
  expect: the appended line is preceded by a blank line, and the binding holds `production_branch`.
  dry run: on the merge base the line joins the previous paragraph and `production_branch` is absent.
- id: `check-02`
  story: As a task writer, the guide states the enforced rules.
  setup: a checkout of the PR head.
  steps:
    1. Read the writing-tasks skill.
  expect: it states the `spec_refs` rule, both path markings, and the brief sign-off staleness rule limited to tasks declaring it.
  dry run: on the merge base the first two are absent.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-12 (implement): `ccp init` appends the `CLAUDE.md` line as its own paragraph
  (`_paragraph_break` in `ccp/init.py`: no separator after an empty file or one already ending in a
  blank line, else line breaks up to one blank line), and writes `production_branch` beside
  `integration_branch` with the same value, as §8.3's example shows (init has no flag for a separate
  production branch; the operator edits the binding to name another). The writing-tasks skill states
  that `spec_refs` is a required key and, by default, a required citation even beside `rule_refs`
  (only a kind with its own `refs_any`, with the architect seat on, leaves it out); how the `new` and
  `removed` markings work (whole word, any case, within 25 characters after the closing backtick; a
  dependency's path also passes; a warning, not a failure); and that a brief sign-off goes stale on an
  edit only for a task declaring `sign_off: brief`. The plane's `CLAUDE.md` says the binding `ccp init`
  writes under the run checkout's gitignored `projects/` is local configuration, not an edit of the
  clone. The estimates-note item was not built: it contradicts SPEC §26.3 as written (see the report's
  open question).

- 2026-11-12 (ruling sm-20261112T113121Z-f073): the estimates-note item is built.
  `estimator.notice` returns nothing while `estimate.auto` is off (checked before the stale scan),
  so `ccp tasks check` and `ccp tasks index` print no estimates note then; with it on, the note and
  the detached launch are as before. SPEC §26.3 now says that with `estimate.auto` on they name the
  tasks that need an estimate (a §31.1 correction of text the change made false). The pinned test
  became `test_auto_is_off_by_default_and_says_nothing`, beside a new auto-on note test, and the
  `tasks check` note test now turns `estimate.auto` on and checks there is no note with it off. The
  same sentence in `docs/design/allowance.md` and `ccp/estimator.py`'s module docstring was
  corrected likewise, since the change made it false.

## Verification notes

- 2026-11-12 — verifier, PR #78 head `159dcc4` (squash `ef22273`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0073-init-polish-and-writing-guide.json.
