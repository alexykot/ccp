# Architecture decision records

The control plane's own decisions, in the plane's ADR format (SPEC §6.1). Each ADR records a
decision, its context and its consequences; each numbered decision (`### D1. Title`) carries a build
state (`not_built`, `built`, `live`, `retired`) in the frontmatter. `INDEX.md` is generated.

- New: `cpl adr new "<title>"` (status `proposed`).
- Accept: `cpl adr status N accepted` (records every decision as `not_built`).
- Progress: `cpl adr decide N D2 built|live|retired [--by "ADR-MMMM Dk"]`.
- Replace: `cpl adr supersede OLD NEW [--decisions D2,D4]`.
- Check: `cpl adr check` (also part of `cpl docs check`); `adr.strict` is on here.

ADRs are written generically: no managed product's names, ids, figures or rulings (docs/ENGINEERING.md E3).
