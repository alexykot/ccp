---
task_id: 0182-language-is-a-required-key
title: The product's language is a required top-level key that the doc checks, the test-output reading and affected follow
status: pending
kind: feature
depends_on: ["0172-fixtures-name-their-config", "0173-plane-json-block-registry", "0176-language-pack-owns-test-facts"]
spec_refs: ["S4", "S8", "S14", "S21", "S29"]
adr_refs: ["0043 D4"]
review_point: R12
paths: ["ccp/config.py", "ccp/doclang/__init__.py", "ccp/doclang/CLAUDE.md", "ccp/pkgdocs.py", "ccp/suite.py", "ccp/init.py", "ccp/cli.py", "ccp/upgrade.py", "contracts/plane_config.schema.json", "templates/docs-delivery/example-plane.json", "README.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/spec/05-operations.md", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md", "tests/helpers.py", "tests/test_toolkit.py", "tests/test_language_key.py", "tests/test_suite.py", "tests/test_suite_cold.py", "tests/test_suite_stages.py", "tests/test_suite_wait.py", "tests/test_suite_affected.py", "tests/test_mutate.py", "tests/test_verify_cache.py", "tests/test_doc_rules.py", "tests/test_pkgdocs_config.py", "tests/test_starter_rules.py", "tests/test_config_unknown_keys.py", "tests/test_init.py", "tests/test_delivery_ids.py", "tests/test_self_hosting.py", "tests/test_upgrade.py"]
adopt: "required: plane.json language (python, or none; with a pack language and no package_docs block the package-doc checks turn on, so a product that had none either adds the package docs or sets none and maps its tests in suite.affected_map)"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0182-language-is-a-required-key

## Intent

A product names its language once, in a top-level plane.json `language` key, and the plane assumes
none. The language pack it names runs the package-doc checks, reads the test output and finds the tests
a change touches; `none` turns the package-doc checks off and leaves test output to the product's own
patterns. A command that needs the language and finds it unset says so, naming the key; during the
grace release it warns and behaves as before, and `ccp init --language` writes it.

## Context (not checked)

- ADR-0043 D4, accepted 2026-11-19, as refined by the operator's ruling on shape F03 (2026-11-19, "1a"):
  "the language is a top-level `language` key; package-doc checks follow it, `none` turns them off".
  The ruling is recorded in ADR-0043's `notes` by this triage's commit.
- Depends on 0176 (the pack owns its test facts; `doclang.for_tests(cfg)` is the one lookup this task
  changes), 0172 (the fixtures name their configuration) and 0173 (the block registry).
- Today, measured at `e9ff0fc` on temp git products with a `src/a.py`, a `src/b.sql`, a root
  `CLAUDE.md` and a fresh index, each run as `ccp --root <dir> docs check`:
  - plane.json `{"project_id": "demo"}`: `docs: clean`, exit 0, nothing said about a language;
  - `{"project_id": "demo", "package_docs": {"language": "none"}}`: exit 1, `src: no .claude.md` (the
    core runs under `none`);
  - `{"project_id": "demo", "language": "python"}`: exit 1, `unknown key language`;
  - `{"project_id": "demo", "package_docs": {"language": "python"}}`: exit 1, `src: no .claude.md`.
  - `ccp suite affected` with no `package_docs` block reads with the Python pack (`def _language` in
    `ccp/suite.py` falls back to `PACKAGE_DOCS_DEFAULTS`); `ccp init` writes no language unless
    `--starter-rules`, which writes `package_docs.language: none` (`STARTER_CONFIG` in `ccp/init.py`).
- Decided here:
  - `language` is a top-level string, one of `doclang.NAMES` (`none`, `python`); any other value is a
    configuration error listing them. It has no default.
  - With a pack language, the package-doc checks (the core, §21.3, and the pack's, §21.4) run, with the
    `package_docs` block's settings or, without the block, their defaults. With `none` they do not
    run. The generic rules a product names in `package_docs.rules` (§21.6) run whatever the language:
    they are opt-in by naming, and the starter rules (§20.5) rely on them under `none`.
  - Test output: the count and summary defaults are the pack's (`for_tests` now follows `language`);
    with `none` only the product's `suite.count_re` and `suite.summary` patterns count.
    `ccp suite affected` uses the pack's reader; with `none`, `suite.affected_map` alone or exit 2, as
    today.
  - Unset `language`: `ccp docs check`, `ccp suite affected` and `ccp suite run`'s reading of test output
    need it. While `config.REQUIRED_KEYS_GRACE` is true (this release's grace, ended by 0191), each warns
    on stderr, naming `language` and the upgrade step, and behaves as at `e9ff0fc`. Other commands
    neither warn nor refuse.
  - `package_docs.language` is the old place of the key: when `language` is unset it is read as
    `language`, with a warning naming the move; the schema marks it deprecated (0191 removes it).
  - `ccp init --language <name>` writes `language` into a new plane.json. Without it, init's result
    (and its stderr) lists `language` as a required key still unset. `--starter-rules` no longer
    writes `package_docs.language`.
  - The fixtures (`helpers.BASE_PLANE`, `ToolkitFixture`) gain `"language": "none"`, which keeps today's
    "no package-doc checks" for them; a test that reads unittest output sets `"language": "python"`.
  - `ccp upgrade status` lists this task's step for a product with no `language`. It proposes no value
    silently. For a product with a `package_docs` block, it names the block's language (`python` when
    the block relied on the old default) as the value to set. For a product with no `package_docs`
    block, it states the choice plainly:
    - (a) `python`: test output is read and `affected` works with the Python pack, and it also turns on
      the package-doc checks, which this product has never run: write the package docs first (every
      source directory's `CLAUDE.md`, §21.3), or the gate's `plane-docs` stage fails;
    - (b) `none`: no package-doc checks, but then the product gives `suite.affected_map` and its own
      `suite.count_re` and `suite.summary` patterns, or `ccp suite affected` exits 2 and the run's tests
      are not counted.
  - **What the coupling costs.** Under 1a one key selects both the test-output reading and the
    package-doc checks, so a product cannot take the Python test reading without the Python doc
    checks, and `none` loses the test reading. A product with history and no package docs pays the
    one-time cost of writing them (a), or maps its tests by hand (b). The pack (0176) keeps the two
    facts apart in code, so splitting them into two keys later is a schema change only.
- This task marks ADR-0043 D4 built in its own PR: the refusal's switch (`REQUIRED_KEYS_GRACE`) is
  part of what it builds; 0191 flips it.
- Any other SPEC sentence this makes false is corrected under §31.1 and quoted in the PR body.

## Scope

- **In:**
  - `ccp/config.py`: `language` loaded and validated; `REQUIRED_KEYS_GRACE = True`; the
    `package_docs.language` fallback and warning; `package_docs` no longer "absent means off" (its
    settings or defaults load whenever the language is a pack).
  - `ccp/doclang/__init__.py` (`for_tests` follows `language`), `ccp/doclang/CLAUDE.md`,
    `ccp/pkgdocs.py`, `ccp/suite.py`: as decided above.
  - `ccp/init.py`, `ccp/cli.py`: `--language`; the required-key lines; `STARTER_CONFIG` without
    `package_docs.language`.
  - `ccp/upgrade.py`: this task's step and its proposal.
  - `contracts/plane_config.schema.json`, `templates/docs-delivery/example-plane.json`, `README.md`
    (the adoption checklist names `language` first, as required).
  - `tests/helpers.py`, `tests/test_toolkit.py`; `tests/test_language_key.py` (new); the modules that
    read unittest output or set `package_docs` (`git grep -l 'Ran [0-9]\|"Ran \|OK (skipped\|package_docs' -- tests`
    at `e9ff0fc`, less the gate-script modules) name their language; they are listed in `paths`.
  - `docs/spec/01-model.md` §8.1: CURRENT (at `e9ff0fc`): "Only `project_id` is
    required: lowercase letters, digits and hyphens." PROPOSED:
    > Two keys are required: `project_id` (lowercase letters, digits and hyphens) and `language`, the product's language pack (§21.4) or `none`; the plane assumes no language. A command that needs the language (the package-doc checks and with them `ccp docs check`, `ccp suite affected`, and the reading of test output, §14.1) refuses with exit 2, naming the key, when it is unset; other commands run. During the grace release that introduces a required key (§29.3), a command that needs it warns instead, naming the key and its upgrade step, and behaves as before the key was required.
  - `docs/spec/01-model.md` §8.1: CURRENT (at `e9ff0fc`): "The schema only gains optional keys." PROPOSED:
    > The schema gains a required key, or drops or moves one, only as §29.3 allows.
  - `docs/spec/05-operations.md` §29.3: CURRENT (at `e9ff0fc`): "- `plane.json`'s schema only gains optional keys." PROPOSED:
    > - `plane.json`'s schema only gains optional keys, except through an upgrade step (a task's `adopt`, §5.2) that comes with a **grace release**. During it a command that will refuse without a required key warns instead and behaves as before; a removed key is ignored with a warning naming it; a moved or merged key is still read at its old place, with a warning naming the new one, when the new place is unset; and `ccp upgrade status` names each step. The release that ends the grace refuses without the required key and no longer reads the old places. A key that becomes a constant in code is never dropped silently: a value other than the constant still applies, with a warning, until the product deletes the key or the plane takes a proposal to keep it.
  - `docs/spec/01-model.md` §8.1, the `package_docs`, `docs` row: CURRENT (at `e9ff0fc`): "doc checks (`claude_md_dirs`, `language`, `path_ref_suffixes`," PROPOSED:
    > doc checks, run when `language` names a pack (`claude_md_dirs`, `path_ref_suffixes`,
  - `docs/spec/01-model.md` §4.5: CURRENT (at `e9ff0fc`): "a minimal `docs/delivery/plane.json` (§8.1): the project id, the worktrees directory, with
    `--gate` the gate lane" PROPOSED:
    > a minimal `docs/delivery/plane.json` (§8.1): the project id, the worktrees directory, with `--language` the language, with `--gate` the gate lane
  - `docs/spec/01-model.md` §4.5, after the sentence ending "and adopts it all the same: review, merge and close need a GitHub origin until the PR host adapter of ADR-0040 exists." CURRENT: none (a new sentence). PROPOSED:
    > Its result, and its stderr, list each required plane.json key (§8.1) still unset, as a step to take before the first task.
  - `docs/spec/02-delivery.md` §14.1: CURRENT (at `e9ff0fc`): "`suite.count_re` (default `^Ran (\d+) tests? in `)" PROPOSED:
    > `suite.count_re` (default: the language pack's, §21.4; Python's reads unittest's `Ran N tests in`)
  - `docs/spec/02-delivery.md` §14.1: CURRENT (at `e9ff0fc`): "The defaults read Python unittest only (`OK (skipped=N)`,
    `FAILED (failures=N, errors=N, skipped=N)`);" PROPOSED:
    > The defaults are the language pack's (Python's read unittest's `OK (skipped=N)` and `FAILED (failures=N, errors=N, skipped=N)`); with `language: none` there are none, and only the product's own patterns count;
  - `docs/spec/02-delivery.md` §14.7: CURRENT (at `e9ff0fc`): "- **The product's language pack reads the tests** (`package_docs.language`; its default, `python`,
    when the block is absent)." PROPOSED:
    > - **The product's language pack reads the tests** (`language`, §8.1).
  - `docs/spec/03-quality.md` §21.3: CURRENT (at `e9ff0fc`): "The rules are opt-in: they run only with a `package_docs` block." PROPOSED:
    > The rules follow the product's `language` (§8.1): a language pack turns them on, with the `package_docs` block's settings or, without the block, their defaults, and `none` turns them off. The generic rules a product names in `package_docs.rules` (§21.6) run whatever the language.
  - `docs/spec/03-quality.md` §21.4: CURRENT (at `e9ff0fc`): "`package_docs.language` selects a pack (default `python`; `none` runs the core alone; any other name
    is a configuration error that lists the packs)." PROPOSED:
    > The top-level `language` (§8.1) selects a pack; it has no default. `none` turns the package-doc rules off (§21.3); any other name that is not a pack is a configuration error that lists the packs. The pack also reads the product's test output (§14.1) and the tests a change touches (§14.7).
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D4 marked built; `docs/adr/INDEX.md`.
- **Out:**
  - Ending the grace (0191), and the gate lane's requirement (0183).
  - A second language pack.

## dod_checks

- id: `lng-01`
  story: As an operator of a product that names no language, the doc check tells me, and during the grace release it still passes as before.
  setup: a checkout of the PR head; a temp git product whose plane.json is `{"project_id": "demo"}`, with `src/a.py`, `src/b.sql`, a root `CLAUDE.md`, a fresh `ccp tasks index`, all committed.
  steps:
    1. Run `ccp --root <dir> docs check`.
    2. Run `ccp --root <dir> suite affected --paths src/a.py`.
  expect: step 1 exits 0 with a stderr warning naming `language`; step 2 exits 0 with a stderr warning naming `language`.
  dry run (`e9ff0fc`): step 1 `docs: clean`, exit 0, no warning; step 2 `no test module depends on the 1 changed path(s)`, no warning.
- id: `lng-02`
  story: As an operator, `language: python` runs the package-doc checks with no package_docs block.
  setup: the product of `lng-01`, its plane.json `{"project_id": "demo", "language": "python"}`, committed.
  steps:
    1. Run `ccp --root <dir> docs check`.
  expect: exit 1, the one failure `src: no .claude.md`; no `unknown key` line.
  dry run (`e9ff0fc`): exit 1 with `unknown key language` (the key is unknown today).
- id: `lng-03`
  story: As an operator, `none` turns the package-doc checks off, and the old key still works with a warning.
  setup: the product of `lng-01`, its plane.json `{"project_id": "demo", "package_docs": {"language": "none"}}`, committed; then a second product with `{"project_id": "demo", "language": "none"}`.
  steps:
    1. Run `ccp --root <dir> docs check` in each.
  expect: the first exits 0 with a warning naming the move from `package_docs.language` to `language`; the second exits 0 with no `src` failure.
  dry run (`e9ff0fc`): the first exits 1 with `src: no .claude.md`; the second exits 1 with `unknown key language`.
- id: `lng-04`
  story: As a plane developer, test output, affected and init follow the language, and the tests bite.
  setup: a checkout of the PR head; then a separate copy where `doclang.for_tests` ignores `language` and always returns the Python pack.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_language_key tests.test_suite tests.test_suite_affected tests.test_init tests.test_doc_rules`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_language_key`.
  expect: step 1 exits 0, its new tests covering `ccp init --language python` writing the key, init without it listing `language` as unset, and a `none` product's `Ran 5 tests` line not counted; step 2 exits non-zero.
  dry run: n/a — `tests.test_language_key` is new and `for_tests` comes with 0176.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed, and D4 is recorded as built.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0182-language-is-a-required-key --base origin/main`.
    2. Run `grep -n '"D4 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: step 1 exits 0 with every passage found; step 2's output contains `- "D4 built"`.
  dry run (`e9ff0fc`): step 2 printed `- "D4 not_built"`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
