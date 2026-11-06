# Map: 01-model

Rows of the pre-restructure `SPEC.md` whose content goes to `docs/spec/01-model.md` (or to its design notes and command reference). Owned by the part's task, which refines each `§N` target in its range to the `§N.M` it writes. Rules listed as `operator (obsolete?)` are copied to `docs/spec/RULINGS.md` and not changed.

| Old | Title | Targets | Note |
|---|---|---|---|
| §1 | Purpose | §1.1, §1.2 |  |
| §2 — Vendor orchestrators | Locked decisions (changelog from early drafts) | §1.2 |  |
| §2 — Operator PR approval | Locked decisions (changelog from early drafts) | §3.1 |  |
| §2 — Integration and production branches | Locked decisions (changelog from early drafts) | §3.4, dropped (product-binding) | production promotion is operator-gated → §3; the product's branch names are its binding |
| §2 — Seats | Locked decisions (changelog from early drafts) | §2.1, §2.2 |  |
| §2 — Durable work record | Locked decisions (changelog from early drafts) | §4.2 |  |
| §2 — Runtime | Locked decisions (changelog from early drafts) | §4.2 |  |
| §2 — Hosting | Locked decisions (changelog from early drafts) | §2.2 |  |
| §2 — Product north star | Locked decisions (changelog from early drafts) | §4.1 |  |
| §3 | Goals and non-goals | §1.3 |  |
| §4 | Product documentation (three layers) | §4.1 |  |
| §5 | Durable task log vs runtime | §4.2 |  |
| §5 — Write rules |  | §4.2 |  |
| §5.1 | The task file (canonical format) | §5.1, §5.2, §5.3, §5.4, §5.5, §5.6 |  |
| §5.2 | ADRs (canonical format) | §6.1, §6.2, §6.3, §6.4, §6.5, §6.6, §6.7, §6.8 |  |
| §6 | Roles (seats) | §2.1, §2.2, §2.3 |  |
| §7 — Production | Surfaces (a product binding) | §3.4 |  |
| §14 | Operator gates | §3.2, §3.3, operator (obsolete?) | the operator gates list lives here; §17 references it |
| §15 | Packaging | §31, §4.5, §8.1, dropped (history) | the SPEC-change rule → §31; "adopt a new product" → §4 and §8; the layout tree is the README's; the push incident is history |
| §22 | Claude orientation | §9.3 |  |
| §22.1 | Problem | §9.3, `docs/design/orientation.md` |  |
| §22.2 | Design | §9.3, §9.5 |  |
| §22.3 | Content of CONTROL-PLANE.md (template: `templates/docs-delivery/CONTROL-PLANE.md`) | §9.3 |  |
| §22.4 | Managed copies and sync | §9.5, `docs/design/orientation.md` | managed copies are retired by the plugin (old §29.3); keep only what still applies |
| §22.6 | Acceptance checks | `docs/design/orientation.md` |  |
| §22.7 | Implementation notes (2026-09-25, non-normative) | `docs/design/orientation.md` |  |
| §24 | Product tooling (`cpl`) | §8.2 |  |
| §24.0 | Problem and intent | §8.2 |  |
| §24.1 | Design choices (and why) | §8.1, §8.2 |  |
| §24.3 | `docs/delivery/plane.json` | §8.1 |  |
| §25 | Claude-team hosting | §2.2 |  |
| §25.0 | Problem and intent | §2.2 |  |
| §25.1 | Hosting | §2.2 |  |
| §25.2 | Seats | §2.1, §2.2, §2.4, §2.5 |  |
| §25.10 | Binding | §8.3 |  |
| §25.13 | Open knobs | §2.6 |  |
| §26.12 | Binding (`plane.json`) | §8.1 |  |
| §28.11 | Binding (`plane.json`) | §8.1 |  |
| §28.11.1 | Ids and references (`ids`) | §7.1, §7.2 |  |
| §28.12 | Seats | §2.1 |  |
| §28.16 | Open knobs | §8.4 |  |
| §29 | Product footprint: a static anchor, and products run `main` | §4.3 |  |
| §29.0 | Problem and intent | §4.3, `docs/design/plugin.md` |  |
| §29.1 | Design choices (and why) | §4.3, §5.7, §9.1 |  |
| §29.2 | What a product holds | §4.3 |  |
| §29.3 | The plugin | §9.1, §9.2, §9.3, §9.4 |  |
| §29.6 | Cloud-team state off the product | §4.2, operator (obsolete?) | the queue is the only runtime state; no state branches → §4; "cpl never reads or deletes a left-over delivery-state branch" looks obsolete → operator |
| §29.7 | `INDEX.yaml` | §5.7 |  |
| §29.8 | Product docs | §4.4 |  |
| §29.10 | Spike (2026-10-21) | `docs/design/plugin.md` |  |
| §29.11 | Acceptance checks (walkable) | `docs/design/plugin.md` |  |
| §29.12 — §22.2 orientation from the plugin | Changes to earlier sections | §9.3, §9.5 |  |
| §29.12 — §22.4/§25.12/§26.2 managed copies retired | Changes to earlier sections | §9.5 |  |
| §29.12 — §25.10 runner agent type | Changes to earlier sections | §8.3 |  |
| §29.12 — §5 INDEX frozen format | Changes to earlier sections | §5.7 |  |
| §29.14 | Implementation notes (2026-10-21, non-normative) | `docs/design/plugin.md` |  |
| §30.10 — §25.2 runner row | Changes to earlier sections | §2.6, §16 |  |

<!-- spec-refs: historical -->
