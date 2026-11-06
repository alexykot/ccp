---
task_id: 0003-spec-part-i-model
title: Write SPEC Part I: the model
status: done
kind: feature
depends_on: ["0002-spec-outline-and-section-map"]
spec_refs: ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]
adr_refs: []
review_point: R1
paths: ["docs/spec/01-model.md", "docs/spec/map/01-model.md", "docs/cli/01-model.md", "docs/spec/RULINGS.md", "docs/design/orientation.md", "docs/design/plugin.md"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0003-spec-part-i-model

## Intent

`docs/spec/01-model.md` states, as rules only, everything its map file (`docs/spec/map/01-model.md`) sends to §1–§9: amendments folded into the rules they amend, history and incident narratives gone, examples neutral. The implementation notes and walk-throughs from the same rows are in their design notes, and call syntax in `docs/cli/01-model.md`. A rule's meaning does not change.

## Context (not checked)

- The old `SPEC.md` stays as it is until the switch to the parts lands; this task builds its part alongside and changes no references.
- It edits only its own files (its part, its map file, its command file, its design notes, and appends to `RULINGS.md`), so the five part tasks can run in parallel.
- A rule found obsolete or contradictory is kept as it reads, marked `operator (obsolete?)` in the map and appended to `RULINGS.md` (ADR-0033 D4).
- ADR-0033 D2–D4 set the layout and the rules this task follows (not cited in `adr_refs`: they are built by the switch task, and a done task citing an unbuilt decision fails the in-force check).
- The ADRs carry the reasons; a section may cite the ADR instead of repeating its rationale.
- The `spec_refs` above use the pre-restructure section numbers; the switch task rewrites them.

## Scope

- **In:** every row of `docs/spec/map/01-model.md`; refining each `§N` target in §1–§9 to the `§N.M` written; its design notes and command file; `RULINGS.md` entries for what it finds.
- **Out:** other parts' files; reference rewrites (the switch task); product-specific text (dropped, or left for the privacy scrub if it is in code).

## dod_checks

- id: `part-01`
  story: As a reader, every row the map sends to §1–§9 has its subsection, and that subsection exists.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 scripts/spec_map_check.py part 01`.
  expect: it reports no unrefined target, no target without a heading, no missing backticked token and no operator row missing from `RULINGS.md`.
  dry run (`1924bf0`): fails as expected — every target is still a bare `§N`.
- id: `part-02`
  story: As a reader, the part holds rules only, with no product specifics.
  setup: a checkout of the PR head and the operator's denylist.
  steps:
    1. Read `docs/spec/01-model.md`; run `CPL_LEAK_DENYLIST=<the denylist> scripts/leak-check.sh`.
  expect: no history, incident narrative, quoted ruling or product example; the leak check is clean.
  dry run: n/a — the part is written by this task.
- id: `part-03`
  story: As the operator, I get every meaning change as a list instead of finding it folded in.
  setup: the PR body and `docs/spec/RULINGS.md`.
  steps:
    1. Read the rows this task added to `RULINGS.md`.
  expect: each entry gives the old place, the rule as it reads and why it looks wrong; none is changed in the part.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-06: wrote `docs/spec/01-model.md` (§1–§9, 43 subsections), `docs/design/orientation.md`,
  `docs/design/plugin.md` and `docs/cli/01-model.md`; refined every map row in range to `§N.M`.
- Folded, not changed: the later rules that already govern (the lead is design seat, steerer and
  spec maintainer for every project; the runner merges; the verifier runs the formal gate; the
  plugin replaced managed copies; worktrees and hooks replaced adapters; several runners), and the
  "changes to earlier sections" rows in range.
- Dropped as history: status banners, quoted rulings and dates, incident and migration narratives, a
  product's binding values; private paths and ids. Listed under the map file's Dropped tokens.
- Two rulings appended to `RULINGS.md` (§14 item 9 Tailscale gate; two obsolete §3 non-goals); both
  kept as they read in the part. §29.6 (delivery-state) was already listed and is kept as it reads.
- Note for the switch and the privacy scrub: the map file's Dropped tokens line has to spell the
  dropped private tokens for `spec_map_check.py` to accept them, so it names private paths and a
  product; `cpl docs check` warns on it. Scrub or strip those lines when the old SPEC is retired.

## Verification notes

*Append-only.*

- `part-01`: pass — `python3 scripts/spec_map_check.py part 01` exits 0 (and `coverage` exits 0).
- `part-02`: pass — read the part: rules only, no history or quoted rulings; no operator denylist was
  available, so the leak check passes vacuously; a grep for product names, the owner and local paths
  finds none in the part, design notes or command file (the map's Dropped tokens line is the known
  exception noted above).
- `part-03`: pass — `RULINGS.md` "From Part I" gives each entry's old place, the rule as it reads and
  why it looks wrong; neither is changed in the part.

<!-- spec-refs: historical -->
