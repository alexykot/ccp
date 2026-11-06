---
task_id: 0002-spec-outline-and-section-map
title: Lay out the SPEC's parts and map every old section
status: done
kind: feature
depends_on: []
spec_refs: ["S31"]
adr_refs: []
review_point: R1
paths: ["docs/spec/", "docs/design/README.md", "docs/cli.md", "docs/cli/", "scripts/spec_map_check.py", "tests/test_spec_map_check.py", "docs/adr/0033-spec-layout-parts-in-docs-spec-renumbered-design.md"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0002-spec-outline-and-section-map

## Intent

A reader and a part writer can see the SPEC's target shape: five part files in `docs/spec/` with their sections numbered by topic, a map (one file per part) that says where every heading of the old `SPEC.md` goes, a list of rules proposed as obsolete for the operator, and a script that checks all of it.

## Context (not checked)

- ADR-0033 sets the layout (its D1 and D2 are built by the switch task, not here); the outline follows the regrouping the operator approved.
- Tables whose rows decide or amend different things (the early decision table, the "changes to earlier sections" tables) are mapped row by row, so each amendment folds into the rule it amends.
- Normative text never goes to the command reference: a section mixing rules and call syntax has both a section target and a `docs/cli/` target.
- The `spec_refs` above use the pre-restructure section numbers; the switch task rewrites them.

## Scope

- **In:** the outline; `docs/spec/MAP.md` (index) and `docs/spec/map/*.md` (one file per part, plus `dropped.md`); `docs/spec/RULINGS.md` with the first candidates; skeleton part files; `docs/design/README.md`; `docs/cli.md` (index) and `docs/cli/*.md` stubs; `scripts/spec_map_check.py` and its test.
- **Out:** moving any SPEC text (the part tasks); rewriting references (the switch task).

## dod_checks

- id: `map-01`
  story: As a part writer, I find every old heading in the map.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 scripts/spec_map_check.py coverage`.
  expect: exit 0: every `##`–`####` heading of `SPEC.md` has at least one map row with a target.
  dry run (`1924bf0`): exit 0; 186 headings, 226 rows.
- id: `map-02`
  story: As a reader, I find the five part files with continuous section numbers.
  setup: a checkout of the PR head.
  steps:
    1. List the `## N.` headings of `docs/spec/0*.md`.
  expect: five files, sections 1 to 31, each once.
  dry run (`1924bf0`): §1–§31, each once.
- id: `map-03`
  story: As the operator, I find every rule proposed as obsolete in one list.
  setup: a checkout of the PR head.
  steps:
    1. Compare the rows marked `operator (obsolete?)` in `docs/spec/map/*.md` with `docs/spec/RULINGS.md`.
  expect: each such row is listed, with the rule as it reads and why it looks obsolete.
  dry run (`1924bf0`): 4 rows, 4 entries.

## Implementation notes

- 2026-11-06: outline of 31 sections in five parts; the map as per-part files (226 rows covering all 186 headings; tables mapped row by row; 21 rows to design notes, 3 to the command reference alongside their section targets, 19 dropped-only, 4 proposed as obsolete); `RULINGS.md` with those 4; skeletons; `scripts/spec_map_check.py` (coverage, part, refs); ADR-0033 accepted.
- 2026-11-06, after review: amendment tables folded row by row; normative rules kept out of the command reference; rows that still carry live rules mapped to sections or proposed to the operator; per-part map, command and design files so the part tasks run in parallel; non-normative sections split into design notes and rules; titles naming a product or the owner made neutral.

## Verification notes

- `map-01`: pass — `spec_map_check.py coverage` exits 0.
- `map-02`: pass — §1–§31 continuous across `01-model.md` … `05-operations.md`.
- `map-03`: pass — 4 operator rows, 4 entries in `RULINGS.md`.

<!-- spec-refs: historical -->
