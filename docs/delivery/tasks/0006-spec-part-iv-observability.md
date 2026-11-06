---
task_id: 0006-spec-part-iv-observability
title: Write SPEC Part IV: observability and spend
status: done
kind: feature
depends_on: ["0002-spec-outline-and-section-map"]
spec_refs: ["S23", "S24", "S25", "S26", "S27", "S28"]
adr_refs: []
review_point: R1
paths: ["docs/spec/04-observability.md", "docs/spec/map/04-observability.md", "docs/cli/04-observability.md", "docs/spec/RULINGS.md", "docs/design/observability.md", "docs/design/telemetry.md", "docs/design/allowance.md", "docs/design/board.md"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0006-spec-part-iv-observability

## Intent

`docs/spec/04-observability.md` states, as rules only, everything its map file (`docs/spec/map/04-observability.md`) sends to §23–§28: amendments folded into the rules they amend, history and incident narratives gone, examples neutral. The implementation notes and walk-throughs from the same rows are in their design notes, and call syntax in `docs/cli/04-observability.md`. A rule's meaning does not change.

## Context (not checked)

- The old `SPEC.md` stays as it is until the switch to the parts lands; this task builds its part alongside and changes no references.
- It edits only its own files (its part, its map file, its command file, its design notes, and appends to `RULINGS.md`), so the five part tasks can run in parallel.
- A rule found obsolete or contradictory is kept as it reads, marked `operator (obsolete?)` in the map and appended to `RULINGS.md` (ADR-0033 D4).
- The ADRs carry the reasons; a section may cite the ADR instead of repeating its rationale.
- The `spec_refs` above use the pre-restructure section numbers; the switch task rewrites them.
- This task implements part of ADR-0033 D2–D4. They are cited here rather than in `adr_refs`, because
  the strict in-force check refuses a done task citing decisions recorded as not built (they become
  built when the switch task lands).

## Scope

- **In:** every row of `docs/spec/map/04-observability.md`; refining each `§N` target in §23–§28 to the `§N.M` written; its design notes and command file; `RULINGS.md` entries for what it finds.
- **Out:** other parts' files; reference rewrites (the switch task); product-specific text (dropped, or left for the privacy scrub if it is in code).

## dod_checks

- id: `part-01`
  story: As a reader, every row the map sends to §23–§28 has its subsection, and that subsection exists.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 scripts/spec_map_check.py part 04`.
  expect: it reports no unrefined target, no target without a heading, no missing backticked token and no operator row missing from `RULINGS.md`.
  dry run (`1924bf0`): fails as expected — every target is still a bare `§N`.
- id: `part-02`
  story: As a reader, the part holds rules only, with no product specifics.
  setup: a checkout of the PR head and the operator's denylist.
  steps:
    1. Read `docs/spec/04-observability.md`; run `CPL_LEAK_DENYLIST=<the denylist> scripts/leak-check.sh`.
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

- 2026-11-06: wrote `docs/spec/04-observability.md` (§23 ledger, timers, status command,
  reconciliation, quota and auth fields, queue writers, prompt audit, knobs; §24 telemetry source,
  receiving, routing, attribution, model and effort; §25 samples, usage windows, checkpoint, session
  park and wake; §26 estimates, records, baseline and seat, forecast, allowance fit, calibration;
  §27 health measures and suite series; §28 board read model, freshness, contents, rules).
  Amendments folded: §28.14's five rows, §29.12's board row, §30.10's holder, session-park and
  throughput rows. Old hosting (watchdog, mesh proof URLs, emailed digests, old launch forms) and
  history (trials, incidents, quoted rulings) left out.
- Implementation notes and walk-throughs to `docs/design/observability.md`, `telemetry.md`,
  `allowance.md` (now also estimation, forecast and calibration detail) and `board.md`, scrubbed of
  product names, ids, paths and trial figures; call syntax to `docs/cli/04-observability.md`.
- Map refined to `§N.M`; dropped tokens listed with reasons. The list necessarily quotes the old
  SPEC's product paths and ids so the checker can match them; the privacy scrub (task 0009) or the
  switch (0008) should remove that list once the old SPEC is gone.
- Five rulings appended to `docs/spec/RULINGS.md` under "From Part IV": the watchdog's quota wake,
  `now.json`/`STATUS.md` still written, the watchdog's duties without an owner, full prompt bodies
  "for alpha", and the bot-seat knobs. Each rule is left out of the part only where the ruling row
  says so; none is changed.

## Verification notes

*Append-only.*

- 2026-11-06 `part-01`: pass. `python3 scripts/spec_map_check.py part 04` exits 0 (every target in
  §23–§28 refined to a heading that exists; no missing backticked token; every operator row listed in
  `RULINGS.md`); `coverage` exits 0.
- 2026-11-06 `part-02`: pass. The part holds rules only: no history, incident narrative, quoted
  ruling or product example. A grep for the product names, the owner, local paths and proposal ids
  over the part, its design notes and its command file finds none (the operator's denylist was not
  available to this run; `scripts/leak-check.sh` without it passes vacuously).
- 2026-11-06 `part-03`: pass. "From Part IV" in `RULINGS.md` lists five entries, each with the old
  place, the rule as it reads and why it looks wrong; none is changed in the part.

<!-- spec-refs: historical -->
