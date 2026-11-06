---
task_id: 0026-readme-homepage
title: README as the open-source homepage
status: done
kind: feature
depends_on: []
spec_refs: ["S4", "S8", "S9"]
review_point: R1
paths: ["README.md", "LICENSE", "templates/", "scripts/leak-check.sh", "tests/test_self_hosting.py", "docs/adr/0027-open-source-under-mit-no-product-specifics.md"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0026-readme-homepage

## Intent

`README.md` is the public homepage, for humans and agents alike. It says what the plane is for, gives
a verified bootstrap (clone, install `cpl`, adopt a product, first task, start the team), explains
how it works (§4 the split, §8 what a product provides, §9 where files go), and gives a brief `cpl`
manual that points at `docs/cli.md`.

## Context (not checked)

- The operator's brief: polished, only clearly useful information, under about 250 lines.
- The old README described a layout and helpers that have since changed.

## Scope

- **In:** `README.md`.
- **In, after the newcomer review:** the templates' role names (steerer → lead) and their stale
  README; the `LICENSE` file, the leak check's exemption for it, ADR-0027 D1 built.
- **Out:** a `cpl init` helper (task 0027); placeholder checks (task 0028).

## dod_checks

- id: `boot-01`
  story: As a new user, the quick start works verbatim.
  setup: a scratch directory, a clone of the PR head, an empty git repo as the product.
  steps:
    1. Run the quick start's sections 1–3 in the product, with `PLANE` pointing at the clone.
    2. Run section 4's `team.sh runner spawn` command.
  expect: `cpl tasks check` and `cpl docs check` pass, `cpl tasks next` prints `0001-first-task`,
    `cpl where` resolves the queue, and `team.sh` prints the Agent call.
  dry run: n/a — the README is new.
- id: `docs-01`
  story: As a reader, every link and command exists.
  setup: a checkout of the PR head.
  steps:
    1. Resolve each relative link; run `cpl <command> -h` for each command in the table.
  expect: every link resolves; every command and flag is accepted.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, everything still passes.
  setup: a checkout of the PR head.
  steps:
    1. Run the leak check, the full suite and `cpl tasks check`, `cpl adr check`, `cpl docs check`.
  expect: all pass; `git branch --list 'state/*'` prints nothing.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- Rewrote `README.md` (134 lines): purpose, quick start in four steps, how it works (map, seats,
  the split, what a product provides, where files go), `cpl` in brief, documentation, license.
- The repository URL was a placeholder until the project was named; it is now `alexykot/ccp`.

- Newcomer cold-follow fixes: prerequisites; a terms line; an overridable `BIN`; the queue copy of
  the binding (`QUEUE_ROOT/project.yaml`, which `team.sh` and the queue code read, §8.3); a ready
  first task as a heredoc; a concrete gate lane (an argv list, not a shell string); the plugin comes
  from the marketplace while `cpl` runs from the clone; launchd extras are macOS-only.
- Operator, 2026-11-06: "MIT copyright names me, since agents are not considered legal entities
  yet." `LICENSE` holds the standard MIT text; `scripts/leak-check.sh` skips the root `LICENSE` only.

## Verification notes

*Append-only.*

- `boot-01` pass: run in a scratch clone; `CPL_DEV=1` silenced the off-`main` warning that cloning
  the branch causes. A first task needs `spec_refs` cited in its text or `tasks check` refuses it;
  the README says to set them.
- `docs-01` pass: links resolve; every listed command's `-h` accepts the shown form.
- `suite-01` pass: leak check clean; 1033 tests OK (1 skipped); tasks, adr and docs checks clean (docs warns that the README names a plane checkout path, which the bootstrap needs); no `state/*` branches.
