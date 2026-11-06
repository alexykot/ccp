---
task_id: 0008-spec-switch-to-parts
title: Switch the SPEC to its parts and rewrite every section reference
status: done
kind: feature
depends_on: ["0003-spec-part-i-model", "0004-spec-part-ii-delivery", "0005-spec-part-iii-quality", "0006-spec-part-iv-observability", "0007-spec-part-v-operations"]
spec_refs: ["S31"]
adr_refs: ["0033 D1", "0033 D2"]
review_point: R1
paths: ["SPEC.md", "docs/spec/", "cpl/", "scripts/", "plugin/", "templates/", "contracts/", "tests/", "docs/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0008-spec-switch-to-parts

## Intent

`SPEC.md` is a short index of the five parts, and every reference to a SPEC section anywhere in the repo names its new place, so a reader following any `§` reference lands on the rule it means.

## Context (not checked)

- The rewrite is mechanical from the map files: a script records, for each reference it rewrites, the old section and the new one; a reference whose old section was dropped is reworded or removed.
- `SPEC.md` may have changed after the map was made: re-run the coverage check on the last old `SPEC.md` before deleting its body.
- ADR and task `spec_refs` take the new numbers; `ids.spec` keeps the `S<n>` form.
- Products that cite plane sections get a prompt for their lead with the old → new map; the plane writes nothing in a product's repo.
- When it lands, record ADR-0033 D1–D4 built (`cpl adr decide 33 Dn built`).
- The `spec_refs` above use the pre-restructure section numbers; the switch task rewrites them.

## Scope

- **In:** `SPEC.md` as the index; deleting the old body; rewriting `§` references in code comments, docstrings, messages, contracts, plugin briefs and skills, templates, tests, `docs/` and ADR/task frontmatter; the product-lead prompt (in the PR body).
- **Out:** changing any rule; product repos.

## dod_checks

- id: `ref-01`
  story: As a part writer, the map still covers the final old SPEC.
  setup: the last commit before the old body is deleted.
  steps:
    1. Run `python3 scripts/spec_map_check.py coverage --spec SPEC.md` on that commit.
  expect: exit 0.
  dry run: n/a.
- id: `ref-02`
  story: As a reader, every rewritten reference lands on the section the map intended.
  setup: a checkout of the PR head and the rewrite script's record.
  steps:
    1. For each recorded rewrite, check the new section equals the map's target for the old one (refined to §N.M where the map has it).
    2. Run `python3 scripts/spec_map_check.py refs $(git ls-files cpl scripts plugin templates contracts tests docs)`.
  expect: every rewrite matches its map row; every `§` reference resolves to a heading of `docs/spec/`.
  dry run: n/a — the parts are not written yet.
- id: `ref-03`
  story: As a plane developer, everything still passes after the switch.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `cpl tasks check`, `cpl adr check`, `cpl docs check`.
  expect: all pass.
  dry run: n/a.
- id: `ref-04`
  story: As a product lead, I have the map to update my product's references.
  setup: the PR body.
  steps:
    1. Read the product-lead prompt.
  expect: it lists the old → new sections a product cites and asks for nothing else.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-06 — The operator ruled on every row of `docs/spec/RULINGS.md` ("I approve all as
  recommended"); the ruling column is filled and the parts apply the rulings (retired rules removed,
  confirmations kept, clarifications stated, code-dependent rules state their target and their task).
  ADR-0034 records the rulings (15 decisions; 9 built here, 6 not built until tasks 0010–0015) and
  amends ADR-0011 (minors before merge) and ADR-0019 (prompt bodies opt-in). New plane tasks
  0010–0015 carry the code follow-ups.
- `SPEC.md` is now the index of the five parts; the old body is deleted. Coverage ran clean on the
  final old SPEC before the deletion.
- References rewritten from the map: about 1,390 rewrites in some 165 files. A section whose map row
  has one target takes it; where a row has several, the target is chosen from the citing context
  (the line and the lines around it, scored against the new headings and the topic words of each
  candidate: prefer/hold/release/drop → §10.4, claim/close → §10.5, triage → §31.5, propose → §31.4,
  park → §25.4, checkpoint → §25.3 and so on), and an unclear choice cites the top-level section
  rather than a guessed subsection. A bare top-level reference maps to a top-level section; a section
  that went to a design note points at the note. Seven references to dropped history were reworded
  by hand, duplicate references a rewrite produced were collapsed, and ADR and task `spec_refs` were
  set by each record's subject. The rewrite log (file, line, old, new, how chosen) is kept outside
  the repo with the plane session.
- The restructure's own records (the map files, `RULINGS.md`, `MAP.md`, tasks 0001–0008, ADR-0033)
  name pre-restructure sections on purpose; they carry the marker `spec-refs: historical`, which
  `spec_map_check.py refs` skips. The map files' "Dropped tokens" lines, which quoted product names
  and paths, are removed.
- ADR-0033 D1–D4 recorded as built.

## Verification notes

*Append-only.*

- `ref-01`: pass — `spec_map_check.py coverage --spec <the final old SPEC>` exit 0 before deletion.
- `ref-02`: pass — every rewrite's target is one of its map row's targets, or that target's top-level
  section (the log records each and how it was chosen); `spec_map_check.py refs` over cpl, scripts,
  plugin, templates, contracts, tests, docs, README.md, CLAUDE.md and SPEC.md exits 0, and every ADR
  and task `spec_refs` entry names an existing section.
- `ref-03`: pass — full suite OK (1034 tests, 1 skipped); `cpl tasks check` (15 tasks), `adr check`,
  `docs check` clean; `state/*` empty.
- `ref-04`: pass — the product-lead prompt is in the PR body.

<!-- spec-refs: historical -->
