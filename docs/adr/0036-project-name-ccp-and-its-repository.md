---
id: ADR-0036
title: "Project name CCP and repository alexykot/ccp"
status: accepted
date: "2026-11-06"
deciders: operator
spec_refs: [S29]
decisions:
  - "D1 built"
  - "D2 built"
  - "D3 built"
  - "D4 built"
notes: "2026-11-06: status proposed → accepted"
---
# ADR-0036 — Project name CCP and repository alexykot/ccp

## Context

The project was known only by its repository name, `control-plane`, a generic phrase that reads as a
description rather than a name. The README and docs used a `<owner>/control-plane` placeholder for
the public repository. Publication needs a name and a home before the README can say how to install
it.

## Decision

### D1. The project is CCP — Claude Control Plane

The README, SPEC, docs, plugin descriptions and prompt templates name the project CCP (Claude Control
Plane). "The plane" stays the shorthand in prose.

### D2. The public repository is alexykot/ccp

The project is published at `github.com/alexykot/ccp`. The README's clone and marketplace
instructions point there.

### D3. The CLI is `ccp`

The command becomes `ccp` and its environment variables `CCP_*`; readers accept the old `CPL_*` names
for one transition. A `cpl` shim warns and forwards until products have migrated, and is removed
before publication. The naming PR keeps `cpl` in the docs so that it stays a docs change; task 0029
does the rename.

### D4. The plugin and marketplace ids become `ccp` at publication

The ids `control-plane` (plugin, marketplace and agent namespace) become `ccp` when the public
repository is created, not before, because every product's `.claude/settings.json` and bindings name
them. Each product's lead gets a prompt with the change.

## Consequences

- Until task 0029 lands, the docs say `cpl`.
- Until publication the README and SPEC show the current ids (`control-plane@control-plane`,
  `control-plane:delivery-runner`), so the instructions work today; they flip to `ccp` in the same
  step as the id rename.
- The rename of ids is one coordinated step on the publishing checklist, not a drift of mixed names.
