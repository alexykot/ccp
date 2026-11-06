# Map: 03-quality

Rows of the pre-restructure `SPEC.md` whose content goes to `docs/spec/03-quality.md` (or to its design notes and command reference). Owned by the part's task, which refines each `§N` target in its range to the `§N.M` it writes. Rules listed as `operator (obsolete?)` are copied to `docs/spec/RULINGS.md` and not changed.

| Old | Title | Targets | Note |
|---|---|---|---|
| §23 | Architecture review | §19.1 | the architecture review is folded into the architect seat |
| §23.0 | Problem and intent | §19.1 |  |
| §23.1 | Design choices (and why) | §19.2 |  |
| §23.2 | Pieces | §19.3 |  |
| §23.3 | Trigger (Task Runner) | §19.6 |  |
| §23.4 | The reviewer call (`run`) | §19.7 |  |
| §23.5 | Triage (`triage`) | §19.8, operator (obsolete?) | the `LOCAL.md` notes vs §26.7 → `RULINGS.md` |
| §23.6 | Seats | §19.9, operator (obsolete?) | the Watchdog duties → `RULINGS.md` |
| §23.7 | Observability | §19.10 |  |
| §23.8 | Binding and knobs | §19.11 |  |
| §23.9 | Implementation notes (2026-09-30, non-normative) | `docs/design/architect.md` |  |
| §24.2 | Commands | §10, §21.1, §21.2, `docs/cli/02-delivery.md`, `docs/cli/03-quality.md` | rules → sections: the exit-code contract and `tasks next` selection → §10, the `tasks check` rule list → §21.1, `docs check` → §21.2; only call syntax and flags → cli |
| §24.4 | Package-doc rules (`package_docs`) | §21.3, §21.4, §21.5, §21.6 |  |
| §24.5 | Docs audit | §21.7, §19.4 |  |
| §24.6 | Seats | §21.8 |  |
| §24.7 | Implementation notes (2026-09-30, non-normative) | `docs/design/doc-checks.md` |  |
| §26 | Architect seat: the structural health of a product and its delivery | §19.1 |  |
| §26.0 | Problem and intent | §19.1 |  |
| §26.1 | Design choices (and why) | §19.2 |  |
| §26.2 | Pieces | §19.3 |  |
| §26.3 | Lenses | §19.4 |  |
| §26.4 | Modes | §19.5 |  |
| §26.5 | Triggers, and how `cpl` enforces them | §19.6, operator (obsolete?) | "more than" vs §26.16's "at least" → `RULINGS.md` |
| §26.6 | The run | §19.7 |  |
| §26.7 | House rules (`rules_doc`) | §20.1, §20.2 |  |
| §26.8 | Refactor tasks | §20.3, §20.4 |  |
| §26.10 | Triage | §19.8 |  |
| §26.11 | Seats | §19.9 |  |
| §26.13 | Migration from §23 and §24.5 | §19.12, operator (obsolete?) | the old commands stay as aliases until every bound project has moved → §19.12; whether they are still needed → operator |
| §26.14 | Acceptance checks (walkable) | `docs/design/architect.md` |  |
| §26.15 | Open knobs | §19.11, operator (obsolete?) | the automatic-shape question → `RULINGS.md` |
| §26.16 | Implementation notes (2026-10-14, non-normative) | `docs/design/architect.md`, §19.5, §19.6, §19.7, §19.8, §20.1, §20.2, §20.3, §20.4, §22.5 | the notes → design; the rules stated in them (merge = a task reaching done, when `next` blocks, failed passes, shape detail, house-rule syntax, budgets outside the gate, a change's own budgets, refactor ordering, the spawn's new-point rule) → their sections |
| §28.9 | Review points on tasks | §22.1, §22.2, §22.3, §22.4, §22.5, §22.6, §22.10 |  |
| §28.24 | Step 5: plan and backlog (2026-10-22, non-normative) | `docs/design/plan.md`, §20.3, §22.3, §22.6, §22.9, §22.10 | marked non-normative: the notes → design; the plan and backlog rules → §22 |
| §28.25 | Review-point backfill, longer notes, worker environment (2026-10-22, non-normative) | `docs/design/review-points.md`, §22.6, §13 | marked non-normative: the notes → design; backfill rules → §22; the worker environment → §13 |
| §28.27 | The review-point register (2026-10-22) | §22.2, §22.3, §22.4, §22.7, §22.8, §22.9 |  |
| §29.12 — §28.9 fields to board.json | Changes to earlier sections | §22.10, §28 |  |

<!-- spec-refs: historical -->
