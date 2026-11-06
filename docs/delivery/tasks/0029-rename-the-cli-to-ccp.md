---
task_id: 0029-rename-the-cli-to-ccp
title: The CLI is renamed from cpl to ccp, with a temporary cpl shim
status: done
kind: refactor
depends_on: []
spec_refs: ["S29"]
review_point: R1
paths: ["bin/", "cpl/", "ccp/", "scripts/", "plugin/", "templates/", "contracts/", "docs/", "tests/", "README.md", "SPEC.md", "CLAUDE.md", "pyproject.toml"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0029-rename-the-cli-to-ccp

## Intent

The command carries the project's name (ADR-0036 D3). Users type `ccp`, read `ccp` in every message
and doc, and set `CCP_*` variables. Products that still call `cpl` keep working until they migrate,
through a shim that is removed before publication.

## Context (not checked)

- ADR-0036 named the project CCP and kept the CLI as `cpl` in the naming PR, so that PR stayed a
  docs change. The operator then ruled the CLI renamed too.
- `cpl` is named in code, messages, docs, prompts, the plugin, templates and tests, and in the
  run-checkout and release scripts, the PATH symlink and the launchd label prefix.

## Scope

- **In:**
  - `bin/ccp` (new) is the entry point; the Python package `cpl/` becomes `ccp/` (new);
  - every `cpl` mention in code, messages, docs, SPEC, prompts, the plugin, templates and tests
    becomes `ccp`;
  - `CPL_*` environment variables become `CCP_*`; each reader falls back to the old `CPL_*` name for
    one transition;
  - the launchd prefix default becomes `dev.ccp`;
  - `scripts/run-checkout.sh`, `scripts/release.sh` and the PATH symlink use the name `ccp`;
  - `bin/cpl` stays as a deprecated shim: it warns on stderr that `cpl` is now `ccp` and forwards
    its arguments and exit code;
  - the PR carries a prompt for each product's lead: the commands, variables and settings to change.
- **Out:** the plugin and marketplace ids (ADR-0036 D4, at publication); removing the shim, which is
  a publishing-checklist item once products have migrated.

## dod_checks

- id: `ccp-01`
  story: As a reader, I meet one name for the command.
  setup: a clone of the PR head.
  steps:
    1. Run `git grep -nP '\bcpl\b'`.
  expect: matches only in `bin/cpl` (the shim) and in history records (ADRs, done tasks).
  dry run: n/a — today `cpl` is named throughout.
- id: `ccp-02`
  story: As a maintainer, the rename breaks nothing.
  setup: a clone of the PR head.
  steps:
    1. Run `python3 -m unittest discover -s tests -t .`.
    2. Run `git branch --list 'state/*'`.
  expect: the suite passes; the branch list is empty.
  dry run: n/a.
- id: `ccp-03`
  story: As a product not yet migrated, my `cpl` calls still work.
  setup: a clone of the PR head; `CPL_LEAK_DENYLIST` set to an empty file.
  steps:
    1. Run `bin/cpl --root . tasks check`, then `bin/ccp --root . tasks check`.
  expect: both print the same result and exit code; `bin/cpl` also warns on stderr that it is
    deprecated; `ccp` reads the `CPL_*` variable when `CCP_*` is unset.
  dry run: n/a — `bin/ccp` does not exist yet.

## Implementation notes

*Append-only, newest last.*

- `bin/ccp` is the entry point and `ccp/` the package; every `cpl` in code, messages, docs, SPEC,
  prompts, the plugin, templates and tests became `ccp`, and `CPL_*` became `CCP_*`. History
  records (ADRs, done tasks, `docs/spec/RULINGS.md`, `docs/spec/map/`) are left as written.
- `ccp/envvars.py` holds the transition: `envvar()` reads `CCP_X`, else `CPL_X`; `for_child()` sets
  each variable `ccp` hands a command (`CCP_SUITE_ID`, `CCP_SUITE_RESULT`, `CCP_WT_*`) under both
  names, so a product script that still reads the old name keeps working. Shell scripts use
  `${CCP_X:-${CPL_X:-…}}`. The test fence drops any `CPL_*` from the developer's environment.
- Telemetry: writers emit `ccp.project_id` and `ccp.seat`; the receiver reads the old `cpl.` keys
  when the new ones are absent, and `sync-product-docs` notes a product still on the old key.
- The launchd prefix default is `dev.ccp`, so the existing `dev.cpl.*` agents must be reinstalled
  once (from a normal terminal); the old plists keep running through the shim until then.
- `bin/cpl` is a deprecated shim: one stderr line, then `ccp`'s `main` with the same arguments and
  exit code. `run-checkout.sh update` adds `~/.local/bin/ccp` beside an old `cpl` link. The plugin's
  hooks fall back to `cpl` on PATH, and `ccp where` also prints the old `cpl` key.
- Pending task 0027 is now `0027-ccp-init` (`renamed_from: 0027-cpl-init`).
- SPEC §29.4 gains a bullet naming the transition; the other § edits are the rename only.
- Review fixes: `run-checkout.sh update` restarts a receiver still under the old default label
  `dev.cpl.control-plane.otel` (only when no label or prefix is named), so it comes back on the new
  code through the shim; `merge.command` gets `CCP_GH_BIN` under both names; the idle hook takes the
  old `--cpl` flag; `envvar()` treats an empty value as unset, like the shell fallbacks; the pinned-id
  warning names the key it found. `bin/cpl` is the only old entry point: `python3 -m cpl` and an
  installed `cpl` console script are gone.

## Verification notes

*Append-only.*

- `ccp-01` pass: `git grep -nP '\bcpl\b'` matches the shim, history records (ADRs, done tasks,
  `RULINGS.md`, `docs/spec/map/`), and the code, tests and docs that name the transition itself
  (`envvars`, the receiver's old keys, the hooks' PATH fallback, `ccp where`'s old key,
  `run-checkout.sh`'s link migration, SPEC §29.4, the roadmap, `0027-ccp-init`'s `renamed_from`).
- `ccp-02` pass: 1046 tests OK (1 skipped); after the review fixes 1048 OK (1 skipped); no `state/*` branches.
- `ccp-03` pass: `bin/cpl --root . tasks check` and `bin/ccp --root . tasks check` print the same
  and exit the same; `bin/cpl` warns on stderr; `CPL_*` fallbacks are covered in
  `tests/test_ccp_rename.py` and `tests/test_plugin.py`. Leak check clean; adr and docs checks clean.
