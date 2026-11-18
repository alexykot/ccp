---
task_id: 0149-gate-cache-in-fix-and-merge-rounds
title: Fix and merge rounds run the product's full suite as its declared lane, so they get the gate's parallel run and test cache
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S13"]
review_point: R10
paths: ["templates/prompts/_common.md", "templates/prompts/fix.md", "templates/prompts/merge.md", "templates/prompts/implement.md", "templates/prompts/ruling.md", "ccp/prompt.py", "ccp/suite.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "CLAUDE.md", "docs/ENGINEERING.md", "tests/test_suite.py", "tests/test_prompt_rounds.py", "tests/test_worker_efficiency.py", "tests/test_full_lane_prompt.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0149-gate-cache-in-fix-and-merge-rounds
## Intent

A worker in a fix, merge or ruling round runs the product's full suite the way the product declares
it, as `ccp suite run --lane <full>` with nothing after `--`, as implement rounds mostly do already. A
product whose gate runs modules in parallel and serves unchanged ones from a test cache gets both in
every round, and the verify after a fix finds that round's results in the cache. A worker that still
passes its own command on a lane plane.json gives a command is told which command it replaced.

## Context (not checked)

- **The cause is the command, not the cache key.** Fix and merge rounds do not run this repo's gate
  at all. They run `ccp suite run --lane full -- python3 -m unittest discover -s tests -t .`: one
  serial process that never touches `scripts/gate.sh`, `scripts/gate_parallel.py` or the cache.
  Measured over this repo's queue, its full and gate lane runs since 2026-11-17T10:15Z (task 0113
  landing), read 2026-11-18 at `85d388b` with this command (each run's phase, command, seconds, cached):

  ```
  python3 -c "import json,os;R=[json.loads(l) for l in open(os.environ['QUEUE_ROOT']+'/runs/_suites.jsonl')];S={r['suite_id']:r for r in R if r['op']=='started'};[print(S[r['suite_id']].get('phase'),S[r['suite_id']]['cmd'],S[r['suite_id']].get('argc'),r['seconds'],r.get('cached')) for r in R if r['op']=='ended' and r['suite_id'] in S and S[r['suite_id']].get('lane') in ('full','gate') and S[r['suite_id']]['at']>='2026-11-17T10:15']"
  ```

  - fix: 13 runs, all `python3` with 7 arguments (`-m unittest discover -s tests -t .`), median 768 s (`the command above`);
  - merge: 3 runs, all the same `python3` command, median 750 s (`the command above`);
  - ruling: 1 run, the same command, 946 s (`the command above`);
  - implement: 40 runs of `gate.sh` with nothing cached, median 145 s (the parallel cold gate), 1 cached, and 4 runs of the `python3` command, median 837 s (`the command above`);
  - verify: 22 runs cached, median 0 s, and 20 not, median 153 s (`the command above`).
- The proposal read every run over 450 s as "uncached" (`the command above`). That threshold separates the serial
  `unittest discover` (`the command above`: about 700 to 1000 s) from the parallel gate (`the command above`: about 120 to 190 s), not cached
  from uncached: implement's gate runs are cold too (the code changed). The cache is not missed by
  these rounds; they never use it.
- **Why fix and merge workers pick that command.** The implement prompt (`templates/prompts/implement.md`) tells the worker to read
  `docs/delivery/standing-dod.md`, which says "The gate is `ccp suite run --lane gate`
  (`scripts/gate.sh`)". The fix, merge and ruling prompts (`fix.md`, `merge.md`, `ruling.md`) do not, so the only full-suite command a
  fresh worker sees is this repo's `CLAUDE.md` ("Run the full suite: `python3 -m unittest discover -s
  tests -t .`"), which Claude Code loads on its own, and `docs/ENGINEERING.md` E1 (the same command).
  The shared lane line in every prompt (`templates/prompts/_common.md`) gives the form
  `ccp suite run --run <run_id> --lane <lane> -- <command>` and says only a lane plane.json gives
  *stages* takes no command, so a worker reads a command after `--` as required. The full lane here is
  an argv (`"full": ["scripts/gate.sh"]` in `docs/delivery/plane.json`), so `ccp suite run` takes the
  command after `--` instead of the lane's own, silently. Task 0145 shows it: its fix round's full
  lane log (`runs/0145-adoption-rule-fixes/fix-suite-*.log`) is one `Ran 2344 tests in 920.384s`, while
  its implement round's full lane run was `gate.sh`.
- **The verify after such a round is cold as a result.** Read with `the command above`, taking each
  verify's previous full or gate lane run of the same task: of the 20 verify runs with nothing cached (`the command above`),
  18 followed a `python3` run and 2 a `gate.sh` run (`the command above`); all 22 cached ones followed a `gate.sh` run (`the command above`). A round that runs `scripts/gate.sh` on its final head records each module, and the
  verify at that head is served from the cache.
- **The key is not the cause, and is left as it is.** `scripts/gate_parallel.py` keys every module on
  all tracked files (`shared_inputs`), so any change to a non-test file misses every module; that is the
  §15.3 rule as built in task 0113 and is why implement's gate runs are cold. A narrower per-module key is
  a separate change and not this task's.
- Expected saving per fix or merge round: the serial run (`the command above`: about 770 s median) becomes the parallel
  cold gate (`the command above`: about 150 s), and the verify after it a cache hit (`the command above`: about 150 s to under 1 s).
- No § rule changes. §14.1 already says `--lane` "without `-- <command>` runs what plane.json
  `suite.lanes` gives that lane". The §14.2 sentence below describes this task's own warning (§31.1).
  `git grep -n "replaces\|replaced" -- docs/spec/02-delivery.md` at `85d388b` finds no sentence on a
  command that replaces an argv lane.

## Scope

- **In:**
  - `ccp/prompt.py`: a `full_lane` value for the templates (`lane_for(cfg, "full")`), beside
    `part_lane` and `gate_lane`. `suite_lanes(cfg, phase)`: a role whose lane plane.json `suite.lanes`
    declares (an argv or stages) is written as that lane with nothing after `--` ("`--lane full` with
    nothing after `--`: the product's full suite, as plane.json gives it"); a lane plane.json does not
    declare keeps today's wording, which asks for the command.
  - `templates/prompts/_common.md`, the lane line: a lane plane.json gives a command (an argv or stages)
    runs as `--lane <lane>` with nothing after `--`; a command after `--` is for a lane plane.json gives
    none, such as a subset on the part lane. The stages sentence is folded into it.
  - `templates/prompts/fix.md`, `templates/prompts/merge.md`, `templates/prompts/ruling.md` and
    `templates/prompts/implement.md`: "the product's full test suite" becomes the product's full test
    suite through `ccp suite run --lane {{full_lane}}`, as the lane line gives it.
  - `ccp/suite.py`: `ccp suite run --lane <lane> -- <command>`, where `<lane>` is the `full` or `gate`
    role's lane and plane.json gives it an argv that differs from `<command>`, still runs `<command>` and
    prints one warning on stderr before it starts: `--lane <lane>` has its own command in plane.json
    (`<argv>`), which this run replaces; run `--lane <lane>` with nothing after `--` to use it. No
    warning on the part role's lane, on a lane plane.json does not declare, or when the command equals
    the argv. The staged-lane refusal is unchanged.
  - §31.1: `docs/spec/02-delivery.md` §14.2, after the sentence on the staged-lane refusal, one sentence
    describing the warning; `docs/cli/02-delivery.md`'s `ccp suite run` row, one clause.
  - This repo: `CLAUDE.md`'s "Run the full suite" line and `docs/ENGINEERING.md` E1 name
    `scripts/gate.sh` (a plane worker runs it as `ccp suite run --lane full`), adding that it runs the
    same modules as `python3 -m unittest discover -s tests -t .` in parallel, with the test cache. E1's
    rule (the full suite passes on every change) is unchanged.
  - `tests/test_full_lane_prompt.py` (new); `tests/test_suite.py`, `tests/test_prompt_rounds.py` and
    `tests/test_worker_efficiency.py` where they pin the lane wording this changes.
- **Out:**
  - The cache key in `scripts/gate_parallel.py` and `scripts/gate.sh` (unchanged).
  - Refusing a command after `--` on an argv lane (a rule change; the warning is enough to show it).
  - `docs/delivery/standing-dod.md` and the verify prompt (already name the gate lane).

## dod_checks

- id: `prm-01`
  story: As a fixer, my prompt tells me to run the product's declared full lane, with no command of my own.
  setup: a scratch product (`tests/helpers.py`) whose plane.json gives `suite.lanes.full` an argv, a task claimed with a PR, and a review run reported with one BLOCKER.
  steps:
    1. Run `ccp prompt fix <task> --pr 7 --head <sha>` and read the rendered prompt file.
    2. Run `ccp prompt merge <task> --pr 7 --head <sha>` on the same task after the fix run reports, and read its prompt file.
  expect: both prompts name `--lane full` for the full suite with nothing after `--` (the text "nothing after `--`" next to `--lane full`), and neither gives `--lane full -- <command>` as the way to run the full suite.
  dry run: n/a — the wording is new.
- id: `prm-02`
  story: As an implementer in a product that declares no full lane, I am still told to give the command.
  setup: the same scratch product with `suite.lanes` empty.
  steps:
    1. Run `ccp prompt implement <task>` and read the rendered prompt file.
  expect: the lane line asks for a command after `--` for `--lane full`, as today, and does not say "nothing after `--`" for it.
  dry run: n/a.
- id: `cmd-01`
  story: As a runner, I see when a worker replaced the product's full lane with a command of its own.
  setup: a scratch product whose plane.json gives `suite.lanes.full` the argv `["sh", "-c", "exit 0"]`; `QUEUE_ROOT` set to its queue.
  steps:
    1. Run `ccp suite run --lane full -- python3 -c "print(1)"`.
    2. Run `ccp suite run --lane part -- python3 -c "print(1)"`.
    3. Run `ccp suite run --lane full`.
  expect: all three exit 0; step 1's stderr has one line naming `--lane full`, the argv `sh -c exit 0` and "replaces"; steps 2 and 3 print no such line.
  dry run: n/a — the warning is new.
- id: `doc-01`
  story: As a worker in this repo, the full-suite command I read is the parallel, cached gate.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n "Run the full suite" -- CLAUDE.md` and `git grep -n '\*\*E1\*\*' -- docs/ENGINEERING.md`.
  expect: each line found names `scripts/gate.sh`.
  dry run (`85d388b`): both lines name `python3 -m unittest discover -s tests -t .` only (the check fails at this commit, as it should).
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
