---
id: ADR-0034
title: "SPEC restructure rulings"
status: accepted
date: "2026-11-06"
deciders: operator
spec_refs: [S3, S13, S15, S17, S18, S19, S23, S25, S29, S30, S31]
amends: ["ADR-0011", "ADR-0019"]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 built"
  - "D6 built"
  - "D7 built"
  - "D8 built"
  - "D9 built"
  - "D10 built"
  - "D11 built — task 0015"
  - "D12 built"
  - "D13 built"
  - "D14 built"
  - "D15 built"
notes: "2026-11-06: status proposed → accepted"
---
# ADR-0034 — SPEC restructure rulings

## Context

Rewriting the SPEC into its parts (ADR-0033) turned up rules that described removed mechanisms,
rules the code had outgrown, contradictions between old sections, and clarifications that existed
only in code or notes. ADR-0033 D4 sent each to the operator rather than settling it in the text;
the full list, with each ruling, is `docs/spec/RULINGS.md`.

## Decision

### D1. Rules of removed mechanisms are retired

Rules that served the removed hosting, seats or mechanisms leave the SPEC: the remote-blindness
digest, the mesh-network gate and non-goals, the watchdog's duties, wakes and knobs, the
spec-maintainer protocol's fail-closed rule, the hand retirement of state branches (the queue stays
the only runtime state), and any place for known-intentional notes other than the house rules.

### D2. Contradictions settle on the code's behaviour

Where old sections disagreed, the SPEC states what the plane does: triage grace counts "at least"
N merges; a run binds whatever the session; a spec question's lead message goes once, to a question
without `lead_messaged_at`; the citation rule reads `ids.spec.prefix`; the status command exits on
the board's blocker list; `cpl` on PATH links the run checkout.

### D3. Clarifications in code become rules

The checkpoint command's refusals, an unknown allowance reading gating nothing, and the deepest
binding root winning are SPEC rules.

### D4. A minor that could cost a later cycle is fixed before the merge

The others are listed in the verifier's record. This amends ADR-0011's merge rules.

### D5. The old architecture-review and docs-audit aliases are retired

Every bound project has moved to the architect seat.

### D6. No seat stale rule and no verify-stale blocker

Every seat is event-only; heartbeats stay. The `stale_seat` and `verify_stale` blockers and the
`cadence.verify_stale_minutes` knob go.

### D7. The board is the status

The older snapshot (`now.json`, `STATUS.md`) and the scripts that write or read it are retired.

### D8. Full prompt bodies are opt-in

The prompt audit keeps ids, refs and the prompt's hash; the full text only when a product opts in,
off by default, with retention by age. This amends ADR-0019.

### D9. A credit quota park is re-checked by the lead

A quota park with no window wake of its own is re-checked by the lead at its next session start.

### D10. Products run main; there is no plane pin

A product cannot pin a plane commit; a rollback is a revert on `main`.

### D11. A proposal untriaged for seven days is flagged

### D12. Neutral CI template defaults

The template ships no database service and expects no store tests unless a product says so.

### D13. Operator contact goes through the lead

Credit misuse or low API credit is raised to the lead as a gate; nothing emails. A product's probes
cover both the Claude login and forbidden ambient keys.

### D14. The worker rules that began as trials are standing rules

The implementer's self-check and exploration hygiene keep no trial framing.

### D15. The task-log owner starts shape

`shape` never runs on its own when an ADR is accepted.

## Consequences

- The SPEC no longer carries rules nothing implements or that contradict each other; each ruling
  that needs code has a plane task under R1 (0010–0015).
- Until those tasks land, the code still carries the retired mechanisms; the SPEC says so where it
  matters.
