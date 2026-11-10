---
task_id: 0057-rules-line-descriptions-and-starter-follow-ups
title: Rules lines take a description; starter-rules follow-ups
status: pending
kind: bug
depends_on: []
spec_refs: ["S20"]
review_point: R4
paths: ["ccp/rules.py", "templates/docs-project/starter-rules.md", "plugin/agents/delivery-verifier.md", "docs/spec/03-quality.md", "tests/test_rules.py", "tests/test_starter_rules.py"]
created: 2026-11-10
updated: 2026-11-10
---

# Task: 0057-rules-line-descriptions-and-starter-follow-ups

## Intent

A rules-doc line `check: docs — <key> — <what it measures>` parses with its trailing description, as the template says it may, and the starter rules say truthfully what each checks and what declining one drops (§20).

## Context (not checked)

- From the review of the starter-rules task: (M1) the trailing description is a parse error; (M2) the refs-resolve rule promises a path check but names only `package_docs.rules.citations`, and declining the package-maps rule drops the whole `package_docs` block, `no_delivery_ids` included; (M3) `ccp init --starter-rules` leaves `architect.rules_doc` unset, so the rules marked `pass` are judged by nobody.
- NITs: the no-dates rule checks only `no_ids` and `history_attr`; the template says 'starter-rules.md beside this file', which is false in a product.
- Verifiers checking a change by hand must run the worktree's `bin/ccp`, not `ccp` on PATH (the run checkout).

## Scope

- **In:** `rule_blocks` cuts the key list at the first ` — `; M2: reword the rule or name `package_docs`, and §20.5 states what declining the package-maps rule drops; M3: one sentence in the template and §20.5 that `architect.rules_doc` must be set for `pass` rules to be judged; the two NITs; the verifier brief says to run the worktree's own `bin/ccp` for hand checks.
- **Out:** new starter rules.

## dod_checks

- id: `check-01`
  story: As a product, a described rules line parses.
  setup: a scratch rules doc with `check: docs — package_docs — what it measures`.
  steps:
    1. Run `ccp docs check`.
  expect: the line is read as the `package_docs` check; no parse error.
  dry run: on the merge base it is a parse error.
- id: `check-02`
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
