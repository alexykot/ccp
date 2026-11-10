---
task_id: 0034-starter-house-rules
title: The plane ships an optional starter set of house rules
status: pending
kind: feature
depends_on: [0033-package-doc-convention-owned-by-the-plane]
spec_refs: ["S20"]
review_point: R3
paths: ["docs/", "templates/", "ccp/", "tests/"]
created: 2026-11-09
updated: 2026-11-09
---

# Task: 0034-starter-house-rules

## Intent

The plane ships a starter set of generic house rules a product may adopt or decline, each with the check that enforces it: one owner for every count or list (docs name the owner); tests check behaviour, never quoted text; current-only docs, with history marked by a git attribute and excluded from absence checks; package docs are maps (task 0033); one home per fact; every reference resolves; deterministic tests (clock, HEAD, load).

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §20.
- These rules are about how agent-maintained code and docs stay correct, not about any product's domain; every product rediscovers them through architect findings.

## Scope

- **In:** a template house-rules file listing each rule, its purpose and its check; `ccp init` (or the template) offers it; where a check is mechanical, it exists in `ccp docs check` or as a documented docs.checks entry; §20 says how a product adopts, declines or overrides a starter rule.
- **Out:** making any rule mandatory.

## dod_checks

- id: `check-01`
  story: As a new product, I can adopt the starter rules.
  setup: a scratch product created from the template.
  steps:
    1. Open the house-rules template.
  expect: each rule names its check, and each named check exists and runs.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, declining a rule is recorded.
  setup: a product that declines one starter rule.
  steps:
    1. Run `ccp docs check`.
  expect: the declined rule's check does not run; the others do.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 — The starter set is `templates/docs-project/starter-rules.md`, a rules doc in the §20.1
  format and the set's one home: seven rules (E1–E7), each with its purpose, a `starter: <name>` line
  and its check. `ccp/rules.py` reads the set from it (`starter_rules()`); a template that does not
  parse is an error, not an empty set.
- The house-rules format gains a fourth check kind, `docs — <plane.json key>[, …]`: a rule `ccp docs
  check` runs (`package_docs` or `package_docs.rules.<name>`). With an architect block, `check_doc`
  fails when a named key is unknown or not set. The three mechanical starter rules use it
  (`current-docs`: `no_ids` + `history_attr`; `package-maps`: `package_docs`; `refs-resolve`:
  `citations`); the other four are `pass`.
- Adoption and declines live in `plane.json` `docs.starter_rules` (default `null`; `{}` adopts all;
  `{"declined": {"<name>": "<reason>"}}`); unknown names and empty reasons are refused at load.
  Adopted: `ccp docs check` fails while an adopted rule's `docs` check is not set. Declined: the keys
  its check names are not run (`pkgdocs.check` skips the package-doc rules, `docrules._rules` drops
  the opt-in rule, so a declined `history_attr` no longer marks history), unless an adopted rule names
  the same key; `ccp docs check` prints one line per decline with its reason.
- `ccp init --starter-rules` writes the set to `docs/ENGINEERING.md` and, into a plane.json it
  writes, `docs.starter_rules` and neutral `package_docs` settings (`language: none`,
  `history_attr: history`, `no_ids` and `citations` over `docs/*.md` against `docs/SPEC.md`), so a
  fresh product is clean. Against a kept plane.json the settings are listed as not applied, like
  `--gate`. It does not set `architect.rules_doc` (that would turn the architect seat on).
- SPEC: §20.1 (the `docs` kind), §20.5 (new: adopt, decline, override), §21.2, the §19.3 pieces table,
  §8.1 and §4.5, drafted from the Intent. Also the schema (`contracts/`), the architect skill's list
  of check kinds (`plugin/`), the rules template's comment and the CLI reference; `contracts/` and
  `plugin/` sit outside the task's `paths`.

## Verification notes

*Append-only.*
