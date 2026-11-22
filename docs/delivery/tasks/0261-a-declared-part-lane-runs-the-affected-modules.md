---
task_id: 0261-a-declared-part-lane-runs-the-affected-modules
title: A part lane plane.json declares runs the affected modules, and the plane's part lane runs them in parallel with the test cache
status: pending
kind: feature
depends_on: []
clashes_with: ["0213-a-green-tree-skips-the-lane-queue", "0256-suite-run-refuses-a-closed-run-and-config-reads"]
spec_refs: ["S14"]
review_refs: ["ar-20261121T111633Z-4e26#F04"]
review_point: R19
paths: ["ccp/suite.py", "scripts/gate.sh", "scripts/gate_parallel.py", "docs/delivery/plane.json", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_suite_affected.py", "tests/test_gate_parallel.py"]
adopt: "plane.json suite.lanes.part: an argv that takes test module names as its last arguments, if the product has a faster runner than the language's command"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0261-a-declared-part-lane-runs-the-affected-modules

## Intent

A targeted test run is never slower than the full gate. A product that declares its own `part`
lane, a runner that takes module names, gets that runner in the command `ccp suite affected`
prints, whatever the number of modules, instead of the language's serial command. The plane itself
declares one: `scripts/gate.sh` given module names runs only those, in parallel and through the
test cache, so a reviewer's or implementer's run of the modules a change touches takes seconds to a
few minutes rather than longer than the cold gate.

## Context (not checked)

Measured at `1aa5e3f`.

- From architect pass `ar-20261121T111633Z-4e26`, F04 (the record is in `docs/delivery/reviews/`).
- **Today.** `bin/ccp suite affected --paths ccp/graph.py` at `1aa5e3f` prints on stderr
  `ccp suite run --lane part -- python3 -m unittest tests.test_graph`: the language pack's command
  (`"TEST_COMMAND = "` in `ccp/doclang/python.py`), whatever plane.json declares. `"def main_affected"`
  in `ccp/suite.py` prints the full-lane line instead past `AFFECTED_FULL_SHARE` (a quarter) of the
  suite's modules (`ls tests/test_*.py | wc -l` at `1aa5e3f`: 173 modules).
- **The plane's lanes.** plane.json `suite.lanes` at `1aa5e3f` holds `gate` and `full`, both
  `["scripts/gate.sh"]`; no `part`. `scripts/gate_parallel.py` runs every `tests/test_*.py` module
  and takes no arguments (`git grep -nE 'argv|argparse' -- scripts/gate_parallel.py` at `1aa5e3f`:
  no line).
- The pass's health figures, quoted from the report (`ccp health` over the queue's suite records, at the pass): 0236's part-lane run 481 s against its cold gate 287 s; 0243 234 s against 246 s; 0228 150 s against 215 s.
- **A command after `--` on a declared lane.** §14.2 runs the command after `--` in place of the
  lane's argv (warning only on the `full` and `gate` roles' lanes), so
  `ccp suite run --lane part -- scripts/gate.sh <modules>` needs nothing new from `ccp suite run`.
- **Rulings for the build** (the lead's):
  - `ccp suite affected`: when plane.json `suite.lanes` gives the part role's lane (`lane_for(cfg,
    "part")`) as an argv, the stderr line is `ccp suite affected: run them with: ccp suite run --lane
    <part lane> -- <that argv> <modules>`, whatever the share; the full-lane line is printed only
    with the language's command, as today. A staged part lane counts as none declared.
  - `scripts/gate_parallel.py` takes optional module names (`tests.test_x`) as arguments and runs only
    those, `GATE_WORKERS` at a time, through the test cache. The cache keys are computed over the
    whole suite as today, so a module's entry is the same in a part run and a full run. A name that
    is not a `tests/test_*.py` module exits 2 naming it, running nothing. With no names it runs every
    module, as today. `scripts/gate.sh` passes its arguments through.
  - plane.json `suite.lanes.part` is `["scripts/gate.sh"]`; `exclusive_lanes` is unchanged, so part
    runs do not queue behind the gate.
- **Rule text.** The §14.7 change below is signed in the brief (§31). §14.1 and §14.2 are unchanged.

## Scope

- **In:**
  - `ccp/suite.py` (`main_affected`), `scripts/gate_parallel.py`, `scripts/gate.sh`,
    `docs/delivery/plane.json` (`suite.lanes.part`), `docs/cli/02-delivery.md` (the stderr line),
    `tests/test_suite_affected.py`, `tests/test_gate_parallel.py`.
  - Signed before the claim (`sign_off: brief`): `docs/spec/02-delivery.md` §14.7, its first
    paragraph, from "After the list it prints" to its end:

    CURRENT (`docs/spec/02-delivery.md` at `1aa5e3f`):
    > After the list it prints, on stderr, the command that
    > runs them on the `part` role's lane (`ccp suite run --lane <part lane> -- <command> <modules>`), for a
    > language whose command it names (Python: `python3 -m unittest`); stdout keeps the list alone. When the list holds more than a fixed share of the suite's test modules (a constant in code; the pack counts the suite), the stderr line says instead to skip the pre-gate and run the `full` role's lane: the part lane runs its modules one after another, and past that share it is slower than the full lane. A product that maps tests with `suite.affected_map` alone has no suite count and always gets the part-lane line.

    PROPOSED:
    > After the list it prints, on stderr, the command that runs them on the `part` role's lane
    > (`ccp suite run --lane <part lane> -- <command> <modules>`). The `<command>` is the argv
    > plane.json `suite.lanes` gives the part role's lane, when it gives one as an argv, which then
    > takes the module names as its last arguments; else the language's command, for a language whose
    > command it names (Python: `python3 -m unittest`); stdout keeps the list alone. With the language's
    > command, when the list holds more than a fixed share of the suite's test modules (a constant in
    > code; the pack counts the suite), the stderr line says instead to skip the pre-gate and run the
    > `full` role's lane: that command runs its modules one after another, and past that share it is
    > slower than the full lane. A declared part lane, and a product that maps tests with
    > `suite.affected_map` alone (it has no suite count), always get the part-lane line.
- **Out:** `ccp suite run` (unchanged), `AFFECTED_FULL_SHARE`'s value, the prompts, `exclusive_lanes`.

## dod_checks

- id: `pl-01`
  story: As a reviewer, the plane's gate script given module names runs only those.
  setup: A checkout of the PR head; no `state/*` branch.
  steps:
    1. Run `GATE_COLD=1 scripts/gate.sh tests.test_graph tests.test_refs 2>&1 | grep -c '^gate module '`.
    2. Run `GATE_COLD=1 scripts/gate.sh tests.test_no_such_module; echo "exit $?"`.
  expect: step 1 prints `2`; step 2 prints a line naming `tests.test_no_such_module` and ends `exit 2`.
  dry run: n/a — at `1aa5e3f` both steps would run the whole suite, since the script ignores its arguments (`git grep -nE 'argv|argparse' -- scripts/gate_parallel.py`: no line).
- id: `pl-02`
  story: As a reviewer in the plane's checkout, `ccp suite affected` hands me the plane's part lane, even for many modules.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite affected --paths ccp/graph.py 2>&1 >/dev/null`.
    2. Run `CCP_DEV=1 ./bin/ccp suite affected --paths ccp/config.py 2>&1 >/dev/null`.
  expect: step 1 prints `ccp suite affected: run them with: ccp suite run --lane part -- scripts/gate.sh tests.test_graph`; step 2 prints one line starting `ccp suite affected: run them with: ccp suite run --lane part -- scripts/gate.sh `, and no line saying to run the full lane.
  dry run (`1aa5e3f`): step 1 printed `ccp suite affected: run them with: ccp suite run --lane part -- python3 -m unittest tests.test_graph`; step 2 printed `ccp suite affected: 79 of 173 test modules: skip the pre-gate and run the full lane: ccp suite run --lane full`.
- id: `pl-03`
  story: As a plane developer, the declared-lane line and the language-command lines are tested, and the tests bite.
  setup: A checkout of the PR head; then a separate copy of it with the declared-argv branch in `main_affected` removed.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_suite_affected tests.test_gate_parallel 2>&1 | tail -4`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_suite_affected`.
  expect: step 1 ends `OK`, with tests for: a declared argv part lane is printed with the modules after it, past the share too; a staged part lane, or none, gets the language's command and the full-lane line past the share; `gate_parallel.py` given names runs only those and refuses an unknown name with exit 2. Step 2 exits non-zero.
  dry run (`1aa5e3f`): step 1 ran 57 tests, `OK` (the new tests are not there yet); step 2 n/a (the branch is new).
- id: `pl-04`
  story: As the operator, §14.7 reads as I signed it.
  setup: A checkout of the PR head; the brief sign-off recorded.
  steps:
    1. Run `./bin/ccp verify spec-text 0261`.
  expect: exit 0, the PROPOSED passage found in `docs/spec/02-delivery.md`.
  dry run (simulated, the passage applied to `docs/spec/02-delivery.md` on a scratch branch off `7b242fe`): exit 0, the passage found in `docs/spec/02-delivery.md`.

## Implementation notes

- Premises re-measured at `934e959`: still no `part` lane and no argument handling in
  `scripts/gate_parallel.py`; the suite has grown to 202 modules (173 at `1aa5e3f`), so `--paths
  ccp/config.py` printed `103 of 202` before the change. The build does not depend on the count.
- `ccp/suite.py`: `declared_part_argv(cfg)` reads the part role's lane (`lane_for(cfg, "part")`) from
  `suite.lanes`, None for no lane, an empty list or stages; `affected_hint(cfg, mods, total,
  test_command)` decides the stderr line on plain values (E15), and `main_affected` only prints it. With a
  declared argv the suite is not counted (the share does not apply). The argv is printed with
  `shlex.join`, so a word with a space is quoted and the line runs as printed; for plain words it is the
  argv joined by spaces. A declared argv is printed even where the language pack names no command.
- `scripts/gate_parallel.py`: `selected(suite, wanted)` keeps the suite's own order (largest first) and
  drops repeats; every unknown name is listed in one exit-2 line before anything runs (the
  `GATE_WORKERS` check comes first, as before). The cache's shared inputs and leaves are computed over the
  whole suite, keys only for the modules that run. The closing line's module count is the modules
  selected. `scripts/gate.sh` passes `"$@"` through (bash 3.2 with `set -u` accepts it empty).
- `docs/cli/02-delivery.md`: the `suite affected` row names the stderr line and where its command comes
  from.

## Verification notes
