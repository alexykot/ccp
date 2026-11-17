---
id: ADR-0041
title: "A release tells each product what to adopt"
status: proposed
date: "2026-11-17"
deciders: operator
spec_refs: [S2, S3, S5, S13, S29]
notes: |-
  Proposed with review point R7, from three accepted plane proposals: one asking for an upgrade
  path to the products that use the plane, and two asking that `ccp init` set the prompt-cache
  lifetime and the compaction window every product should have. The operator decides it; tasks
  0109–0111 build it.
decisions:
  - "D1 not_built"
  - "D2 not_built"
  - "D3 not_built"
  - "D4 not_built"
  - "D5 not_built"
  - "D6 not_built"
---
# ADR-0041 — A release tells each product what to adopt

## Context

Most new plane behaviour ships behind a knob that is off by default: a `plane.json` key, a binding
key, or a setting in the product's `.claude/settings.json`. Plugin changes reach a lead only at its
next session start. A proposal that is built is closed with a triage reason that names the merge,
and nothing tells the product that asked for it how to switch it on.

Twice this was found only by a manual analysis of telemetry:

- a product ran for weeks without fixes it had itself asked for (the skip of a re-review after a
  clean review, the test-cache acceptance), because each was off until set;
- the plane had not set, for itself, the settings its own products' proposals recommended: the
  teammate prompt-cache lifetime, the lead's compaction window, rotation by context size, and the
  skip of a re-review after a clean review.

Two of those settings belong to Claude Code, not the plane. A runner is an agent-team teammate, and
a teammate's prompt cache follows the `subagentPromptCacheTtl` setting, not the `cacheTtl` an agent
definition sets in its frontmatter. Only worker subagents honour the frontmatter value. SPEC §2.4
and §13.5's "Cache lifetime" bullet say the definition's value covers the runner too, which is false.
The lead is a long interactive session whose durable state is in git. Left at Claude Code's default
compaction window, it grows to near the model's whole context, and most of its cost is re-reading
that context.

`release.sh` already checks each bound product's integration branch after a release (§29.3) and
prints which went stale. It does not say what arrived.

## Decision

### D1. Each task names its adoption step

A task's frontmatter may carry `adopt:`, one line: what a product must do to use what the task
delivers. The value is `none` (it applies by itself), or a concrete step naming the file and key:
`plane.json verify.accept_cache`, `.claude/settings.json subagentPromptCacheTtl "1h"`, `run ccp
docs regen`. A missing key reads as `none`. The writing-tasks skill asks for it on every task that
adds a knob, a setting or a file a product must create. `ccp tasks check` warns on a task not yet
`done` or `dropped` whose `paths` name the plane.json schema or a settings template and that carries
no `adopt:`.

### D2. `ccp upgrade notes` and `ccp upgrade status`

- `ccp upgrade notes [--since <commit>]` lists the plane's merged tasks since that commit (default:
  the run checkout's previous release), each with its title, its `adopt:` step and the proposals it
  answers. It reads the plane's own task log, so the notes need no file kept by hand.
- `ccp upgrade status` (run in a product) compares the product's `plane.json`, binding and
  `.claude/settings.json` with the adoption steps of every merged plane task, and lists each step
  the product has not taken: the task, the proposal the product filed for it when there is one, and
  the exact change to adopt it. A step the product declined is recorded in plane.json
  `upgrade.declined` (task ids, with a reason) and no longer listed.

### D3. A release leaves each bound product an upgrade notice

After its staleness check, `release.sh` renders an `upgrade` notice for each bound product: the
release's `ccp upgrade notes`, filtered to steps that product has not taken (`ccp upgrade status`).
It records the notice as pending in that product's queue, with nothing written to the product's
repository. §3.6 gains an `upgrade` trigger, so the notice goes through the notify path of
ADR-0039: the product's lead sends or reads it at its next session start, where orientation lists
pending notices. A release that leaves a product nothing to adopt records no notice for it.

### D4. A proposal closed as built names its step

`ccp plane built <proposal> --task <id>` closes an accepted proposal as built by a merged task,
copying the task's `adopt:` step into the proposal's record. `ccp plane list` shows the step, so the
proposer's lead learns what to do, not only that it shipped.

### D5. `ccp init` writes the settings every product needs

`ccp init` and adoption write two settings into the product's `.claude/settings.json` when absent,
never overwriting a value the product set:

- `subagentPromptCacheTtl: "1h"`, so the runner teammate's cache outlasts a wait on a worker;
- `autoCompactWindow`, from the binding's `lead.auto_compact_window` (default `350000`), so the lead
  compacts long before the model's whole context.

Both are knobs: the binding key changes the window, and a product may set either setting itself.

### D6. The SPEC says which setting reaches which seat

§2.4's agent-definition bullet and §13.5's "Cache lifetime" bullet are corrected: the definition's
`cacheTtl` covers worker subagents; the runner teammate's cache lifetime comes from
`subagentPromptCacheTtl` in settings (D5), which ranks above the definition's value.

## Consequences

- A product learns at its lead's next session start what a release asks of it, and can see at any
  time what it has not adopted.
- Writing a task gains one line for tasks that add a knob.
- The notice lives in the queue, which is plane runtime; `release.sh` still writes nothing to a
  product's repository.
- New adopters start with the settings existing products had to discover.
