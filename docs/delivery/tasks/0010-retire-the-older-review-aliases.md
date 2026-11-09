---
task_id: 0010-retire-the-older-review-aliases
title: Retire the older architecture-review and docs-audit aliases
status: pending
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S19"]
adr_refs: ["0034 D5"]
review_point: R1
paths: ["scripts/architecture-review.sh", "scripts/observability/architecture_review.py", "ccp/docaudit.py", "ccp/cli.py", "ccp/seats.py", "ccp/config.py", "scripts/sync-product-docs.sh", "plugin/", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0010-retire-the-older-review-aliases

## Intent

The architect seat is the only review command: `scripts/architecture-review.sh` and `ccp docs audit` no longer exist, and nothing in the plane calls them.

## Context (not checked)

- Every bound project has moved to the architect seat (ADR-0034 D5); §19.12 already states the aliases as retired.
- A sync keeps reporting a product's leftover managed copies of the two older skills as `retired`.
- Old queue records written by the aliases (reviews, state files) stay readable by the board and health.
- Ruling sm-20261109T212706Z-3761 (2026-11-09): this task's PR deletes the §19.12 parenthetical
  that says the aliases are still in the code, and the second sentence of §21.7 (`ccp docs audit`
  with no `architect` block). A plane.json `docs_audit` block is refused as an unknown key; a
  binding's `architecture_review` block stays allowed by the schema and unread. The §31 approval
  is the RULINGS §26.13 row (retire the aliases; code: task 0010, operator, 2026-11-06).

## Scope

- **In:** the alias script and command, the code paths only they use, their config keys, briefs and skills that mention them, tests.
- **Out:** the architect seat itself; reading old records.

## dod_checks

- id: `code-01`
  story: As a plane developer, no alias command remains.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -E 'architecture-review\.sh|docs audit' -- ccp scripts plugin`.
  expect: no match apart from a reader of old records, each with a comment saying so.
  dry run (`216cda1`): 11 matching lines in ccp/, scripts/ and plugin/.
- id: `compat-01`
  story: As an operator with older queue records, the board and health still build.
  setup: a temporary `QUEUE_ROOT` holding an older architecture-review state file and report.
  steps:
    1. Run `ccp board build` and `ccp health` against it.
  expect: both succeed.
  dry run: n/a — the test this task adds builds the queue.

## Implementation notes

*Append-only, newest last.*

- 2026-11-09 (implementer): Removed `scripts/architecture-review.sh`, `ccp/docaudit.py`, the
  `ccp docs audit` subcommand (and its board-refresh entries) and `tests/test_docaudit.py`.
  `scripts/observability/architecture_review.py` keeps only the review kit the architect uses:
  `Kind`, lock, validation, rendering, triage. The alias-only `AR` kind, the project.yaml
  `architecture_review` reader, due/run/status/main and the CLI entry point are gone. Every
  function now takes its kind, and `triage` takes a required `max_new` with no `probes`, which it
  never used. The plane.json `docs_audit` key, its defaults and its schema block are gone, so a
  `docs_audit` block is now refused as an unknown key. No bound product carries one.
- Old records stay readable. `ccp/seats.py` still reads `docs-audit.json`, with a comment saying
  it is a reader of old records. `lib.py` keeps the `architecture_review` and `docs_audit` event
  types for older ledgers. `contracts/project.schema.json` still allows a binding's
  `architecture_review` block, which nothing reads. `sync-product-docs.sh` still reports and
  removes leftover managed copies of the two older skills as `retired`.
- New `tests/test_review_aliases_retired.py`: board and health against a queue that holds older
  alias state, reports and events, plus the removed command. The alias tests in `test_architect.py`
  and `test_team_hosting.py` are gone. Briefs, skills, package docs and design notes were updated.
  ADR-0034 D5 is recorded as built.
- Not done, pending a ruling: SPEC §19.12's parenthetical ("still in the code until task 0010
  removes them") and §21.7's second sentence (`ccp docs audit` with no architect block) now
  describe removed code. The task gives no SPEC edit, so both are left for the runner or the lead.
- 2026-11-09 (implementer, round 2): Applied ruling sm-20261109T212706Z-3761. SPEC §19.12 loses
  its parenthetical saying the aliases are still in the code, and §21.7 keeps only its first
  sentence. The ruling also asked for the Context bullet above, which records it. Merged
  `origin/main` (task 0046). Two SPEC passages outside the ruling still name the removed alias:
  `docs/spec/01-model.md`, the seat table (`ccp docs audit run`) and the config-block table (a
  `docs_audit` block). Both are left for a ruling.

## Verification notes

*Append-only.*
