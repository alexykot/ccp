# Map: 04-observability

Rows of the pre-restructure `SPEC.md` whose content goes to `docs/spec/04-observability.md` (or to its design notes and command reference). Owned by the part's task, which refines each `§N` target in its range to the `§N.M` it writes. Rules listed as `operator (obsolete?)` are copied to `docs/spec/RULINGS.md` and not changed.

| Old | Title | Targets | Note |
|---|---|---|---|
| §20 | Observability | §23.1, operator (obsolete?) | the layers → §23.1; the bot watchdog's quota wake-after-reset → operator |
| §20.0 | Layers (both locked) | §23.1 |  |
| §20.1 | Layer 1 — Ops board | §23.1 |  |
| §20.1.1 | Source of truth | §23.1 | the snapshot and status files → replaced by the board (§28.1) |
| §20.1.2 | Event log schema (`events.jsonl`) | §23.2 | example → `docs/design/observability.md` |
| §20.1.3 | Snapshot schema (`now.json`) | §23.3, §28.1, operator (obsolete?) | timer rules → §23.3; the snapshot → board; `now.json` and `STATUS.md` still written → operator; example → design |
| §20.1.5 | Status CLI + remote read | §23.4, operator (obsolete?), `docs/cli/04-observability.md` | the status rule (non-zero on an open blocker) → §23.4; the remote-blindness rule (emailed digest, copy to a personal path) looks obsolete → operator; the script list → cli |
| §20.1.6 | Durable reconciliation | §23.5 |  |
| §20.1.7 | Structured quota / auth fields | §23.6 |  |
| §20.1.8 | Who writes what | §23.2, §23.7, operator (obsolete?) | commands emit → §23.2; writers → §23.7; the bot watchdog's duties → operator |
| §20.2 | Layer 2 — Alpha prompt audit | §23.8, operator (obsolete?) | retention of full prompt text "for alpha" → operator |
| §20.2.1 | Requirement | §23.8 |  |
| §20.2.2 | Audit file schema | §23.8 | example → design |
| §20.2.3 | Out of scope for Layer 2 | §23.8 |  |
| §20.4 | Acceptance (plane-level) | `docs/design/observability.md` |  |
| §20.6 | Open knobs (defaults locked; the operator may override later) | §23.9, operator (obsolete?) | seat stale, retention → §23.9; verify stale (gone under the team) → operator; bot watchdog tick, verifier schedule, runner idle wake, second watchdog, STATUS.md → operator |
| §25.6 | Queue data: same files, new writers | §23.7 |  |
| §26.9 | Measurements (`cpl health`) | §27.1, §27.2 | the one-off backfill (removed) → dropped |
| §28.5 | Events | §23.2 |  |
| §28.6 | Usage, model and effort | §24.1, §24.2, §24.3, §24.4, §24.5 | the join-key spike → `docs/design/telemetry.md` |
| §28.7 | Allowance | §25.1, §25.2, §25.3, §25.4 |  |
| §28.8 | The board | §28.1, §28.2, §28.3, §28.4 | source ages → `docs/design/board.md` |
| §28.14 — §20.1.1 snapshot → board | Changes to earlier sections | §23.1, §28.1 |  |
| §28.14 — §20.1.5 status command | Changes to earlier sections | §23.4 |  |
| §28.14 — §20.1.8 commands emit | Changes to earlier sections | §23.2 |  |
| §28.14 — §25.6 writers are cpl | Changes to earlier sections | §23.7 |  |
| §28.14 — §26.9 cpl report records suite time | Changes to earlier sections | §27.1 |  |
| §28.18 | Step 2 spike: headless results (non-normative) | `docs/design/telemetry.md` |  |
| §28.19 | Step 2 implementation notes (non-normative) | `docs/design/telemetry.md` |  |
| §28.20 | Implementation notes: the checkpoint and the advisory design seat (non-normative) | `docs/design/allowance.md` |  |
| §28.21 | Step 3 implementation notes: the board (non-normative) | `docs/design/board.md`, §28.2, §28.3 | rebuild on every change → §28.2; contents and rules → §28.3, §28.4 |
| §28.22 | Telemetry system-wide, routed by session (non-normative) | `docs/design/telemetry.md`, §24.1, §24.3 | the notes → design; enabling and the project key → §24.1; the routing rules → §24.3 |
| §28.28 | Task estimation, phase A: records, actuals, the baseline | §26.1, §26.2, §26.3, §26.4, §26.5, §26.6 | implementation detail → `docs/design/allowance.md`; trial results → dropped |
| §29.12 — §28.9 fields to board.json | Changes to earlier sections | §22, §28.3 |  |
| §30.10 — §25.3 claim holder; §25.4/§25.5/§28.7 answer the holder | Changes to earlier sections | §10, §17, §25.3 |  |
| §30.10 — §28.7 session park | Changes to earlier sections | §25.4 |  |
| §30.10 — §28.28 throughput model | Changes to earlier sections | §26.4 |  |

<!-- spec-refs: historical -->
