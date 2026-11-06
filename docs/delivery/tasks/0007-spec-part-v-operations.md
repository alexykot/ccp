---
task_id: 0007-spec-part-v-operations
title: Write SPEC Part V: operations
status: done
kind: feature
depends_on: ["0002-spec-outline-and-section-map"]
spec_refs: ["S29", "S30", "S31"]
adr_refs: []
review_point: R1
paths: ["docs/spec/05-operations.md", "docs/spec/map/05-operations.md", "docs/cli/05-operations.md", "docs/spec/RULINGS.md"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0007-spec-part-v-operations

## Intent

`docs/spec/05-operations.md` states, as rules only, everything its map file (`docs/spec/map/05-operations.md`) sends to §29–§31: amendments folded into the rules they amend, history and incident narratives gone, examples neutral. The implementation notes and walk-throughs from the same rows are in their design notes, and call syntax in `docs/cli/05-operations.md`. A rule's meaning does not change.

## Context (not checked)

- Implements ADR-0033 D2–D4 for Part V; those decisions stay `not_built` until the switch task
  (0008), so they are cited here, not in `adr_refs` (the strict in-force check refuses a done task
  citing a not-built decision).
- The old `SPEC.md` stays as it is until the switch to the parts lands; this task builds its part alongside and changes no references.
- It edits only its own files (its part, its map file, its command file, its design notes, and appends to `RULINGS.md`), so the five part tasks can run in parallel.
- A rule found obsolete or contradictory is kept as it reads, marked `operator (obsolete?)` in the map and appended to `RULINGS.md` (ADR-0033 D4).
- The ADRs carry the reasons; a section may cite the ADR instead of repeating its rationale.
- The `spec_refs` above use the pre-restructure section numbers; the switch task rewrites them.

## Scope

- **In:** every row of `docs/spec/map/05-operations.md`; refining each `§N` target in §29–§31 to the `§N.M` written; its design notes and command file; `RULINGS.md` entries for what it finds.
- **Out:** other parts' files; reference rewrites (the switch task); product-specific text (dropped, or left for the privacy scrub if it is in code).

## dod_checks

- id: `part-01`
  story: As a reader, every row the map sends to §29–§31 has its subsection, and that subsection exists.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 scripts/spec_map_check.py part 05`.
  expect: it reports no unrefined target, no target without a heading, no missing backticked token and no operator row missing from `RULINGS.md`.
  dry run (`1924bf0`): fails as expected — every target is still a bare `§N`.
- id: `part-02`
  story: As a reader, the part holds rules only, with no product specifics.
  setup: a checkout of the PR head and the operator's denylist.
  steps:
    1. Read `docs/spec/05-operations.md`; run `CPL_LEAK_DENYLIST=<the denylist> scripts/leak-check.sh`.
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

- 2026-11-06: wrote `docs/spec/05-operations.md`: §29.1–§29.5 (merged is released and pinning,
  the run checkout, compatibility across a release, `cpl` on PATH, knobs), §30.1–§30.3 (credential
  checks, two wallets, no ambient keys), §31.1–§31.5 (SPEC changes, ADRs, no local automation,
  proposing a tool, triage). Map rows refined to `§N.M`; dropped tokens listed with reasons
  (other parts' §2 rows and §15 paragraph, removed tooling, old-hosting proof URLs, one machine's
  paths). Call syntax in `docs/cli/05-operations.md`. Five candidate rulings appended to
  `RULINGS.md` under "From Part V"; each rule is kept as it reads.
- The map's dropped-token line quotes two local paths and the repo slug because the check needs the
  exact tokens; the switch (0008) or the privacy scrub (0009) removes the line once the old SPEC is
  gone.

## Verification notes

*Append-only.*

- `part-01`: pass — `python3 scripts/spec_map_check.py part 05` prints nothing (exit 0);
  `coverage` is clean too.
- `part-02`: pass, judged — the part holds rules only (no history, incident or quoted ruling; the
  push incident and the mesh-network paragraph are left out). The leak check passes vacuously here
  (no denylist set in this worktree); the operator's run with the denylist is still owed.
- `part-03`: pass — five rows under "From Part V" in `RULINGS.md`, each with the old place, the rule
  as it reads and why it looks wrong; none is changed in the part.

<!-- spec-refs: historical -->
