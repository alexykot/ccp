---
task_id: 0311-suite-affected-and-suite-run-affected-run-a-staged-part-lane-as-declared
title: ccp suite affected names, and ccp suite run --affected runs, a part lane declared with stages as declared, instead of a language command that lane refuses
status: pending
kind: feature
depends_on: []
spec_refs: ["S14"]
review_point: R30
paths: ["ccp/suite.py", "ccp/cli.py", "tests/test_suite_affected.py", "tests/test_suite_run_affected.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md"]
clashes_with: ["0191-the-grace-release-ends"]
adopt: "none"
sign_off: brief
created: 2026-11-23
updated: 2026-11-23
---

# Task: 0311-suite-affected-and-suite-run-affected-run-a-staged-part-lane-as-declared

## Intent

A product whose plane.json declares its part lane with stages can run its pre-gate with
`ccp suite run --affected`. Today `ccp suite affected` tells such a product to run the language's test
command on that lane, which `ccp suite run` refuses for a staged lane, so `--affected` prints what it
would run and exits 2 with nothing run. After this, both name the part lane as plane.json declares it,
`ccp suite run --lane <part lane>`, and `--affected` runs it and records the run.

## Context (not checked)

Covers the open follow-up `0299-the-pre-gate-and-review-run-what-the-branch-touches-and-every-recorded-suite-run-keeps-a-log/review#3`
(`ccp --root . tasks follow-ups --open`). Measured at `e13c1380` (origin/main).

- **The failure, measured.** A scratch Python product (the setup of `cmd-01`: `suite.lanes` `gate` `["true"]` and `part`
  `[{"name": "unit", "cmd": "true"}]`, `tests/test_a.py` importing `pkg/a.py` beside six filler test modules, committed, then
  `pkg/a.py` changed). `CCP_DEV=1 ./bin/ccp --root <repo> suite affected` printed `tests.test_a` and, on stderr,
  "ccp suite affected: run them with: ccp suite run --lane part -- python3 -m unittest tests.test_a", exit 0.
  `QUEUE_ROOT=<scratch> CCP_DEV=1 ./bin/ccp --root <repo> suite run --affected --summary` printed
  `ccp suite run --affected: 1 test module(s): running ccp suite run --lane part -- python3 -m unittest tests.test_a`, then
  "ccp suite: --lane part has stages in plane.json suite.lanes, so it takes no command after `--`: run `ccp suite run --lane part`
  (SPEC §14.2)", exit 2.
- **Where.** `"def declared_part_argv"` returns None for a staged part lane, so `"def affected_plan"` falls through to the share
  rule and then the language's `test_command`. `tests/test_suite_affected.py`'s `test_a_staged_part_lane_counts_as_none_declared`
  pins that line, and the full-lane line past the share.
- **The ruling.** A staged lane takes no command and so no module names; ccp never rewrites a product's stages. The product
  declared what its part lane runs, so the line names that lane as declared, as the refusal itself already suggests. The full
  lane was the other choice: it runs everything and is the gate's own work, which the pre-gate never stands in for (§13.5), so
  it is not chosen. §14.7 already says "A declared part lane … always get[s] the part-lane line"; the share rule stays for the
  language's command only.
- **SPEC.** §14.7's sentence on `<command>` names the argv and the language's command and nothing for stages, so the rule is
  new text: one sentence, signed below, with the earlier sentence that lists what `--affected` runs. `awk '/^### 14.7/{f=1;next} f&&/^##/{exit} f' docs/spec/02-delivery.md | grep -c stages` at `e13c1380`: 0.
  The earlier sentence ("`ccp suite run --affected` … runs … what the stderr line below names: the part lane with the modules, or
  the full lane …") lists the two runs there are today, so it gains the third, signed below as the second passage.
- **Other tasks.** A script over the pending tasks' `paths` at `e13c1380` (0191, 0296, 0300, 0303, 0304, 0305, 0306, 0307, 0309,
  0310): 0191 names `ccp/cli.py`, `docs/spec/02-delivery.md` and `tests/`, recorded as a clash. 0300 names `ccp/cli.py` (mutate's
  `--test` help and `--revert` metavar) and `ccp/suite.py` (a new `section_patterns`), 0303 names `ccp/cli.py`
  (`cmd_tasks_estimate`'s actor), 0306 names `docs/spec/02-delivery.md` (a §15.4 passage) and 0310 names `ccp/suite.py`
  (`ended_summary`): other logic, not clashes.

### Rulings for the build (the lead's)

- `affected_plan` gives a part lane plane.json declares with stages that lane with no command, before the share rule, whatever
  the list holds. `affected_hint` prints, for it, exactly
  `ccp suite affected: the part lane has stages and takes no modules: run it with: ccp suite run --lane part` (the part role's
  lane name in place of `part`). `affected_run` prints `ccp suite run --affected: <n> test module(s): running ccp suite run --lane part,
  the lane as declared` and runs it, recorded as any run. The full-lane line and run for the language's command past the share are
  unchanged. `affected_modules` skips the pack's `suite_size` count whenever plane.json declares the part role's lane at all (an
  argv or stages), not only for an argv: the count is read only by the share rule, which a declared part lane never reaches.
- `--affected`'s help in `ccp/cli.py` becomes "run what `ccp suite affected` names on stderr: the part lane with the test modules
  the change touches, the part lane as declared when it has stages, or the full lane when it says so; no --lane and no command
  after `--` (SPEC §14.7)".
- `docs/cli/02-delivery.md`'s `ccp suite affected` row adds, after "the command the argv plane.json gives the part role's lane,
  else the language's": "; a part lane with stages: `ccp suite run --lane <part lane>`, the lane as declared".
- Tests: `test_a_staged_part_lane_counts_as_none_declared` becomes `test_a_staged_part_lane_runs_as_declared`, asserting the new
  line both with one module touched and past the share (`touch_three_of_eight`). `tests/test_suite_run_affected.py` gains
  `test_affected_runs_a_staged_part_lane_as_declared`: a staged part lane whose stage writes a marker file; `--affected` exits 0,
  the marker exists, and one `ended` row with lane `part` is recorded.

## Scope

- **In:** `ccp/suite.py` (`affected_modules`, `affected_plan`, `affected_hint`, `affected_run`), `ccp/cli.py` (`--affected`'s help),
  `tests/test_suite_affected.py`, `tests/test_suite_run_affected.py`, `docs/spec/02-delivery.md`, `docs/cli/02-delivery.md`.
- **SPEC, signed before the claim (`sign_off: brief`):** two passages in `docs/spec/02-delivery.md`, both in §14.7.

    CURRENT (`docs/spec/02-delivery.md` at `e13c1380`), §14.7, the first paragraph, its third sentence:
    > `ccp suite run --affected [--since <ref>]` takes the same change and runs, recorded as any run (§14.4), what the stderr line below names: the part lane with the modules, or the full lane when the line says so.

    PROPOSED:
    > `ccp suite run --affected [--since <ref>]` takes the same change and runs, recorded as any run (§14.4), what the stderr line below names: the part lane with the modules, the part lane as declared when it has stages, or the full lane when the line says so.

    CURRENT (`docs/spec/02-delivery.md` at `e13c1380`), §14.7, the paragraph that starts "After the list it prints", its second sentence:
    > The `<command>` is the argv plane.json `suite.lanes` gives the part role's lane, when it gives one as an argv, which then takes the module names as its last arguments; else the language's command, for a language whose command it names (Python: `python3 -m unittest`); stdout keeps the list alone.

    PROPOSED:
    > The `<command>` is the argv plane.json `suite.lanes` gives the part role's lane, when it gives one as an argv, which then takes the module names as its last arguments; else the language's command, for a language whose command it names (Python: `python3 -m unittest`); stdout keeps the list alone. When plane.json gives the part role's lane stages, which take no command (§14.2), the line is `ccp suite run --lane <part lane>`, the lane as declared, whatever the list holds.

  No sentence is retired: the first passage gains a clause, the second a sentence.
- **Out:** how a staged lane runs (§14.2); the share rule for the language's command; the briefs (0310).

## dod_checks

- id: `cmd-01`
  story: As a worker on a product with a staged part lane, `--affected` runs that lane and records it instead of exiting 2.
  setup: A checkout of the PR head at `<checkout>`, in your own worktree (a delivery-verifier seat). A scratch git repo `<repo>` outside it, with `docs/delivery/plane.json` holding `{"project_id": "demo", "language": "python", "suite": {"lanes": {"gate": ["true"], "part": [{"name": "unit", "cmd": "true"}]}}}`, `pkg/__init__.py` and `tests/__init__.py` empty, `pkg/a.py` holding `X = 1`, `tests/test_a.py` holding `import unittest` and `from pkg import a`, and six `tests/test_f<n>.py` holding `import unittest`, all committed; then `pkg/a.py` gains a line `Y = 2`, uncommitted. An empty scratch queue `<q>`.
  steps:
    1. Run `CCP_DEV=1 <checkout>/bin/ccp --root <repo> suite affected`.
    2. Run `QUEUE_ROOT=<q> CCP_DEV=1 <checkout>/bin/ccp --root <repo> suite run --affected --summary; echo "exit $?"`.
    3. Run `grep -c '"op": "ended"' <q>/runs/_suites.jsonl`.
  expect: step 1 prints `tests.test_a` on stdout and, on stderr, `ccp suite affected: the part lane has stages and takes no modules: run it with: ccp suite run --lane part`; step 2 prints `ccp suite run --affected: 1 test module(s): running ccp suite run --lane part, the lane as declared`, a summary for lane `part`, and `exit 0`; step 3 prints `1`.
  dry run (`e13c1380`): step 1 printed "ccp suite affected: run them with: ccp suite run --lane part -- python3 -m unittest tests.test_a"; step 2 printed the "has stages … takes no command after `--`" refusal and `exit 2`; step 3: no such file (nothing recorded).
- id: `code-01`
  story: As a plane developer, the tests pin the staged part lane's line and run.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_suite_affected tests.test_suite_run_affected`.
    2. Run `grep -e staged -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_suite_run_affected --revert ccp/suite.py`.
  expect: step 1 exits 0; step 2 lists `test_a_staged_part_lane_runs_as_declared` and `test_affected_runs_a_staged_part_lane_as_declared`, each `ok`, no `test_a_staged_part_lane_counts_as_none_declared`, then `OK`; step 3 prints the mutant `killed`.
  dry run (`e13c1380`): step 1 (scratch QUEUE_ROOT, run one module at a time) passed, 48 and 8 tests; step 2 listed only `test_a_staged_part_lane_counts_as_none_declared` `ok`, then `OK`; step 3: n/a — `--revert` needs the branch.
- id: `doc-01`
  story: As a reader of the CLI reference and `--help`, the staged part lane's line is named.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nF 'a part lane with stages: `ccp suite run --lane <part lane>`, the lane as declared' -- docs/cli/02-delivery.md`.
    2. Run `COLUMNS=400 CCP_DEV=1 ./bin/ccp suite run --help`.
  expect: step 1 prints exactly 1 line; step 2's `--affected` help holds "the part lane as declared when it has stages".
  dry run (`e13c1380`): step 1 printed nothing; step 2's help read "… the test modules the change touches, or the full lane when it says so …".
- id: `spec-01`
  story: As the operator, §14.7 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0311`.
  expect: exit 0, both PROPOSED passages found.
  dry run: n/a — the passages land with the build; each CURRENT sentence is found once in `docs/spec/02-delivery.md` at `e13c1380` (whitespace-normalised, a `python3 -c` search).

## Implementation notes

- `ccp/suite.py`: a private `_declared_part_lane` returns what `suite.lanes` gives the part role's lane (an argv or
  stages, a non-empty list) or None; `declared_part_argv` reads it. `affected_plan` gives a staged part lane
  `(part lane, None, "part")` before the share rule; the full lane past the share is now `(full lane, None, "full")`,
  so a lane-own plan's third element names the role it runs as and `affected_hint` and `affected_run` tell the two
  apart without comparing lane names (the two roles may share a lane). `affected_modules` skips the pack's
  `suite_size` whenever `_declared_part_lane` is set.
- Tests: `test_a_staged_part_lane_counts_as_none_declared` became `test_a_staged_part_lane_runs_as_declared` (one module
  and past the share); beside it `test_the_staged_line_names_the_lane_the_product_gives_the_part_role` (a `roles.part`
  lane) and `test_a_declared_part_lane_never_counts_the_suite` (argv and stages, a pack whose `suite_size` raises).
  `tests/test_suite_run_affected.py` gains `RunAffectedWithAStagedPartLane.test_affected_runs_a_staged_part_lane_as_declared`;
  the `ended` row carries no lane, so the test reads the lane from the `started` row and matches the `ended` row by
  `suite_id`.
- SPEC §14.7: the two signed passages, as written; `--affected`'s help and the `ccp suite affected` row as ruled.

## Verification notes
