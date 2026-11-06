---
task_id: 0025-drop-legacy-role-names
title: Drop the pre-rename role names; only the operator names are read
status: done
kind: feature
depends_on: ["0009-privacy-scrub"]
spec_refs: ["S10", "S17", "S23"]
adr_refs: ["0006 D6"]
review_point: R1
paths: ["scripts/observability/lib.py", "scripts/observability/set-waiting-on.sh", "scripts/observability/emit-event.sh", "scripts/observability/spec_maintainer.py", "scripts/observability/team.py", "scripts/observability/architecture_review.py", "scripts/formal-submit.template.sh", "plugin/hooks/runner-idle.sh", "cpl/", "contracts/", "docs/spec/02-delivery.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0025-drop-legacy-role-names

## Intent

The plane reads and accepts only the operator role names. The names used before the operator rename
are gone from code, contracts, prompts and the SPEC; a product rewrites its old queue data before it
upgrades. Writers that validate input refuse the old names.

## Context (not checked)

- The operator ruled on 2026-11-06 that the managed product rewrites its own queue data and the plane
  drops the aliases without waiting for it.
- The old names carried a personal name, which a public repository must not.

## Scope

- **In:** the alias tables and normalisers in `scripts/observability/lib.py` and their callers; old values
  in `set-waiting-on.sh`, `emit-event.sh`, the idle hook, the submit template, `team.py`'s hidden verb,
  `spec_maintainer.py`; the contracts' deprecated values and fields; SPEC §10.1's sentence on them; tests.
- **Out:** a managed product's queue data (its lead rewrites it).

## dod_checks

- id: `code-01`
  story: As a plane developer, no pre-rename role name is left in the plane.
  setup: a checkout of the PR head and the operator's local denylist with case-insensitive patterns for the old names.
  steps:
    1. Run `CPL_LEAK_DENYLIST=<the denylist> scripts/leak-check.sh`.
  expect: `leak-check: clean`.
  dry run (`a6dcca1`): 12 files carried the old names (contracts, scripts, the hook, SPEC §10.1, tests).
- id: `code-02`
  story: As a runner, an old wait name is refused, not silently mapped.
  setup: a temporary queue.
  steps:
    1. Run `tests/test_operator_rename.py`.
  expect: `set-waiting-on.sh` refuses both old wait reasons; the actor and wait vocabularies hold only the operator names.
  dry run: n/a — the test is new.
- id: `suite-01`
  story: As a plane developer, everything still passes.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite and `cpl tasks check`, `cpl adr check`, `cpl docs check`.
  expect: all pass.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- Removed the alias tables (`OLD_VALUE_ALIASES`, `OLD_FIELD_ALIASES`) and every normaliser (`norm`,
  `field`, `norm_event`, `norm_task`, `norm_triage`, `norm_gate`, `norm_answer`) with their calls in the
  board, drill, quality, queue, architect, architecture review, spec maintainer and team scripts; the
  hidden pre-rename `gate` verb; the old gate status in the idle hook and submit template.
- Contracts: deprecated enum values and properties removed; the answer schema's `needs_operator` rule
  requires `question_for_operator` directly; the snapshot's questions require `operator_wait_hours`.
- SPEC §10.1: only the listed wait names are read; old data is rewritten by the product.
- ADR-0006 D6 amended.

## Verification notes

*Append-only.*

- `code-01` pass: the leak check with the case-insensitive old-name patterns prints `leak-check: clean`.
- `code-02` pass: `tests/test_operator_rename.py` (3 tests) passes.
- `suite-01`: see the PR's checks.
