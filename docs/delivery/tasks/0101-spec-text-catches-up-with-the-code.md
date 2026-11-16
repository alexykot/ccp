---
task_id: 0101-spec-text-catches-up-with-the-code
title: SPEC passages that say less than the code does, or the wrong thing, are corrected
status: pending
kind: docs
depends_on: []
spec_refs: ["S2", "S3", "S4", "S5", "S10", "S12", "S13", "S14", "S15", "S16", "S27", "S28"]
review_point: R6
paths: ["docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "README.md"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0101-spec-text-catches-up-with-the-code

## Intent

Earlier tasks made SPEC passages false or incomplete. This task corrects each one so that it says
what the code does. All of it is §31.1 text: it describes accepted features or corrects passages a
merged change made false. It adds no rule and changes no code.

## Context (not checked)

- Eleven accepted plane proposals (operator, 2026-11-16: all approved), the follow-ups of earlier tasks.
  Each one names a passage below.
- The tool and test follow-ups from the same proposals are tasks 0102–0105. This task is text only.

## Scope

- **In**, one correction per passage:
  - §4.5: `ccp` is allowed by name. Only `team.sh` and `spec-maintainer-ask.sh` are allowed by path,
    as §4.3 and the template already do.
  - §10.3: `ccp tasks next` reads task statuses at the integration tip, and skips tasks the queue
    holds as done or dropped.
  - §2.6: the seat knobs list `rotate_at_context_tokens` beside `rotate_after_tasks`, and state that
    single-runner mode does not take the claim's holder into account for rotation.
  - §4.5 or `ccp init`'s section: an origin on GitHub Enterprise is warned about as "not GitHub". This
    is deliberate, and the text says so.
  - §3.6: `notify.lead`'s `tool` and `to` are "non-empty, single-line strings".
  - §5.5: the marking window stops at the next backtick. §13.4: say which report-field values count as
    the pasted template, as the code now judges them.
  - §13.2 and the last sentence of §15.2's lead bullet: name the minor-only skip of the re-review, as
    §15.2 states it elsewhere.
  - §14.2: `{head}` is the task head under test (the product checkout's HEAD), not the HEAD of the
    tip's worktree where provers now run.
  - §12.1: a SIGTERM before the worktree exists exits 143 with no result JSON, unless task 0104 makes
    it emit one: write whichever is true at merge. A descendant that leaves the process group can
    hold a timeout open. `--shallow` needs git protocol v2.
  - §16.5: "or can be made" is stated as it is checked (the dry run does not check that
    `origin/<integration>` resolves, unless task 0103 adds that check: write whichever is true at
    merge).
  - §27.1 and §28.3: the round lists name merge and ruling rounds.
  - README: the deny rules are prefix matches. They catch the spellings listed, not every spelling
    (task 0102 adds more forms; the README says what holds after it).
- **Out:**
  - Any change to code, or to what a rule requires.

## dod_checks

- id: `check-01`
  story: As a reader of the SPEC, each listed passage says what the code does.
  setup: a checkout of the PR head.
  steps:
    1. For each passage in Scope, read the new text and the code it describes.
  expect: each one matches the code at the head, and none adds a requirement the code does not
    enforce.
  dry run: n/a.
- id: `check-02`
  story: As the operator, nothing here needed my approval.
  setup: the PR diff.
  steps:
    1. Read every changed SPEC line.
  expect: each one describes existing behaviour or corrects a false passage (§31.1). The verdict's
    `spec_beyond_intent` is empty.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
