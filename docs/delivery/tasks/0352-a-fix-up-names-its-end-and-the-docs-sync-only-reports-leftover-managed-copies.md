---
task_id: 0352-a-fix-up-names-its-end-and-the-docs-sync-only-reports-leftover-managed-copies
title: A release's fix-up command names its end in the plane's roadmap, with its signed §29.3 sentence; scripts/sync-product-docs.sh only checks, reporting a product's leftover managed copies as §9.5 says, its install mode, daily stamp and --allow-dirty gone, and the plugin skills and scripts doc stop saying it installs copies
status: pending
kind: feature
depends_on: []
spec_refs: ["S9", "S29", "S31"]
review_refs: ["ar-20261125T184522Z-c248#F02", "ar-20261125T202431Z-1a86#F03"]
review_point: R39
paths: ["docs/spec/05-operations.md", "scripts/sync-product-docs.sh", "scripts/CLAUDE.md", "ccp/queue.py", "plugin/skills/review-triage/SKILL.md", "plugin/skills/spec-maintainer/SKILL.md", "docs/design/orientation.md", "tests/test_team_hosting.py", "tests/test_plugin.py", "tests/test_binding_reader.py", "tests/test_binding_by_id.py", "tests/test_usage.py", "tests/test_plane_check.py"]
clashes_with: ["0191-the-grace-release-ends"]
sign_off: brief
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0352-a-fix-up-names-its-end-and-the-docs-sync-only-reports-leftover-managed-copies

## Intent

A maintainer reading §29.3 learns that a fix-up command a release ships is not permanent: the plane's roadmap names
when it goes, and it goes with any compatibility reading it serves once no bound product's dry run changes anything.
An operator checking a product with `scripts/sync-product-docs.sh --check` is told only what §9.5 asks: the managed
copies a product still holds, which the plugin now ships, and the settings notes; the script can no longer install
copies, and no plane doc says it does.

## Context (not checked)

Finding F02 of architect pass `ar-20261125T184522Z-c248` (`docs/delivery/reviews/ar-20261125T184522Z-c248.md`) and
the operator's answer to that triage's question 2, given on 2026-11-25 through the lead:

> Sign both (Recommended)

That is option (a): "Sign the §29.3 sentence and apply E9's text; the roadmap gets a trigger for `adr migrate
--markers` and `review-points migrate`, and each is retired by a signed task once every bound product's dry run
changes nothing". The sentence the operator approved is this task's one PROPOSED addition, verbatim; the lead records
the brief sign-off with these words. Triage `ar-20261125T202431Z-1a86` applied E9's text and added the two roadmap
end entries; the retiring tasks come later, each signed.

Also finding F03 of architect pass `ar-20261125T202431Z-1a86` (`docs/delivery/reviews/ar-20261125T202431Z-1a86.md`):
§9.5 says no product holds a managed copy and the sync's `--check` reports a leftover one as stale, yet the script's
default mode still writes copies and its `--daily-stamp` mode serves the retired watchdog seat. The script is the
first fix-up of this kind to reach its end: every bound product is on the plugin.

0191 (on hold; it removes the moved keys' fallback reads, and its `paths` hold all of `tests/`) rules on neither the sync nor `QUEUE_OWNED`; whichever lands second rebases.

Measured at `becb6417`:

- `wc -l scripts/sync-product-docs.sh` at `becb6417`: 317 lines. Without `--check` it writes the managed copies
  (`"def expected"`, the `else:` branch of the managed loop) and appends the CLAUDE.md section; `"def plugin_enabled"`
  picks between installing them and reporting them stale.
- `git grep -nE 'daily.stamp|allow.dirty|product-docs-check' -- scripts ccp tests | wc -l` at `becb6417`: 15 lines,
  in the script, `ccp/queue.py` (`QUEUE_OWNED`'s `"product-docs-check.json"`) and `tests/test_plane_check.py`, and the
  `--allow-dirty` calls in `tests/test_plugin.py` and `tests/test_team_hosting.py`.
- `git grep -l sync-product-docs -- tests` at `becb6417`: `tests/test_binding_by_id.py`, `tests/test_binding_reader.py`,
  `tests/test_plugin.py`, `tests/test_team_hosting.py`, `tests/test_usage.py`.
- `git grep -n 'sync-product-docs' -- plugin | wc -l` at `becb6417`: 2 lines, the comments of
  `plugin/skills/review-triage/SKILL.md` and `plugin/skills/spec-maintainer/SKILL.md`.
- `git grep -n 'daily-stamp\|allow-dirty' -- docs/spec docs/cli` at `becb6417`: nothing, so the cut needs no SPEC
  change beyond the signed sentence; §9.5 and §4.3 already describe a check-only script.

**Ruled.**

- `scripts/sync-product-docs.sh <project_id> --check [--product-root DIR] [--project-yaml FILE]` is the one form; a
  call without `--check`, or with `--daily-stamp` or `--allow-dirty`, exits 2 with the usage line. Every product is
  read as one on the plugin (§9.5), so the `plugin_enabled` branch goes: each path the script managed (the
  orientation, the two protocol docs, the architect skill and the two skills it replaced, the four agents, the two
  hooks) that carries the managed-copy header is reported `DRIFT <path>: retired`, one without the header is a
  `left alone` note, and a missing one is nothing. The CLAUDE.md import line and the settings hook entries that
  call `.claude/hooks/` copies are reported as now for a plugin product; the telemetry, `cpl.project_id` and
  `rules_doc` notes stay. Exit 0 clean, 1 drift. Its last line on drift says to delete the listed copies and commit
  the product change. The header comment describes only this.
- `ccp/queue.py`: `"product-docs-check.json"` leaves `QUEUE_OWNED`, so a live queue's old stamp is a §31.3 leftover
  that `ccp plane check --archive` archives; `tests/test_plane_check.py`'s list follows. That makes a live queue
  holding the old stamp fail `ccp plane check` (exit 1) until it is archived, so the PR names
  `ccp plane check --archive` as this change's fix-up, as §29.3 requires.
- Tests: the install tests go (`tests.test_team_hosting.TestSync.test_installs_agent_and_executable_hook`, the
  install half of `test_architect_skill_replaces_the_two_old_ones` and of
  `tests.test_plugin`'s `test_a_product_on_the_plugin_gets_no_copies_and_loses_stale_ones`); a `--check` test that
  read a missing copy as drift (`tests.test_binding_reader`'s maintainer-doc and bindings-directory tests,
  `tests.test_binding_by_id.BindingById.test_sync_reads_the_binding_project_yaml_names`) uses a leftover copy
  carrying the header instead. New tests `tests.test_team_hosting.TestSync.test_a_call_without_check_is_refused` (a bare call, with no
  `--check` and none of the removed options, so `code-02`'s grep stays clean) and
  `tests.test_team_hosting.TestSync.test_a_leftover_copy_is_reported_and_nothing_is_written`.
  `tests.test_binding_by_id.BindingById.test_sync_refuses_a_project_with_no_binding` stays as it is.
- The two plugin skills' comments drop the sentence naming the sync; `scripts/CLAUDE.md` says the script reports a
  product's leftover managed copies (§9.5); `docs/design/orientation.md`'s last paragraph says the sync only reports
  them.

## Scope

- **In:** `scripts/sync-product-docs.sh`; `scripts/CLAUDE.md`; `ccp/queue.py` (`QUEUE_OWNED` only);
  `plugin/skills/review-triage/SKILL.md` and `plugin/skills/spec-maintainer/SKILL.md` (the comment only);
  `docs/design/orientation.md`; `tests/test_team_hosting.py`; `tests/test_plugin.py`; `tests/test_binding_reader.py`;
  `tests/test_binding_by_id.py`; `tests/test_usage.py`; `tests/test_plane_check.py`; the SPEC, signed:

  CURRENT (`docs/spec/05-operations.md` at `becb6417`), §29.3:
  > A plane change that would make a conforming product fail a check (a renamed generator, a tightened check) ships its own fix-up (a migrate or regenerate command) and names that command in its pull request, which is the release's note. The pull request template asks whether the change breaks conforming products.

  PROPOSED:
  > A plane change that would make a conforming product fail a check (a renamed generator, a tightened
  > check) ships its own fix-up (a migrate or regenerate command) and names that command in its pull
  > request, which is the release's note. The fix-up names its end in the plane's roadmap: it is retired, with any
  > compatibility reading it serves, once no bound product's dry run changes anything. The pull request template
  > asks whether the change breaks conforming products.

  Nothing retired: the sentence is added.
- **Out:** retiring `ccp adr migrate --markers` and `ccp review-points migrate` (later signed tasks, on their
  `docs/ROADMAP.md` triggers); `docs/ROADMAP.md` and `docs/ENGINEERING.md` (triage `ar-20261125T202431Z-1a86` wrote
  them); the constant keys of §29.3's second bullet (the operator's question on `ar-20261125T202431Z-1a86` F04).

## dod_checks

- id: `spec-01`
  story: As the operator, §29.3 says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0352`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`becb6417`, with this brief): exit 1, the PROPOSED passage not found.
- id: `code-01`
  story: As an operator, the docs sync only checks, and reports a leftover managed copy without touching it.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_team_hosting.TestSync.test_a_call_without_check_is_refused tests.test_team_hosting.TestSync.test_a_leftover_copy_is_reported_and_nothing_is_written tests.test_team_hosting tests.test_plugin tests.test_binding_reader tests.test_binding_by_id tests.test_usage tests.test_plane_check`.
  expect: exit 0.
  dry run (`becb6417`): exit 1 (`AttributeError: type object 'TestSync' has no attribute 'test_a_call_without_check_is_refused'`).
- id: `code-02`
  story: As a maintainer, the install mode's options and the watchdog's stamp are gone from code and tests.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nE 'daily.stamp|allow.dirty|product-docs-check' -- scripts ccp tests`.
  expect: prints nothing (git grep's exit 1).
  dry run (`becb6417`): printed 15 lines.
- id: `doc-01`
  story: As a reader of the plugin skills and the scripts doc, nothing says the sync installs copies.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n 'sync-product-docs' -- plugin`.
    2. Run `git grep -n 'not on the plugin' -- scripts/CLAUDE.md`.
  expect: step 1 and step 2 each print nothing (git grep's exit 1).
  dry run (`becb6417`): step 1 printed 2 lines; step 2 printed 1 line.

## Implementation notes

## Verification notes
