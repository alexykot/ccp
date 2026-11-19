---
task_id: 0191-the-grace-release-ends
title: ADR-0043's grace release ends: the language and the gate lane are enforced, and old key places are no longer read
status: pending
kind: feature
depends_on: ["0181-models-block-and-role-defaults", "0182-language-is-a-required-key", "0183-gate-lane-is-required", "0186-account-facts-on-the-machine", "0187-short-plane-json", "0188-short-binding", "0190-the-plane-takes-its-own-upgrade-steps"]
spec_refs: ["S8", "S29"]
adr_refs: ["0043 D9"]
review_point: R12
paths: ["ccp/config.py", "ccp/lifecycle.py", "ccp/models.py", "ccp/prompt.py", "ccp/seats.py", "ccp/usage.py", "ccp/init.py", "ccp/upgrade.py", "scripts/observability/lib.py", "plugin/agents/delivery-runner.md", "contracts/plane_config.schema.json", "contracts/project.schema.json", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/spec/04-observability.md", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md", "tests/test_grace_ended.py", "tests/"]
adopt: "required: the ADR-0043 steps ccp upgrade status lists (plane.json language and suite.lanes.gate; move every key it names from its old place)"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0191-the-grace-release-ends

## Intent

The release after a product could take ADR-0043's steps, the plane stops carrying both shapes of the
configuration: a command that needs the language or the gate lane refuses without it, and a key read
at its old place during the grace (the language under `package_docs`, the implementer models under
`workers`, the account keys in plane.json, the merged plane.json keys, the binding's compaction window)
is ignored with a warning instead. The code that read the old places is gone.

## Context (not checked)

- ADR-0043 D9's migration ("a removed key keeps working for one release"; "the refusals in D4 and D5
  apply only once the step's grace release ends"), accepted 2026-11-19, and §29.3 as 0182 amends it.
  This task marks D9 built: its last part, the end of the grace, is this.
- **Operator prerequisite, before the claim:** every bound product has taken the required steps
  (`ccp upgrade status` in each lists none of 0182, 0183 or 0185 as not taken). The lead holds this
  task (`ccp tasks hold`) until the products' leads confirm it; the plane itself takes them in 0190.
- Not ended here, by the ADR: a constant's non-default value keeps applying, with its warning, until
  the product deletes the key (0187); removed keys keep being ignored with a warning.
- Today, at `e9ff0fc`: the old places are read by name in
  `git grep -cwP 'implementer_model|post_close|modules_ran_re|modules_cached_re' -- ccp scripts plugin ':!ccp/upgrade.py' ':!ccp/config.py'`:
  15 lines in `ccp/lifecycle.py` (5), `ccp/models.py` (1), `ccp/prompt.py` (6), `ccp/seats.py` (1),
  `ccp/usage.py` (2), `plugin/agents/delivery-runner.md` (1). The fallbacks the R12 tasks add for
  `package_docs.language`, `telemetry.allowance_*`, the merged keys and `lead.auto_compact_window` are
  measured by the implementer at its base.
- Decided here:
  - `config.REQUIRED_KEYS_GRACE` is removed and the refusals of 0182 and 0183 apply: exit 2, naming the
    key.
  - Each fallback to an old place is removed. A product that still sets the old key loads with one
    warning naming the key and its replacement, and the old value is not used. The schema keeps the
    old keys marked deprecated, so an old file still validates.
  - `ccp upgrade status` marks the ADR-0043 steps not taken as required and overdue.
  - SPEC sentences that describe the grace as current ("during the grace release …, read at its old
    place") for these keys are corrected under §31.1 and quoted in the PR body; §29.3's general rule
    (0182) stays.

## Scope

- **In:**
  - `ccp/config.py`, `scripts/observability/lib.py`, `ccp/usage.py`, `ccp/lifecycle.py`,
    `ccp/models.py`, `ccp/prompt.py`, `ccp/seats.py`, `ccp/init.py`: the fallbacks removed, the
    refusals on.
  - `ccp/upgrade.py`; `plugin/agents/delivery-runner.md`; the two schemas' descriptions.
  - `tests/test_grace_ended.py` (new); the grace tests of 0182, 0183, 0186, 0187 and 0188 updated to
    the refusal or the ignore.
  - The SPEC sentences above, §31.1.
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D9 marked built; `docs/adr/INDEX.md`.
- **Out:**
  - Removing the deprecated keys from the schemas. Constants' non-default values.

## dod_checks

- id: `gr-01`
  story: As a runner of a product with no gate lane, next now refuses.
  setup: a checkout of the PR head; `ccp sandbox create <dir>` (no `--gate`); one pending task file added and indexed, committed; the sandbox's `PROJECT_YAML` and `QUEUE_ROOT` exported.
  steps:
    1. In the sandbox's product root, run `ccp tasks next`.
  expect: exits 2 with `no gate lane` on stderr, and names no task.
  dry run (`e9ff0fc`): exit 0, `0001-first  Do the first thing`.
- id: `gr-02`
  story: As an operator, a key at its old place is no longer used, and I am told where it goes.
  setup: a checkout of the PR head; then a separate copy where `package_docs.language` is still read as `language`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_grace_ended`.
    2. In the copy, run the same.
  expect: step 1 exits 0, its tests covering for each old place (`package_docs.language`, `workers.implementer_model`, plane.json `telemetry.allowance_cmd`, `task_log.spec_paths`, `adapter.post_close`, `task_log.review_point_pattern`, binding `lead.auto_compact_window`) that the value is not used and one warning names the replacement, and `ccp docs check` exiting 2 on a product with no `language`; step 2 exits non-zero.
  dry run: n/a — new module.
- id: `gr-03`
  story: As a plane developer, no code reads the old places by name.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -cwP 'implementer_model|post_close|modules_ran_re|modules_cached_re' -- ccp scripts plugin ':!ccp/upgrade.py' ':!ccp/config.py'`.
    2. Run `git grep -n 'REQUIRED_KEYS_GRACE' -- ccp scripts plugin tests`.
  expect: both print nothing.
  dry run (`e9ff0fc`): step 1 printed 6 files, 15 lines (Context); step 2 nothing (the switch comes with 0182).
- id: `spec-01`
  story: As the operator, D9 is recorded as built.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n '"D9 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: prints `- "D9 built"`.
  dry run (`e9ff0fc`): printed `- "D9 not_built"`.
- id: `suite-01`
  story: As a plane developer, nothing else broke, the plane's own configuration included.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass with no deprecation warning about `docs/delivery/plane.json`, and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
