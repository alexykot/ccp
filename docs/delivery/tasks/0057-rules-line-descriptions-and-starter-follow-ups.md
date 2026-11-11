---
task_id: 0057-rules-line-descriptions-and-starter-follow-ups
title: Rules lines take a description; starter-rules follow-ups
status: done
kind: bug
depends_on: []
spec_refs: ["S20"]
review_point: R4
paths: ["ccp/rules.py", "templates/docs-project/starter-rules.md", "plugin/agents/delivery-verifier.md", "docs/spec/03-quality.md", "tests/test_rules.py", "tests/test_starter_rules.py"]
created: 2026-11-10
updated: 2026-11-11
---

# Task: 0057-rules-line-descriptions-and-starter-follow-ups

## Intent

A rules-doc line `check: docs — <key> — <what it measures>` parses with its trailing description, as the template says it may, and the starter rules say truthfully what each checks and what declining one drops (§20).

## Context (not checked)

- From the review of the starter-rules task: (M1) the trailing description is a parse error; (M2) the refs-resolve rule promises a path check but names only `package_docs.rules.citations`, and declining the package-maps rule drops the whole `package_docs` block, `no_delivery_ids` included; (M3) `ccp init --starter-rules` leaves `architect.rules_doc` unset, so the rules marked `pass` are judged by nobody.
- NITs: the no-dates rule checks only `no_ids` and `history_attr`; the template says 'starter-rules.md beside this file', which is false in a product.
- Verifiers checking a change by hand must run the worktree's `bin/ccp`, not `ccp` on PATH (the run checkout).
- §31: this task's SPEC text describes its own feature. If the operator's standing ruling for such text (given for R3, 2026-11-10) is not extended to R4, the merge waits on their approval.

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

- 2026-11-11 (implementer): `rule_blocks` cuts a `docs` check's key list at the first ` — ` (em dash
  with spaces), so a trailing description is prose, not a key; a key after it is never read. M2:
  the refs-resolve rule (E7) no longer promises the path check; the package-maps rule (E6) now says
  every path a package doc names exists, and its check line describes what `package_docs` covers.
  §20.5 Decline says declining `package-maps` turns off the §21.3/§21.4 package-doc checks,
  `no_delivery_ids` and the path check included, while `package_docs.rules` still run (already the
  code's behaviour; a test now pins it). M3: §20.5 Adopt and the starter template say
  `architect.rules_doc` must be set for the `pass` rules to be judged. NITs: E5's check line now
  says it covers delivery ids outside history files and leaves dates and history to the architect's
  docs lens; the house-rules template (`templates/docs-project/ENGINEERING.md`, not in `paths`, but
  it holds the NIT's text) points at the plane's `templates/docs-project/starter-rules.md`. The
  verifier brief gains a bullet: for the control plane itself, hand checks use the checkout's own
  `bin/ccp`. §20.1 does not mention the optional description; the house-rules template does.

## Verification notes

- 2026-11-11 — verifier, PR #47 head `6ebbd4c` (squash `940edc1`): APPROVE. Passed: check-01, check-02. Gate: `scripts/gate.sh` exit 0, `bin/ccp tasks check` exit 0, `bin/ccp docs check` exit 0. Record: verification/0057-rules-line-descriptions-and-starter-follow-ups.json.
