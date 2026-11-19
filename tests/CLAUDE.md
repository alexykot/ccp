# tests — the plane's suite

Run it with `scripts/gate.sh` (a plane worker runs it as `ccp suite run --lane full`): the same modules
as `python3 -m unittest discover -s tests -t .`, in parallel, with the test cache. Afterwards
`git branch --list 'state/*'` must print nothing.

**The suite is fenced** (`__init__.py`): no live queue, no real plane or product repo, no GitHub, no
launchd. Every test builds its product in a temp directory, points
`QUEUE_ROOT` at a temp queue, and stubs headless Claude calls. A test never asserts on prose, help
text or prompt wording beyond the token it checks. `test_self_hosting.py` runs the plane's own
checks against this repo, read-only.

## Shared fixtures

Modules share a few fixtures; reuse one before building another. Where a check needs no repository,
queue or subprocess, test a function on plain values instead (`test_catch_up_decision.py`).
- `helpers.py`'s `Product`: a temp product root with a `plane.json` and helpers to add tasks and files.
  Most modules build on it.
- `test_toolkit.py`'s `ToolkitFixture`: a git product (a bare origin, a main clone and a runner worktree), a
  queue and a fake `gh`. The most reused one: for close, claim, verify and
  every test that runs `ccp` against a real repository.
- `test_team_hosting.py`'s `TeamCase`: a `Product` and a claude-team queue (`project.yaml`, `work.json`,
  claimed task files) with a `run_cmd` that runs a script against it.
- `test_init.py`'s `InitCase`: a temp git repository, a temp home and bindings directory, and `ccp()` and
  `init()` to run `ccp init` there.
- `test_gate_parallel.py`'s `GateFixture`: a temp git repository holding copies of the gate scripts, and
  `module()`, `gate()` and `read()` to write test modules and run the gate on them.

**Reuse rule.** A fixture shared across modules is a class with no test methods (`ToolkitFixture`
mixes into a `TestCase`; the others are `TestCase` bases that hold no tests), imported by name. A class
that holds tests is never imported into another module: discovery would run its tests twice.
