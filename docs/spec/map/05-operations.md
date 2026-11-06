# Map: 05-operations

Rows of the pre-restructure `SPEC.md` whose content goes to `docs/spec/05-operations.md` (or to its design notes and command reference). Owned by the part's task, which refines each `§N` target in its range to the `§N.M` it writes. Rules listed as `operator (obsolete?)` are copied to `docs/spec/RULINGS.md` and not changed.

| Old | Title | Targets | Note |
|---|---|---|---|
| §2 — Auth | Locked decisions (changelog from early drafts) | §30.1 |  |
| §11 | Auth, spend wallets, and Tailscale | §30.1, dropped (old-hosting) | the mesh-network paragraph is old hosting; proof URLs are §12's `env.urls` |
| §11 — Prepaid vs API credits (locked 2026-09-17) |  | §30.1, §30.2, §30.3 | auth-check reporting → §30.1; wallets → §30.2; ambient-key ban, launch hygiene, misuse → §30.3 |
| §15 | Packaging | §31.1, §4, §8, dropped (history) | the SPEC-change rule → §31; "adopt a new product" → §4 and §8; the layout tree is the README's; the push incident is history |
| §28.10 | No local automation; propose a tool | §31.3, §31.4, §31.5 |  |
| §29.4 | Products run `main` | §29.1, §29.2, §29.3 |  |
| §29.5 | `cpl` on PATH | §29.4 |  |
| §29.13 | Open knobs | §29.5 |  |
| §21.1 | Project binding | §29.2 | only its parenthesis: bindings are local and gitignored in the run checkout; that a release keeps them is `scripts/run-checkout.sh update`'s behaviour; the rest of §21.1 is §17's |

<!-- spec-refs: historical -->
