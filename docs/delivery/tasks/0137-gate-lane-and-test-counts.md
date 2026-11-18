---
task_id: 0137-gate-lane-and-test-counts
title: ccp init --gate keeps a shell line whole as one stage, and suite.count_re reads any runner's summary lines
status: done
kind: feature
depends_on: []
spec_refs: ["S4", "S14"]
review_point: R9
paths: ["ccp/init.py", "ccp/suite.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "README.md", "tests/test_init.py", "tests/test_suite.py", "tests/test_sandbox.py"]
adopt: "plane.json suite.count_re, a pattern or a list of patterns matching the product's test runners' summary lines, when they are not Python unittest's"
created: 2026-11-17
updated: 2026-11-18
---

# Task: 0137-gate-lane-and-test-counts
## Intent

A product adopted with a gate that chains steps or changes directory gets a gate lane that runs
exactly that shell line, and a product whose tests run under any runner (go test, shell scripts, a mix)
gets its test count recorded on every suite run.

## Context (not checked)

- `ccp init --gate` stores `shlex.split(GATE)` as an argv lane (`"def plane_json_text"` in
  `ccp/init.py`). A shell line loses its meaning: `--gate "cd sub && make check"` is stored as the argv
  `cd`, `sub`, `&&`, `make`, `check`. Probe (`ccp sandbox create S -- --gate "cd . && python3 -c pass"`,
  then `ccp suite run --lane gate` at `921507e`): the lane is that argv, and the run **passes** on macOS,
  where `/usr/bin/cd` exists and succeeds without running anything after it; where no `cd` executable
  exists it fails on its first run. Init succeeds and reports nothing either way.
- A staged lane's `cmd` is a shell string run by `/bin/sh -c` (§14.2). One stage named `gate` holding
  the line keeps it whole with no schema change. A staged gate also gets the plane's own `plane-docs`
  stage (`ccp docs check`, §14.2); the same probe with the lane rewritten by hand to
  one `gate` stage ran both stages and passed on the fresh sandbox (`ccp suite run --lane gate` at
  `921507e`: `stages: gate passed, plane-docs passed`).
- Ruling: every `--gate` is stored as one stage, whatever it holds, so init has one shape, not two
  chosen by guessing whether a line needs a shell. A `--gate` that `shlex` cannot split (an unclosed
  quote) is still refused, writing nothing, as today.
- Counts: without a result file, a run's test count is the sum of `suite.count_re`'s first group over
  the output's lines (§14.3; `"def _count_re"` in `ccp/suite.py`). The knob exists already, but it is one
  pattern, and config refuses a pattern without a group (`"suite.count_re is not a regular expression
  with a count group"` in `ccp/config.py`). So a gate mixing runners cannot count them all, and a runner
  that prints one line per test with no number in it (`go test -v`'s `--- PASS: TestX`) cannot be
  counted at all. `go test` without `-v` prints one `ok <package>` line per package and no test count:
  counting those lines would count packages as tests, so the README says to run it with `-v` (or
  `-json`) instead.
- A stage can also write `$CCP_SUITE_RESULT` (§14.3), the route for a runner whose output carries no
  count; the README says so beside the patterns.
- §31.1: the SPEC text below only describes this task's own feature; the default pattern is unchanged.

## Scope

- **In:**
  - `ccp/init.py`: `--gate GATE` writes `suite.lanes.gate` as `[{"name": "gate", "cmd": GATE}]`, the
    line verbatim; a `GATE` that `shlex.split` refuses is refused as today.
  - `ccp/config.py`, `contracts/plane_config.schema.json`: `suite.count_re` takes a string or a
    non-empty list of strings. A pattern with a group counts its first group; one without counts each
    matching line as one. A pattern that does not compile is refused as today.
  - `ccp/suite.py`: each output line is matched against the patterns in order and the first that
    matches counts it, so no line is counted twice; the matches over all lines are summed.
  - `tests/test_suite.py` `"def test_config_refuses_bad_lanes_and_patterns"`: its `"no group"` case is
    now valid and leaves the list; `tests/test_init.py`'s gate expectations become the staged form.
  - §31.1: `docs/spec/01-model.md` §4.5, "with `--gate` the gate lane" gains "(one stage, `gate`, running
    the line as given)"; `docs/spec/02-delivery.md` §14.3, the `suite.count_re` sentence says it is a
    pattern or a list, the first matching pattern counting a line, a pattern without a group counting
    the line as one.
  - `README.md`, beside `suite.lanes` in the adoption checklist: `suite.count_re` with one line each for
    pytest (`^=+ (\d+) passed`), `go test -v` (`^--- PASS: `), and a shell test script (print a line the
    pattern matches, or write `$CCP_SUITE_RESULT`).
- **Out:**
  - Changing the default pattern, or adding per-stage patterns.
  - Rewriting the gate lane of a product already adopted.
  - The permission entry `ccp init --permissions` prints for a stage (it already prints the stage's
    `cmd`).

## dod_checks

- id: `init-01`
  story: As an adopting lead, my chained gate runs as I wrote it.
  setup: a scratch directory `S` that does not exist; a scratch file `M` that does not exist.
  steps:
    1. Run `ccp sandbox create S -- --gate "cd . && touch M && python3 -c pass"`, with `M` given as its absolute path.
    2. With the printed `env` lines exported, run `ccp suite run --lane gate` in the printed `root`.
  expect: the sandbox's plane.json `suite.lanes.gate` is exactly one stage, named `gate`, whose `cmd` is the line given; step 2 exits 0 and `M` exists.
  dry run (`921507e`): the lane was the argv `cd`, `.`, `&&`, `touch`, …; the run passed and no file was made (the fault this task fixes).
- id: `init-02`
  story: As an adopting lead, a line that cannot be a shell command is refused.
  setup: a scratch git repository with one commit.
  steps:
    1. Run `ccp init --project-id demo --gate 'echo "x'` there with `CCP_BINDINGS_DIR` set to a scratch directory.
  expect: exit 2, the message names `--gate`; no `docs/delivery/plane.json` is written.
  dry run: n/a.
- id: `count-01`
  story: As a product with two test runners, both counts are recorded.
  setup: a scratch product whose gate lane is one stage printing `Ran 3 tests in 0.1s`, then two lines `--- PASS: TestA` and `--- PASS: TestB`, then `ok  example/pkg  0.01s`; `suite.count_re` is the list `["^Ran (\\d+) tests? in ", "^--- PASS: "]`.
  steps:
    1. Run `ccp suite run --lane gate`.
  expect: exit 0; the summary line says `5 tests` and the `ended` row in `runs/_suites.jsonl` records `tests: 5`.
  dry run: n/a — a list and a pattern without a group are refused by config at `921507e`.
- id: `count-02`
  story: As a product, a line two patterns match is counted once.
  setup: a scratch product whose gate prints `Ran 4 tests in 1s`, with `suite.count_re` `["^Ran (\\d+) tests? in ", "^Ran "]`.
  steps:
    1. Run `ccp suite run --lane gate`.
  expect: the recorded `tests` is 4.
  dry run: n/a.
- id: `count-03`
  story: As a product on the default, nothing changes.
  setup: a scratch product with no `suite.count_re`, whose gate prints `Ran 2 tests in 0s` twice.
  steps:
    1. Run `ccp suite run --lane gate`.
  expect: the recorded `tests` is 4, as at `921507e`.
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

- 2026-11-18 (implementer): `ccp init --gate` writes `suite.lanes.gate` as one stage `{"name": "gate",
  "cmd": GATE}`, the line verbatim; `plane_json_text` still calls `shlex.split` on it only to refuse an
  unclosed quote (exit 2, nothing written). `suite.count_re` is a non-blank string or a non-empty list
  of non-blank strings, each compiling; a blank pattern is refused too, since without a group it would
  count every line (narrowest reading of "a string"). `suite._count_res` compiles the list in order;
  `_Counter` takes the list and counts a line with the first pattern that matches it (its first group,
  or 1 for a pattern with no group), then stops; `digest` ends a failure section at a dash rule before
  any count pattern's line. An optional group that matched nothing counts nothing instead of raising.
  SPEC §4.5 and §14.3 carry the task's §31.1 text; the README's adoption checklist gains a
  `suite.count_re` row and the pytest, `go test -v` and shell-script patterns below the table.

## Verification notes
- 2026-11-18 — verifier, PR #155 head `f8d13fc` (squash `2a1eadc`): APPROVE. Passed: init-01, init-02, count-01, count-02, count-03, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0137-gate-lane-and-test-counts.json.

