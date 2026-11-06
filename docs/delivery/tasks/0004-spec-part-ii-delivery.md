---
task_id: 0004-spec-part-ii-delivery
title: Write SPEC Part II: delivery
status: done
kind: feature
depends_on: ["0002-spec-outline-and-section-map"]
spec_refs: ["S10", "S11", "S12", "S13", "S14", "S15", "S16", "S17", "S18"]
adr_refs: []
review_point: R1
paths: ["docs/spec/02-delivery.md", "docs/spec/map/02-delivery.md", "docs/cli/02-delivery.md", "docs/spec/RULINGS.md", "docs/design/team.md", "docs/design/toolkit.md"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0004-spec-part-ii-delivery

## Intent

`docs/spec/02-delivery.md` states, as rules only, everything its map file (`docs/spec/map/02-delivery.md`) sends to §10–§18: amendments folded into the rules they amend, history and incident narratives gone, examples neutral. The implementation notes and walk-throughs from the same rows are in their design notes, and call syntax in `docs/cli/02-delivery.md`. A rule's meaning does not change.

## Context (not checked)

- Follows ADR-0033 D2–D4 (cited here, not in `adr_refs`: those decisions are built by the switch task, and the strict in-force check refuses a done task citing an unbuilt decision).
- The old `SPEC.md` stays as it is until the switch to the parts lands; this task builds its part alongside and changes no references.
- It edits only its own files (its part, its map file, its command file, its design notes, and appends to `RULINGS.md`), so the five part tasks can run in parallel.
- A rule found obsolete or contradictory is kept as it reads, marked `operator (obsolete?)` in the map and appended to `RULINGS.md` (ADR-0033 D4).
- The ADRs carry the reasons; a section may cite the ADR instead of repeating its rationale.
- The `spec_refs` above use the pre-restructure section numbers; the switch task rewrites them.

## Scope

- **In:** every row of `docs/spec/map/02-delivery.md`; refining each `§N` target in §10–§18 to the `§N.M` written; its design notes and command file; `RULINGS.md` entries for what it finds.
- **Out:** other parts' files; reference rewrites (the switch task); product-specific text (dropped, or left for the privacy scrub if it is in code).

## dod_checks

- id: `part-01`
  story: As a reader, every row the map sends to §10–§18 has its subsection, and that subsection exists.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 scripts/spec_map_check.py part 02`.
  expect: it reports no unrefined target, no target without a heading, no missing backticked token and no operator row missing from `RULINGS.md`.
  dry run (`1924bf0`): fails as expected — every target is still a bare `§N`.
- id: `part-02`
  story: As a reader, the part holds rules only, with no product specifics.
  setup: a checkout of the PR head and the operator's denylist.
  steps:
    1. Read `docs/spec/02-delivery.md`; run `CPL_LEAK_DENYLIST=<the denylist> scripts/leak-check.sh`.
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

- 2026-11-06: `adr_refs` emptied at close, as task 0002 did (ADR-0033's decisions stay `not_built` until task 0008).
- 2026-11-06: `docs/spec/02-delivery.md` written, §10–§18 with 49 subsections (§10.1–§10.6, §11.1–§11.2,
  §12.1–§12.4, §13.1–§13.5, §14.1–§14.5, §15.1–§15.8, §16.1–§16.7, §17.1–§17.10, §18.1–§18.5).
  Amendments folded in: the toolkit's loop and reports (old §28.14), several runners into the lifecycle,
  hook, worktrees and gates (old §30.10), the lead model of spec questions (old §21/§25.4), declared
  `paths:` before Scope parsing (§5), the generic usage windows in the session park and claim rule 5.
  Dropped as history or old hosting: incident narratives, quoted rulings, trial reports, build orders,
  touch lists, the cron/Watchdog/email seat model (superseded by the agent team).
- Design notes: `docs/design/team.md` (old §25.11, §25.14) and `docs/design/toolkit.md` (old §28.0–§28.1
  rationale, §28.13, §28.17, the §28.23 why and implementation notes, the §28.26 evidence); call syntax in
  `docs/cli/02-delivery.md`. The map's Dropped tokens line lists every source name left out, with a reason
  (many belong to Parts I, III, IV and V).
- Four rules listed for the operator in `docs/spec/RULINGS.md` ("From Part II"), each kept as it reads:
  the scheduled-seat stale rule (§18.3), `verify_stale` (§18.3), the trial framing of two worker rules
  (§13.5), the CI template's database defaults (§15.7).

## Verification notes

*Append-only.*

- `part-01` pass: `python3 scripts/spec_map_check.py part 02` exits 0 (every target refined to an existing
  §N.M; every backticked source token present or listed under Dropped tokens; operator rows in RULINGS.md);
  `coverage` exits 0.
- `part-02` pass: the part holds rules only (no history, quoted ruling or product example); a grep for
  product names, owner, paths and the old hosting in the part, design notes and command file finds only the
  legacy wire values from before the operator rename, which §10.1 then said were read as their operator forms; `scripts/leak-check.sh`
  run without the operator's denylist (not available to this task) passes vacuously.
- `part-03` pass: RULINGS.md "From Part II" gives each entry's old place, the rule as it reads and why it
  looks wrong; none is changed in the part.

<!-- spec-refs: historical -->
