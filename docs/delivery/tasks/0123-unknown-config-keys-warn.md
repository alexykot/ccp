---
task_id: 0123-unknown-config-keys-warn
title: An older ccp warns on a plane.json key it does not know, and docs check refuses it
status: done
kind: feature
depends_on: []
spec_refs: ["S8", "S16", "S19"]
review_point: R8
sign_off: brief
paths: ["ccp/config.py", "ccp/docs.py", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "tests/test_config*.py", "tests/test_docs*.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0123-unknown-config-keys-warn
## Intent

A plane change that adds a plane.json key no longer stops every older `ccp` from loading the
product's plane.json between the merge and the release; a typo still fails the product's gate.

## Context (not checked)

- When a plane task added a top-level plane.json block to the plane's own file, the `ccp` on PATH
  refused the file ("unknown top-level key(s)") from the merge until the run checkout was released,
  and the runner's queue steps failed in that gap (one review point of the plane, 2026-11-17). A
  product that takes a new key before its `ccp` is updated breaks the same way.
- Every gate runs `ccp docs check`, so refusing there keeps the typo guard.

## Scope

- **In:**
  - `ccp/config.py`: unknown keys, at any level, warn on stderr when the configuration loads, naming
    each key and the file and saying the running `ccp` may predate it; loading goes on without them.
  - `ccp docs check`: refuses unknown plane.json keys (exit 1), naming each.
  - `docs/spec/01-model.md` §8. CURRENT (at `b4de6ad`): "- Unknown keys are refused, so a typo cannot silently turn a rule off. The schema only gains optional keys." PROPOSED:
    > - Unknown keys warn when the configuration loads (stderr, naming each and saying the running `ccp` may predate it) and are otherwise ignored, so a `ccp` older than a key keeps working until it is updated; `ccp docs check`, which every gate runs, refuses them, so a typo cannot silently turn a rule off. The schema only gains optional keys.
  - `docs/spec/02-delivery.md` §16.3. CURRENT (at `b4de6ad`): "Config loading validates these blocks; unknown keys are refused." PROPOSED:
    > Config loading validates these blocks; unknown keys are handled as §8 says.
  - `docs/spec/03-quality.md` §19, the architect block. CURRENT (at `b4de6ad`): "(§8; unknown keys are refused)" PROPOSED:
    > (§8)
- **Out:**
  - Unknown keys in the binding or the task file's frontmatter.

## dod_checks

- id: `cmd-01`
  story: As a runner on an older ccp, the queue keeps working.
  setup: a scratch product whose plane.json adds a top-level `future_block: {}` and a `verify.future_knob: true`.
  steps:
    1. Run `ccp tasks next`.
  expect: exits as it would without the two keys; stderr names `future_block` and `verify.future_knob`.
  dry run: n/a.
- id: `cmd-02`
  story: As a product, a typo still fails my gate.
  setup: the product of cmd-01.
  steps:
    1. Run `ccp docs check`.
  expect: exit 1, naming both keys.
  dry run: n/a.
- id: `cmd-03`
  story: As a product, known keys still validate.
  setup: a scratch product whose plane.json sets `verify.skip_review_after_clean` to `"yes"`.
  steps:
    1. Run `ccp tasks next`.
  expect: exit 2, naming the key and its expected type.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §8, §16.3 and §19 edits with the PROPOSED text above.
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

- 2026-11-17: `ccp/config.py` holds the keys plane.json may carry at every level it reads by key
  (`PLANE_KEYS`, built from the blocks' defaults and the key constants the validators use). `_parse`
  drops the keys outside it before any validator runs, and records them on `Config.unknown_keys` as
  dotted paths (`verify.future_knob`, `architect.checks[0].shell`, `suite.lanes.gate[0].x`); `load`
  warns on stderr once per file and key in a process. `skip_rules_at` parses the same way, without
  the warning, so a committed plane.json with a newer key still gives its skip rules. Free-named maps
  (`architect.areas`, `prompts.worker_env`, `upgrade.declined`, a lane's name) are not key-checked,
  as before. The per-block refusals of unknown keys stay in the validators, now unreachable through
  `load`.
- `ccp docs check` is in `ccp/cli.py` (`cmd_docs_check`; there is no `ccp/docs.py`): it adds one
  failure per unknown key (`config.unknown_key_errors`).
- The §16.3 edit's CURRENT text sits in §16.2 ("The knob"); it was edited where it stands. README,
  the plane.json contract's description and `docs/design/architect.md` said "refused" and now
  describe the new behaviour. Tests that expected a refusal for an unknown key were moved to the new
  behaviour (`test_estimate`, `test_parallel_claims`, `test_pkgdocs_config`, `test_rules`, `test_wt`).

## Verification notes
- 2026-11-17 — verifier, PR #139 head `26acfdb` (squash `ef82a33`): APPROVE. Passed: cmd-01, cmd-02, cmd-03, check-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0123-unknown-config-keys-warn.json.

