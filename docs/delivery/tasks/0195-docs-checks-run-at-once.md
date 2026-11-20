---
task_id: 0195-docs-checks-run-at-once
title: The docs.workers constant runs every check command at once, as ADR-0043 D9 decided
status: pending
kind: feature
depends_on: ["0192-plane-json-constants-and-defaults"]
spec_refs: ["S21"]
rule_refs: []
review_point: R12
paths: ["ccp/config.py", "ccp/rules.py", "contracts/plane_config.schema.json", "docs/spec/03-quality.md", "tests/test_plane_json_constants.py", "tests/test_doc_rules.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0195-docs-checks-run-at-once

## Intent

ADR-0043 D9 (appendix, "`plane.json`, constants") makes `docs.workers` a constant: "as many as
there are checks". Task 0192 built it as a constant at the old default, 1, so a product that deletes
the key, as its upgrade step tells it to, runs its check commands one at a time. That is slower
than before for every product that set a higher value, and slower than the ADR decided. With this
task, the constant runs every check command at once, and a product that still sets a number keeps
it, with 0192's constant warning.

## Context (not checked)

- `ccp/rules.py` `run_checks` runs `docs.checks` and `architect.checks` with
  `workers = min(int((cfg.docs or {}).get("workers", 1)), len(checks))`
  (`git grep -n '"workers"' ccp/rules.py` at `6f90b9f`).
- `ccp/config.py` holds the old default in `DOCS_DEFAULTS` and registers it as the constant;
  `_docs` refuses any value that is not a positive integer; `constant_override` prints the constant
  with `repr` (`git grep -n 'workers\|out.value!r' ccp/config.py` at `6f90b9f`).
- `contracts/plane_config.schema.json` types `docs.workers` as an integer with the old default, and
  `tests/test_plane_config_defaults.py` asserts that schema defaults equal the code's
  (`git grep -n '"workers"' contracts/plane_config.schema.json` at `6f90b9f`).
- `tests/test_doc_rules.py` `ParallelChecks` pins a serial default and lists `None` as a refused
  value; `tests/test_plane_json_constants.py` pins the old value in its literal table and uses
  `docs.workers` as its example of a key set equal to its constant
  (`git grep -n workers tests/test_doc_rules.py tests/test_plane_json_constants.py` at `6f90b9f`).
- Each check runs in its own process group under its own timeout (SPEC §21.5), so running them
  together changes no result, only the wall time. A product whose checks race on shared setup (two
  checks creating the same virtualenv, for example) fixes that in its own scripts. It can keep a
  number in `docs.workers` meanwhile, with the constant warning.
- `docs/spec/01-model.md`'s key table lists `docs.workers` among the product check keys. That stays
  true and needs no change.
- This plane's own `docs/delivery/plane.json` sets a number equal to its check count. Task 0190
  (already claimed, so not edited here) keeps that key if it closes before this task, and the lead
  has told its runner so; whichever lands second deletes it. This task leaves the file alone.

## Scope

- **The constant is `null`, meaning as many workers as there are checks.**
  - `DOCS_DEFAULTS["workers"]` and the registered constant become `None`.
  - `_docs` accepts `null` or an integer >= 1, refusing anything else with "docs.workers must be null
    or an integer >= 1".
  - `run_checks` runs `len(checks)` at once when the value is `null`. A number set in `plane.json`
    still applies, capped at `len(checks)` as today.
- **The warning names the constant in words.** The constant's outcome gets an optional display
  text, and `docs.workers` sets it to "as many as there are checks". `constant_override` prints that
  text in place of `repr` when it is set, in both messages. An explicit `"workers": null` equals the
  constant, so it gets 0192's "set to that value: delete it" warning.
- **Schema:** `docs.workers` becomes `{"type": ["integer", "null"], "minimum": 1, "default":
  null}`, described as "Constant: as many as there are checks; a number still caps them, with a
  warning".
- **SPEC §21.5.** CURRENT, verbatim at `6f90b9f`: "`docs.workers` (default 1) is how many check
  commands (`docs.checks` and `architect.checks`) run at once, each under its own timeout; results
  are reported in declared order." PROPOSED: "All check commands (`docs.checks` and
  `architect.checks`) run at once, each under its own timeout; results are reported in declared
  order. A number in `docs.workers` still caps them, with the constant warning (§29.3)." This states
  ADR-0043 D9, which the operator accepted (§31.1).
- **`tests/test_doc_rules.py` `ParallelChecks`**, the one home for these tests:
  - the default test becomes "the default runs every check at once". Three checks each `touch` a
    marker in a directory of the test's own, empty at the start of each run, then wait up to 5 s for
    all three markers. The run passes only if they ran together.
  - with `docs.workers: 1`, the same three checks fail, which proves they ran one after another, and
    the load warns once, naming the key and "as many as there are checks";
  - `None` leaves the refused-values list;
  - failures come back in declared order either way (an existing test, kept).
- **`tests/test_plane_json_constants.py`:**
  - the literal table pins `None`;
  - the `(600, 1, 14)` tuple follows;
  - the "set to that value: delete it" test and the `TheUpgradeStatus` "set to the constant, so not
    listed" test take another constant key as their example, such as `architect.max_days: 14`.

Out of scope: any product's own check scripts, `architect.checks`' own settings, and this plane's
`plane.json`, which task 0190 handles.

## dod_checks

The barrier check used below is a `docs.checks` entry `{"id": "<x>", "cmd": "touch $D/<x>; for n in
$(seq 50); do [ -e $D/a ] && [ -e $D/b ] && [ -e $D/c ] && exit 0; sleep 0.1; done; exit 1"}`, for
`<x>` in `a`, `b` and `c`, with `$D` replaced by the absolute path of an empty temp directory
written into each cmd. It passes only when all three run at once.

- id: `dw-01`
  story: As a product that took 0192's upgrade step, my check commands run at once.
  setup: a temp product root with `docs/delivery/plane.json` setting a `project_id`, `language: none`
    and the three barrier checks, no `docs.workers` key, and an empty `docs/delivery/tasks/`, in a
    git repo. Run `ccp --root <temp> tasks index` once, so `docs check` finds its index. (Dry run at
    `6f90b9f`: with `workers: 3` this setup prints `docs: clean`; with `workers: 1`, `docs check a`
    and `b` exit 1.)
  steps:
    1. `ccp --root <temp> docs check; echo rc=$?`.
  expect: `rc=0`, and no warning names `docs.workers`.

- id: `dw-02`
  story: As a product that still sets a number, it keeps applying.
  setup: the same root, its marker directory emptied first (`rm -f <dir>/*`), with `"workers": 1`
    added to `docs`.
  steps:
    1. `ccp --root <temp> docs check; echo rc=$?`.
  expect: a non-zero `rc`, with `docs check a` reported as exited 1, and one warning naming
    `docs.workers` and "as many as there are checks".

- id: `dw-03`
  story: As the SPEC reader, §21.5 states the constant.
  setup: the PR head.
  steps:
    1. `grep -n 'default 1' docs/spec/03-quality.md`.
    2. `grep -n 'run at once' docs/spec/03-quality.md`.
  expect: step 1 shows no `docs.workers` line; step 2 shows the new §21.5 sentence.

- id: `dw-04`
  story: As the plane, the suite passes.
  setup: the PR head.
  steps:
    1. `scripts/gate.sh`.
  expect: exit 0.

## Refs

- ADR-0043 D9 and its appendix (`docs.workers`: "as many as there are checks").
- Task 0192 (the constants mechanism and warning); task 0190 (the plane's own key).
- SPEC §21.5, §29.3.
