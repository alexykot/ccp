---
task_id: NNNN-kebab-slug
title: One line, imperative
status: pending          # pending | done | dropped (in-flight states live in the queue, not here)
kind: feature            # feature | refactor (plane SPEC §20; a refactor changes no behaviour)
depends_on: []           # ["0001-first-task", ...] — never bury a dependency in a check
spec_refs: []            # ["docs/SPEC.md#flows"] — the sections this task must satisfy
# A refactor cites house rules or review findings instead of spec_refs/adr_refs:
# rule_refs: ["E3"]   review_refs: ["ar-20261014T120000Z-ab12#F03"]   (one per line)
# A new task citing an ADR the architect has not shaped (architect.shape_adrs), only with a reason:
# shaping: waived — <reason>
# The files or globs this task touches; parallel scheduling reads them (plane SPEC §16.3):
# paths: ["src/exports/", "tests/test_exports.py"]
# Only when the task-log owner amends this task's id (a new slug, the same NNNN): the old id.
# renamed_from: NNNN-old-slug
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Task: NNNN-kebab-slug

> The plane's canonical task format (plane SPEC §5). Never delete this file. `ccp tasks check`
> validates it; `ccp tasks close` writes `status: done` and the verification note.
> Writing rules: the `writing-tasks` skill, then `docs/delivery/WRITING-tasks.md`.

<!-- Frontmatter is one `key: value` per line; lists are inline (`[a, "b"]`). A product may
     require more fields (e.g. `adr_refs`) in docs/delivery/plane.json. If task intent drifts from
     the cited SPEC, or SPEC conflicts with PROJECT, raise a spec question (plane SPEC §17) or
     escalate to the lead (the design seat); only the lead may escalate to the operator, and it may record
     rulings in `## Context (not checked)` below (commit `spec(<question_id>): …`). -->

## Intent

One paragraph: what is true for the product's user when this is done. An outcome, not a diff.

## Context (not checked)

Background, product policy and constraints that shape the build but are **not** walked by the
verifier as pass/fail checks.

- …

## Scope

- **In:** …
- **Out:** …

## dod_checks

Task-specific checks only: the standing DoD always applies. Each check is a user story the
verifier can perform: setup → steps → an observable result. At most six; no soft language.

- id: `ui-01`
  story: As a <role>, I <action> …
  setup: <preconditions / URL / account / data>
  steps:
    1. …
  expect: <concrete, observable result>
  dry run (`<commit>`): <what each command step printed, or its count. Only on a check with a step that runs a command; if it cannot run yet: `dry run: n/a — <why>`>

## Implementation notes

*Append-only, newest last.* The runner, from the implementer's report.

## Verification notes

*Append-only.* The verifier, per check id: pass or fail, with evidence, one `- ` line each.
`ccp tasks close` adds the merge record (PR, head, merge commit).
