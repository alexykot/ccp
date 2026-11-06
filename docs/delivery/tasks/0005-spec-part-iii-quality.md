---
task_id: 0005-spec-part-iii-quality
title: Write SPEC Part III: quality
status: done
kind: feature
depends_on: ["0002-spec-outline-and-section-map"]
spec_refs: ["S19", "S20", "S21", "S22"]
adr_refs: []
review_point: R1
paths: ["docs/spec/03-quality.md", "docs/spec/map/03-quality.md", "docs/cli/03-quality.md", "docs/spec/RULINGS.md", "docs/design/architect.md", "docs/design/doc-checks.md", "docs/design/plan.md", "docs/design/review-points.md"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0005-spec-part-iii-quality

## Intent

`docs/spec/03-quality.md` states, as rules only, everything its map file (`docs/spec/map/03-quality.md`) sends to §19–§22: amendments folded into the rules they amend, history and incident narratives gone, examples neutral. The implementation notes and walk-throughs from the same rows are in their design notes, and call syntax in `docs/cli/03-quality.md`. A rule's meaning does not change.

## Context (not checked)

- The old `SPEC.md` stays as it is until the switch to the parts lands; this task builds its part alongside and changes no references.
- It edits only its own files (its part, its map file, its command file, its design notes, and appends to `RULINGS.md`), so the five part tasks can run in parallel.
- A rule found obsolete or contradictory is kept as it reads, marked `operator (obsolete?)` in the map and appended to `RULINGS.md` (ADR-0033 D4).
- ADR-0033 D2–D4 set what this part does (cited here, not in `adr_refs`: the strict in-force check refuses a done task citing decisions the switch task has not built yet, as for task 0002).
- The ADRs carry the reasons; a section may cite the ADR instead of repeating its rationale.
- The `spec_refs` above use the pre-restructure section numbers; the switch task rewrites them.

## Scope

- **In:** every row of `docs/spec/map/03-quality.md`; refining each `§N` target in §19–§22 to the `§N.M` written; its design notes and command file; `RULINGS.md` entries for what it finds.
- **Out:** other parts' files; reference rewrites (the switch task); product-specific text (dropped, or left for the privacy scrub if it is in code).

## dod_checks

- id: `part-01`
  story: As a reader, every row the map sends to §19–§22 has its subsection, and that subsection exists.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 scripts/spec_map_check.py part 03`.
  expect: it reports no unrefined target, no target without a heading, no missing backticked token and no operator row missing from `RULINGS.md`.
  dry run (`1924bf0`): fails as expected — every target is still a bare `§N`.
- id: `part-02`
  story: As a reader, the part holds rules only, with no product specifics.
  setup: a checkout of the PR head and the operator's denylist.
  steps:
    1. Read `docs/spec/03-quality.md`; run `CPL_LEAK_DENYLIST=<the denylist> scripts/leak-check.sh`.
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

- 2026-11-06: `docs/spec/03-quality.md` written: §19 the architect seat (19.1–19.12), §20 house rules,
  budgets and refactors (20.1–20.4), §21 doc checks (21.1–21.8), §22 review points and the plan
  (22.1–22.10). The older architecture review and docs audit are folded into §19 and §21.7; the
  §29.12 amendment (INDEX frozen, plan fields on `board.json`) is folded into §22.10; the rules stated
  inside the old non-normative notes (§26.16, §28.24, §28.25) are in their sections; the notes,
  walk-throughs and the older kinds' files are in `docs/design/architect.md`, `doc-checks.md`,
  `plan.md` and `review-points.md`; call syntax in `docs/cli/03-quality.md`. Every map row refined
  to `§N.M`; the dropped tokens are listed with reasons.
- Meaning changes found, kept as built and listed in `docs/spec/RULINGS.md` ("From Part III"): the
  triage grace "more than" vs "at least"; the Watchdog's review duties (the seat is gone); the
  known-intentional notes' home (`LOCAL.md` vs the house rules).

## Verification notes

*Append-only.*

- `part-01` pass: `python3 scripts/spec_map_check.py part 03` exits 0 (no unrefined target, no
  missing heading, no missing token, no operator row missing from `RULINGS.md`); `coverage` exits 0.
- `part-02` pass: the part holds rules only (history, incident narratives, quoted rulings and
  product examples left out; the example register is neutral). `scripts/leak-check.sh` has no
  denylist in this worktree, so it passes vacuously; a grep for the managed products' names, the
  owner and local paths over the part, its design notes and command file finds nothing.
- `part-03` pass: three entries appended to `RULINGS.md` under "From Part III", each with the old
  place, the rule as it reads and why; none is changed in the part.

<!-- spec-refs: historical -->
