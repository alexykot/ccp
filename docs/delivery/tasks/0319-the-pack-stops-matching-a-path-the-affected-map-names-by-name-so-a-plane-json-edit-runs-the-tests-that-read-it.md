---
task_id: 0319-the-pack-stops-matching-a-path-the-affected-map-names-by-name-so-a-plane-json-edit-runs-the-tests-that-read-it
title: A changed path that plane.json suite.affected_map matches is no longer matched to tests by its name, so the language pack stops marking every test that names the file while a changed test module and a module's importers still count, and this repo maps its own plane.json to the tests that read it
status: pending
renamed_from: 0319-a-path-the-affected-map-names-is-the-map-s-alone-so-a-plane-json-edit-runs-the-tests-that-read-it
kind: feature
depends_on: []
spec_refs: ["S14"]
review_refs: ["ar-20261123T230912Z-197a#F01"]
review_point: R32
paths: ["ccp/suite.py", "ccp/doclang/python.py", "tests/test_suite_affected.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "contracts/plane_config.schema.json", "docs/delivery/plane.json"]
clashes_with: ["0191-the-grace-release-ends", "0310-worker-briefs-name-suite-run-affected-and-log-texts-follow-the-pruning-of-every-suite-run-log", "0311-suite-affected-and-suite-run-affected-run-a-staged-part-lane-as-declared"]
sign_off: brief
adopt: "plane.json suite.affected_map: map a widely named file (a config file the test fixtures write, say) to the test ids that read it, so the language pack stops matching that file's name in every test"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0319-the-pack-stops-matching-a-path-the-affected-map-names-by-name-so-a-plane-json-edit-runs-the-tests-that-read-it

## Intent

A product can tell `ccp suite affected` which tests a widely named file really touches. A changed path that a
glob of plane.json `suite.affected_map` matches is not matched to tests by its name: its tests are the ids the map
gives, not every test whose text names the file. A changed test module still counts for itself, and a changed
module's importers are still found, whether or not the map matches it. In this repo, an edit to
`docs/delivery/plane.json` then makes the pre-gate and the review's affected run take the tests that read the
plane's own config, not about four in ten of the suite.

## Context (not checked)

Finding F01 of architect pass `ar-20261123T230912Z-197a` (`docs/delivery/reviews/ar-20261123T230912Z-197a.md`), whose
deferral (`ar-20261121T174754Z-7df5` F01, `docs/ROADMAP.md`) this takes up for config files; the roadmap's choice for
the cli and config hub modules stays deferred.

Measured at `bb102371`:

- **The breadth.** `CCP_DEV=1 ./bin/ccp suite affected --paths docs/delivery/plane.json 2>/dev/null | wc -l`: 100 of
  233 test modules (`git ls-files 'tests/test*.py' | wc -l`). The Python pack (`"def affected"` in
  `ccp/doclang/python.py`) marks a test that names a changed file's name in its text, and the fixtures write their
  own `docs/delivery/plane.json`. Since 0299 every implementer pre-gate and every review run this set, the review
  cold (plane.json sets no `verify.accept_cache.review`). The gate's test cache keys every module on all shared
  inputs (Known intentional, `docs/ENGINEERING.md`), so the pre-gate's run largely pre-pays the gate that follows;
  the cost that stays is the cold review run (181 s in 0301's review, by its friction note) and a slower fail-fast.
  `git log --oneline 16d9c62c..b09de675 -- docs/delivery/plane.json | wc -l`: 5 of the window's 24 commits.
- **Who reads the plane's own plane.json.** `git grep -nE '(PLANE_ROOT|ROOT)[^"]{0,30}"docs/delivery/plane\.json"|load\((lib\.|helpers\.)?(PLANE_ROOT|ROOT)\)' -- 'tests/*.py'`:
  one line, `tests/test_self_hosting.py` (it reads `architect.checks`). The implementer re-runs this, and also
  `git grep -lE 'cwd=(str\()?(lib\.)?(PLANE_ROOT|ROOT)\b|"--root", str\((lib\.)?(PLANE_ROOT|ROOT)\)' -- 'tests/test*.py'`
  (one file, the same), and lists in the map every module either finds.
- **The map today.** `"def _mapped"` and `"def affected"` in `ccp/suite.py`: the ids the map gives are added to what
  the pack reads from every changed path. No bound product sets `suite.affected_map` (read from each binding's
  product plane.json on this machine), so the narrowing changes no product's list today.
- **Ruled.** The map replaces only the pack's name rule. The pack's reader (`"def affected"` in
  `ccp/doclang/python.py`, called from `"def affected"` in `ccp/suite.py`) gains a keyword argument `named`, the
  changed paths whose names it matches tests by (default: all of `changed`, as today). `ccp/suite.py` passes every
  changed path as `changed` and, as `named`, those no glob matches. A changed test module still counts for itself and a
  changed module's importers are still found for every changed path, matched or not. A pack with no reader is
  unchanged (the map alone). `docs/delivery/plane.json` gains
  `"suite": {…, "affected_map": {"docs/delivery/plane.json": ["tests.test_self_hosting"]}}` (plus any module the two
  searches above add). The schema's `affected_map` description and the docs/cli row for `ccp suite affected` say the
  same. The test is `test_a_path_the_map_matches_is_not_matched_by_name` in `tests/test_suite_affected.py` (class
  `AffectedMap`): a fixture where `tests/test_names_conf.py` names `conf.json` and `pkg/a.py`, and `tests/test_imports_a.py`
  imports `pkg.a`; with the map `{"conf.json": ["tests.test_reads_conf"], "pkg/*": ["tests.test_reads_conf"], "tests/*": ["tests.test_reads_conf"]}`,
  a change to `conf.json` lists only `tests.test_reads_conf`; a change to `pkg/a.py` lists `tests.test_imports_a` and
  `tests.test_reads_conf`, not `tests.test_names_conf`; a change to `tests/test_names_conf.py` lists `tests.test_names_conf`
  and `tests.test_reads_conf`.
- **The cli row and the schema.** `docs/cli/02-delivery.md`'s `ccp suite affected` row says the map "adds the test ids of
  each glob a changed path matches"; `contracts/plane_config.schema.json`'s description says "`ccp suite affected` adds
  them to what the language pack reads". Both become: the map adds the tests of each path a glob matches, and the
  pack no longer matches tests by that path's name (§31.1: they describe this feature).

## Scope

- **In:** `ccp/suite.py` (`affected`, `_mapped`); `ccp/doclang/python.py` (`affected`'s `named`); `tests/test_suite_affected.py`; `docs/spec/02-delivery.md`
  (§14.7, the passage below); `docs/cli/02-delivery.md` (the `ccp suite affected` row);
  `contracts/plane_config.schema.json` (`suite.affected_map`'s description); `docs/delivery/plane.json`
  (`suite.affected_map`).
- **SPEC, signed before the claim (`sign_off: brief`):** one passage in `docs/spec/02-delivery.md`, §14.7.

    CURRENT (`docs/spec/02-delivery.md` at `bb102371`), §14.7, the bullet "A product's map":
    > - **A product's map.** plane.json `suite.affected_map` maps globs to test ids: each changed path is matched against every glob (`fnmatch.fnmatchcase` on the root-relative path, so `*` crosses `/`), and the ids of each match are added to what the pack reads; the list stays sorted, each id once.

    PROPOSED:
    > - **A product's map.** plane.json `suite.affected_map` maps globs to test ids: each changed path is matched against every glob (`fnmatch.fnmatchcase` on the root-relative path, so `*` crosses `/`), and the ids of each match are added to what the pack reads. The pack does not match tests by the name of a changed path that a glob matches; a changed test module still counts for itself and a changed module's importers are still found. The list stays sorted, each id once.

  No sentence is retired: the bullet gains one sentence, and its last clause becomes a sentence of its own.
- **Out:** the Python pack's import and name rules for paths no glob matches; the share rule for the language's command; the cli
  and config hub modules (still deferred in `docs/ROADMAP.md`); `verify.accept_cache.review`.

## dod_checks

- id: `cmd-01`
  story: As a plane developer editing plane.json, the affected run takes the tests that read it.
  setup: A checkout of the PR head (any seat), with a scratch `QUEUE_ROOT`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite affected --paths docs/delivery/plane.json 2>/dev/null`.
    2. Run `CCP_DEV=1 ./bin/ccp suite affected --paths docs/delivery/plane.json ccp/rules.py 2>/dev/null | grep -c test_rules`.
  expect: step 1 prints the map's ids for `docs/delivery/plane.json` (at least `tests.test_self_hosting`) and at most 5 lines; step 2 prints `1` (an unmapped path is still read by the pack).
  dry run (`bb102371`): step 1 printed 100 lines; step 2 printed `1`.
- id: `code-01`
  story: As a product owner, a mapped path is not matched by its name, while a changed test module and a module's importers still count.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_suite_affected.AffectedMap.test_a_path_the_map_matches_is_not_matched_by_name`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_suite_affected.AffectedMap.test_a_path_the_map_matches_is_not_matched_by_name --revert ccp/suite.py`.
    3. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_suite_affected`.
  expect: step 1 exits 0; step 2 prints the mutant `killed`; step 3 exits 0.
  dry run: n/a — the test is new; `--revert` needs the branch.
- id: `spec-01`
  story: As the operator, §14.7 says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0319`.
  expect: exit 0, the PROPOSED passage found.
  dry run: n/a — the passage lands with the build; the CURRENT bullet is found once in `docs/spec/02-delivery.md` at `bb102371` (whitespace-normalised).

## Implementation notes

## Verification notes
