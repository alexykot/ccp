---
task_id: 0095-sign-off-policy-and-spec-beyond-intent
title: Text that only describes an accepted feature needs no sign-off; text beyond the task's intent is caught and signed
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S15"]
review_point: R5
paths: ["ccp/lifecycle.py", "ccp/verify.py", "ccp/report.py", "templates/prompts/", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-runner.md", "plugin/skills/writing-tasks/", "docs/spec/01-model.md", "contracts/", "tests/test_sign_off*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0095-sign-off-policy-and-spec-beyond-intent

## Intent

A product's operator signs only text a task adds beyond what its accepted brief and ADR call for:
text that only describes the accepted feature needs no sign-off, and the reviewer and verifier catch
anything beyond it, so approved PRs do not wait on sign-offs they do not need and unexpected rule
changes still reach the operator (§3.5).

## Context (not checked)

- Accepted plane proposal. A managed product's approved PRs waited hours for SPEC sign-off after
  verify, holding runner slots, although the text only described the task's own feature. The plane's
  own repo already follows this policy (§31.1).
- Operator approval, 2026-11-12, in the lead session: "I approve proposed changes for 15c4 and
  9f18." This is the acceptance (§31.1): § text that states only what this task describes needs no
  further gate.

## Scope

- **In:**
  - §3.5 and the writing-tasks skill state the default: a task whose SPEC or contract text follows
    from its accepted ADR and brief declares no `sign_off`.
  - The reviewer's and the verifier's reports carry `spec_beyond_intent`: the normative text the PR
    adds or changes that the brief and its ADR do not call for (an empty list when none). Their
    briefs and prompts say how to judge it.
  - A non-empty `spec_beyond_intent` in the latest verdict makes a `build` sign-off due on the task
    even if undeclared: `ccp tasks close` refuses until the lead records it (`ccp tasks sign-off`),
    and the runner tells the lead which text needs it.
- **Out:** changing who may sign or how a sign-off is recorded.

## dod_checks

- id: `check-01`
  story: As the operator, I'm asked only about text beyond the task's intent.
  setup: a scratch product; a task with no `sign_off`; a verdict whose `spec_beyond_intent` lists one
    passage.
  steps:
    1. Run `ccp tasks close <task> --pr <n>`.
    2. Record a build sign-off, then close again.
  expect: the first close is refused naming the passage and `ccp tasks sign-off`; the second
    proceeds.
  dry run: on the merge base the field does not exist and close proceeds.
- id: `check-02`
  story: As a runner, describing text alone does not hold a task.
  setup: as check-01 with `spec_beyond_intent: []`.
  steps:
    1. Run `ccp tasks close <task> --pr <n>`.
  expect: no sign-off is required.
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

*Append-only.*
