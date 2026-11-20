---
task_id: 0195-docs-checks-run-at-once
title: The docs.workers constant runs every check command at once, as ADR-0043 D9 decided
status: pending
kind: feature
depends_on: ["0192-plane-json-constants-and-defaults"]
spec_refs: ["S21"]
rule_refs: []
review_point: R12
paths: ["ccp/config.py", "ccp/rules.py", "docs/spec/03-quality.md", "tests/test_plane_json_constants.py", "tests/test_docs_checks_at_once.py"]
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

- `ccp/rules.py` `run_checks` runs `docs.checks` and `architect.checks`. Today it computes
  `min(int(docs.workers or 1), len(checks))` workers.
- `ccp/config.py` `DOCS_DEFAULTS` holds the old default, and `tests/test_plane_json_constants.py`
  pins it (`grep -n workers ccp/config.py tests/test_plane_json_constants.py` at `6f90b9f`). 0192
  lists `docs.workers` as a constant.
- Each check runs in its own process group under its own timeout (SPEC §21.5), so running them
  together changes no result, only the wall time. A product whose checks race on shared setup (two
  checks creating the same virtualenv, for example) fixes that in its own scripts. It can keep a
  number in `docs.workers` meanwhile, with the constant warning.

## Scope

- The constant is `null`, meaning as many workers as there are checks. `DOCS_DEFAULTS["workers"]`
  becomes `None`. `run_checks` runs `len(checks)` at once when the value is `null`. A number set
  in `plane.json` still applies, capped at `len(checks)` as today. The constant warning (0192)
  names the constant as "as many as there are checks", not "None".
- The schema's `docs.workers` description, if the schema has one, follows.
- SPEC §21.5: "`docs.workers` (default 1) is how many check commands ... run at once" becomes "All
  check commands (`docs.checks` and `architect.checks`) run at once, each under its own timeout;
  results are reported in declared order. A number in `docs.workers` still caps them, with the
  constant warning (§29.3)." This states ADR-0043 D9, which the operator accepted (§31.1).
- `tests/test_plane_json_constants.py` pins the new constant.
- New `tests/test_docs_checks_at_once.py`:
  - with no `docs.workers`, three checks that each sleep briefly and record their start time all
    start before any finishes;
  - with `docs.workers: 1`, they run one after another, and the load warns once about the key;
  - failures come back in declared order either way.

  No test sleeps longer than 0.3 s per check.

Out of scope: any product's own check scripts, and `architect.checks`' own settings.

## dod_checks

- id: `dw-01`
  story: As a product that took 0192's upgrade step, my check commands run at once.
  setup: a temp product root with `language` set, three `docs.checks` entries that each run `sleep
    0.3`, and no `docs.workers` key.
  steps:
    1. Time `ccp --root <temp> docs check`.
  expect: it exits 0 in well under 0.9 s of check time (under 0.7 s), and prints no warning about
    `docs.workers`.

- id: `dw-02`
  story: As a product that still sets a number, it keeps applying.
  setup: the same root with `"docs": {"workers": 1, "checks": [...]}`.
  steps:
    1. Time `ccp --root <temp> docs check`.
  expect: it takes at least 0.9 s and prints one warning naming `docs.workers` and the constant "as
    many as there are checks".

- id: `dw-03`
  story: As the SPEC reader, §21.5 states the constant.
  setup: the PR head.
  steps:
    1. `grep -n 'docs.workers' docs/spec/03-quality.md`.
  expect: no line says "default 1"; the §21.5 line says all check commands run at once.

- id: `dw-04`
  story: As the plane, the suite passes.
  setup: the PR head.
  steps:
    1. `scripts/gate.sh`.
  expect: exit 0.

## Refs

- ADR-0043 D9 and its appendix (`docs.workers`: "as many as there are checks").
- Task 0192 (the constants mechanism and warning).
- SPEC §21.5, §29.3.
