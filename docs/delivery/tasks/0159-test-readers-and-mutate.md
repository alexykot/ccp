---
task_id: 0159-test-readers-and-mutate
title: A product maps its own paths to tests for ccp suite affected, ccp mutate tells a mutant that does not build from one a test killed, and a shallow ver works with LFS and --revert
status: done
kind: feature
depends_on: []
spec_refs: ["S14", "S20", "S12"]
review_point: R10
paths: ["ccp/suite.py", "ccp/mutate.py", "ccp/wt.py", "ccp/config.py", "contracts/plane_config.schema.json", "contracts/worktree.schema.json", "scripts/observability/lib.py", "docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/cli/02-delivery.md", "docs/cli/03-quality.md", "tests/test_suite_affected.py", "tests/test_mutate.py", "tests/test_wt.py"]
adopt: "plane.json suite.affected_map: a product whose language has no test reader (or whose tests are scripts) maps path globs to the test ids its part lane runs; plane.json mutate.unbuilt_re: a pattern its test command prints when the code does not build or import"
sign_off: brief
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0159-test-readers-and-mutate
## Intent

A product in any language, or one whose tests are scripts, gets the tests a change touches from
`ccp suite affected` through a path-to-test map it keeps in plane.json, so its implementers run the
part lane instead of the whole gate. A mutant that stops the code building or importing is recorded
as `unbuilt`, not as a test that killed it. And a verifier whose only option is a shallow `ver`
worktree gets one that checks out a git-LFS repo with its files' content and lets `ccp mutate --revert`
find the merge base.

## Context (not checked)

- `AFFECTED_READERS` in `ccp/suite.py` holds only `python`; any other `package_docs.language` exits 2
  ("has no test reader"), and the only other language a product may set is `none` (`PACKS` in
  `ccp/doclang/__init__.py` at `85d388b`: `python` and `none`). A Go reader would need a Go language
  pack and the Go toolchain in the fenced suite; a per-product map covers Go packages and script
  tests alike with no toolchain, so this task adds the map and no Go reader.
- `ccp mutate` records a mutant `killed` whenever the test exits non-zero (the `outcome` line
  in `_run`, `ccp/mutate.py`), so a mutant that breaks the build or an
  import is a recorded kill that proves nothing. Seen in an adopting product with a compiled language.
  Which output means "did not build" is the product's (`go test` prints `[build failed]`; Python
  unittest prints `Failed to import test module`), so it is a plane.json pattern, off by default.
- `--shallow` clones with `git init`, `git fetch --depth 1 <main checkout> <sha>` and
  `git checkout --detach FETCH_HEAD` (`_clone_shallow` in `ccp/wt.py`). With git-lfs's filter
  configured, that checkout runs the smudge filter, which has no remote to fetch from and fails; with
  smudge skipped the LFS files stay pointers. Seen in an adopting product: tests reading LFS images
  failed until objects were copied by hand.
- `ccp mutate --revert` takes `wt.merge_base(cfg, q, head)`, which fetches `origin` and runs
  `git merge-base` in `main_checkout(cfg)`; in a shallow clone that is the clone itself, with no
  `origin` and no history, so it exits 3. Seen in the same product: the integration branch was
  fetched by hand.
- §14.7 says a pack with no test reader exits 2, and §20.6 says a mutant is `killed` whenever the test
  exits non-zero and gives the exit codes: these change, `sign_off: brief`, the passages below. The
  §14.7 map bullet and the §12.1 shallow sentence describe this task's own features (§31.1).

## Scope

- **In:**
  - `ccp/config.py` and `contracts/plane_config.schema.json`: `suite.affected_map` (default `{}`), an
    object from a glob to a list of test ids; `mutate.unbuilt_re` (default null), a regular expression
    or a list of them. A value of another shape fails the load naming the key.
  - `ccp/suite.py` `affected`: each changed path is matched against every glob of `suite.affected_map`
    (`fnmatch.fnmatchcase` on the root-relative path, so `*` crosses `/`), and the ids of each match are
    added to the language reader's output; the result is sorted and has no duplicates. A language with
    no reader and a non-empty map uses the map alone; with an empty map it exits 2 as today, the
    message also naming `suite.affected_map`.
  - §31.1: `docs/spec/02-delivery.md` §14.7, a bullet after **Python.**: **A product's map.** plane.json
    `suite.affected_map` maps globs to test ids, matched as above, added to what the pack reads.
  - `docs/spec/02-delivery.md` §14.7. CURRENT (at `85d388b`): "A pack with no test reader (`none`) exits 2." PROPOSED:
    > A pack with no test reader (`none`) exits 2 unless plane.json `suite.affected_map` is set, which then reads the tests alone.
  - `ccp/mutate.py`: with `mutate.unbuilt_re` set, a mutant whose test exits non-zero with an output
    line matching it (`re.search`, each line of that run's output) is recorded `unbuilt`, not `killed`.
    The result and the `run`/`recorded` event gain `unbuilt` (the count); `survived` stays the count
    exiting 0. The unmutated run is not read for it (it must pass, as today). Exit 1 when any mutant
    survived or is unbuilt. `scripts/observability/lib.py`: `unbuilt` joins the `run`/`recorded` fields.
  - `docs/spec/03-quality.md` §20.6, two passages:
    1. CURRENT (at `85d388b`): "the mutant is `killed` when it exits non-zero and `survived` when it exits 0." PROPOSED:
       > the mutant is `killed` when it exits non-zero and `survived` when it exits 0, except that one whose run exits non-zero with an output line matching plane.json `mutate.unbuilt_re` (a regular expression or a list of them; null, the default, matches nothing) is `unbuilt`: the code did not build or import, which proves nothing about the test.
    2. CURRENT (at `85d388b`): "- **Exit codes:** 0 when every mutant was killed, 1 when one survived." PROPOSED:
       > - **Exit codes:** 0 when every mutant was killed, 1 when one survived or was `unbuilt`.
  - `ccp/wt.py` `_clone_shallow`: the checkout runs with `GIT_LFS_SKIP_SMUDGE=1`. Then, when git-lfs
    is on PATH and the clone's tree has LFS files (`git lfs ls-files` lists any), the clone's
    `lfs.storage` is set to the main checkout's LFS store (`git lfs env`'s `LocalMediaDir` there, or
    `<git dir>/lfs`) and `git lfs checkout` fills each file whose object that store holds. A file whose
    object it lacks stays a pointer and `create` warns, naming the count and that `git lfs fetch` in the
    main checkout fills the store.
  - `ccp/wt.py` `create --shallow`: the merge base of `--sha` and the integration branch on origin, taken in the
    main checkout as `merge_base` takes it, is fetched into the clone at depth 1 and recorded as
    `merge_base` in the worktree record (`contracts/worktree.schema.json`). No merge base is a warning,
    and none is recorded. `ccp mutate --revert` in a shallow worktree takes the record's `merge_base`
    and refuses (exit 2) when there is none, saying the shallow worktree has no merge base.
  - §31.1: `docs/spec/02-delivery.md` §12.1, after the `--shallow` bullet's first sentence, one
    sentence each: the LFS checkout from the main checkout's store, and the recorded merge base that
    `ccp mutate --revert` uses there.
  - `docs/cli/02-delivery.md` (`ccp suite affected`) and `docs/cli/03-quality.md` (`ccp mutate`): one
    clause each.
  - Tests: `tests/test_suite_affected.py`, `tests/test_mutate.py`, `tests/test_wt.py` for the checks
    below; the LFS test is skipped where git-lfs is not on PATH.
- **Out:**
  - A Go language pack or any reader beyond Python's.
  - Fetching LFS objects from a remote; changing a full (non-shallow) worktree.

## dod_checks

- id: `aff-01`
  story: As an implementer in a product with no test reader, I get the tests my change touches from the product's map.
  setup: a fenced scratch product with `package_docs.language` `none` and `suite.affected_map` `{"internal/store/*": ["./internal/store/..."], "ops/*.sh": ["ops/test_ops.sh"]}`.
  steps:
    1. Run `ccp suite affected --paths internal/store/db.go ops/deploy.sh docs/readme.md`.
    2. Remove `suite.affected_map` and run step 1 again.
  expect: step 1 exits 0 printing exactly `./internal/store/...` and `ops/test_ops.sh`, sorted; step 2 exits 2 and stderr names `suite.affected_map`.
  dry run (`85d388b`): with language `none` and no map, `ccp suite affected` exits 2, "has no test reader" (`tests/test_suite_affected.py`).
- id: `aff-02`
  story: As an implementer in a Python product, the map adds to what the reader finds.
  setup: a fenced scratch product with language `python`, a test module importing `pkg.a`, and `suite.affected_map` `{"scripts/*.sh": ["tests.test_scripts"]}`.
  steps:
    1. Run `ccp suite affected --paths pkg/a.py scripts/x.sh`.
  expect: exit 0; exactly the importing test module and `tests.test_scripts`, sorted, each once.
  dry run: n/a.
- id: `mut-01`
  story: As a verifier, a mutant that stops the code importing is not counted as killed.
  setup: a fenced scratch product with `mutate.command` `python3 -m unittest {test}` and `mutate.unbuilt_re` `Failed to import test module`, a module and a test of it that passes, and an open implement run in its recorded `impl` worktree.
  steps:
    1. Run `ccp mutate --run <run_id> --test <test> --mutant '<module>:<a line>=><a syntax error>' --mutant '<module>:<a value>=><a wrong value>'`.
  expect: exit 1; the run's `mutation` rows are `unbuilt` for mutant 1 and `killed` for mutant 2; the result has `killed: 1`, `unbuilt: 1`, `survived: 0`; the module is byte for byte as before.
  dry run: n/a.
- id: `wt-01`
  story: As a verifier with only a shallow worktree, an LFS repo checks out with its files' content.
  setup: a fenced scratch product, git-lfs on PATH and its filter configured in the test's own git global config, the main checkout tracking `data/blob.bin` through LFS with its object in the main store.
  steps:
    1. Run `ccp wt create --kind ver --task <task> --sha <head> --shallow`.
  expect: exit 0; the worktree's `data/blob.bin` holds the committed content, not an LFS pointer (no line `version https://git-lfs.github.com/spec/v1`).
  dry run: n/a.
- id: `wt-02`
  story: As a verifier in a shallow worktree, `--revert` finds the merge base.
  setup: a fenced scratch product whose task branch changes one line of a module that a passing test checks, pushed to its origin, and an open verify run.
  steps:
    1. Run `ccp wt create --kind ver --task <task> --sha <branch head> --shallow`.
    2. In it, run `ccp mutate --run <run_id> --test <test> --revert <module>`.
  expect: step 1's record has `merge_base`, the integration tip the branch started from; step 2 exits 0 with the mutant `killed` and its result's `merge_base` equal to it.
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

- 2026-11-18 (implementer): `suite.affected_map` and `mutate.unbuilt_re` are new keys of `SUITE_DEFAULTS` and
  `MUTATE_DEFAULTS` (`ccp/config.py`), checked at load with a message naming the key; a map value must be a
  non-empty list of non-blank ids. `affected` (`ccp/suite.py`) unions the reader's modules with `_mapped`, sorted.
- `ccp mutate` reads only the mutant run's own output for `unbuilt_re`: `_test` notes the log offset after its
  header line, and `_says_unbuilt` reads from there. `unbuilt` joins the result, the `run`/`recorded` event and
  `REQUIRED_PAYLOAD`; the exit code is unchanged in form (1 unless every mutant was killed).
- The `mut-01` premise does not hold for a syntax error: `python3 -m unittest <dotted id>` prints `Failed to
  import test module` only for an ImportError (its loader catches nothing else; a SyntaxError ends in a
  traceback, `SyntaxError: ...`). The test for it uses a mutant that breaks the import (renames the function
  the test imports); a second test shows a list of patterns (`^SyntaxError: ` added) marking a syntax error
  `unbuilt`. Flagged to the runner.
- `--shallow`: the checkout runs with `GIT_LFS_SKIP_SMUDGE=1`; with git-lfs on PATH and LFS files listed, the
  clone's `lfs.storage` is the directory that holds `git lfs env`'s LocalMediaDir in the main checkout (the
  store, whose `objects/` LocalMediaDir is; LocalMediaDir itself would put the objects one level too deep),
  else `<git common dir>/lfs`, then `git lfs checkout`. A file still a pointer (`git lfs ls-files` marks it
  `-`) is counted in the warning. `create` takes the merge base with `wt.merge_base` (which fetches origin
  again), fetches it into the clone at depth 1 and records `merge_base`; no merge base, or a fetch that fails,
  is a warning in the result's `warnings` (printed on stderr by `ccp wt`), and nothing is recorded.

## Verification notes
- 2026-11-18 — verifier, PR #177 head `999f546` (squash `d6c1f75`): APPROVE. Passed: aff-01, aff-02, mut-01, wt-01, wt-02, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp suite run --lane part -- python3 -m unittest tests.test_suite_affected tests.test_mutate tests.test_wt` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0159-test-readers-and-mutate.json.

