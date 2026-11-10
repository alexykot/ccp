---
task_id: 0033-package-doc-convention-owned-by-the-plane
title: The plane owns the package-doc convention
status: done
kind: feature
depends_on: []
spec_refs: ["S9", "S21"]
review_point: R3
paths: ["ccp/", "docs/spec/", "plugin/", "tests/"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0033-package-doc-convention-owned-by-the-plane

## Intent

The package-doc system becomes a plane feature with one definition: the tiers (the root `CLAUDE.md` always loaded; package docs auto-loaded under a source directory; dot-prefixed `.claude.md` docs read on demand); a package doc is a map of what exists, never a record of what a task did; no task, finding or ruling ids in package docs or code comments; every source directory covered and modules carry docstrings. `ccp docs check` checks all of it.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §9 and §21.
- Agent efficiency on any non-trivial codebase depends on discoverable, map-style package docs.
- The plane already checks coverage; products restate the rest in prose, each slightly differently.

## Scope

- **In:** §21 (and §9 for loading) states the tiers and the map rule; `ccp docs check` adds a check that flags task, finding and ruling ids (per the product's id patterns) in package docs and code comments, with a knob to turn it off; the orientation and `writing-tasks` skill point to §21 instead of restating it.
- **Out:** rewriting any product's docs; language packs beyond what exists.

## dod_checks

- id: `check-01`
  story: As a lead, a package doc citing a task id is flagged.
  setup: a scratch product whose package doc says 'added in 0012'.
  steps:
    1. Run `ccp docs check`.
  expect: it reports the file, the line and the id.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, a code comment citing a ruling id is flagged.
  setup: a source file with a comment naming a ruling id.
  steps:
    1. Run `ccp docs check`.
  expect: it reports it; with the knob off, it does not.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-03`
  story: As a plane developer, the plane's own tree passes.
  setup: the PR head.
  steps:
    1. Run `ccp docs check`.
  expect: clean.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 — `ccp docs check` gains the delivery-id rule (`ccp/pkgdocs.py` `ids_check`), on by
  default wherever `package_docs` is set: every line of a package doc and every code comment of a
  file under `docstring_globs` is searched for task ids (at `ids.task.width`), architect pass and
  finding ids (`ar-`/`sh-<stamp>-<hex4>[#F<n>]`) and spec-question ruling ids (`sm-<stamp>-<hex4>`),
  plus the product's `package_docs.delivery_id_patterns`; `package_docs.no_delivery_ids: false` turns
  it off. Hits are reported as `file:line: … names delivery id(s) <ids>`. History paths are skipped.
- The id patterns live in `ccp/refs.py` (`Ids.task_mention_patterns`, `Ids.delivery_id_patterns`);
  `rules.no_ids` now takes its defaults from there. A zero-padded task number may now be followed by
  a sentence's full stop (`added in 0042.` is a hit; `0042.5` is not), in both checks.
- Comments are read by the language pack (`Pack.comments`; Python: `#` comments via `tokenize`, so
  strings and docstrings are not comments). `language: none` checks package docs only. Tests' files
  are outside `docstring_globs` here, so fixture task numbers in test comments are not flagged.
- SPEC: §21.3 states the tiers, the map rule and the check; §21.4 says what Python's comments are;
  §9.6 (new) states how the tiers load; §8.1 lists the two knobs. The task carried no
  CURRENT → PROPOSED text: this text was drafted from the Intent and needs the operator's approval
  (§31.1). The orientation and the `writing-tasks` skill point at §21.3.
- The plane's own tree: one comment in `ccp/forecast.py` read as `task 16` and was reworded;
  `contracts/plane_config.schema.json` documents the two knobs.

## Verification notes

- 2026-11-10 — verifier, PR #26 head `c1815bf` (squash `526e74a`): APPROVE. Passed: check-01, check-02, check-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0033-package-doc-convention-owned-by-the-plane.json.
