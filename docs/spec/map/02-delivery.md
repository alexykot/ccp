# Map: 02-delivery

Rows of the pre-restructure `SPEC.md` whose content goes to `docs/spec/02-delivery.md` (or to its design notes and command reference). Owned by the part's task, which refines each `§N` target in its range to the `§N.M` it writes. Rules listed as `operator (obsolete?)` are copied to `docs/spec/RULINGS.md` and not changed.

| Old | Title | Targets | Note |
|---|---|---|---|
| §2 — Implementer | Locked decisions (changelog from early drafts) | §13.1 |  |
| §2 — Same-session PR | Locked decisions (changelog from early drafts) | §13.1 |  |
| §2 — Separate review session | Locked decisions (changelog from early drafts) | §13.1 |  |
| §2 — Who merges | Locked decisions (changelog from early drafts) | §15.5 |  |
| §2 — Formal gate | Locked decisions (changelog from early drafts) | §15.1 |  |
| §2 — Token budget | Locked decisions (changelog from early drafts) | §18.4 |  |
| §7 — Claude (no --bare) | Surfaces (a product binding) | §13.1 |  |
| §7 — Worktrees and environment | Surfaces (a product binding) | §12.1 |  |
| §8 | Happy path | §10.1 |  |
| §8 — State machine |  | §10.1 |  |
| §9 | Standing DoD | §15.1 |  |
| §10 | Escalation | §17.1 |  |
| §12 | Operating window (locked 2026-09-17) | §18.1 |  |
| §12.1 | verify_stale | §18.3, operator (obsolete?) |  |
| §13 | Quota | §18.4 |  |
| §20.1.4 | Seat liveness | §18.3, operator (obsolete?) |  |
| §21 | Spec maintainer | §17.1 |  |
| §21.0 | Intent | §17.1 |  |
| §21.1 | Project binding | §17.2 |  |
| §21.2 | Who may raise a question, and triage | §17.2 |  |
| §21.3 | Question channel | §17.3 |  |
| §21.3.1 | Question file | §17.3 |  |
| §21.3.2 | Raise sequence | §17.3 |  |
| §21.4 | Authority | §17.4 |  |
| §21.5 | Verdicts and answer file | §17.5 |  |
| §21.6 | needs_operator | §17.6 |  |
| §21.7 | Lock files (shared stale rule) | §11.2 | the shared process-lock rule |
| §21.8 | Skip-ahead | §17.7 |  |
| §21.9 | Observability | §17.8 |  |
| §21.9.1 | Events | §17.8 |  |
| §21.9.2 | Wait reason and board | §17.8 |  |
| §24.2 | Commands | §10.6, §21, `docs/cli/02-delivery.md`, `docs/cli/03-quality.md` | rules → sections: the exit-code contract and `tasks next` selection → §10, the `tasks check` rule list → §21; only call syntax and flags → cli |
| §25.3 | Runner lifecycle | §10.2 |  |
| §25.3.1 | Merge and verify rules | §15.6, §15.2 |  |
| §25.4 | Spec questions | §17.3 |  |
| §25.5 | Gates: the design seat approves *(operator, 2026-09-30)* | §17.9 | gate decision mechanics; the gates list is §3 |
| §25.7 | Route to the operator | §17.10 |  |
| §25.8 | Liveness without a watchdog | §18.2, §18.4, §18.3 |  |
| §25.9 | Working trees | §12.1 |  |
| §25.11 | Acceptance checks (walkable) | `docs/design/team.md` |  |
| §25.14 | Implementation notes (2026-09-30, non-normative) | `docs/design/team.md` |  |
| §27 | Verification and merge | §15.1 |  |
| §27.1 | Formal gate and standing DoD | §15.1, §15.3, §15.4, §15.5, §15.7, operator (obsolete?) |  |
| §27.2 | Queue rules beside the gate | §15.8 |  |
| §28 | Seat toolkit, telemetry and the project board | §10.6 |  |
| §28.0 | Problem and intent | §10.6 |  |
| §28.1 | Design choices (and why) | §10.6 |  |
| §28.2 | Runs | §11.1 |  |
| §28.3 | The toolkit | §10.3, §10.4, §10.5, §10.6, `docs/cli/02-delivery.md` | the rules (and the note) → §10; only call syntax and flags → cli |
| §28.4 | Worker prompts | §13.2, §13.3, §15.2 |  |
| §28.13 | Acceptance checks (walkable) | `docs/design/toolkit.md` |  |
| §28.14 — §25.2 reports through cpl report | Changes to earlier sections | §13.4 |  |
| §28.14 — §25.3 step 2 loop through cpl | Changes to earlier sections | §10.2 |  |
| §28.17 | Implementation notes (2026-10-21, non-normative) | `docs/design/toolkit.md` |  |
| §28.23 | Test runs through `cpl suite run` | §14.1, §14.2, §14.3, §14.4, §14.5, `docs/design/toolkit.md` |  |
| §28.25 | Review-point backfill, longer notes, worker environment (2026-10-22, non-normative) | `docs/design/review-points.md`, §22, §13.3 | marked non-normative: the notes → design; backfill rules → §22; the worker environment → §13 |
| §28.26 | Worker efficiency (2026-10-22) | §13.5, operator (obsolete?) |  |
| §28.29 | Worktrees and environments (`cpl wt`) | §12.1, §12.2, §12.3, §12.4, §15.5, §10.5 |  |
| §30 | Parallel tasks: several runners | §16.1 |  |
| §30.0 | Problem and intent | §16.1 |  |
| §30.1 | Design choices (and why) | §16.1 |  |
| §30.2 | The knob | §16.2 |  |
| §30.3 | Which tasks may start together | §16.3 |  |
| §30.4 | Queue state | §16.4 |  |
| §30.5 | How the runners work | §16.5 |  |
| §30.6 | Exclusive test lanes | §16.6 |  |
| §30.7 | Forecast, actuals, usage and the board | §16.7 |  |
| §30.10 — §25.2 runner row | Changes to earlier sections | §2, §16.1 |  |
| §30.10 — §25.3 several runners, claim, rotation | Changes to earlier sections | §10.2, §16.5 |  |
| §30.10 — §25.8 hook per runner | Changes to earlier sections | §18.2, §16.5 |  |
| §30.10 — §25.9 merge worktree per runner | Changes to earlier sections | §12.1, §16.5 |  |
| §30.10 — §25.3 claim holder; §25.4/§25.5/§28.7 answer the holder | Changes to earlier sections | §10.5, §17.9, §25 |  |
| §30.10 — §25.13 several runners settled | Changes to earlier sections | §16.1 |  |
| §30.10 — §28.3 next and claim | Changes to earlier sections | §10.3, §16.3 |  |

<!-- spec-refs: historical -->
