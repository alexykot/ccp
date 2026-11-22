# tests — the plane's suite

Run it with `scripts/gate.sh`; the house rules for it are E1, E2 and E4 (`docs/ENGINEERING.md`). `test_self_hosting.py`
runs the plane's own checks against this repo, read-only. Every test builds its product in a temp directory, points
`QUEUE_ROOT` at a temp queue, and stubs headless Claude calls.

## Shared fixtures

Modules share a few fixtures; reuse one before building another. Where a check needs no repository,
queue or subprocess, test a function on plain values instead (`test_catch_up_decision.py`).
- `helpers.py`'s `Product`: a temp product root with a plane config and helpers to add tasks and files.
  Most modules build on it.
- `helpers.py`'s `binding(**keys)`: the text of a binding, `project_id: demo` first, then each key. A test
  that needs a binding writes it with this; only a test of the binding's format or of `ccp init`'s output
  keeps literal text. A test names the worktrees directory as `config.WORKTREES_DIR`, never as a copied literal.
- `test_toolkit.py`'s `ToolkitFixture`: a git product (a bare origin, a main clone and a runner worktree) and
  a queue, on the local PR host (`pr_host.adapter: local`); `open_pr()` opens the task's PR and `pr_record()`
  reads its record. The most reused one: for close, claim, verify and every test that runs `ccp` against a
  real repository. No test code stands in for a PR host; only the GitHub adapter's own tests stub `gh`.
  Each test class builds the three repositories once (`setUpClass`, from the class's own `PLANE_JSON`) and every
  test copies that tree; a class that changes the build before `setUp` ends sets `SHARED_REPO = False`.
- `review_flow.py`'s `ReviewFlow`: a mixin (before `ToolkitFixture`) that drives a claimed task through review,
  fix and verify rounds (`run_phase`, `review`, `fix`, `verdict`, `verify_round`) and commits in a worktree (`commit`).
- `review_flow.py`'s `SkipFlow`: `ReviewFlow` plus a proof command and the task's worktree, for `verify.skip_review`
  (`reviewed`, `push`, `verify`, its own `commit` and `fix`; `PROOF`, `SKIP_REVIEW_PLANE`).
- `helpers.py`'s `done_report(phase, *lines)`: the text of a done report of a phase that `ccp report` accepts,
  with the section the phase needs when done. A test that files a done report for something else writes it with this.
- `helpers.py`'s `FoldRuns` (`mkrun`, `write`, `rows`: run records and usage rows in a temp queue) and `BoardPage`
  (`page`: the board page's script run under node): mixins for a `TestCase`.
- `test_team_hosting.py`'s `TeamCase`: a `Product` and a claude-team queue (its binding, work state and
  claimed task files) with a `run_cmd` that runs a script against it.
- `test_init.py`'s `InitCase`: a temp git repository, a temp home and bindings directory, and `ccp()` and
  `init()` to run `ccp init` there.
- `test_gate_parallel.py`'s `GateFixture`: a temp git repository holding copies of the gate scripts, and
  `module()`, `gate()` and `read()` to write test modules and run the gate on them.

**Reuse rule.** A fixture shared across modules is a class with no test methods (`ToolkitFixture` and the
mixins above mix into a `TestCase`; the others are `TestCase` bases that hold no tests), imported by name. A class
that holds tests is never imported into another module: discovery would run its tests twice. No module binds
another module's test-class methods as its own helpers (a class attribute assigned from `test_x.Class`): the
helper moves to a mixin or a fixture, and the architect's `E4` command check fails on the binding.
