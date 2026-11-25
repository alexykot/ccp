# Architecture decision records

The control plane's own decisions, in the plane's ADR format (SPEC §6.1). Each ADR records a
decision, its context and its consequences; each numbered decision (`### D1. Title`) carries a build
state (`not_built`, `built`, `live`, `retired`) in the frontmatter. `INDEX.md` is generated.

The commands are `ccp adr …` (`docs/cli/01-model.md`), the rules SPEC §6; `adr.strict` is on here.

ADRs are written generically: no managed product's names, ids, figures or rulings (docs/ENGINEERING.md E3).
