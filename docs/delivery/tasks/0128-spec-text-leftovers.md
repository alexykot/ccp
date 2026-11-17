---
task_id: 0128-spec-text-leftovers
title: SPEC text left behind by R7: notices in the orientation, the upgrade trigger, spec_paths, the lead's compaction knob and suite exit 2
status: pending
kind: feature
depends_on: []
spec_refs: ["S2", "S3", "S4", "S5", "S8", "S9", "S14"]
review_point: R8
sign_off: brief
paths: ["docs/spec/01-model.md", "docs/spec/02-delivery.md"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0128-spec-text-leftovers
## Intent

The SPEC states what R7 built: the orientation's pending notices, the upgrade trigger's record-only
channel, the `task_log.spec_paths` knob, the binding's `lead.auto_compact_window`, init's
`--force` with settings, and every case where `ccp suite run` exits 2. Nothing in the code changes.

## Context (not checked)

- Each passage below was found stale or missing by a review or verify of an R7 task. The code
  already does what the PROPOSED text says.
- The §8.1 `health` row, the §2.6 and §8.3 knob lines and the §14.5 correction only describe
  built features (§31.1); they are quoted here so the implementer writes no SPEC text of its own.

## Scope

- **In:**
  - `docs/spec/01-model.md` §9.3, a new bullet after the first. CURRENT (at `b4de6ad`): none. PROPOSED:
    > - After the orientation, the hook and `ccp orientation` list the product's pending notices (`ccp notify pending`, §3.6): each one's subject, reason and the call that records it sent, within the hook's cap.
  - `docs/spec/01-model.md` §3.6, Content. CURRENT (at `b4de6ad`): "the trigger one of the four above or `other`," PROPOSED:
    > the trigger one of the five above or `other`,
  - `docs/spec/01-model.md` §3.6, Channels. CURRENT (at `b4de6ad`): "the unattended channel `ccp` runs on each trigger," PROPOSED:
    > the unattended channel `ccp` runs on each trigger but `upgrade`, which is only recorded for the lead to dispatch, so a release runs no product command,
  - `docs/spec/01-model.md` §3.5. CURRENT (at `b4de6ad`): "(plane.json `task_log.spec_paths`, default `["docs/spec/", "SPEC.md"]`)" PROPOSED:
    > (plane.json `task_log.spec_paths`, default `["docs/spec/", "SPEC.md"]`; a path meets an entry it equals or, for an entry ending in `/`, lies under, so `docs/spec` without its `/` meets none)
  - `docs/spec/01-model.md` §5. CURRENT (at `b4de6ad`): "`refs_any`, the kinds, `max_checks`, the soft words, `dry_run`, the records directory" PROPOSED:
    > `refs_any`, the kinds, `max_checks`, the soft words, `dry_run`, the SPEC paths (`spec_paths`, §3.5), the records directory
  - `docs/spec/01-model.md` §8.1, the `task_log` row. CURRENT (at `b4de6ad`): "`dry_run`, `reviews_dir`, `index`;" PROPOSED:
    > `dry_run`, `spec_paths`, `reviews_dir`, `index`;
  - `docs/spec/01-model.md` §2.4. CURRENT (at `b4de6ad`): "`subagentPromptCacheTtl` setting or `FORCE_PROMPT_CACHING_5M` overrides it, and" PROPOSED:
    > `subagentPromptCacheTtl` setting or `FORCE_PROMPT_CACHING_5M` overrides a worker definition's `cacheTtl`, and
  - `docs/spec/01-model.md` §4.5. CURRENT (at `b4de6ad`): "It keeps a file that already exists and lists it as kept, unless given `--force`, so running it again changes nothing." PROPOSED:
    > It keeps a file that already exists and lists it as kept, unless given `--force`, so running it again changes nothing. Even with `--force` it merges into `.claude/settings.json` and keeps every value already there, `subagentPromptCacheTtl` and `autoCompactWindow` included.
  - §31.1: `docs/spec/01-model.md` §2.6, a new bullet after the rotation bullet:
    > - `lead.auto_compact_window` (default 350000): the `autoCompactWindow` `ccp init` writes into the product's settings (§4.5).
  - §31.1: `docs/spec/01-model.md` §8.3's binding example, after the `runner` block:
    > `lead:` then `  auto_compact_window: 350000            # autoCompactWindow ccp init writes (§4.5)`
  - §31.1: `docs/spec/01-model.md` §8.1, the `health` row. CURRENT (at `b4de6ad`): "the line below which a merged task counts as small (`small_task_lines`, default 100)" PROPOSED:
    > the line below which a merged task counts as small (`small_task_lines`, default 100), the slowest test modules listed (`slowest_modules`, default 5) and the gate runs the suite trend spans (`suite_trend_runs`, default 10)
  - §31.1: `docs/spec/02-delivery.md` §14.5. CURRENT (at `b4de6ad`): "It exits 2 only with no command to run, or with options that do not parse (§14.2):" PROPOSED:
    > It exits 2 only with no command to run, with a command after `--` on a staged lane, or with options that do not parse (§14.2):
- **Out:**
  - Any code change.

## dod_checks

- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare each edit with the PROPOSED text above.
  expect: they match word for word, the PR changes no file outside `docs/spec/`, and no other § rule changes.
  dry run: n/a.
- id: `check-02`
  story: As a reader, the text is true of the code.
  setup: a scratch product made by `ccp init` with a pending notice fired by `ccp notify fire other`.
  steps:
    1. Run `ccp orientation` there, then `ccp init --force` and read `.claude/settings.json`'s `autoCompactWindow` after setting it to 123 by hand first.
  expect: the orientation ends with the notice's subject; `autoCompactWindow` is still 123.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp tasks check`, `ccp docs check`, `ccp adr check`.
  expect: all pass.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 (implementer): the twelve CURRENT → PROPOSED edits are applied word for word in
  `docs/spec/01-model.md` (§2.4, §2.6, §3.5, §3.6 twice, §4.5, §5.6, §8.1 twice, §8.3, §9.3) and
  `docs/spec/02-delivery.md` (§14.5). Changed lines were not reflowed, so each edit reads as one
  line in the diff. No code changes.
- check-02 names `ccp notify fire other`, a command that does not exist: a pending notice is fired
  only by a step, and `other` is never fired (`ccp/notify.py` `fire`). The check was run with a
  `blocker` notice fired by `ccp tasks wait <task> operator_step` in a `ccp sandbox`: the
  orientation ended with the notice's subject, and `autoCompactWindow` set to 123 stayed 123 after
  `ccp init --force`.
- §3.5's new clause says a path lies under an entry only when the entry ends in `/`; the code
  (`ccp/tasklog.py` `_names_spec`) also treats an entry without the `/` as a directory. Raised in
  the report, not changed here.

## Verification notes
