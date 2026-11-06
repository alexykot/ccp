---
task_id: 0009-privacy-scrub
title: Scrub the repo of managed-product and personal specifics
status: done
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S31"]
adr_refs: ["0027 D4"]
review_point: R1
paths: ["cpl/", "scripts/", "plugin/", "templates/", "contracts/", "tests/", "README.md", ".claude/settings.json", "docs/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0009-privacy-scrub

## Intent

Nothing tracked in the repository names a managed product, its people, ids, paths or data, or carries the operator's personal identifiers where a neutral value works; the leak check passes against the operator's full denylist.

## Context (not checked)

- Known leftovers include product names in code comments and docstrings, a test fixture named after a product, product proposal ids in comments, and a launchd label prefix built from a personal identifier.
- The denylist stays untracked: the operator keeps it locally and points `CPL_LEAK_DENYLIST` at it; document how in `docs/ENGINEERING.md`.
- The repository's own URL in docs and the plugin marketplace anchor is a publication decision, not part of this scrub, unless the operator rules otherwise.
- The `spec_refs` above use the pre-restructure section numbers; the switch task rewrites them.

## Scope

- **In:** comments, docstrings, messages, test names and fixtures, contracts' descriptions and examples, templates, briefs and skills, README; the launchd label prefix becomes configurable with a neutral default; how to keep and run the denylist.
- **Out:** the SPEC text (done by the part and switch tasks); git history (handled at publication).

## dod_checks

- id: `leak-01`
  story: As the operator, the leak check is clean against my full denylist.
  setup: the operator's local denylist; a checkout of the PR head.
  steps:
    1. Run `CPL_LEAK_DENYLIST=<the denylist> scripts/leak-check.sh`.
  expect: no match.
  dry run: n/a — the denylist is local.
- id: `leak-02`
  story: As a plane developer, a launchd agent's label carries no personal identifier by default.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'com\.[a-z]*\.control-plane' -- cpl scripts`.
  expect: only the configurable default prefix.
  dry run (`1924bf0`): the personal prefix appears in the otel and board labels.
- id: `leak-03`
  story: As a plane developer, everything still passes.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite and `cpl docs check`.
  expect: all pass.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-06 — Scrubbed: product proposal ids and product names from code comments, docstrings and
  one user-facing message; product paths, the owner's handle and name from READMEs, script usage
  text, skills' source lines, plugin and marketplace manifests (owner now "control-plane
  maintainers"); contract `$id`s now `urn:control-plane:contracts:<file>`; a product review-point
  name and product source paths in fixtures and docs examples; a password-vault file name; stale
  mesh-network lines. Test fixtures: the allowance sample renamed to `tests/data/allowance-sample.jsonl`
  (numbers and times only), product ids, paths, a session id and a personal cwd replaced with neutral
  values. The launchd label prefix is `CPL_LAUNCHD_PREFIX` (default `dev.cpl`; SPEC §29.5).
  `.claude/settings.json` no longer anchors the plugin to a GitHub repo: an operator who wants the
  plugin in plane sessions enables it in a local settings file. `scripts/leak-check.sh` matches
  Perl-compatible patterns (`\b`, a leading `(?i)`), with a test on a scratch repository. The task
  cited ADR-0027 D1/D2 (licence, fresh history), which this task doesn't build; it cites D4 now.

## Verification notes

*Append-only.*

- 2026-11-06 — `leak-01` pass: the operator's local denylist (27 patterns) finds no match.
  `leak-02` pass: no `com.<name>.control-plane` label left in `cpl` or `scripts`; the default prefix
  is `dev.cpl`. `leak-03` pass: the full suite and `cpl tasks|adr|docs check` (see the PR).
