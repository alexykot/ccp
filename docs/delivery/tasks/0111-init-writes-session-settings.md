---
task_id: 0111-init-writes-session-settings
title: ccp init writes the prompt-cache and compaction settings, and the SPEC says which setting reaches which seat
status: pending
kind: feature
depends_on: []
spec_refs: ["S2", "S4", "S13"]
adr_refs: ["0041 D5", "0041 D6"]
review_point: R7
sign_off: brief
paths: ["ccp/init.py", "ccp/config.py", "contracts/project.schema.json", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "tests/test_init*.py"]
adopt: "set subagentPromptCacheTtl to 1h and autoCompactWindow in .claude/settings.json by hand; ccp init does it for new products"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0111-init-writes-session-settings
## Intent

A new product starts with the session settings existing products had to discover: a one-hour
prompt cache for the runner teammate and an early compaction window for the lead. The SPEC stops
saying an agent definition's cache lifetime reaches the runner.

## Context (not checked)

- ADR-0041 D5 and D6, from two accepted product proposals.
- A product's telemetry showed every runner-teammate cache write at the 5-minute lifetime despite `cacheTtl: 1h` in the runner's definition; teammates follow `subagentPromptCacheTtl`, which ranks above the definition's value (Claude Code settings documentation).
- The lead's durable state is in git, so compacting earlier loses little.
- The plane itself already set both settings by hand on 2026-11-16.

## Scope

- **In:**
  - `docs/spec/01-model.md` §2.4. CURRENT (at `7094dfe`): "Every delivery definition, the runner's included, sets `experimental: {cacheTtl: 1h}`: a one-hour prompt-cache lifetime, so a long suite run or a wait on a worker does not expire the cache." PROPOSED:
    > Every delivery definition sets `experimental: {cacheTtl: 1h}`: a one-hour prompt-cache lifetime for worker subagents, so a long suite run does not expire the cache. The runner is an agent-team teammate, whose cache lifetime comes from the `subagentPromptCacheTtl` setting, not its definition; `ccp init` sets it to `1h` (§4.5).
  - `docs/spec/01-model.md` §4.5, the list of what `ccp init` writes. CURRENT (at `7094dfe`): "the anchor merged into `.claude/settings.json`, leaving its other keys and values alone, and the one `CLAUDE.md` line, once (§4.3);" PROPOSED:
    > the anchor merged into `.claude/settings.json`, leaving its other keys and values alone, with `subagentPromptCacheTtl: "1h"` and `autoCompactWindow` (the binding's `lead.auto_compact_window`, default `350000`) added when absent and never overwritten, and the one `CLAUDE.md` line, once (§4.3);
  - `docs/spec/02-delivery.md` §13.5. CURRENT (at `7094dfe`): "**Cache lifetime.** `experimental.cacheTtl: 1h` in every delivery definition; `ccp usage` shows the 1-hour cache writes (`W-1H`) per run and seat." PROPOSED:
    > **Cache lifetime.** `experimental.cacheTtl: 1h` in every delivery definition covers worker subagents; the runner teammate's comes from `subagentPromptCacheTtl` in settings (§2.4). `ccp usage` shows the 1-hour cache writes (`W-1H`) per run and seat.
  - `ccp/init.py`: write both settings when absent, report each as added or kept; `ccp/config.py` and `contracts/project.schema.json`: the binding's `lead.auto_compact_window`.
- **Out:**
  - Changing a product's settings that already exist.

## dod_checks

- id: `cmd-01`
  story: As a new adopter, init writes both settings.
  setup: a scratch repository with a `.claude/settings.json` holding only `{"permissions": {}}`.
  steps:
    1. Run `ccp init` for it.
  expect: the file now also holds `"subagentPromptCacheTtl": "1h"` and `"autoCompactWindow": 350000`; `permissions` is unchanged; the output lists both as added.
  dry run: n/a.
- id: `cmd-02`
  story: As a product that chose its own values, init keeps them.
  setup: a scratch repository whose settings hold `"subagentPromptCacheTtl": "5m"` and `"autoCompactWindow": 200000`, and a binding with `lead.auto_compact_window: 500000`.
  steps:
    1. Run `ccp init` again.
  expect: both values are unchanged and listed as kept.
  dry run: n/a.
- id: `cmd-03`
  story: As a lead, the binding sets the window for a new product.
  setup: a scratch repository with no settings file and a binding with `lead.auto_compact_window: 500000`.
  steps:
    1. Run `ccp init`.
  expect: the new settings file holds `"autoCompactWindow": 500000`.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §2.4, §4.5 and §13.5 edits with the PROPOSED text above.
  expect: they match word for word, and no other § rule changes.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 (implementer): `ccp init` adds `subagentPromptCacheTtl: "1h"` and `autoCompactWindow` to
  `.claude/settings.json` when absent (`ccp/init.py` `_merged_settings`), never overwriting either,
  `--force` included, and its result gains `settings`: each setting named `added` or `kept`. The
  window is the binding's as it stands after init: a kept binding's `lead.auto_compact_window`, else
  `config.LEAD_DEFAULTS` (350000); a value that is no positive whole number reads as the default, as
  the runner's rotation knobs do. `contracts/project.schema.json` gains the `lead` block. §2.4 keeps
  its sentence on the environment overrides after the PROPOSED text, which replaced only the
  sentence the CURRENT quoted. README's adoption section names the two settings.
- 2026-11-17 (implementer, fix 1): ADR-0041 D5 and D6 recorded `built` (`ccp adr decide`), as this
  task builds both; review MAJOR 1.

## Verification notes
