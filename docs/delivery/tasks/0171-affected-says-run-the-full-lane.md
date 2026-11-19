---
task_id: 0171-affected-says-run-the-full-lane
title: ccp suite affected says to run the full lane when a change reaches most of the suite, and the worker templates stop restating the pre-gate
status: done
kind: feature
depends_on: []
spec_refs: ["S13", "S14"]
review_point: R12
paths: ["ccp/suite.py", "templates/prompts/implement.md", "templates/prompts/fix.md", "templates/prompts/merge.md", "templates/prompts/ruling.md", "docs/spec/02-delivery.md", "tests/test_suite_affected.py"]
adopt: "none"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0171-affected-says-run-the-full-lane

## Intent

A worker whose change reaches most of the test suite (a change to a module nearly everything imports)
is told by `ccp suite affected` to skip the part-lane pre-gate and run the full lane, which runs in
parallel and finishes sooner than the serial part lane would on that list. The four worker templates
that run the pre-gate name the command and do what its stderr line says, instead of restating the
pre-gate rule.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, finding F09 (the fail-fast pre-gate costs more than the full lane
  for any `ccp/config.py` change). Written first in R12 and depending on nothing, because every
  ADR-0043 task changes `ccp/config.py`.
- Measured at `e9ff0fc`: `ccp suite affected --paths ccp/config.py` lists 61 test modules
  (`./bin/ccp --root . suite affected --paths ccp/config.py | wc -l`), of 142 test modules
  (`ls tests/test_*.py | wc -l`). Friction notes in the shape: 59 affected modules took 428 s serial
  against 186 s for the full lane; the cold full lane's median is 174 s (health summary, not
  re-measured).
- The share is a constant in `ccp/suite.py` (`AFFECTED_FULL_SHARE = 0.25`, decided here): past a
  quarter of the suite's test modules the serial part lane loses to the parallel full lane on this
  repo's measurements. It is not a plane.json knob (ADR-0043 D1: a value a product would not change
  is a constant).
- The suite's size is what the language pack counts as test modules (for Python, the `test*.py` files
  git tracks or does not ignore, the set the reader already walks). A product using
  `suite.affected_map` alone (no pack reader) has no suite size, and the line is unchanged for it.
- stdout keeps the list unchanged in every case; only the stderr line differs. A script that reads
  stdout sees no change.
- The templates restate the pre-gate (house rule E13): `git grep -n "the test modules that depend on the paths" -- templates/prompts`
  at `e9ff0fc`: 4 lines, `implement.md`, `fix.md`, `merge.md` (its wording: "depend on the paths the
  merge changed"), `ruling.md`. Each keeps the `ccp suite run --lane part` pre-gate step and the
  `architect_checks` section; only the restated rule goes.
- SPEC: §14.7 gains the full-lane sentence and §13.5's *Fail fast* bullet points at it. This is a new
  rule from an architect finding, not from an accepted ADR, so it carries `sign_off: brief`.

## Scope

- **In:**
  - `ccp/suite.py`: `AFFECTED_FULL_SHARE = 0.25`. `main_affected`: when the language pack's reader
    counts the suite and the list holds more than that share of its test modules, the stderr line is
    `ccp suite affected: <n> of <total> test modules: skip the pre-gate and run the full lane: ccp suite run --lane <full lane>`
    (the `full` role's lane, `lane_for(cfg, "full")`) in place of the `run them with` line. Otherwise
    the stderr line is as today. stdout and the exit code are unchanged.
  - `templates/prompts/implement.md`, `fix.md`, `merge.md`, `ruling.md`: the pre-gate sentence names
    the command and its answer: run, through `ccp suite run`, the line `{{ccp}} suite affected --since <ref>`
    prints on stderr (the part lane, or the full lane when it says so), with the house-rule checks
    where the template has them. The sentence "so a cheap failure shows in seconds rather than after
    the whole suite" and the restated "the test modules that depend on the paths …" go; "The pre-gate
    never stands in for the full suite" stays once per template.
  - `docs/spec/02-delivery.md` §14.7: CURRENT (at `e9ff0fc`): "After the list it prints, on stderr, the command that
    runs them on the `part` role's lane (`ccp suite run --lane <part lane> -- <command> <modules>`), for a
    language whose command it names (Python: `python3 -m unittest`); stdout keeps the list alone."
    PROPOSED:
    > After the list it prints, on stderr, the command that runs them on the `part` role's lane (`ccp suite run --lane <part lane> -- <command> <modules>`), for a language whose command it names (Python: `python3 -m unittest`); stdout keeps the list alone. When the list holds more than a fixed share of the suite's test modules (a constant in code; the pack counts the suite), the stderr line says instead to skip the pre-gate and run the `full` role's lane: the part lane runs its modules one after another, and past that share it is slower than the full lane. A product that maps tests with `suite.affected_map` alone has no suite count and always gets the part-lane line.
  - `docs/spec/02-delivery.md` §13.5: CURRENT (at `e9ff0fc`): "- **Fail fast.** Before the full suite, the implementer and fixer run a pre-gate: the product's
    `architect.checks` commands (rendered from plane.json) and the test modules depending on the
    changed paths as `ccp suite affected` lists them (§14.7), through `ccp suite run --lane part`. It
    never stands in for the full suite, which runs on the final code and must be
    green."
    PROPOSED:
    > - **Fail fast.** Before the full suite, the implementer and fixer run a pre-gate: the product's `architect.checks` commands (rendered from plane.json) and the run `ccp suite affected` prints on stderr (§14.7), through `ccp suite run`: the part lane, or, when it says the change reaches most of the suite, no pre-gate and the full lane. It never stands in for the full suite, which runs on the final code and must be green.
  - `tests/test_suite_affected.py`: the checks below.
- **Out:**
  - A plane.json knob for the share.
  - `ccp suite run` itself, the lanes, and the gate.
  - The runner brief (`plugin/agents/delivery-runner.md`), which does not run the pre-gate.

## dod_checks

- id: `aff-01`
  story: As an implementer whose change touches most of the suite, affected tells me to run the full lane.
  setup: a checkout of the PR head.
  steps:
    1. Run `./bin/ccp --root . suite affected --paths ccp/config.py 2>err.txt | wc -l`, then `cat err.txt`.
  expect: step 1 prints a number above 40; `err.txt` holds one `ccp suite affected:` line that contains `skip the pre-gate and run the full lane` and `ccp suite run --lane full`, and no `run them with` line.
  dry run (`e9ff0fc`): 61 modules; stderr was `ccp suite affected: run them with: ccp suite run --lane part -- python3 -m unittest tests.test_adr …` (the part-lane line), so the expect fails today.
- id: `aff-02`
  story: As an implementer with a narrow change, affected still hands me the part-lane command.
  setup: a checkout of the PR head.
  steps:
    1. Run `./bin/ccp --root . suite affected --paths ccp/doclang/python.py`.
  expect: stdout lists 3 or fewer modules; stderr holds the `run them with: ccp suite run --lane part -- python3 -m unittest` line and no `full lane` text.
  dry run (`e9ff0fc`): 1 module (`tests.test_doc_rules`) and the part-lane line (a regression guard: this case must not change).
- id: `aff-03`
  story: As a plane developer, the share's branch is tested and the test bites.
  setup: a checkout of the PR head; then a separate copy with `AFFECTED_FULL_SHARE` set to `1.0`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_suite_affected`.
    2. In the copy, run the same.
  expect: step 1 passes; step 2 fails with at least one failure.
  dry run (`e9ff0fc`): step 1 passes today (34 tests); the new tests do not exist yet.
- id: `tpl-01`
  story: As a worker, my brief names the command and does what it says, without restating the rule.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n "the test modules that depend on the paths" -- templates/prompts`.
    2. Run `git grep -c "suite affected" -- templates/prompts/implement.md templates/prompts/fix.md templates/prompts/merge.md templates/prompts/ruling.md`.
  expect: step 1 prints nothing; step 2 prints a count of at least 1 for each of the four files.
  dry run (`e9ff0fc`): step 1 printed 4 lines (`fix.md:11`, `implement.md:9`, `merge.md:9`, `ruling.md:9`); step 2 printed 1 for each file.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0171-affected-says-run-the-full-lane --base origin/main`.
  expect: exit 0, both passages found.
  dry run: n/a — the passages are not in the SPEC at `e9ff0fc`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- `ccp/suite.py`: `AFFECTED_FULL_SHARE = 0.25` and `AFFECTED_SIZERS` (a pack's count of its test modules; Python:
  `_python_suite_size`, the files the reader walks, via a new `_python_test_files` the reader now shares).
  `main_affected` prints the full-lane line when the list is strictly more than the share of that count (a quarter
  exactly keeps the part-lane line); a language with no sizer (a map-only product) has no count and keeps today's
  line. Measured: `--paths ccp/config.py` prints "61 of 142 test modules", `--paths ccp/doclang/python.py` the
  part-lane line.
- The four templates carry the new pre-gate sentence; `tests/test_worker_efficiency.py` pinned the old wording and
  moved with it. The scratch product in `tests/test_suite_affected.py` gains six filler test modules so one or two
  touched modules stay under the share.

## Verification notes
- 2026-11-19 — verifier, PR #195 head `59a7d89` (squash `d0f131d`): APPROVE. Passed: aff-01, aff-02, aff-03, tpl-01, spec-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0171-affected-says-run-the-full-lane.json.

