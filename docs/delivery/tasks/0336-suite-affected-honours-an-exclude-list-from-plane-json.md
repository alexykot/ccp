---
task_id: 0336-suite-affected-honours-an-exclude-list-from-plane-json
title: ccp suite affected and suite run --affected leave out the paths plane.json suite.affected_exclude names, so a test module the product's lanes do not run is never listed, run or counted in the suite
status: done
kind: feature
depends_on: []
spec_refs: ["S14"]
review_point: R35
paths: ["ccp/suite.py", "ccp/config.py", "contracts/plane_config.schema.json", "tests/test_suite_affected.py", "docs/spec/02-delivery.md", "README.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver"]
adopt: "plane.json suite.affected_exclude"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0336-suite-affected-honours-an-exclude-list-from-plane-json

## Intent

A product whose tree holds test modules its own lanes do not run (a retired test tree, a tool's self-tests) lists
them in plane.json `suite.affected_exclude`, and `ccp suite affected` and `ccp suite run --affected` then leave them
out: such a module is never listed as touched, never run, and never counted in the suite, so it never pushes the
selection past the full-lane share on its own account. Such a product can use the pre-gate's
`ccp suite run --affected` again instead of having it fail on modules the product never runs.

## Context (not checked)

An accepted plane proposal, generic as stated here. A managed product's tree holds `test*.py` modules its test
runner refuses: a deprecated legacy tree and a tool's own self-tests. The Python pack lists every `test*.py` module
git tracks or does not ignore, so a change that those modules import lists them, and `ccp suite run --affected`
fails before it runs a test the product cares about. `suite.affected_map` only adds ids, so the product has no
workaround: it cannot use `--affected`, which the Fail fast pre-gate (§13.5) runs on every task. The lead accepted the
design on 2026-11-24 and gives this task priority (the preference is the lead's to set with `ccp tasks prefer`; it is
not written here).

Measured at `41cabf26`:

- `"def affected(cfg: Config, since"` (`ccp/suite.py`) passes `_tracked_files(cfg.root)` to the pack's reader, and
  `"def affected_modules"` passes it to `pack.suite_size`; nothing filters it. `"def _test_files"`
  (`ccp/doclang/python.py`) takes every `test*.py` file among those as a module.
- `contracts/plane_config.schema.json` `suite` has `additionalProperties: false` and the properties `exclusive_lanes`,
  `lanes`, `count_re`, `roles`, `affected_map`, `log_keep_days`, `summary`
  (`python3 -c 'import json; print(list(json.load(open("contracts/plane_config.schema.json"))["properties"]["suite"]["properties"]))'`).
  An unknown `suite.affected_exclude` loads with the warning `unknown key(s) suite.affected_exclude ignored` and is
  read by nothing.
- The scratch product of cmd-01 (a changed `src/core.py` imported by `tests/test_core.py`,
  `legacy/tests/test_x.py` and `ops/test_tool.py`, plus four filler modules) lists all three modules and prints
  `ccp suite affected: 3 of 7 test modules: skip the pre-gate and run the full lane: ccp suite run --lane gate`.

**Ruled.**

- **The key.** plane.json `suite.affected_exclude`: a list of globs, default `[]`. Each is matched against a
  root-relative path with `fnmatch.fnmatchcase`, so `*` crosses `/`: the same matching `suite.affected_map` uses for
  its keys (`"def _mapped"`). Path globs, not dotted module ids: the pack walks file paths, the map's keys are path
  globs already, a path glob is language-neutral (a pack for another language names its modules differently), and
  one glob can name a whole tree (`legacy/*`). A value that is not a list of non-blank strings is refused when
  plane.json is read, as `suite.affected_map` is (`"suite.affected_map must map"` in `ccp/config.py`): the message is
  `suite.affected_exclude must be a list of path globs (§14.7)`, and the command exits 2. The schema gains the
  property, `"type": "array"`, items non-empty strings, `"default": []`, with a description that cites §14.7.
- **Where it applies.** `ccp/suite.py` drops every path a glob matches from the files the pack's reader and its suite
  counter walk (the list `_tracked_files` gives, at both its callers in `"def affected"` and
  `"def affected_modules"`): one filter, before the pack reads anything, so no pack changes. So an excluded
  `test*.py` file is no test module: never listed, never run by `--affected`, never counted in `suite_size`, and the
  full-lane share is of the modules left. The change itself is not filtered: a changed path a glob matches still
  counts as changed, and a kept module that imports it is still listed. An excluded package `__init__.py` is not
  walked either, so a kept test is not reached through it (the one-level package rule of §14.7 needs the walked
  `__init__.py`); this follows from the one filter and is accepted.
- **The map.** The ids `suite.affected_map` gives are added as written, never filtered: they are test ids, not
  paths, and the map is the product's own explicit word. A product that maps a path to an excluded module's id has
  contradicted itself; the plane does not check it.
- **Tests.** `tests/test_suite_affected.py` gains class `Exclude(Scratch, unittest.TestCase)` with
  `test_an_excluded_test_module_is_never_listed`, `test_excluded_modules_leave_the_suite_count` (a change that
  touches one kept module and excluded ones gets the part-lane line, not the full-lane one),
  `test_a_changed_excluded_path_is_still_part_of_the_change` and `test_the_key_must_be_a_list_of_path_globs`.
- **README.** The adoption checklist (`#### Adoption checklist`) gains a `suite.affected_exclude` row after
  `suite.count_re`'s: what it is for (paths whose test modules the lanes do not run, which `ccp suite affected` and
  `ccp suite run --affected` then leave out, §14.7), and when a product needs it (its tree holds `test*.py` modules
  its lanes do not run). `docs/cli/02-delivery.md`'s `ccp suite affected` row gives call syntax only and is
  unchanged.
- No other test expectation changes.

## Scope

- **In:** `ccp/suite.py` (the filter), `ccp/config.py` (the default and the validation),
  `contracts/plane_config.schema.json` (`suite.affected_exclude`), `tests/test_suite_affected.py` (class `Exclude`),
  `README.md` (one adoption-checklist row); the SPEC, describing this task's own feature (§31.1): one clause in the Python
  bullet and one new bullet, which only describe the key and what `ccp suite affected` does with it; no other §14.7
  sentence changes.

  CURRENT (`docs/spec/02-delivery.md` at `41cabf26`), §14.7, the Python bullet's first sentence (the rest of the bullet
  unchanged):
  > - **Python.** A test module is a `test*.py` file git tracks or does not ignore, named by its dotted
  >   path from the root (`tests/test_a.py` is `tests.test_a`).

  PROPOSED:
  > - **Python.** A test module is a `test*.py` file git tracks or does not ignore and no `suite.affected_exclude` glob matches (below), named by its dotted path from the root (`tests/test_a.py` is `tests.test_a`).

  CURRENT (`docs/spec/02-delivery.md` at `41cabf26`), §14.7, the bullet the new one follows, unchanged (the new
  bullet goes after it and retires no sentence):
  > - **A product's map.** plane.json `suite.affected_map` maps globs to test ids: each changed path is
  >   matched against every glob (`fnmatch.fnmatchcase` on the root-relative path, so `*` crosses `/`),
  >   and the ids of each match are added to what the pack reads. The pack does not match tests by the
  >   name of a changed path that a glob matches; a changed test module still counts for itself and a
  >   changed module's importers are still found. The list stays sorted, each id once.

  PROPOSED:
  > - **What the lanes do not run.** plane.json `suite.affected_exclude` lists globs of root-relative paths the product's lanes do not run (a retired test tree, a tool's own self-tests), matched as `suite.affected_map`'s are. The pack walks the product's files without the paths a glob matches: such a file is never a test module, so it is never listed or run as touched and never counted in the suite, and the share past which the line names the full lane is of the modules left. A changed path a glob matches is still part of the change, and the ids `suite.affected_map` gives are added as written. Default: none.
- **Out:** a per-lane exclude; filtering `suite.affected_map`'s ids; any change to a language pack, to the full or
  gate lane's own command, or to `docs/cli/02-delivery.md`; checking that a map id names an excluded module.

## dod_checks

- id: `cmd-01`
  story: As a product's worker, the tests my lanes do not run are never listed as touched, and they leave the suite count.
  setup: A checkout of the PR head (any seat); the step builds its scratch product.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && mkdir -p "$P/src" "$P/tests" "$P/legacy/tests" "$P/ops" && printf 'X = 1\n' > "$P/src/core.py" && printf 'import unittest\nfrom src import core\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.assertEqual(core.X, 1)\n' > "$P/tests/test_core.py" && for n in a b c d; do printf 'import unittest\n' > "$P/tests/test_$n.py"; done && for f in legacy/tests/test_x.py ops/test_tool.py; do printf 'from src import core\nraise SystemExit("the lanes do not run this")\n' > "$P/$f"; done && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["language"] = "python"; c["suite"] = {"lanes": {"gate": ["python3", "-m", "unittest"]}}; json.dump(c, open(p, "w"))' "$P" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" suite affected --paths src/core.py 2>/dev/null | grep -c . && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["suite"]["affected_exclude"] = ["legacy/*", "ops/test_tool.py"]; json.dump(c, open(p, "w"))' "$P" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" suite affected --paths src/core.py 2>&1 && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" suite affected --paths src/core.py tests/test_a.py 2>&1 | tail -1`.
  expect: exactly four lines, in this order: `3` (without the key, the three modules that import `src/core.py`), `tests.test_core`, `ccp suite affected: run them with: ccp suite run --lane part -- python3 -m unittest tests.test_core` (1 of the 5 kept modules), and, for the change to `src/core.py` and `tests/test_a.py`, `ccp suite affected: 2 of 5 test modules: skip the pre-gate and run the full lane: ccp suite run --lane gate` (the two excluded modules neither listed nor counted; a build that counts them prints `2 of 7`).
  dry run (`41cabf26`): printed `3`, then the warning `unknown key(s) suite.affected_exclude ignored`, `legacy.tests.test_x`, `ops.test_tool`, `tests.test_core`, `ccp suite affected: 3 of 7 test modules: skip the pre-gate and run the full lane: ccp suite run --lane gate`, and `ccp suite affected: 4 of 7 test modules: skip the pre-gate and run the full lane: ccp suite run --lane gate`, exit 0.
- id: `cmd-02`
  story: As a product's worker, the pre-gate's suite run --affected runs the kept module alone and passes, not the modules my lanes refuse.
  setup: A checkout of the PR head (any seat); the step builds its scratch product, commits it, changes `src/core.py` and runs from the product's root (a suite run runs its command in the current directory).
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && mkdir -p "$P/src" "$P/tests" "$P/legacy/tests" "$P/ops" && printf 'X = 1\n' > "$P/src/core.py" && printf 'import unittest\nfrom src import core\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.assertEqual(core.X, 1)\n' > "$P/tests/test_core.py" && for n in a b c d; do printf 'import unittest\n' > "$P/tests/test_$n.py"; done && for f in legacy/tests/test_x.py ops/test_tool.py; do printf 'from src import core\nraise SystemExit("the lanes do not run this")\n' > "$P/$f"; done && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["language"] = "python"; c["suite"] = {"lanes": {"gate": ["python3", "-m", "unittest"]}, "affected_exclude": ["legacy/*", "ops/test_tool.py"]}; json.dump(c, open(p, "w"))' "$P" && git -C "$P" add -A && git -C "$P" -c user.name=t -c user.email=t@example.invalid commit -qm fixture && printf 'X = 1\nY = 2\n' > "$P/src/core.py" && C="$PWD/bin/ccp" && cd "$P" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 "$C" --root "$P" suite run --affected 2>&1 | grep -E '^ccp suite run --affected: |: (passed|FAILED), exit'; echo "exit ${PIPESTATUS[0]}"`.
  expect: the first line is `ccp suite run --affected: 1 test module(s): running ccp suite run --lane part -- python3 -m unittest tests.test_core`; the run's summary line says `passed, exit 0`; the last line is `exit 0`.
  dry run (`41cabf26`): printed `ccp suite run --affected: 3 test module(s): running ccp suite run --lane gate, the full lane (3 of 7 test modules)`, the summary line `FAILED, exit 5, lane gate`, and `exit 5`.
- id: `cmd-03`
  story: As a product's lead, a malformed exclude list is refused when plane.json is read, not silently ignored.
  setup: A checkout of the PR head (any seat); the step builds its scratch product.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["language"] = "python"; c["suite"] = {"lanes": {"gate": ["python3", "-m", "unittest"]}, "affected_exclude": "legacy/*"}; json.dump(c, open(p, "w"))' "$P" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" suite affected --paths README.md 2>&1 | grep -c 'suite.affected_exclude must be a list of path globs'; echo "exit ${PIPESTATUS[0]}"`.
  expect: prints `1` then `exit 2`.
  dry run (`41cabf26`): printed `0` then `exit 0` (the key ignored with a warning).
- id: `code-01`
  story: As a plane developer, the tests hold the exclude list's rules.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_suite_affected.Exclude.test_an_excluded_test_module_is_never_listed tests.test_suite_affected.Exclude.test_excluded_modules_leave_the_suite_count tests.test_suite_affected.Exclude.test_a_changed_excluded_path_is_still_part_of_the_change tests.test_suite_affected.Exclude.test_the_key_must_be_a_list_of_path_globs`.
  expect: exit 0.
  dry run (`41cabf26`): exit 1 (`AttributeError: module 'tests.test_suite_affected' has no attribute 'Exclude'`).
- id: `doc-01`
  story: As a product's lead adopting the plane, the contract and the adoption checklist name the key.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `python3 -c 'import json; print(json.load(open("contracts/plane_config.schema.json"))["properties"]["suite"]["properties"]["affected_exclude"]["default"])'`.
    2. Run `grep -c 'suite\.affected_exclude' README.md`.
  expect: step 1 prints `[]`; step 2 prints `1`.
  dry run (`41cabf26`): step 1 exit 1 (`KeyError: 'affected_exclude'`); step 2 printed `0`, exit 1.
- id: `spec-01`
  story: As the operator, §14.7 describes the key, in the Python bullet and its own, and what the affected selection does with it.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0336`.
  expect: exit 0, both PROPOSED passages found.
  dry run (`41cabf26`, with this brief): exit 1, both PROPOSED passages `not found in the SPEC`.

## Implementation notes

- `ccp/config.py`: `SUITE_DEFAULTS["affected_exclude"] = []`; a value that is not a list of non-blank strings
  (`_str_list`, as the map's ids are checked) fails the load with `suite.affected_exclude must be a list of path
  globs (§14.7)`.
- `ccp/suite.py`: `_kept(files, globs)` (plain values) drops every path a glob matches with `fnmatch.fnmatchcase`;
  `_walked_files(cfg)` applies it to `_tracked_files(cfg.root)`, and both callers (`affected`'s reader call and
  `affected_modules`' `suite_size` call) take it in place of `_tracked_files`. `changed` and `named` are not
  filtered, nor the map's ids.
- Schema: `suite.affected_exclude`, array of `minLength: 1` strings, default `[]` (the schema says what `minLength`
  can; the blank-string refusal is the loader's, as for `affected_map`).
- Tests: class `Exclude` in `tests/test_suite_affected.py`, the four tests the task names.

## Verification notes
- 2026-11-25 — verifier, PR #407 head `c4d664f` (squash `f9467d5`): APPROVE. Passed: cmd-01, cmd-02, cmd-03, code-01, doc-01, spec-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0336-suite-affected-honours-an-exclude-list-from-plane-json.json.

