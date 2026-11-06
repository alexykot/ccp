# Orientation: why and how it reaches sessions

Non-normative. The rules are SPEC §9.3 and §9.5.

## Why there is an orientation

Claude sessions in a product repository (workers, the lead, the operator's interactive sessions)
otherwise learn about the plane only from each prompt. Nothing gives them a standing picture of the
system, the seats or their authority. The orientation is that picture, kept short and role-neutral;
role-specific authority stays in each role's own instructions.

## The earlier mechanism: managed copies

Before the plugin, the orientation (`CONTROL-PLANE.md`) and the spec maintainer's protocol
(`SPEC-MAINTAINER.md`) were managed copies installed into each product:

- `scripts/sync-product-docs.sh <project_id>` copied the templates (`templates/docs-delivery/CONTROL-PLANE.md`
  and the protocol) into `product_root/docs/delivery/`, as `docs/delivery/CONTROL-PLANE.md` and
  `docs/delivery/SPEC-MAINTAINER.md`, stamped a header, and added a `## Control plane` section to the
  product's `CLAUDE.md` holding the import line `@docs/delivery/CONTROL-PLANE.md`.
- The header named the last plane commit that changed the template (`git log -1 -- <template>`,
  shown as `<sha>`), not the plane's head, so unrelated plane commits never made every product drift.
  A sync from an uncommitted template was refused unless `--allow-dirty`, and the stamp then ended
  `+dirty`. A leading `<!-- … -->` template note was dropped on sync.
- `scripts/sync-product-docs.sh <project> [--check]` reported drift (a copy differing byte for byte
  from header plus template, a missing file, a missing import line) and exited non-zero; it never
  wrote to the product.
- `--product-root DIR` pointed the sync at a product worktree, so a live runner checkout was never
  touched. A daily check ran as `--check --daily-stamp "$QUEUE_ROOT/product-docs-check.json"`,
  recording `{checked_at, date_local, drift, items, priority: low}` in the queue.
- Product-specific additions went to a product-owned file, never into the copy. The onboarding steps
  lived in `templates/docs-delivery/README.md`.
- The protocol doc (`spec_maintainer.protocol_doc`, the product's copy) was read by the old headless
  ask script (`spec-maintainer-ask.sh`), which refused to run without it; `REVIEW-TRIAGE.md` was the
  review-triage protocol, copied the same way.

The plugin replaced all of it: the orientation is injected by its SessionStart hook and the
protocols are its skills, so a release reaches every product with no product commit. The sync now
only reports and removes leftover copies.

## How the orientation was accepted

A product held the orientation and the import, a fresh headless session asked "what is your delivery
role and who do you take spec questions to?" answered consistently with it, and a one-line template
edit made the drift check fail. With the plugin, the same question is answered from the SessionStart
context.
